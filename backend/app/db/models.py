from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class MarketSnapshot(Base):
    """A point-in-time price/volume reading for a market ticker."""

    __tablename__ = "market_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String, index=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    yes_bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    yes_ask: Mapped[float | None] = mapped_column(Float, nullable=True)
    no_bid: Mapped[float | None] = mapped_column(Float, nullable=True)
    no_ask: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Signal(Base):
    """An estimated probability for a ticker from a given source (Apify actor/module)."""

    __tablename__ = "signal"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String, index=True)
    ticker: Mapped[str] = mapped_column(String, index=True)
    estimated_probability: Mapped[float] = mapped_column(Float)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Decision(Base):
    """A logged trade/no-trade evaluation of a Signal — the backtest data."""

    __tablename__ = "decision"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String, index=True)
    signal_id: Mapped[int | None] = mapped_column(ForeignKey("signal.id"), nullable=True)
    estimated_probability: Mapped[float] = mapped_column(Float)
    side: Mapped[str | None] = mapped_column(String, nullable=True)
    kalshi_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_edge: Mapped[float | None] = mapped_column(Float, nullable=True)
    fee_adjusted_edge: Mapped[float | None] = mapped_column(Float, nullable=True)
    would_trade: Mapped[bool] = mapped_column(Boolean)
    size_pct_of_bankroll: Mapped[float | None] = mapped_column(Float, nullable=True)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Trade(Base):
    """A (paper, through Milestone 7) trade: entry, and outcome once settled."""

    __tablename__ = "trade"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String, index=True)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    decision_id: Mapped[int | None] = mapped_column(ForeignKey("decision.id"), nullable=True)
    side: Mapped[str] = mapped_column(String)
    entry_price: Mapped[float] = mapped_column(Float)
    size: Mapped[float] = mapped_column(Float)  # number of contracts
    fee: Mapped[float] = mapped_column(Float, default=0.0)  # total fee paid to open (per-contract fee * size)
    status: Mapped[str] = mapped_column(String, default="open")
    result: Mapped[str | None] = mapped_column(String, nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    opened_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    settled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Alert(Base):
    """A threshold-triggered notification (Milestone 7)."""

    __tablename__ = "alert"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str] = mapped_column(String)
    delivered: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
