from __future__ import annotations

import datetime as dt
import math
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Trade
from app.engine.decision import fee_for_price
from app.kalshi_client import KalshiClient

SOURCE = "btc_15min_scalp"
SERIES_TICKER = "KXBTC15M"

# Same terminal-status rule as app.engine.paper_trading.settle_paper_trades.
RESOLVED_STATUSES = {"determined", "finalized"}


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _seconds_remaining(close_time_raw: str | None, now: dt.datetime) -> float | None:
    if not close_time_raw:
        return None
    close_time = dt.datetime.fromisoformat(close_time_raw.replace("Z", "+00:00"))
    return max((close_time - now).total_seconds(), 0.0)


def _seconds_since_open(open_time_raw: str | None, now: dt.datetime) -> float | None:
    if not open_time_raw:
        return None
    open_time = dt.datetime.fromisoformat(open_time_raw.replace("Z", "+00:00"))
    return max((now - open_time).total_seconds(), 0.0)


def _current_window_market(kalshi_client: KalshiClient) -> dict[str, Any] | None:
    response = kalshi_client.get_markets(limit=5, status="open", series_ticker=SERIES_TICKER)
    markets = response.get("markets", [])
    return markets[0] if markets else None


def _open_trade(session: Session) -> Trade | None:
    return session.query(Trade).filter(Trade.source == SOURCE, Trade.status == "open").first()


def _already_traded(session: Session, ticker: str) -> bool:
    return session.query(Trade).filter(Trade.source == SOURCE, Trade.ticker == ticker).first() is not None


def _real_account_snapshot(kalshi_client: KalshiClient) -> dict[str, float | None]:
    """Real Kalshi account cash/portfolio value — display only, for context
    alongside a paper trade's open/close. Never used in any sizing or
    trading decision. Swallows failures rather than breaking a trading tick.
    """
    try:
        balance = kalshi_client.get_balance()
        cash = balance.get("balance_dollars")
        portfolio_cents = balance.get("portfolio_value")
        return {
            "real_cash_usd": float(cash) if cash is not None else None,
            "real_portfolio_value_usd": (portfolio_cents / 100.0) if portfolio_cents is not None else None,
        }
    except Exception:
        return {"real_cash_usd": None, "real_portfolio_value_usd": None}


