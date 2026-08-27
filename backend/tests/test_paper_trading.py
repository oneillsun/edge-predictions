from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.models import Base, Decision, Trade
from app.engine import paper_trading


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def add_decision(
    session,
    ticker: str,
    would_trade: bool,
    kalshi_price: float | None,
    size_pct_of_bankroll: float | None,
    side: str = "yes",
    fee: float = 0.02,
    ts: dt.datetime | None = None,
) -> Decision:
    d = Decision(
        ticker=ticker,
        estimated_probability=0.7,
        side=side,
        kalshi_price=kalshi_price,
        fee=fee,
        raw_edge=0.1,
        fee_adjusted_edge=0.08,
        would_trade=would_trade,
        size_pct_of_bankroll=size_pct_of_bankroll,
        inputs={"signal_source": "polymarket_arb"},
        ts=ts or dt.datetime.now(dt.timezone.utc),
    )
    session.add(d)
    session.commit()
    return d


class FakeKalshiClient:
    def __init__(self, market_by_ticker: dict[str, dict[str, Any]]) -> None:
        self._market_by_ticker = market_by_ticker

    def get_market(self, ticker: str) -> dict[str, Any]:
        return {"market": self._market_by_ticker.get(ticker, {})}


@pytest.fixture(autouse=True)
def fixed_bankroll(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "paper_bankroll_usd", 1000.0)


def test_open_paper_trades_computes_contracts_and_fee() -> None:
    session = make_session()
    add_decision(session, "KXETH-T1", would_trade=True, kalshi_price=0.5, size_pct_of_bankroll=0.03)

    opened = paper_trading.open_paper_trades(session)

    assert opened == 1
    trade = session.query(Trade).one()
    assert trade.ticker == "KXETH-T1"
    assert trade.side == "yes"
    assert trade.entry_price == 0.5
    assert trade.size == 60  # floor(0.03 * 1000 / 0.5)
    assert trade.fee == pytest.approx(0.02 * 60)
    assert trade.status == "open"
    assert trade.source == "polymarket_arb"


def test_open_paper_trades_skips_ticker_with_existing_open_trade() -> None:
    session = make_session()
    session.add(
        Trade(
            ticker="KXETH-T1",
            source="polymarket_arb",
            side="yes",
            entry_price=0.4,
            size=10,
            fee=0.1,
            status="open",
            opened_at=dt.datetime.now(dt.timezone.utc),
        )
    )
    session.commit()
    add_decision(session, "KXETH-T1", would_trade=True, kalshi_price=0.5, size_pct_of_bankroll=0.03)

    opened = paper_trading.open_paper_trades(session)

    assert opened == 0
    assert session.query(Trade).count() == 1


def test_open_paper_trades_skips_would_trade_false() -> None:
    session = make_session()
    add_decision(session, "KXETH-T1", would_trade=False, kalshi_price=0.5, size_pct_of_bankroll=None)

    opened = paper_trading.open_paper_trades(session)

    assert opened == 0


def test_open_paper_trades_skips_when_size_rounds_to_zero_contracts() -> None:
    session = make_session()
    # 0.0001 * 1000 / 0.99 = 0.101... -> floors to 0 contracts
    add_decision(session, "KXETH-T1", would_trade=True, kalshi_price=0.99, size_pct_of_bankroll=0.0001)

    opened = paper_trading.open_paper_trades(session)

    assert opened == 0


def test_open_paper_trades_ignores_stale_decisions() -> None:
    session = make_session()
    stale_ts = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=120)
    add_decision(session, "KXETH-T1", would_trade=True, kalshi_price=0.5, size_pct_of_bankroll=0.03, ts=stale_ts)

    opened = paper_trading.open_paper_trades(session, lookback_minutes=60)

    assert opened == 0


def test_settle_paper_trades_marks_win_and_computes_pnl() -> None:
    session = make_session()
    session.add(
        Trade(
            ticker="KXETH-T1",
            source="polymarket_arb",
            side="yes",
            entry_price=0.5,
            size=60,
            fee=1.0,
            status="open",
            opened_at=dt.datetime.now(dt.timezone.utc),
        )
    )
    session.commit()
    kalshi_client = FakeKalshiClient({"KXETH-T1": {"status": "finalized", "result": "yes"}})

    settled = paper_trading.settle_paper_trades(kalshi_client, session)  # type: ignore[arg-type]

    assert settled == 1
    trade = session.query(Trade).one()
    assert trade.status == "settled"
    assert trade.result == "win"
    # payout 60*1 - cost 60*0.5 - fee 1.0 = 60 - 30 - 1 = 29
    assert trade.pnl == pytest.approx(29.0)
    assert trade.settled_at is not None


def test_settle_paper_trades_marks_loss_and_computes_negative_pnl() -> None:
    session = make_session()
    session.add(
        Trade(
            ticker="KXETH-T1",
            source="polymarket_arb",
            side="yes",
            entry_price=0.5,
            size=60,
            fee=1.0,
            status="open",
            opened_at=dt.datetime.now(dt.timezone.utc),
        )
    )
    session.commit()
    kalshi_client = FakeKalshiClient({"KXETH-T1": {"status": "finalized", "result": "no"}})

    settled = paper_trading.settle_paper_trades(kalshi_client, session)  # type: ignore[arg-type]

    assert settled == 1
    trade = session.query(Trade).one()
    assert trade.result == "loss"
    # payout 0 - cost 30 - fee 1 = -31
    assert trade.pnl == pytest.approx(-31.0)


def test_settle_paper_trades_leaves_unresolved_market_open() -> None:
    session = make_session()
    session.add(
        Trade(
            ticker="KXETH-T1",
            source="polymarket_arb",
            side="yes",
            entry_price=0.5,
            size=60,
            fee=1.0,
            status="open",
            opened_at=dt.datetime.now(dt.timezone.utc),
        )
    )
    session.commit()
    kalshi_client = FakeKalshiClient({"KXETH-T1": {"status": "active", "result": ""}})

    settled = paper_trading.settle_paper_trades(kalshi_client, session)  # type: ignore[arg-type]

    assert settled == 0
    trade = session.query(Trade).one()
    assert trade.status == "open"
