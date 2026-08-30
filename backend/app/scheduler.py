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
from app.strategies import btc_15min_scalp

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


def _format_btc_scalp_log(result: dict) -> str:
    status = result.get("status")
    ticker = result.get("ticker", "-")
    target = result.get("target_price")
    remaining = result.get("seconds_remaining")
    remaining_str = f"{int(remaining)}s" if remaining is not None else "-"
    parts = [f"[{ticker}]", f"status={status}", f"target=${target}", f"remaining={remaining_str}"]

    if status == "opened":
        parts.append(f"entry=${result['entry_price']:.2f} contracts={result['contracts']} fee=${result['fee']:.2f}")
    elif status == "monitoring":
        gain = result.get("gain_pct")
        gain_str = f"{gain:+.1%}" if gain is not None else "-"
        parts.append(f"entry=${result['entry_price']:.2f} bid=${result.get('current_bid')} gain={gain_str}")
    elif status in ("closed_profit_target", "closed_at_settlement"):
        parts.append(f"result={result.get('result', 'target_hit')} pnl=${result.get('pnl'):.2f}")

    return " ".join(parts)


def run_btc_15min_scalp_tick() -> None:
    """Paper-simulated only — never places a real order. See app/strategies/btc_15min_scalp.py."""
    kalshi_client = build_client_from_settings(settings)
    session = SessionLocal()
    try:
        result = btc_15min_scalp.poll(kalshi_client, session)
        if result.get("status") == "no_open_market":
            logger.info("btc_15min_scalp: no open KXBTC15M market")
        else:
            logger.info("btc_15min_scalp %s", _format_btc_scalp_log(result))
    except Exception:
        logger.exception("btc_15min_scalp tick failed")
    finally:
        kalshi_client.close()
        session.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    now = dt.datetime.now()
    scheduler.add_job(run_pipeline, "interval", minutes=INTERVAL_MINUTES, next_run_time=now)
    scheduler.add_job(
        run_btc_15min_scalp_tick,
        "interval",
        seconds=settings.btc_15min_poll_seconds,
        next_run_time=now,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    return scheduler