def poll(kalshi_client: KalshiClient, session: Session) -> dict[str, Any]:
    """One poll tick: maybe enter a new window, maybe exit on profit target, maybe
    settle a rolled-over window against Kalshi's real result.

    Paper-simulated only — never calls an order-placement endpoint. Buys
    "Yes" unconditionally at the start of a window it hasn't already traded
    (no edge/signal check — this is a timed-entry strategy, not the
    Milestone 4 decision engine), then closes early once the current yes_bid
    implies a BTC_15MIN_PROFIT_TARGET_PCT gain over the entry price, or at
    real settlement if the target is never hit. If more than
    BTC_15MIN_ENTRY_WINDOW_SECONDS have passed since the window opened
    before we notice it (e.g. after a restart, or a slow tick), the entry is
    skipped entirely rather than chasing a stale window — it waits for the
    next one.

    Every returned dict carries target_price, close_time, and
    seconds_remaining for the *current* window — all read directly off
    Kalshi's own market data, no other data source involved. The "opened"
    and "closed_*" results also carry real_cash_usd/real_portfolio_value_usd
    — your actual Kalshi account balance at that moment, for context only
    (never used in sizing or any trading decision — this strategy is still
    paper-simulated only).

    Returns a small dict describing what happened this tick, for logging.
    """
    market = _current_window_market(kalshi_client)
    if market is None:
        return {"status": "no_open_market"}

    ticker = market["ticker"]
    yes_bid = _as_float(market.get("yes_bid_dollars"))
    yes_ask = _as_float(market.get("yes_ask_dollars"))
    target_price = market.get("floor_strike")
    close_time = market.get("close_time")
    now = dt.datetime.now(dt.timezone.utc)
    window_info = {
        "target_price": target_price,
        "close_time": close_time,
        "seconds_remaining": _seconds_remaining(close_time, now),
    }

    trade = _open_trade(session)

    if trade is not None and trade.ticker != ticker:
        # The window rolled over while we still held a position in the old
        # one — the profit target was never hit, so wait for it to actually
        # settle rather than guessing at an exit price.
        market_data = kalshi_client.get_market(trade.ticker).get("market", {})
        status = market_data.get("status")
        result = market_data.get("result")
        if status in RESOLVED_STATUSES and result in ("yes", "no"):
            won = result == trade.side
            payout = trade.size * 1.0 if won else 0.0
            cost = trade.size * trade.entry_price
            trade.status = "settled"
            trade.result = "win" if won else "loss"
            trade.pnl = payout - cost - trade.fee
            trade.settled_at = now
            session.commit()
            return {
                "status": "closed_at_settlement",
                "ticker": trade.ticker,
                "result": trade.result,
                "pnl": trade.pnl,
                **window_info,
                **_real_account_snapshot(kalshi_client),
            }
        return {"status": "waiting_for_settlement", "ticker": trade.ticker, **window_info}

    if trade is not None and trade.ticker == ticker:
        if yes_bid is None or trade.entry_price <= 0:
            return {
                "status": "monitoring",
                "ticker": ticker,
                "entry_price": trade.entry_price,
                "current_bid": yes_bid,
                **window_info,
            }

        gain_pct = (yes_bid - trade.entry_price) / trade.entry_price
        if gain_pct >= settings.btc_15min_profit_target_pct:
            fee_multiplier = float(kalshi_client.get_series(SERIES_TICKER).get("series", {}).get("fee_multiplier", 1))
            exit_fee = fee_for_price(yes_bid, fee_multiplier) * trade.size
            payout = trade.size * yes_bid
            cost = trade.size * trade.entry_price
            trade.status = "settled"
            trade.result = "win"
            trade.pnl = payout - cost - trade.fee - exit_fee
            trade.settled_at = now
            session.commit()
            return {
                "status": "closed_profit_target",
                "ticker": ticker,
                "entry_price": trade.entry_price,
                "exit_price": yes_bid,
                "gain_pct": gain_pct,
                "pnl": trade.pnl,
                **window_info,
                **_real_account_snapshot(kalshi_client),
            }

        return {
            "status": "monitoring",
            "ticker": ticker,
            "entry_price": trade.entry_price,
            "current_bid": yes_bid,
            "gain_pct": gain_pct,
            **window_info,
        }

    # No open position: enter this window if we haven't already traded it.
    if _already_traded(session, ticker):
        return {"status": "watching", "ticker": ticker, "yes_bid": yes_bid, "yes_ask": yes_ask, **window_info}

    elapsed_since_open = _seconds_since_open(market.get("open_time"), now)
    if elapsed_since_open is not None and elapsed_since_open > settings.btc_15min_entry_window_seconds:
        # We're too late into this window to call it a "start of window"
        # entry anymore — skip it rather than chasing a stale entry, and
        # wait for the next window.
        return {
            "status": "missed_entry_window",
            "ticker": ticker,
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "elapsed_since_open": elapsed_since_open,
            **window_info,
        }

    if yes_ask is None or not (0 < yes_ask < 1):
        return {"status": "watching", "ticker": ticker, "yes_bid": yes_bid, "yes_ask": yes_ask, **window_info}

    contracts = math.floor(settings.btc_15min_position_size_usd / yes_ask)
    if contracts < 1:
        return {"status": "watching", "ticker": ticker, "yes_bid": yes_bid, "yes_ask": yes_ask, **window_info}

    fee_multiplier = float(kalshi_client.get_series(SERIES_TICKER).get("series", {}).get("fee_multiplier", 1))
    entry_fee = fee_for_price(yes_ask, fee_multiplier) * contracts

    session.add(
        Trade(
            ticker=ticker,
            source=SOURCE,
            side="yes",
            entry_price=yes_ask,
            size=contracts,
            fee=entry_fee,
            status="open",
            opened_at=now,
        )
    )
    session.commit()
    return {
        "status": "opened",
        "ticker": ticker,
        "entry_price": yes_ask,
        "contracts": contracts,
        "fee": entry_fee,
        **window_info,
        **_real_account_snapshot(kalshi_client),
    }
