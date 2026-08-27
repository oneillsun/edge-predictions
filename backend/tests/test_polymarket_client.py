from __future__ import annotations

from typing import Any

from app.polymarket_client import PolymarketClient


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        assert self._payload is not None
        return self._payload


class FakeHttpClient:
    def __init__(self, response: FakeResponse) -> None:
        self._response = response
        self.requested_url: str | None = None

    def get(self, url: str) -> FakeResponse:
        self.requested_url = url
        return self._response


def make_client(response: FakeResponse) -> tuple[PolymarketClient, FakeHttpClient]:
    client = PolymarketClient(base_url="https://gamma-api.polymarket.com")
    fake_http = FakeHttpClient(response)
    client._http = fake_http  # type: ignore[assignment]
    return client, fake_http


def test_get_event_by_slug_builds_url_and_returns_json() -> None:
    payload = {"slug": "ethereum-above-on-august-27-2026", "markets": []}
    client, fake_http = make_client(FakeResponse(200, payload))

    result = client.get_event_by_slug("ethereum-above-on-august-27-2026")

    assert result == payload
    assert fake_http.requested_url == "https://gamma-api.polymarket.com/events/slug/ethereum-above-on-august-27-2026"


def test_get_event_by_slug_returns_none_on_404() -> None:
    client, _ = make_client(FakeResponse(404))

    result = client.get_event_by_slug("no-such-event")

    assert result is None
