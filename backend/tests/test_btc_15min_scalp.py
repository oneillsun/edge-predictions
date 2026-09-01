from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.models import Base, Trade
from app.strategies import btc_15min_scalp


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class FakeKalshiClient:
    def __init__(
        self,
        open_markets: list[dict[str, Any]] | None = None,
        markets_by_ticker: dict[str, dict[str, Any]] | None = None,
        fee_multiplier: float = 1.0,
        balance: dict[str, Any] | None = None,
    ) -> None:
        self._open_markets = open_markets or []
        self._markets_by_ticker = markets_by_ticker or {}
        self._fee_multiplier = fee_multiplier
        self._balance = balance if balance is not None else {"balance_dollars": "1.82", "portfolio_value": 0}

    def get_markets(self, **kwargs: Any) -> dict[str, Any]:
        return {"markets": self._open_markets}

    def get_market(self, ticker: str) -> dict[str, Any]:
        return {"market": self._markets_by_ticker.get(ticker, {})}

    def get_series(self, series_ticker: str) -> dict[str, Any]:
        return {"series": {"fee_multiplier": self._fee_multiplier, "fee_type": "quadratic"}}

    def get_balance(self) -> dict[str, Any]:
        return self._balance


def window_market(
    ticker: str,
    yes_bid: str,
    yes_ask: str,
    floor_strike: float = 78000.0,
    close_time: str = "2026-08-29T22:45:00Z",
    open_time: str | None = None,
    no_bid: str | None = None,
    no_ask: str | None = None,
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "yes_bid_dollars": yes_bid,
        "yes_ask_dollars": yes_ask,
        "no_bid_dollars": no_bid,
        "no_ask_dollars": no_ask,
        "floor_strike": floor_strike,
        "close_time": close_time,
        "open_time": open_time,
    }


