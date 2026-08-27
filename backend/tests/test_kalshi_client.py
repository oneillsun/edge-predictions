from __future__ import annotations

from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.kalshi_client import KalshiClient, sign_pss_text


@pytest.fixture()
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeHttpClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> FakeResponse:
        self.calls.append({"url": url, "params": params, "headers": headers})
        return FakeResponse(self.payload)


def make_client(private_key: rsa.RSAPrivateKey, payload: dict[str, Any]) -> tuple[KalshiClient, FakeHttpClient]:
    client = KalshiClient(
        key_id="test-key", private_key=private_key, base_url="https://external-api.kalshi.com"
    )
    fake_http = FakeHttpClient(payload)
    client._http = fake_http  # type: ignore[assignment]
    return client, fake_http


def test_sign_pss_text_produces_base64_signature(private_key: rsa.RSAPrivateKey) -> None:
    signature = sign_pss_text(private_key, "1700000000000GET/trade-api/v2/markets")
    assert isinstance(signature, str)
    assert len(signature) > 0


def test_get_markets_signs_request_and_returns_payload(private_key: rsa.RSAPrivateKey) -> None:
    client, fake_http = make_client(private_key, {"markets": [], "cursor": ""})

    result = client.get_markets(limit=10)

    assert result == {"markets": [], "cursor": ""}
    assert len(fake_http.calls) == 1
    call = fake_http.calls[0]
    assert call["url"] == "https://external-api.kalshi.com/trade-api/v2/markets"
    assert call["params"] == {"limit": 10}
    headers = call["headers"]
    assert headers["KALSHI-ACCESS-KEY"] == "test-key"
    assert "KALSHI-ACCESS-TIMESTAMP" in headers
    assert "KALSHI-ACCESS-SIGNATURE" in headers


def test_get_orderbook_builds_ticker_path(private_key: rsa.RSAPrivateKey) -> None:
    client, fake_http = make_client(private_key, {"orderbook": {}})

    client.get_orderbook("INXD-24DEC31-B5000", depth=10)

    call = fake_http.calls[0]
    assert call["url"] == "https://external-api.kalshi.com/trade-api/v2/markets/INXD-24DEC31-B5000/orderbook"
    assert call["params"] == {"depth": 10}


def test_get_market_builds_ticker_path(private_key: rsa.RSAPrivateKey) -> None:
    client, fake_http = make_client(private_key, {"market": {"status": "finalized", "result": "yes"}})

    result = client.get_market("KXETH-26AUG2717-T3209.99")

    assert result == {"market": {"status": "finalized", "result": "yes"}}
    call = fake_http.calls[0]
    assert call["url"] == "https://external-api.kalshi.com/trade-api/v2/markets/KXETH-26AUG2717-T3209.99"


def test_get_series_builds_series_path(private_key: rsa.RSAPrivateKey) -> None:
    client, fake_http = make_client(private_key, {"series": {"fee_multiplier": 1, "fee_type": "quadratic"}})

    result = client.get_series("KXETH")

    assert result == {"series": {"fee_multiplier": 1, "fee_type": "quadratic"}}
    call = fake_http.calls[0]
    assert call["url"] == "https://external-api.kalshi.com/trade-api/v2/series/KXETH"


def test_no_order_placement_methods_exist() -> None:
    """Hard safety boundary: no order-placement method may exist before Milestone 8."""
    forbidden = {
        "place_order",
        "create_order",
        "post_order",
        "cancel_order",
        "amend_order",
        "submit_order",
    }
    client_methods = {name for name in dir(KalshiClient) if not name.startswith("_")}
    assert not (client_methods & forbidden)
