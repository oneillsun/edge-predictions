"""Milestone 1/2 acceptance check: print 10 live Kalshi markets and store a
MarketSnapshot row for each.

Read-only against Kalshi — uses KalshiClient.get_markets (GET only). Hits
your real Kalshi account since this project uses no demo/sandbox, but no
order is ever sent. Run from backend/ (after `alembic upgrade head`):
    python scripts/print_markets.py [SERIES_TICKER]

Note: Kalshi's /markets has no server-side sort, and a large share of "open"
markets are auto-generated multivariate-event shards with zero trading
interest, so results may show low-activity markets. That's expected — this
script only needs to prove read access works, not surface liquid markets.

Optional: pass a series ticker to filter, e.g.:
    python scripts/print_markets.py KXBTC
"""

import datetime as dt
import sys

from app.config import settings
from app.db.models import MarketSnapshot
from app.db.session import SessionLocal
from app.kalshi_client import build_client_from_settings


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]


def main() -> None:
    series_ticker = sys.argv[1] if len(sys.argv) > 1 else None

    client = build_client_from_settings(settings)
    try:
        response = client.get_markets(limit=10, status="open", series_ticker=series_ticker)
    finally:
        client.close()

    markets = response.get("markets", [])
    now = dt.datetime.now(dt.timezone.utc)

    session = SessionLocal()
    try:
        for market in markets:
            ticker = market.get("ticker")
            title = market.get("title")
            yes_sub_title = market.get("yes_sub_title")
            yes_bid = market.get("yes_bid_dollars")
            yes_ask = market.get("yes_ask_dollars")
            no_bid = market.get("no_bid_dollars")
            no_ask = market.get("no_ask_dollars")
            print(f"{ticker:<24} {title} ({yes_sub_title})")
            print(f"  yes_bid={yes_bid} yes_ask={yes_ask} no_bid={no_bid} no_ask={no_ask}")

            session.add(
                MarketSnapshot(
                    ticker=ticker,
                    ts=now,
                    yes_bid=_as_float(yes_bid),
                    yes_ask=_as_float(yes_ask),
                    no_bid=_as_float(no_bid),
                    no_ask=_as_float(no_ask),
                    volume=_as_float(market.get("volume_24h_fp")),
                )
            )
        session.commit()
    finally:
        session.close()

    print(f"\nStored {len(markets)} market_snapshot rows.")


if __name__ == "__main__":
    main()
