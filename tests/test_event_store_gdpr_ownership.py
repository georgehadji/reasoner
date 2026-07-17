"""Tests for EventStore.list_aggregate_ids_for_user (GDPR erasure support).

Pins the fix for the silent-no-op bug: the old JSON-file-scanning version
returned [] on ANY error (missing file, corrupt JSON), and data_eraser.py's
receipt logic then reported erasure as having "succeeded" while deleting
nothing. The new version delegates to PipelineOwnershipRepository, scoped to
this EventStore's own db_path, and propagates genuine failures instead of
swallowing them to [].
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from reasoner.infrastructure.persistence.event_store import EventStore


@pytest.fixture
def store(tmp_path: Path) -> EventStore:
    return EventStore(tmp_path / "gdpr_test.db")


@pytest.mark.asyncio
async def test_returns_pipeline_ids_owned_by_user(store: EventStore):
    from reasoner.infrastructure.persistence.pipeline_ownership_repo import (
        PipelineOwnershipRepository,
    )

    repo = PipelineOwnershipRepository(db_path=store.db_path)
    await repo.set_owner("p1", "user-a", "p1")
    await repo.set_owner("p2", "user-a", "p2")
    await repo.set_owner("p3", "user-b", "p3")

    ids = await store.list_aggregate_ids_for_user("user-a")
    assert sorted(ids) == ["p1", "p2"]


@pytest.mark.asyncio
async def test_returns_empty_list_for_user_with_no_pipelines(store: EventStore):
    """A genuine 'found nothing' result is still []."""
    assert await store.list_aggregate_ids_for_user("nobody") == []


@pytest.mark.asyncio
async def test_lookup_failure_propagates_instead_of_returning_empty_list(
    store: EventStore,
):
    """The bug this replaces: list_pipeline_ids_for_user raising used to be
    swallowed into [], which data_eraser.py's caller could not distinguish
    from "this user genuinely owns nothing" -- erasure reported success
    while deleting nothing. It must now propagate."""
    with patch(
        "reasoner.infrastructure.persistence.pipeline_ownership_repo."
        "PipelineOwnershipRepository.list_pipeline_ids_for_user",
        new_callable=AsyncMock,
        side_effect=RuntimeError("db is on fire"),
    ):
        with pytest.raises(RuntimeError, match="db is on fire"):
            await store.list_aggregate_ids_for_user("user-a")


@pytest.mark.asyncio
async def test_data_eraser_logs_failure_instead_of_reporting_success(
    store: EventStore,
):
    """Integration check against the actual GDPR erasure caller: a lookup
    failure must NOT produce a receipt claiming deleted_aggregates worked."""
    from reasoner.application.services.data_eraser import UserDataEraser

    with patch.object(
        store,
        "list_aggregate_ids_for_user",
        new_callable=AsyncMock,
        side_effect=RuntimeError("db is on fire"),
    ):
        eraser = UserDataEraser(event_store=store)
        receipt = await eraser.erase("user-a")

    # deleted_aggregates must be 0, not silently reported as if the (empty)
    # list from a swallowed error meant "nothing to delete".
    assert receipt["deleted_aggregates"] == 0
