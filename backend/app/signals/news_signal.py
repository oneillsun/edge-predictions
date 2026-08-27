from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.apify_client import ApifyClient
from app.db.models import Signal

SOURCE = "news_eth"
KALSHI_SERIES_TICKER = "KXETH"  # category-level signal, not tied to one strike

NEWS_SOURCES = [
    "https://www.coindesk.com/price/ethereum/",
    "https://cointelegraph.com/tags/ethereum",
    "https://decrypt.co/price/ethereum",
]

_POSITIVE_KEYWORDS = [
    "surge",
    "rally",
    "bullish",
    "soar",
    "gain",
    "record high",
    "breakout",
    "rebound",
    "jump",
    "climb",
]
_NEGATIVE_KEYWORDS = [
    "crash",
    "plunge",
    "bearish",
    "sell-off",
    "selloff",
    "drop",
    "decline",
    "slump",
    "tumble",
    "fear",
]


def score_sentiment(text: str) -> float:
    """Naive keyword-count heuristic in [0, 1]; 0.5 means neutral/no signal.

    Deliberate first-pass simplification: PLAN.md allows an LLM call here,
    but that needs its own API key/credential. This heuristic needs none.
    Swap it for a real LLM call once that's wired up.
    """
    lowered = text.lower()
    positive = sum(lowered.count(word) for word in _POSITIVE_KEYWORDS)
    negative = sum(lowered.count(word) for word in _NEGATIVE_KEYWORDS)
    total = positive + negative
    if total == 0:
        return 0.5
    return positive / total


def run(
    apify_client: ApifyClient,
    session: Session,
    actor_id: str,
    sources: list[str] | None = None,
) -> int:
    """Scrape ETH news/price pages, score sentiment, store one Signal row per page.

    Returns the number of Signal rows stored.
    """
    urls = sources if sources is not None else NEWS_SOURCES
    run_input = {
        "startUrls": [{"url": url} for url in urls],
        "maxCrawlPages": len(urls),
        "crawlerType": "cheerio",
    }
    items = apify_client.run_actor(actor_id, run_input)

    now = dt.datetime.now(dt.timezone.utc)
    stored = 0
    for item in items:
        text = item.get("text") or ""
        if not text:
            continue

        probability = score_sentiment(text)
        session.add(
            Signal(
                source=SOURCE,
                ticker=KALSHI_SERIES_TICKER,
                estimated_probability=probability,
                raw_payload={
                    "url": item.get("url"),
                    "title": (item.get("metadata") or {}).get("title"),
                    "text_excerpt": text[:1000],
                    "note": (
                        "estimated_probability is a naive keyword-sentiment "
                        "heuristic, not a calibrated probability. ticker is "
                        "the series (category-level), not a specific strike."
                    ),
                },
                ts=now,
            )
        )
        stored += 1

    session.commit()
    return stored
