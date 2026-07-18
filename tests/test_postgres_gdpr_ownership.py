"""Tests for PostgreSQLEventStore.list_aggregate_ids_for_user.

This method was previously entirely absent from PostgreSQLEventStore, so
GDPR erasure raised AttributeError on any deployment running
EVENT_STORE_BACKEND=postgres. No live Postgres connection is needed here:
the method doesn't touch self._pool at all -- it delegates to the same
backend-agnostic PipelineOwnershipRepository the SQLite EventStore uses,
since neither backend's own aggregates table tracks ownership.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

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


@pytest.fixture
def ownership_repo(tmp_path: Path):
    repo = PipelineOwnershipRepository(db_path=tmp_path / "pg_gdpr_test.db")
    with patch(
        "reasoner.infrastructure.persistence.pipeline_ownership_repo.get_pipeline_ownership_repo",
        return_value=repo,
    ):
        yield repo


@pytest.mark.asyncio
async def test_list_aggregate_ids_for_user_no_live_connection_needed(ownership_repo):
    """The method must not require self._pool / a live connection."""
    store = PostgreSQLEventStore(connection_string="postgresql://unused/unused")
    await ownership_repo.set_owner("p1", "user-a", "p1")
    await ownership_repo.set_owner("p2", "user-a", "p2")
    await ownership_repo.set_owner("p3", "user-b", "p3")

    ids = await store.list_aggregate_ids_for_user("user-a")
    assert sorted(ids) == ["p1", "p2"]


@pytest.mark.asyncio
async def test_list_aggregate_ids_for_user_no_match_returns_empty(ownership_repo):
    store = PostgreSQLEventStore(connection_string="postgresql://unused/unused")
    assert await store.list_aggregate_ids_for_user("nobody") == []
