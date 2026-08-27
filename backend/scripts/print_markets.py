"""Milestone 1 acceptance check: print 10 live Kalshi markets with current prices.

Read-only — uses KalshiClient.get_markets (GET only). Hits your real Kalshi
account since this project uses no demo/sandbox, but no order is ever sent.
Run from backend/: python scripts/print_markets.py
"""

from app.config import settings
from app.kalshi_client import build_client_from_settings


def main() -> None:
    client = build_client_from_settings(settings)
    try:
        response = client.get_markets(limit=10)
    finally:
        client.close()

    for market in response.get("markets", []):
        ticker = market.get("ticker")
        yes_bid = market.get("yes_bid_dollars")
        yes_ask = market.get("yes_ask_dollars")
        no_bid = market.get("no_bid_dollars")
        no_ask = market.get("no_ask_dollars")
        print(f"{ticker:<24} yes_bid={yes_bid} yes_ask={yes_ask} no_bid={no_bid} no_ask={no_ask}")


if __name__ == "__main__":
    main()
