from __future__ import annotations

import pytest

from app.config import settings
from app.kalshi_client import build_client_from_settings

pytestmark = pytest.mark.skipif(
    not settings.kalshi_live_test_enabled,
    reason="Live Kalshi smoke test disabled (set KALSHI_LIVE_TEST_ENABLED=true in .env to run)",
)


def test_get_markets_against_live_account() -> None:
    """Read-only smoke test against the real Kalshi account. GET only — no order is ever sent."""
    client = build_client_from_settings(settings)
    try:
        result = client.get_markets(limit=5)
    finally:
        client.close()

    assert "markets" in result
    assert isinstance(result["markets"], list)
