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
    failure must NOT produce a receipt claiming deleted_aggregates worked,
    and status must say so explicitly."""
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
    assert receipt["status"] == "failed"
    assert "db is on fire" in receipt["error"]


@pytest.mark.asyncio
async def test_receipt_not_falsely_completed_via_cache_eviction_alone(
    store: EventStore,
):
    """The actual bug this fix targets: status was `"completed" if
    deleted_aggregates > 0 or cache_evicted else "partial"` -- a successful
    cache eviction alone could mark the whole erasure "completed" even
    though the event-store deletion (the user's actual pipeline data) had
    just failed. Status must reflect the aggregate-deletion outcome, not be
    rescued by an unrelated successful side-effect."""
    from reasoner.application.services.data_eraser import UserDataEraser

    with patch.object(
        store,
        "list_aggregate_ids_for_user",
        new_callable=AsyncMock,
        side_effect=RuntimeError("db is on fire"),
    ):
        eraser = UserDataEraser(event_store=store, clear_cache_fn=lambda: None)
        receipt = await eraser.erase("user-a")

    assert receipt["cache_evicted"] is True  # the side-effect DID succeed
    assert receipt["deleted_aggregates"] == 0
    assert receipt["status"] == "failed"  # must not be "completed"


@pytest.mark.asyncio
async def test_receipt_status_completed_on_genuine_success(store: EventStore):
    """Regression guard for the happy path: real deletions still report
    status="completed" with no error field."""
    from reasoner.application.services.data_eraser import UserDataEraser
    from reasoner.infrastructure.persistence.pipeline_ownership_repo import (
        PipelineOwnershipRepository,
    )

    repo = PipelineOwnershipRepository(db_path=store.db_path)
    await repo.set_owner("p1", "user-a", "p1")

    eraser = UserDataEraser(event_store=store)
    receipt = await eraser.erase("user-a")

    assert receipt["deleted_aggregates"] == 1
    assert receipt["status"] == "completed"
    assert "error" not in receipt
