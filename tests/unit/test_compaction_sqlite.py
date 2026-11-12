"""Unit tests for EventStore.prune_events_before (SQLite)."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from reasoner.core.events.domain_events import DomainEvent, PipelineEventType
from reasoner.infrastructure.persistence.event_store import EventStore


def _make_event(aggregate_id: str, version: int) -> DomainEvent:
    return DomainEvent(
        event_id=str(uuid.uuid4()),
        event_type=PipelineEventType.PIPELINE_STARTED,
        timestamp=time.time(),
        aggregate_id=aggregate_id,
        version=version,
    )


@pytest.fixture
def store(tmp_path):
    return EventStore(tmp_path / "test_events.db")


@pytest.mark.asyncio
async def test_prune_does_not_delete_without_snapshot(store):
    """Events with no covering snapshot must never be pruned."""
    await store.save_events([_make_event("agg-1", i) for i in range(3)])
    deleted = await store.prune_events_before(
        cutoff=datetime.now(tz=UTC) + timedelta(days=1)
    )
    assert deleted == 0


@pytest.mark.asyncio
async def test_prune_deletes_events_covered_by_snapshot(store):
    """Events at version <= snapshot version must be pruned."""
    events = [_make_event("agg-2", i) for i in range(5)]
    await store.save_events(events)
    await store.save_snapshot("agg-2", version=3, state={"dummy": True})

    deleted = await store.prune_events_before(
        cutoff=datetime.now(tz=UTC) + timedelta(days=1)
    )
    # versions 0, 1, 2, 3 are covered by snapshot at v3
    assert deleted == 4

    remaining = await store.get_events("agg-2")
    assert [e.version for e in remaining] == [4]


@pytest.mark.asyncio
async def test_prune_respects_cutoff_date(store):
    """Events newer than cutoff must not be pruned even when covered by snapshot."""
    await store.save_events([_make_event("agg-3", 0)])
    await store.save_snapshot("agg-3", version=0, state={})

    deleted = await store.prune_events_before(
        cutoff=datetime.now(tz=UTC) - timedelta(days=1)
    )
    assert deleted == 0


@pytest.mark.asyncio
async def test_prune_batch_size_limits_single_pass(store):
    """Each prune_events_before call deletes at most batch_size rows."""
    await store.save_events([_make_event("agg-4", i) for i in range(10)])
    await store.save_snapshot("agg-4", version=9, state={})

    deleted_first = await store.prune_events_before(
        cutoff=datetime.now(tz=UTC) + timedelta(days=1),
        batch_size=3,
    )
    assert deleted_first == 3

    remaining = await store.get_events("agg-4")
    assert len(remaining) == 7


@pytest.mark.asyncio
async def test_count_eligible_events(store):
    await store.save_events([_make_event("agg-5", i) for i in range(4)])
    await store.save_snapshot("agg-5", version=2, state={})

    count = await store.count_eligible_events(
        datetime.now(tz=UTC) + timedelta(days=1)
    )
    assert count == 3  # versions 0, 1, 2


@pytest.mark.asyncio
async def test_prune_multiple_aggregates_independent(store):
    """Pruning one aggregate must not affect another."""
    await store.save_events([_make_event("agg-A", i) for i in range(3)])
    await store.save_snapshot("agg-A", version=2, state={})

    await store.save_events([_make_event("agg-B", i) for i in range(3)])
    # agg-B has no snapshot

    await store.prune_events_before(
        cutoff=datetime.now(tz=UTC) + timedelta(days=1)
    )

    # from_version=-1 → version > -1 → all versions including 0
    remaining_b = await store.get_events("agg-B", from_version=-1)
    assert len(remaining_b) == 3  # untouched


# ── Version-0 audit rows (audit-5 decision Q6) ─────────────────────────────
# prune_events_before above still deletes only snapshot-covered rows; the
# version-0 audit rows the bus persists for every event are pruned here.

_FUTURE = timedelta(days=1)


@pytest.mark.asyncio
async def test_audit_rows_pruned_without_snapshot(store):
    await store.save_events([_make_event(f"audit-{i}", 0) for i in range(3)])

    deleted = await store.prune_audit_events_before(cutoff=datetime.now(tz=UTC) + _FUTURE)

    assert deleted == 3
    assert await store.count_eligible_audit_events(datetime.now(tz=UTC) + _FUTURE) == 0


@pytest.mark.asyncio
async def test_audit_prune_respects_batch_size_and_cutoff(store):
    await store.save_events([_make_event(f"audit-b{i}", 0) for i in range(5)])

    assert await store.prune_audit_events_before(
        cutoff=datetime.now(tz=UTC) - _FUTURE
    ) == 0
    assert await store.prune_audit_events_before(
        cutoff=datetime.now(tz=UTC) + _FUTURE, batch_size=2
    ) == 2


@pytest.mark.asyncio
async def test_versioned_rows_kept_and_replay_unaffected(store):
    await store.save_events([_make_event("run-1", i) for i in range(4)])

    await store.prune_audit_events_before(cutoff=datetime.now(tz=UTC) + _FUTURE)

    assert [e.version for e in await store.get_events("run-1")] == [1, 2, 3]
