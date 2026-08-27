from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Decision, Signal
from app.engine import decision


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class FakeKalshiClient:
    def __init__(self, fee_multiplier: float = 1.0) -> None:
        self._fee_multiplier = fee_multiplier
        self.requested_series: list[str] = []

    def get_series(self, series_ticker: str) -> dict[str, Any]:
        self.requested_series.append(series_ticker)
        return {"series": {"ticker": series_ticker, "fee_multiplier": self._fee_multiplier, "fee_type": "quadratic"}}


def add_signal(session, ticker: str, estimated_probability: float, yes_ask: str, no_ask: str, ts: dt.datetime) -> Signal:
    signal = Signal(
        source="polymarket_arb",
        ticker=ticker,
        estimated_probability=estimated_probability,
        raw_payload={"kalshi": {"ticker": ticker, "yes_ask": yes_ask, "no_ask": no_ask}},
        ts=ts,
    )
    session.add(signal)
    session.commit()
    return signal


def test_fee_for_price_matches_kalshi_quadratic_formula() -> None:
    # 0.07 * 0.5 * 0.5 = 0.0175 -> rounds up to the next cent
    assert decision.fee_for_price(0.5, fee_multiplier=1.0) == 0.02


def test_fee_for_price_scales_with_fee_multiplier() -> None:
    assert decision.fee_for_price(0.5, fee_multiplier=0.0) == 0.0


def test_best_edge_picks_yes_side_when_underpriced() -> None:
    edge = decision.best_edge(estimated_probability=0.8, yes_ask=0.5, no_ask=0.9, fee_multiplier=1.0)
    assert edge is not None
    assert edge["side"] == "yes"
    assert edge["raw_edge"] == pytest.approx(0.3)


def test_best_edge_picks_no_side_when_underpriced() -> None:
    edge = decision.best_edge(estimated_probability=0.2, yes_ask=0.9, no_ask=0.5, fee_multiplier=1.0)
    assert edge is not None
    assert edge["side"] == "no"
    # implied no probability = 0.8, no_ask = 0.5 -> raw edge 0.3
    assert edge["raw_edge"] == pytest.approx(0.3)


def test_best_edge_returns_none_without_usable_prices() -> None:
    assert decision.best_edge(0.6, yes_ask=None, no_ask=None, fee_multiplier=1.0) is None


def test_run_logs_would_trade_case() -> None:
    session = make_session()
    now = dt.datetime.now(dt.timezone.utc)
    add_signal(session, "KXETH-26AUG2717-T3209.99", estimated_probability=0.8, yes_ask="0.5000", no_ask="0.9000", ts=now)
    kalshi_client = FakeKalshiClient(fee_multiplier=1.0)

    stored = decision.run(kalshi_client, session)  # type: ignore[arg-type]

    assert stored == 1
    row = session.query(Decision).one()
    assert row.would_trade is True
    assert row.side == "yes"
    assert row.size_pct_of_bankroll is not None
    assert row.size_pct_of_bankroll > 0
    assert row.fee_adjusted_edge is not None
    assert row.fee_adjusted_edge > 0


def test_run_logs_edge_too_small_case() -> None:
    session = make_session()
    now = dt.datetime.now(dt.timezone.utc)
    # yes_ask very close to estimated probability -> edge too small after fees
    add_signal(session, "KXETH-26AUG2717-T3209.99", estimated_probability=0.51, yes_ask="0.5000", no_ask="0.9000", ts=now)
    kalshi_client = FakeKalshiClient(fee_multiplier=1.0)

    stored = decision.run(kalshi_client, session)  # type: ignore[arg-type]

    assert stored == 1
    row = session.query(Decision).one()
    assert row.would_trade is False
    assert row.size_pct_of_bankroll is None
    assert row.fee_adjusted_edge is not None


def test_run_ignores_stale_signals_outside_lookback() -> None:
    session = make_session()
    stale_ts = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=120)
    add_signal(session, "KXETH-26AUG2717-T3209.99", estimated_probability=0.8, yes_ask="0.5000", no_ask="0.9000", ts=stale_ts)
    kalshi_client = FakeKalshiClient()

    stored = decision.run(kalshi_client, session, lookback_minutes=60)  # type: ignore[arg-type]

    assert stored == 0


def test_run_only_evaluates_most_recent_signal_per_ticker() -> None:
    session = make_session()
    now = dt.datetime.now(dt.timezone.utc)
    add_signal(session, "KXETH-T1", estimated_probability=0.5, yes_ask="0.9000", no_ask="0.9000", ts=now - dt.timedelta(minutes=10))
    add_signal(session, "KXETH-T1", estimated_probability=0.8, yes_ask="0.5000", no_ask="0.9000", ts=now)
    kalshi_client = FakeKalshiClient()

    stored = decision.run(kalshi_client, session)  # type: ignore[arg-type]

    assert stored == 1
    row = session.query(Decision).one()
    assert row.estimated_probability == 0.8
