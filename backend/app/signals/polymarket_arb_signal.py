from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Signal
from app.kalshi_client import KalshiClient
from app.polymarket_client import PolymarketClient

SOURCE = "polymarket_arb"
KALSHI_SERIES = "KXETH"

# Polymarket's strike ladder for an event can lag the current price (e.g. it
# tops out at $2,900 while ETH trades at $3,200+), in which case the
# "nearest" match is really "no match" and storing it would fabricate a
# signal out of an irrelevant contract. Skip matches further than this.
MAX_STRIKE_DIFF = 100.0

_THRESHOLD_TICKER_RE = re.compile(r"-T[\d.]+$")
_ABOVE_SUB_TITLE_RE = re.compile(r"^\$([\d,]+(?:\.\d+)?) or above$")


def _polymarket_slug_for_date(date: dt.date) -> str:
    month = date.strftime("%B").lower()
    return f"ethereum-above-on-{month}-{date.day}-{date.year}"


def parse_kalshi_threshold(market: dict[str, Any]) -> tuple[float, dt.datetime] | None:
    """Return (strike, close_time) for a Kalshi "$X or above" threshold market, else None.

    Only "-T..." threshold tickers are handled here — the "-B..." price-bucket
    tickers (e.g. "$3,170 to 3,209.99") don't have a clean Polymarket
    equivalent (Polymarket's markets are single-strike "above $X"), so this
    first pass skips them rather than fabricating a match.
    """
    ticker = market.get("ticker", "")
    if not _THRESHOLD_TICKER_RE.search(ticker):
        return None

    sub_title_match = _ABOVE_SUB_TITLE_RE.match(market.get("yes_sub_title", ""))
    if not sub_title_match:
        return None
    strike = float(sub_title_match.group(1).replace(",", ""))

    close_time_raw = market.get("close_time")
    if not close_time_raw:
        return None
    close_time = dt.datetime.fromisoformat(close_time_raw.replace("Z", "+00:00"))

    return strike, close_time


def find_nearest_strike_market(poly_event: dict[str, Any], strike: float) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_diff = float("inf")
    for market in poly_event.get("markets", []):
        try:
            poly_strike = float(market.get("groupItemTitle", "").replace(",", ""))
        except ValueError:
            continue
        diff = abs(poly_strike - strike)
        if diff < best_diff:
            best_diff = diff
            best = market
    return best


def run(kalshi_client: KalshiClient, polymarket_client: PolymarketClient, session: Session) -> int:
    """Cross-reference Kalshi KXETH threshold markets against Polymarket, store Signal rows.

    Returns the number of Signal rows stored.
    """
    response = kalshi_client.get_markets(limit=1000, status="open", series_ticker=KALSHI_SERIES)

    event_cache: dict[str, dict[str, Any] | None] = {}
    stored = 0

    for market in response.get("markets", []):
        parsed = parse_kalshi_threshold(market)
        if parsed is None:
            continue
        strike, close_time = parsed

        date_key = close_time.date().isoformat()
        if date_key not in event_cache:
            slug = _polymarket_slug_for_date(close_time.date())
            event_cache[date_key] = polymarket_client.get_event_by_slug(slug)
        poly_event = event_cache[date_key]
        if poly_event is None:
            continue

        poly_market = find_nearest_strike_market(poly_event, strike)
        if poly_market is None:
            continue

        try:
            outcome_prices = json.loads(poly_market.get("outcomePrices", "[]"))
            poly_yes_prob = float(outcome_prices[0])
            poly_strike = float(poly_market.get("groupItemTitle", "").replace(",", ""))
        except (ValueError, IndexError):
            continue

        if abs(poly_strike - strike) > MAX_STRIKE_DIFF:
            continue

        poly_end_raw = poly_market.get("endDate")
        time_diff_seconds = None
        if poly_end_raw:
            poly_end = dt.datetime.fromisoformat(poly_end_raw.replace("Z", "+00:00"))
            time_diff_seconds = abs((poly_end - close_time).total_seconds())

        session.add(
            Signal(
                source=SOURCE,
                ticker=market["ticker"],
                estimated_probability=poly_yes_prob,
                raw_payload={
                    "kalshi": {
                        "ticker": market["ticker"],
                        "strike": strike,
                        "yes_bid": market.get("yes_bid_dollars"),
                        "yes_ask": market.get("yes_ask_dollars"),
                        "no_bid": market.get("no_bid_dollars"),
                        "no_ask": market.get("no_ask_dollars"),
                        "close_time": market.get("close_time"),
                    },
                    "polymarket": {
                        "event_slug": poly_event.get("slug"),
                        "question": poly_market.get("question"),
                        "strike": poly_strike,
                        "outcome_prices": outcome_prices,
                        "end_date": poly_end_raw,
                    },
                    "match_quality": {
                        "strike_diff": abs(poly_strike - strike),
                        "time_diff_seconds": time_diff_seconds,
                        "note": (
                            "Kalshi and Polymarket resolve at different times of "
                            "day for the same date — not a guaranteed same-event "
                            "match. See time_diff_seconds."
                        ),
                    },
                },
                ts=dt.datetime.now(dt.timezone.utc),
            )
        )
        stored += 1

    session.commit()
    return stored
