from __future__ import annotations

import json
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Signal
from app.signals import polymarket_arb_signal as sig


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class FakeKalshiClient:
    def __init__(self, markets: list[dict[str, Any]]) -> None:
        self._markets = markets

    def get_markets(self, **kwargs: Any) -> dict[str, Any]:
        return {"markets": self._markets}


class FakePolymarketClient:
    def __init__(self, events_by_slug: dict[str, dict[str, Any] | None]) -> None:
        self._events_by_slug = events_by_slug

    def get_event_by_slug(self, slug: str) -> dict[str, Any] | None:
        return self._events_by_slug.get(slug)


def make_kalshi_threshold_market(ticker: str, sub_title: str, close_time: str) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "yes_sub_title": sub_title,
        "yes_bid_dollars": "0.4000",
        "yes_ask_dollars": "0.4500",
        "close_time": close_time,
    }


def make_poly_market(group_item_title: str, question: str, outcome_prices: list[str], end_date: str) -> dict[str, Any]:
    return {
        "groupItemTitle": group_item_title,
        "question": question,
        "outcomePrices": json.dumps(outcome_prices),
        "endDate": end_date,
    }


def test_parse_kalshi_threshold_extracts_strike_and_close_time() -> None:
    market = make_kalshi_threshold_market(
        "KXETH-26AUG2717-T3209.99", "$3,210 or above", "2026-08-27T21:00:00Z"
    )
    result = sig.parse_kalshi_threshold(market)
    assert result is not None
    strike, close_time = result
    assert strike == 3210.0
    assert close_time.isoformat() == "2026-08-27T21:00:00+00:00"


def test_parse_kalshi_threshold_skips_bucket_tickers() -> None:
    market = make_kalshi_threshold_market(
        "KXETH-26AUG2717-B3190", "$3,170 to 3,209.99", "2026-08-27T21:00:00Z"
    )
    assert sig.parse_kalshi_threshold(market) is None


def test_find_nearest_strike_market_picks_closest() -> None:
    event = {
        "markets": [
            make_poly_market("3000", "q1", ["0.5", "0.5"], "2026-08-27T16:00:00Z"),
            make_poly_market("3200", "q2", ["0.6", "0.4"], "2026-08-27T16:00:00Z"),
            make_poly_market("3500", "q3", ["0.1", "0.9"], "2026-08-27T16:00:00Z"),
        ]
    }
    best = sig.find_nearest_strike_market(event, 3210.0)
    assert best is not None
    assert best["groupItemTitle"] == "3200"


def test_run_stores_signal_with_match_quality_metadata() -> None:
    kalshi_market = make_kalshi_threshold_market(
        "KXETH-26AUG2717-T3209.99", "$3,210 or above", "2026-08-27T21:00:00Z"
    )
    poly_event = {
        "slug": "ethereum-above-on-august-27-2026",
        "markets": [
            make_poly_market("3200", "Will ETH be above $3,200?", ["0.62", "0.38"], "2026-08-27T16:00:00Z"),
        ],
    }
    kalshi_client = FakeKalshiClient([kalshi_market])
    poly_client = FakePolymarketClient({"ethereum-above-on-august-27-2026": poly_event})
    session = make_session()

    stored = sig.run(kalshi_client, poly_client, session)  # type: ignore[arg-type]

    assert stored == 1
    row = session.query(Signal).one()
    assert row.source == "polymarket_arb"
    assert row.ticker == "KXETH-26AUG2717-T3209.99"
    assert row.estimated_probability == 0.62
    assert row.raw_payload["match_quality"]["strike_diff"] == 10.0
    assert row.raw_payload["match_quality"]["time_diff_seconds"] == 5 * 3600


def test_run_skips_matches_beyond_max_strike_diff() -> None:
    kalshi_market = make_kalshi_threshold_market(
        "KXETH-26AUG2717-T3209.99", "$3,210 or above", "2026-08-27T21:00:00Z"
    )
    poly_event = {
        "slug": "ethereum-above-on-august-27-2026",
        "markets": [
            make_poly_market("2900", "Will ETH be above $2,900?", ["0.001", "0.999"], "2026-08-27T16:00:00Z"),
        ],
    }
    kalshi_client = FakeKalshiClient([kalshi_market])
    poly_client = FakePolymarketClient({"ethereum-above-on-august-27-2026": poly_event})
    session = make_session()

    stored = sig.run(kalshi_client, poly_client, session)  # type: ignore[arg-type]

    assert stored == 0
    assert session.query(Signal).count() == 0


def test_run_skips_markets_with_no_matching_polymarket_event() -> None:
    kalshi_market = make_kalshi_threshold_market(
        "KXETH-26AUG2717-T3209.99", "$3,210 or above", "2026-08-27T21:00:00Z"
    )
    kalshi_client = FakeKalshiClient([kalshi_market])
    poly_client = FakePolymarketClient({})
    session = make_session()

    stored = sig.run(kalshi_client, poly_client, session)  # type: ignore[arg-type]

    assert stored == 0
    assert session.query(Signal).count() == 0
