"""Watch the BTC 15-min scalp strategy live, printing status every
BTC_15MIN_POLL_SECONDS.

Read-only: never opens, closes, or modifies a trade. Safe to run alongside
`uvicorn app.main:app`, which is the process actually executing the
strategy (via app.scheduler.run_btc_15min_scalp_tick) — this script only
observes and prints.

Run from backend/: python -u scripts/watch_btc_scalp.py
(-u avoids output buffering delays when stdout isn't a real terminal)
"""

import datetime as dt
import time

from app.config import settings
from app.db.models import Trade
from app.db.session import SessionLocal
from app.kalshi_client import build_client_from_settings
from app.strategies.btc_15min_scalp import SERIES_TICKER, SOURCE


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]


def _seconds_remaining(close_time_raw: str | None, now: dt.datetime) -> float | None:
    if not close_time_raw:
        return None
    close_time = dt.datetime.fromisoformat(close_time_raw.replace("Z", "+00:00"))
    return max((close_time - now).total_seconds(), 0.0)


def print_status_once() -> None:
    kalshi_client = build_client_from_settings(settings)
    session = SessionLocal()
    try:
        response = kalshi_client.get_markets(limit=5, status="open", series_ticker=SERIES_TICKER)
        markets = response.get("markets", [])
        if not markets:
            print("no open KXBTC15M market")
            return
        market = markets[0]

        ticker = market["ticker"]
        yes_bid = _as_float(market.get("yes_bid_dollars"))
        target_price = market.get("floor_strike")
        remaining = _seconds_remaining(market.get("close_time"), dt.datetime.now(dt.timezone.utc))
        remaining_str = f"{int(remaining)}s" if remaining is not None else "-"

        yes_bid_str = f"{yes_bid:.2f}" if yes_bid is not None else "-"
        line = f"[{ticker}] target=${target_price} remaining={remaining_str} yes_bid=${yes_bid_str}"

        trade = session.query(Trade).filter(Trade.source == SOURCE, Trade.status == "open").first()
        if trade is None:
            line += " | no open position"
        elif trade.ticker != ticker:
            line += f" | position open on previous window ({trade.ticker}), awaiting settlement"
        elif yes_bid is not None and trade.entry_price:
            gain_pct = (yes_bid - trade.entry_price) / trade.entry_price
            line += (
                f" | position: entry=${trade.entry_price:.2f} contracts={trade.size:.0f} "
                f"gain={gain_pct:+.1%} (target {settings.btc_15min_profit_target_pct:.0%})"
            )
        else:
            line += " | position open, price unavailable"

        print(line)
    finally:
        kalshi_client.close()
        session.close()


def main() -> None:
    print(f"Watching {SOURCE} every {settings.btc_15min_poll_seconds}s (read-only, Ctrl+C to stop)")
    try:
        while True:
            print_status_once()
            time.sleep(settings.btc_15min_poll_seconds)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
