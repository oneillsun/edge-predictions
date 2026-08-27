"""Milestone 1 acceptance check: print 10 live Kalshi markets with descriptions and current prices.

Read-only — uses KalshiClient.get_markets (GET only). Hits your real Kalshi
account since this project uses no demo/sandbox, but no order is ever sent.
Run from backend/: python scripts/print_markets.py

Note: Kalshi's /markets has no server-side sort, and a large share of "open"
markets are auto-generated multivariate-event shards with zero trading
interest, so results may show low-activity markets. That's expected — this
script only needs to prove read access works, not surface liquid markets.

Optional: pass a series ticker to filter, e.g.:
    python scripts/print_markets.py KXBTC
"""

import sys

from app.config import settings
from app.kalshi_client import build_client_from_settings


def main() -> None:
    series_ticker = sys.argv[1] if len(sys.argv) > 1 else None

    client = build_client_from_settings(settings)
    try:
        response = client.get_markets(limit=10, status="open", series_ticker=series_ticker)
    finally:
        client.close()

    for market in response.get("markets", []):
        ticker = market.get("ticker")
        title = market.get("title")
        yes_sub_title = market.get("yes_sub_title")
        yes_bid = market.get("yes_bid_dollars")
        yes_ask = market.get("yes_ask_dollars")
        no_bid = market.get("no_bid_dollars")
        no_ask = market.get("no_ask_dollars")
        print(f"{ticker:<24} {title} ({yes_sub_title})")
        print(f"  yes_bid={yes_bid} yes_ask={yes_ask} no_bid={no_bid} no_ask={no_ask}")


if __name__ == "__main__":
    main()
