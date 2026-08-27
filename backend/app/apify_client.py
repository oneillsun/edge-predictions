from __future__ import annotations

from typing import Any

from apify_client import ApifyClient as _ApifyClient


class ApifyClient:
    """Thin wrapper over apify-client: run an actor, wait, return dataset items."""

    def __init__(self, token: str, client: _ApifyClient | None = None) -> None:
        self._client = client or _ApifyClient(token)

    def run_actor(self, actor_id: str, run_input: dict[str, Any]) -> list[dict[str, Any]]:
        run = self._client.actor(actor_id).call(run_input=run_input)
        if run is None:
            return []
        return list(self._client.dataset(run.default_dataset_id).iterate_items())
