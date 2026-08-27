from __future__ import annotations

import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, MarketSnapshot, Signal


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_market_snapshot_round_trip() -> None:
    session = make_session()
    ts = dt.datetime.now(dt.timezone.utc)

    session.add(
        MarketSnapshot(
            ticker="KXBTC-TEST",
            ts=ts,
            yes_bid=0.10,
            yes_ask=0.20,
            no_bid=0.80,
            no_ask=0.90,
            volume=100.0,
        )
    )
    session.commit()

    rows = session.query(MarketSnapshot).all()
    assert len(rows) == 1
    assert rows[0].ticker == "KXBTC-TEST"
    assert rows[0].yes_bid == 0.10


def test_signal_stores_raw_payload_json() -> None:
    session = make_session()
    ts = dt.datetime.now(dt.timezone.utc)

    session.add(
        Signal(
            source="polymarket_arb",
            ticker="KXBTC-TEST",
            estimated_probability=0.62,
            raw_payload={"foo": "bar", "nested": [1, 2, 3]},
            ts=ts,
        )
    )
    session.commit()

    row = session.query(Signal).one()
    assert row.raw_payload == {"foo": "bar", "nested": [1, 2, 3]}
