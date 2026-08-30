from __future__ import annotations

import datetime as dt
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from app.apify_client import ApifyClient
from app.config import settings
from app.db.session import SessionLocal
from app.engine import decision, paper_trading
from app.kalshi_client import KalshiClient, build_client_from_settings
from app.polymarket_client import PolymarketClient
from app.signals import news_signal, polymarket_arb_signal

logger = logging.getLogger(__name__)

INTERVAL_MINUTES = 20


def _run_polymarket_arb_signal(kalshi_client: KalshiClient, polymarket_client: PolymarketClient, session: Session) -> None:
    try:
        count = polymarket_arb_signal.run(kalshi_client, polymarket_client, session)
        logger.info("polymarket_arb_signal stored %d rows", count)
    except Exception:
        logger.exception("polymarket_arb_signal job failed")


def _run_news_signal(session: Session) -> None:
    if not settings.apify_api_token:
        logger.warning("APIFY_API_TOKEN not set; skipping news_signal job")
        return
    apify_client = ApifyClient(settings.apify_api_token)
    try:
        count = news_signal.run(apify_client, session, settings.apify_news_actor_id)
        logger.info("news_signal stored %d rows", count)
    except Exception:
        logger.exception("news_signal job failed")


def _run_decision_engine(kalshi_client: KalshiClient, session: Session) -> None:
    try:
        count = decision.run(kalshi_client, session)
        logger.info("decision engine stored %d rows", count)
    except Exception:
        logger.exception("decision engine job failed")


def _run_paper_trading_open(session: Session) -> None:
    try:
        opened = paper_trading.open_paper_trades(session)
        logger.info("paper_trading opened %d trades", opened)
    except Exception:
        logger.exception("paper_trading open job failed")


def _run_paper_trading_settle(kalshi_client: KalshiClient, session: Session) -> None:
    try:
        settled = paper_trading.settle_paper_trades(kalshi_client, session)
        logger.info("paper_trading settled %d trades", settled)
    except Exception:
        logger.exception("paper_trading settle job failed")


def run_pipeline() -> None:
    """Signals -> decisions -> paper trades -> settlement, in that order, every tick.

    A single job (rather than independently-scheduled ones) so each stage
    always sees the freshest output of the stage before it, instead of
    relying on APScheduler's incidental ordering of same-tick jobs. Each
    stage catches its own exceptions and logs, so one stage failing doesn't
    block the rest of the pipeline from running.

    Note: the BTC 15-min scalp strategy does NOT run here — it was pulled
    out into its own standalone script (scripts/run_btc_15min_scalp.py) so
    it can run in isolation, without depending on Apify/Polymarket calls or
    this 20-minute cadence. Do not add it back here and also run the
    standalone script at the same time — both would poll/trade
    independently and could open duplicate positions on the same window.
    """
    kalshi_client = build_client_from_settings(settings)
    polymarket_client = PolymarketClient(base_url=settings.polymarket_api_base_url)
    session = SessionLocal()
    try:
        _run_polymarket_arb_signal(kalshi_client, polymarket_client, session)
        _run_news_signal(session)
        _run_decision_engine(kalshi_client, session)
        _run_paper_trading_open(session)
        _run_paper_trading_settle(kalshi_client, session)
    finally:
        kalshi_client.close()
        polymarket_client.close()
        session.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    now = dt.datetime.now()
    scheduler.add_job(run_pipeline, "interval", minutes=INTERVAL_MINUTES, next_run_time=now)
    scheduler.start()
    return scheduler
