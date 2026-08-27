from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from app.config import REPO_ROOT, Settings

API_PREFIX = "/trade-api/v2"


def load_private_key(path: Path) -> RSAPrivateKey:
    return serialization.load_pem_private_key(path.read_bytes(), password=None)


def sign_pss_text(private_key: RSAPrivateKey, text: str) -> str:
    signature = private_key.sign(
        text.encode("utf-8"),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(signature).decode("utf-8")


class KalshiClient:
    """Read-only Kalshi API client.

    Only GET endpoints belong here through Milestone 7 — no order
    placement/cancel/amend method may be added before Milestone 8.
    """

    def __init__(
        self,
        key_id: str,
        private_key: RSAPrivateKey,
        base_url: str,
        timeout: float = 10.0,
    ) -> None:
        self._key_id = key_id
        self._private_key = private_key
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(timeout=timeout)

    def _signed_headers(self, method: str, path: str) -> dict[str, str]:
        timestamp_ms = str(int(time.time() * 1000))
        signature = sign_pss_text(self._private_key, f"{timestamp_ms}{method}{path}")
        return {
            "KALSHI-ACCESS-KEY": self._key_id,
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "KALSHI-ACCESS-SIGNATURE": signature,
        }

    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        path = f"{API_PREFIX}{endpoint}"
        headers = self._signed_headers("GET", path)
        response = self._http.get(f"{self._base_url}{path}", params=params, headers=headers)
        response.raise_for_status()
        return response.json()

    def get_markets(
        self,
        *,
        limit: int = 100,
        cursor: str | None = None,
        status: str | None = None,
        series_ticker: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if status:
            params["status"] = status
        if series_ticker:
            params["series_ticker"] = series_ticker
        return self._get("/markets", params=params)

    def get_orderbook(self, ticker: str, *, depth: int | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if depth is not None:
            params["depth"] = depth
        return self._get(f"/markets/{ticker}/orderbook", params=params)

    def get_series(self, series_ticker: str) -> dict[str, Any]:
        return self._get(f"/series/{series_ticker}")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> KalshiClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


def build_client_from_settings(settings: Settings) -> KalshiClient:
    key_path = Path(settings.kalshi_private_key_path)
    if not key_path.is_absolute():
        key_path = REPO_ROOT / key_path
    private_key = load_private_key(key_path)
    return KalshiClient(
        key_id=settings.kalshi_key_id,
        private_key=private_key,
        base_url=settings.kalshi_api_base_url,
    )
