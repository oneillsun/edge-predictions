from __future__ import annotations

import datetime as dt
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.apify_client import ApifyClient
from app.config import settings
from app.db.session import SessionLocal
from app.kalshi_client import build_client_from_settings
from app.polymarket_client import PolymarketClient
from app.signals import news_signal, polymarket_arb_signal

logger = logging.getLogger(__name__)

INTERVAL_MINUTES = 20


def run_polymarket_arb_job() -> None:
    kalshi_client = build_client_from_settings(settings)
    polymarket_client = PolymarketClient(base_url=settings.polymarket_api_base_url)
    session = SessionLocal()
    try:
        count = polymarket_arb_signal.run(kalshi_client, polymarket_client, session)
        logger.info("polymarket_arb_signal stored %d rows", count)
    except Exception:
        logger.exception("polymarket_arb_signal job failed")
    finally:
        kalshi_client.close()
        polymarket_client.close()
        session.close()


def run_news_signal_job() -> None:
    if not settings.apify_api_token:
        logger.warning("APIFY_API_TOKEN not set; skipping news_signal job")
        return
    apify_client = ApifyClient(settings.apify_api_token)
    session = SessionLocal()
    try:
        count = news_signal.run(apify_client, session, settings.apify_news_actor_id)
        logger.info("news_signal stored %d rows", count)
    except Exception:
        logger.exception("news_signal job failed")
    finally:
        session.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    now = dt.datetime.now()
    scheduler.add_job(run_polymarket_arb_job, "interval", minutes=INTERVAL_MINUTES, next_run_time=now)
    scheduler.add_job(run_news_signal_job, "interval", minutes=INTERVAL_MINUTES, next_run_time=now)
    scheduler.start()
    return scheduler
