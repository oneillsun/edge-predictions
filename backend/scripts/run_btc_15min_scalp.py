"""Standalone BTC 15-min scalp runner — isolated from the rest of the app.

No signals, no Polymarket/Apify calls, no 20-minute pipeline — just this one
strategy, polling Kalshi every BTC_15MIN_POLL_SECONDS. Paper-simulated
only: never calls an order-placement endpoint.

Do NOT run this at the same time as `uvicorn app.main:app` if that app's
scheduler still runs the BTC job (it doesn't, as of this script's
introduction — see app/scheduler.py) — running the strategy from two places
at once risks duplicate positions on the same window.

Run from backend/: python -u scripts/run_btc_15min_scalp.py
(-u avoids output buffering delays when stdout isn't a real terminal)
"""

import logging
import time

from app.config import settings
from app.strategies.btc_15min_scalp import SOURCE, run_once

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info(
        "Starting standalone %s runner: $%.2f/trade, %.0f%% profit target, polling every %ss",
        SOURCE,
        settings.btc_15min_position_size_usd,
        settings.btc_15min_profit_target_pct * 100,
        settings.btc_15min_poll_seconds,
    )
    while True:
        run_once()
        time.sleep(settings.btc_15min_poll_seconds)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
