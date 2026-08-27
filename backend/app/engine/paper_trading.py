from __future__ import annotations

import datetime as dt
import math

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Decision, Trade
from app.kalshi_client import KalshiClient

DEFAULT_LOOKBACK_MINUTES = 60

# A market is treated as resolved once it reaches one of these terminal
# statuses with a non-empty result. "disputed"/"amended" are intentionally
# excluded — this is paper money, but there's no reason to settle on a
# result that might still change.
RESOLVED_STATUSES = {"determined", "finalized"}


def open_paper_trades(session: Session, lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES) -> int:
    """Open a simulated Trade for each recent would-trade Decision.

    No real order is ever submitted — this only writes rows to the trade
    table. Skips a ticker that already has an open trade, so a signal that
    keeps firing "would trade" every cycle doesn't keep opening new
    positions on top of an existing one. Entry price is the Kalshi price
    snapshot already captured on the Decision, not a fresh re-fetch — kept
    simple since this is a paper simulation, not real execution.

    Returns the number of Trade rows opened.
    """
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=lookback_minutes)
    decisions = (
        session.query(Decision)
        .filter(Decision.would_trade.is_(True))
        .filter(Decision.ts >= cutoff)
        .order_by(Decision.ts.desc())
        .all()
    )

    open_tickers = {
        ticker for (ticker,) in session.query(Trade.ticker).filter(Trade.status == "open").distinct()
    }

    opened = 0
    for decision in decisions:
        if decision.ticker in open_tickers:
            continue
        if decision.kalshi_price is None or decision.size_pct_of_bankroll is None:
            continue

        dollar_size = decision.size_pct_of_bankroll * settings.paper_bankroll_usd
        contracts = math.floor(dollar_size / decision.kalshi_price)
        if contracts < 1:
            continue

        session.add(
            Trade(
                ticker=decision.ticker,
                source=decision.inputs.get("signal_source") if decision.inputs else None,
                decision_id=decision.id,
                side=decision.side,
                entry_price=decision.kalshi_price,
                size=contracts,
                fee=(decision.fee or 0.0) * contracts,
                status="open",
                opened_at=dt.datetime.now(dt.timezone.utc),
            )
        )
        open_tickers.add(decision.ticker)
        opened += 1

    session.commit()
    return opened


def settle_paper_trades(kalshi_client: KalshiClient, session: Session) -> int:
    """Check each open paper trade against Kalshi and settle it if the market has resolved.

    Read-only against Kalshi (GET /markets/{ticker}) — never places an order.
    Returns the number of Trade rows settled.
    """
    open_trades = session.query(Trade).filter(Trade.status == "open").all()

    settled = 0
    for trade in open_trades:
        market_data = kalshi_client.get_market(trade.ticker).get("market", {})
        status = market_data.get("status")
        result = market_data.get("result")

        if status not in RESOLVED_STATUSES or result not in ("yes", "no"):
            continue

        won = result == trade.side
        payout = trade.size * 1.0 if won else 0.0
        cost = trade.size * trade.entry_price
        pnl = payout - cost - trade.fee

        trade.status = "settled"
        trade.result = "win" if won else "loss"
        trade.pnl = pnl
        trade.settled_at = dt.datetime.now(dt.timezone.utc)
        settled += 1

    session.commit()
    return settled
