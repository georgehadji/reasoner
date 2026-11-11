"""Audit 6 finding 6: the pipeline list is filtered by owner in the query.

60 pipelines, user B owns three of the oldest. The old route paged the global
list and filtered each row afterwards, so B's first page came back empty.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from reasoner.api.routes import pipelines as pipelines_route
from reasoner.application.handlers.handlers import GetHistoryQueryHandler
from reasoner.application.queries import GetHistoryQuery
from reasoner.domain.saas import User
from reasoner.infrastructure.persistence import pipeline_ownership_repo
from reasoner.infrastructure.persistence.event_store import EventStore
from reasoner.infrastructure.persistence.pipeline_ownership_repo import (
    PipelineOwnershipRepository,
)

pytestmark = pytest.mark.unit

TOTAL = 60
B_PIPELINES = ["p-10", "p-20", "p-30"]  # old, so deep in a newest-first list


@pytest.fixture
async def world(tmp_path: Path, monkeypatch):
    store = EventStore(tmp_path / "e.db")
    conn = store._get_connection()
    for i in range(TOTAL):
        conn.execute(
            "INSERT INTO aggregates (aggregate_id, aggregate_type, status, problem, created_at) "
            "VALUES (?, 'pipeline', ?, ?, ?)",
            (f"p-{i:02d}", "completed" if i % 2 == 0 else "failed", f"problem {i}",
             f"2026-01-01 00:00:{i:02d}"),
        )
    conn.commit()
    owners = PipelineOwnershipRepository(db_path=store.db_path)
    user_a, user_b = str(uuid4()), str(uuid4())
    for i in range(TOTAL):
        pid = f"p-{i:02d}"
        await owners.set_owner(pid, user_b if pid in B_PIPELINES else user_a, pid)

    monkeypatch.setattr("reasoner.api.get_architecture_components", lambda: (store, None))
    monkeypatch.setattr(pipeline_ownership_repo, "get_pipeline_ownership_repo", lambda: owners)
    monkeypatch.setattr(
        pipeline_ownership_repo, "ensure_pipeline_ownership_backfilled", AsyncMock()
    )
    return SimpleWorld(store, owners, user_a, user_b)


class SimpleWorld:
    def __init__(self, store, owners, user_a, user_b):
        self.store, self.owners, self.user_a, self.user_b = store, owners, user_a, user_b


def _user(user_id: str, scopes: set[str] | None = None) -> User:
    from uuid import UUID

    return User(id=UUID(user_id), email="u@example.com", scopes=scopes or set())


@pytest.mark.asyncio
async def test_store_filters_by_ids_and_counts(world):
    store = world.store
    rows = await store.list_pipelines(limit=50, aggregate_ids=B_PIPELINES)
    assert sorted(r["aggregate_id"] for r in rows) == B_PIPELINES
    assert await store.count_pipelines(aggregate_ids=B_PIPELINES) == 3
    assert await store.list_pipelines(limit=2, offset=2, aggregate_ids=B_PIPELINES) != []
    assert len(await store.list_pipelines(limit=2, offset=2, aggregate_ids=B_PIPELINES)) == 1
    # status filter composes with the id filter: p-10, p-20, p-30 are all even -> completed
    assert await store.count_pipelines(status="failed", aggregate_ids=B_PIPELINES) == 0
    assert await store.count_pipelines(status="completed", aggregate_ids=B_PIPELINES) == 3


@pytest.mark.asyncio
async def test_empty_ids_match_nothing_and_none_means_all(world):
    assert await world.store.list_pipelines(aggregate_ids=[]) == []
    assert await world.store.count_pipelines(aggregate_ids=[]) == 0
    assert await world.store.count_pipelines() == TOTAL


@pytest.mark.asyncio
async def test_route_returns_the_owners_pipelines_on_the_first_page(world):
    result = await pipelines_route.list_pipelines(
        user=_user(world.user_b), limit=50, offset=0, status=None
    )
    assert sorted(p["aggregate_id"] for p in result["pipelines"]) == B_PIPELINES
    assert result["total"] == 3


@pytest.mark.asyncio
async def test_route_for_a_user_with_none_is_empty(world):
    result = await pipelines_route.list_pipelines(
        user=_user(str(uuid4())), limit=50, offset=0, status=None
    )
    assert result == {"pipelines": [], "total": 0}


@pytest.mark.asyncio
async def test_route_for_admin_sees_everything_with_a_real_total(world):
    result = await pipelines_route.list_pipelines(
        user=_user(str(uuid4()), {"admin"}), limit=50, offset=0, status=None
    )
    assert len(result["pipelines"]) == 50
    assert result["total"] == TOTAL


@pytest.mark.asyncio
async def test_route_fails_closed_when_ownership_lookup_fails(world, monkeypatch):
    broken = AsyncMock()
    broken.list_pipeline_ids_for_user.side_effect = RuntimeError("db down")
    monkeypatch.setattr(pipeline_ownership_repo, "get_pipeline_ownership_repo", lambda: broken)
    result = await pipelines_route.list_pipelines(
        user=_user(world.user_b), limit=50, offset=0, status=None
    )
    assert result == {"pipelines": [], "total": 0}


@pytest.mark.asyncio
async def test_history_handler_needs_an_owner_scope(world):
    handler = GetHistoryQueryHandler(world.store)
    base = {"query_id": "q", "timestamp": datetime.now(UTC)}
    unscoped = await handler.handle(GetHistoryQuery(**base))
    assert unscoped == {"total": 0, "entries": []}
    scoped = await handler.handle(GetHistoryQuery(**base, owner_ids=tuple(B_PIPELINES)))
    assert sorted(e["id"] for e in scoped["entries"]) == B_PIPELINES
