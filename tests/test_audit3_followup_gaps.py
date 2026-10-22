"""Gaps recorded in docs/plans/audit-remediation-3-2026-10-21.md section 7.

1. ``delete_aggregate`` removed events, aggregates and snapshots but left the
   ``pipeline_owners`` row, so erasing a user kept their user_id on file and
   ``list_aggregate_ids_for_user`` kept returning ids with no data behind them.
2. ``GetHistoryQueryHandler._get_file_history`` globbed a directory that does
   not exist and, if it ever did, would list every user's entries. With no event
   store the handler has nothing to read; it must say so, not guess a path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from reasoner.application.handlers.handlers import GetHistoryQueryHandler
from reasoner.application.queries import GetHistoryQuery
from reasoner.infrastructure.persistence.event_store import EventStore
from reasoner.infrastructure.persistence.pipeline_ownership_repo import (
    PipelineOwnershipRepository,
    reset_pipeline_ownership_repo,
)
from reasoner.infrastructure.persistence.postgres_store import PostgreSQLEventStore


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_pipeline_ownership_repo()
    yield
    reset_pipeline_ownership_repo()


@pytest.mark.asyncio
async def test_sqlite_delete_aggregate_removes_the_ownership_row(tmp_path: Path):
    store = EventStore(tmp_path / "e.db")
    repo = PipelineOwnershipRepository(db_path=store.db_path)
    await repo.set_owner("p1", "user-a", "p1")
    await repo.set_owner("p2", "user-a", "p2")

    await store.delete_aggregate("p1")

    assert await repo.get_owner("p1") is None
    assert await repo.get_owner("p2") is not None, "other pipelines keep their owner"
    assert await store.list_aggregate_ids_for_user("user-a") == ["p2"]


@pytest.mark.asyncio
async def test_postgres_delete_aggregate_removes_the_ownership_row(tmp_path: Path):
    repo = PipelineOwnershipRepository(db_path=tmp_path / "own.db")
    await repo.set_owner("p1", "user-a", "p1")

    class _Conn:
        async def execute(self, *a: object) -> None:
            return None

        def transaction(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

    class _Pool:
        def acquire(self, timeout: float = 0):
            return _Conn()

    store = PostgreSQLEventStore(connection_string="postgresql://unused/unused")

    async def _ready():
        return _Pool()

    with (
        patch.object(store, "_ready", _ready),
        patch(
            "reasoner.infrastructure.persistence.pipeline_ownership_repo.get_pipeline_ownership_repo",
            return_value=repo,
        ),
    ):
        await store.delete_aggregate("p1")

    assert await repo.get_owner("p1") is None


@pytest.mark.asyncio
async def test_history_handler_without_event_store_returns_nothing():
    result = await GetHistoryQueryHandler(None).handle(GetHistoryQuery(query_id="q", timestamp=datetime.now(UTC)))

    assert result == {"total": 0, "entries": []}
