from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.apify_client import ApifyClient


@dataclass
class FakeRun:
    default_dataset_id: str


class FakeDataset:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self._items = items

    def iterate_items(self):
        return iter(self._items)


class FakeActorHandle:
    def __init__(self, run_result: FakeRun | None) -> None:
        self._run_result = run_result
        self.call_args: dict[str, Any] | None = None

    def call(self, run_input: dict[str, Any]) -> FakeRun | None:
        self.call_args = run_input
        return self._run_result


class FakeApifyClient:
    def __init__(self, dataset_items: list[dict[str, Any]]) -> None:
        self._dataset = FakeDataset(dataset_items)
        self.actor_handle = FakeActorHandle(FakeRun(default_dataset_id="ds1"))
        self.requested_actor_id: str | None = None
        self.requested_dataset_id: str | None = None

    def actor(self, actor_id: str) -> FakeActorHandle:
        self.requested_actor_id = actor_id
        return self.actor_handle

    def dataset(self, dataset_id: str) -> FakeDataset:
        self.requested_dataset_id = dataset_id
        return self._dataset


def test_run_actor_returns_dataset_items() -> None:
    fake = FakeApifyClient([{"url": "https://example.com", "text": "hello"}])
    client = ApifyClient(token="test-token", client=fake)  # type: ignore[arg-type]

    items = client.run_actor("apify/website-content-crawler", {"startUrls": [{"url": "https://example.com"}]})

    assert items == [{"url": "https://example.com", "text": "hello"}]
    assert fake.requested_actor_id == "apify/website-content-crawler"
    assert fake.requested_dataset_id == "ds1"
    assert fake.actor_handle.call_args == {"startUrls": [{"url": "https://example.com"}]}


def test_run_actor_returns_empty_list_when_run_is_none() -> None:
    fake = FakeApifyClient([{"should": "not be returned"}])
    fake.actor_handle = FakeActorHandle(None)
    client = ApifyClient(token="test-token", client=fake)  # type: ignore[arg-type]

    items = client.run_actor("apify/website-content-crawler", {})

    assert items == []
