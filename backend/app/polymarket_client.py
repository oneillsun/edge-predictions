from __future__ import annotations

from typing import Any

import httpx


class PolymarketClient:
    """Read-only wrapper over Polymarket's public Gamma API.

    No account or auth needed — this is public market metadata (questions,
    strikes, current outcome prices), not the order-book/trading API.
    """

    def __init__(self, base_url: str = "https://gamma-api.polymarket.com", timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(timeout=timeout)

    def get_event_by_slug(self, slug: str) -> dict[str, Any] | None:
        response = self._http.get(f"{self._base_url}/events/slug/{slug}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> PolymarketClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
