from __future__ import annotations

import datetime as dt
import math
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Decision, Signal
from app.engine import sizing
from app.kalshi_client import KalshiClient
from app.signals import polymarket_arb_signal

BASE_FEE_RATE = 0.07
DEFAULT_LOOKBACK_MINUTES = 60


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def fee_for_price(price: float, fee_multiplier: float) -> float:
    """Kalshi's quadratic taker fee for one contract at this price, rounded up to the cent.

    fee = ceil_to_cent(fee_multiplier * 0.07 * price * (1 - price))

    fee_multiplier is queried live per-series (KalshiClient.get_series) rather
    than assumed constant — Kalshi can set a different multiplier per series.
    """
    raw_fee = fee_multiplier * BASE_FEE_RATE * price * (1 - price)
    return math.ceil(raw_fee * 100) / 100


def best_edge(
    estimated_probability: float,
    yes_ask: float | None,
    no_ask: float | None,
    fee_multiplier: float,
) -> dict[str, Any] | None:
    """Return the better fee-adjusted edge across the yes/no sides, or None if
    neither side has a usable price.
    """
    candidates: list[dict[str, Any]] = []

    if yes_ask is not None and 0 < yes_ask < 1:
        raw_edge = estimated_probability - yes_ask
        fee = fee_for_price(yes_ask, fee_multiplier)
        candidates.append(
            {"side": "yes", "price": yes_ask, "raw_edge": raw_edge, "fee": fee, "fee_adjusted_edge": raw_edge - fee}
        )

    if no_ask is not None and 0 < no_ask < 1:
        implied_no_probability = 1 - estimated_probability
        raw_edge = implied_no_probability - no_ask
        fee = fee_for_price(no_ask, fee_multiplier)
        candidates.append(
            {"side": "no", "price": no_ask, "raw_edge": raw_edge, "fee": fee, "fee_adjusted_edge": raw_edge - fee}
        )

    if not candidates:
        return None
    return max(candidates, key=lambda c: c["fee_adjusted_edge"])


def _series_ticker(ticker: str) -> str:
    return ticker.split("-")[0]


def run(kalshi_client: KalshiClient, session: Session, lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES) -> int:
    """Evaluate recent polymarket_arb signals into fee-aware trade/no-trade Decisions.

    Only polymarket_arb signals are evaluated — they carry a specific Kalshi
    contract ticker plus a Kalshi price snapshot captured at signal time.
    news_eth signals are category-level (ticker is a series, not a specific
    strike/price) and aren't directly actionable by this first-pass engine.

    Returns the number of Decision rows stored.
    """
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=lookback_minutes)
    signals = (
        session.query(Signal)
        .filter(Signal.source == polymarket_arb_signal.SOURCE)
        .filter(Signal.ts >= cutoff)
        .order_by(Signal.ts.desc())
        .all()
    )

    latest_by_ticker: dict[str, Signal] = {}
    for signal in signals:
        latest_by_ticker.setdefault(signal.ticker, signal)

    fee_multiplier_cache: dict[str, float] = {}
    stored = 0

    for ticker, signal in latest_by_ticker.items():
        series = _series_ticker(ticker)
        if series not in fee_multiplier_cache:
            series_data = kalshi_client.get_series(series)
            fee_multiplier_cache[series] = float(series_data.get("series", {}).get("fee_multiplier", 1))
        fee_multiplier = fee_multiplier_cache[series]

        kalshi_snapshot = signal.raw_payload.get("kalshi", {})
        yes_ask = _as_float(kalshi_snapshot.get("yes_ask"))
        no_ask = _as_float(kalshi_snapshot.get("no_ask"))

        edge = best_edge(signal.estimated_probability, yes_ask, no_ask, fee_multiplier)
        would_trade = edge is not None and edge["fee_adjusted_edge"] > settings.edge_margin_threshold

        size_pct = None
        if would_trade and edge is not None:
            win_probability = signal.estimated_probability if edge["side"] == "yes" else 1 - signal.estimated_probability
            size_pct = sizing.capped_position_size(
                probability=win_probability,
                price=edge["price"],
                kelly_fraction_cap=settings.kelly_fraction_cap,
                max_position_pct=settings.max_position_pct_of_bankroll,
            )

        session.add(
            Decision(
                ticker=ticker,
                signal_id=signal.id,
                estimated_probability=signal.estimated_probability,
                side=edge["side"] if edge else None,
                kalshi_price=edge["price"] if edge else None,
                fee=edge["fee"] if edge else None,
                raw_edge=edge["raw_edge"] if edge else None,
                fee_adjusted_edge=edge["fee_adjusted_edge"] if edge else None,
                would_trade=would_trade,
                size_pct_of_bankroll=size_pct,
                inputs={
                    "signal_source": signal.source,
                    "signal_ts": signal.ts.isoformat(),
                    "kalshi_snapshot": kalshi_snapshot,
                    "fee_multiplier": fee_multiplier,
                    "edge_margin_threshold": settings.edge_margin_threshold,
                },
                ts=dt.datetime.now(dt.timezone.utc),
            )
        )
        stored += 1

    session.commit()
    return stored