def iso(delta: dt.timedelta) -> str:
    return (dt.datetime.now(dt.timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(autouse=True)
def fixed_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "btc_15min_position_size_usd", 20.0)
    monkeypatch.setattr(settings, "btc_15min_profit_target_pct", 0.15)
    monkeypatch.setattr(settings, "btc_15min_min_entry_price", 0.40)
    monkeypatch.setattr(settings, "btc_15min_max_entry_price", 0.60)


def test_no_open_market_returns_status() -> None:
    session = make_session()
    client = FakeKalshiClient(open_markets=[])

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result == {"status": "no_open_market"}
    assert session.query(Trade).count() == 0


def test_opens_position_on_new_window() -> None:
    session = make_session()
    client = FakeKalshiClient(open_markets=[window_market("KXBTC15M-A", "0.30", "0.40")])

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "opened"
    trade = session.query(Trade).one()
    assert trade.ticker == "KXBTC15M-A"
    assert trade.side == "yes"
    assert trade.entry_price == 0.40
    assert trade.size == 50  # floor(20 / 0.40)
    assert trade.status == "open"
    assert trade.fee > 0
    assert result["real_cash_usd"] == 1.82
    assert result["real_portfolio_value_usd"] == 0.0


def test_result_carries_window_info_from_kalshi_only() -> None:
    session = make_session()
    client = FakeKalshiClient(
        open_markets=[window_market("KXBTC15M-A", "0.30", "0.40", floor_strike=78000.0, close_time="2026-08-29T22:45:00Z")]
    )

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["target_price"] == 78000.0
    assert result["close_time"] == "2026-08-29T22:45:00Z"
    assert result["seconds_remaining"] is not None
    assert result["seconds_remaining"] >= 0
    assert "btc_spot_price_usd" not in result


def test_does_not_reenter_same_window_twice() -> None:
    session = make_session()
    client = FakeKalshiClient(open_markets=[window_market("KXBTC15M-A", "0.30", "0.40")])
    btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    # simulate the position having since been closed (e.g. settled), but the
    # window ticker is still the current "open" one somehow
    session.query(Trade).update({"status": "settled"})
    session.commit()

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "watching"
    assert session.query(Trade).count() == 1


def test_skips_entry_when_price_degenerate() -> None:
    session = make_session()
    client = FakeKalshiClient(open_markets=[window_market("KXBTC15M-A", "0.00", "1.0000")])

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "watching"
    assert session.query(Trade).count() == 0


def test_skips_entry_when_price_below_range() -> None:
    session = make_session()
    client = FakeKalshiClient(open_markets=[window_market("KXBTC15M-A", "0.30", "0.35")])

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "price_out_of_range"
    assert session.query(Trade).count() == 0


def test_skips_entry_when_price_above_range() -> None:
    session = make_session()
    client = FakeKalshiClient(open_markets=[window_market("KXBTC15M-A", "0.65", "0.70")])

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "price_out_of_range"
    assert session.query(Trade).count() == 0


def test_enters_at_price_range_boundaries() -> None:
    session = make_session()
    client = FakeKalshiClient(open_markets=[window_market("KXBTC15M-A", "0.55", "0.60")])

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "opened"
    assert session.query(Trade).count() == 1


def test_enters_when_within_entry_window() -> None:
    session = make_session()
    client = FakeKalshiClient(
        open_markets=[window_market("KXBTC15M-A", "0.30", "0.40", open_time=iso(-dt.timedelta(seconds=10)))]
    )

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "opened"
    assert session.query(Trade).count() == 1


def test_skips_entry_after_entry_window_elapsed() -> None:
    session = make_session()
    client = FakeKalshiClient(
        open_markets=[window_market("KXBTC15M-A", "0.30", "0.40", open_time=iso(-dt.timedelta(seconds=90)))]
    )

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "missed_entry_window"
    assert result["elapsed_since_open"] == pytest.approx(90, abs=2)
    assert session.query(Trade).count() == 0


def test_monitors_open_position_below_profit_target() -> None:
    session = make_session()
    session.add(
        Trade(
            ticker="KXBTC15M-A", source="btc_15min_scalp", side="yes", entry_price=0.40, size=50, fee=1.0,
            status="open", opened_at=dt.datetime.now(dt.timezone.utc),
        )
    )
    session.commit()
    # yes_bid 0.44 -> 10% gain, below the 15% target
    client = FakeKalshiClient(open_markets=[window_market("KXBTC15M-A", "0.44", "0.45")])

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "monitoring"
    trade = session.query(Trade).one()
    assert trade.status == "open"


def test_closes_on_profit_target_hit() -> None:
    session = make_session()
    session.add(
        Trade(
            ticker="KXBTC15M-A", source="btc_15min_scalp", side="yes", entry_price=0.40, size=50, fee=1.0,
            status="open", opened_at=dt.datetime.now(dt.timezone.utc),
        )
    )
    session.commit()
    # yes_bid 0.47 -> 17.5% gain, clears the 15% target
    client = FakeKalshiClient(open_markets=[window_market("KXBTC15M-A", "0.47", "0.48")])

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "closed_profit_target"
    trade = session.query(Trade).one()
    assert trade.status == "settled"
    assert trade.result == "win"
    # payout 50*0.47=23.5, cost 50*0.40=20, entry fee 1.0, exit fee = fee_for_price(0.47,1.0)*50 = 0.02*50 = 1.0
    assert trade.pnl == pytest.approx(23.5 - 20.0 - 1.0 - 1.0)
    assert result["real_cash_usd"] == 1.82
    assert result["real_portfolio_value_usd"] == 0.0


def test_waits_for_settlement_when_window_rolls_over_unresolved() -> None:
    session = make_session()
    session.add(
        Trade(
            ticker="KXBTC15M-A", source="btc_15min_scalp", side="yes", entry_price=0.40, size=50, fee=1.0,
            status="open", opened_at=dt.datetime.now(dt.timezone.utc),
        )
    )
    session.commit()
    client = FakeKalshiClient(
        open_markets=[window_market("KXBTC15M-B", "0.30", "0.40")],
        markets_by_ticker={"KXBTC15M-A": {"status": "closed", "result": ""}},
    )

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "waiting_for_settlement"
    trade = session.query(Trade).one()
    assert trade.status == "open"


def test_settles_at_real_result_when_target_never_hit_and_won() -> None:
    session = make_session()
    session.add(
        Trade(
            ticker="KXBTC15M-A", source="btc_15min_scalp", side="yes", entry_price=0.40, size=50, fee=1.0,
            status="open", opened_at=dt.datetime.now(dt.timezone.utc),
        )
    )
    session.commit()
    client = FakeKalshiClient(
        open_markets=[window_market("KXBTC15M-B", "0.30", "0.40")],
        markets_by_ticker={"KXBTC15M-A": {"status": "finalized", "result": "yes"}},
    )

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "closed_at_settlement"
    trade = session.query(Trade).one()
    assert trade.status == "settled"
    assert trade.result == "win"
    # payout 50*1=50, cost 20, fee 1 -> pnl 29
    assert trade.pnl == pytest.approx(29.0)
    assert result["real_cash_usd"] == 1.82


def test_settles_at_real_result_when_target_never_hit_and_lost() -> None:
    session = make_session()
    session.add(
        Trade(
            ticker="KXBTC15M-A", source="btc_15min_scalp", side="yes", entry_price=0.40, size=50, fee=1.0,
            status="open", opened_at=dt.datetime.now(dt.timezone.utc),
        )
    )
    session.commit()
    client = FakeKalshiClient(
        open_markets=[window_market("KXBTC15M-B", "0.30", "0.40")],
        markets_by_ticker={"KXBTC15M-A": {"status": "finalized", "result": "no"}},
    )

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "closed_at_settlement"
    trade = session.query(Trade).one()
    assert trade.result == "loss"
    # payout 0, cost 20, fee 1 -> pnl -21
    assert trade.pnl == pytest.approx(-21.0)


def _add_settled_trade(session, side: str, result: str, ticker: str = "KXBTC15M-PREV") -> None:
    session.add(
        Trade(
            ticker=ticker, source="btc_15min_scalp", side=side, entry_price=0.5, size=10, fee=0.1,
            status="settled", result=result, pnl=1.0 if result == "win" else -1.0,
            opened_at=dt.datetime.now(dt.timezone.utc), settled_at=dt.datetime.now(dt.timezone.utc),
        )
    )
    session.commit()


def test_next_side_defaults_to_yes_with_no_history() -> None:
    session = make_session()
    assert btc_15min_scalp.next_side(session) == "yes"


def test_next_side_flips_after_a_win() -> None:
    session = make_session()
    _add_settled_trade(session, side="yes", result="win")
    assert btc_15min_scalp.next_side(session) == "no"

    session2 = make_session()
    _add_settled_trade(session2, side="no", result="win")
    assert btc_15min_scalp.next_side(session2) == "yes"


def test_next_side_repeats_after_a_loss() -> None:
    session = make_session()
    _add_settled_trade(session, side="yes", result="loss")
    assert btc_15min_scalp.next_side(session) == "yes"

    session2 = make_session()
    _add_settled_trade(session2, side="no", result="loss")
    assert btc_15min_scalp.next_side(session2) == "no"


def test_enters_no_side_after_a_yes_win() -> None:
    session = make_session()
    _add_settled_trade(session, side="yes", result="win")
    # no_ask 0.50 is within the entry price range
    client = FakeKalshiClient(
        open_markets=[window_market("KXBTC15M-NEXT", "0.30", "0.70", no_bid="0.40", no_ask="0.50")]
    )

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "opened"
    assert result["side"] == "no"
    trade = session.query(Trade).filter(Trade.ticker == "KXBTC15M-NEXT").one()
    assert trade.side == "no"
    assert trade.entry_price == 0.50


def test_monitors_no_side_position_using_no_bid() -> None:
    session = make_session()
    session.add(
        Trade(
            ticker="KXBTC15M-A", source="btc_15min_scalp", side="no", entry_price=0.40, size=50, fee=1.0,
            status="open", opened_at=dt.datetime.now(dt.timezone.utc),
        )
    )
    session.commit()
    # no_bid 0.53 -> 32.5% gain on the "no" side, clears the 15% target
    client = FakeKalshiClient(open_markets=[window_market("KXBTC15M-A", "0.46", "0.47", no_bid="0.53", no_ask="0.54")])

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "closed_profit_target"
    assert result["side"] == "no"
    trade = session.query(Trade).one()
    assert trade.result == "win"


def test_opens_position_even_if_balance_fetch_fails() -> None:
    class BrokenBalanceClient(FakeKalshiClient):
        def get_balance(self) -> dict[str, Any]:
            raise RuntimeError("network error")

    session = make_session()
    client = BrokenBalanceClient(open_markets=[window_market("KXBTC15M-A", "0.30", "0.40")])

    result = btc_15min_scalp.poll(client, session)  # type: ignore[arg-type]

    assert result["status"] == "opened"
    assert result["real_cash_usd"] is None
    assert result["real_portfolio_value_usd"] is None
    assert session.query(Trade).count() == 1
