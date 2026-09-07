"""Mock implementations for testing without external dependencies."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock

# MockLLMProvider lived here and subclassed ports.BaseLLMProvider -- the second
# provider base, whose complete(messages, config) -> LLMResponse interface the
# router cannot drive. It had no users anywhere in the suite, so P2
# (docs/plans/root-cause-remediation-2026-09-07.md) deleted it along with that
# base class rather than porting a dummy nobody called. A test that needs a
# provider double should subclass reasoner.infrastructure.llm.base.BaseLLMProvider,
# which is the one ProviderRouter actually calls.


class MockEventStore:
    """In-memory event store for testing."""

    def __init__(self):
        self.events: list[dict[str, Any]] = []
        self.snapshots: dict[str, Any] = {}

    async def append(self, aggregate_id: str, events: list[Any]) -> None:
        for evt in events:
            self.events.append({
                "aggregate_id": aggregate_id,
                "event": evt,
            })

    async def get_events(self, aggregate_id: str) -> list[Any]:
        return [
            e["event"]
            for e in self.events
            if e["aggregate_id"] == aggregate_id
        ]

    async def save_snapshot(self, aggregate_id: str, snapshot: Any) -> None:
        self.snapshots[aggregate_id] = snapshot

    async def get_snapshot(self, aggregate_id: str) -> Any | None:
        return self.snapshots.get(aggregate_id)

    async def list_pipelines(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        return []

    async def delete_aggregate(self, aggregate_id: str) -> None:
        self.events = [
            e for e in self.events
            if e["aggregate_id"] != aggregate_id
        ]
        self.snapshots.pop(aggregate_id, None)


class MockAuthStore:
    """In-memory auth store for testing."""

    def __init__(self):
        self.keys: dict[str, dict[str, Any]] = {}

    async def get(self, key_hash: str) -> dict[str, Any] | None:
        return self.keys.get(key_hash)

    async def set(self, key_hash: str, data: dict[str, Any]) -> None:
        self.keys[key_hash] = data

    async def delete(self, key_hash: str) -> None:
        self.keys.pop(key_hash, None)


def create_mock_redis() -> MagicMock:
    """Create a mock Redis client with async methods."""
    mock = MagicMock()
    mock.get = asyncio.coroutine(lambda k: None)
    mock.set = asyncio.coroutine(lambda k, v, **kw: True)
    mock.delete = asyncio.coroutine(lambda *k: 0)
    mock.exists = asyncio.coroutine(lambda k: 0)
    mock.expire = asyncio.coroutine(lambda k, t: True)
    mock.ttl = asyncio.coroutine(lambda k: -1)
    mock.incr = asyncio.coroutine(lambda k: 1)
    mock.decr = asyncio.coroutine(lambda k: 0)
    mock.flushdb = asyncio.coroutine(lambda: True)
    return mock


class MockNLI:
    """A generic Mock NLI model for VS pipeline testing."""
    def __init__(self, scores: list[float] | float | None = None):
        from unittest.mock import AsyncMock
        if isinstance(scores, (int, float)):
            self.score_entailment = AsyncMock(return_value=float(scores))
        elif isinstance(scores, list):
            self.score_entailment = AsyncMock(side_effect=scores)
        else:
            self.score_entailment = AsyncMock(side_effect=[0.9, 0.5, 0.3, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5])



class MockLLM:
    """A generic Mock LLM for VS pipeline testing."""
    def __init__(self, response: str = ""):
        from unittest.mock import AsyncMock
        self.generate = AsyncMock(return_value=response)
