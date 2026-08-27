from __future__ import annotations

from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Signal
from app.signals import news_signal


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class FakeApifyClient:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self._items = items
        self.actor_id: str | None = None
        self.run_input: dict[str, Any] | None = None

    def run_actor(self, actor_id: str, run_input: dict[str, Any]) -> list[dict[str, Any]]:
        self.actor_id = actor_id
        self.run_input = run_input
        return self._items


def test_score_sentiment_neutral_with_no_keywords() -> None:
    assert news_signal.score_sentiment("Ethereum traded sideways today.") == 0.5


def test_score_sentiment_positive_bias() -> None:
    score = news_signal.score_sentiment("Ethereum saw a huge rally and surge today, bullish breakout.")
    assert score > 0.5


def test_score_sentiment_negative_bias() -> None:
    score = news_signal.score_sentiment("Ethereum saw a crash and plunge today amid a bearish sell-off.")
    assert score < 0.5


def test_run_stores_one_signal_per_page_with_text() -> None:
    fake_apify = FakeApifyClient(
        [
            {"url": "https://a.example", "text": "ETH rallied and surged.", "metadata": {"title": "A"}},
            {"url": "https://b.example", "text": "", "metadata": {"title": "B"}},
            {"url": "https://c.example", "text": "ETH crashed and plunged.", "metadata": {"title": "C"}},
        ]
    )
    session = make_session()

    stored = news_signal.run(fake_apify, session, "apify/website-content-crawler", sources=["https://a.example"])  # type: ignore[arg-type]

    assert stored == 2  # the empty-text item is skipped
    assert fake_apify.actor_id == "apify/website-content-crawler"
    assert fake_apify.run_input == {
        "startUrls": [{"url": "https://a.example"}],
        "maxCrawlPages": 1,
        "crawlerType": "cheerio",
    }

    rows = session.query(Signal).order_by(Signal.id).all()
    assert [r.source for r in rows] == ["news_eth", "news_eth"]
    assert rows[0].ticker == "KXETH"
    assert rows[0].estimated_probability > 0.5
    assert rows[1].estimated_probability < 0.5
