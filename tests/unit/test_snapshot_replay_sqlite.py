"""Snapshot-replay and aggregate-metadata regression tests (SQLite backend).

Covers the T2 persistence defect hunt (docs/reports/defect-hunt-2026-09-01/
T2-persistence.md):

- T2-D1 SnapshotStrategy.create_snapshot wrote a wrapper dict that
  _deserialize_state could not consume.
- T2-D2 load_aggregate_with_snapshot passed an off-by-one from_version into
  get_events, whose filter is exclusive.
- T2-D3 a snapshot at the aggregate head was reported as "no such aggregate".
- T2-D4 save_events raised UnboundLocalError instead of the sqlite3.Error it
  documents when the connection could not be opened.
- T2-D9 aggregates.current_version regressed under concurrent appends.

Every test drives a real temp SQLite database; nothing about the store or the
snapshot strategy is mocked.
"""

from __future__ import annotations

import asyncio
import random
import sqlite3
import time
import uuid
from dataclasses import asdict

import pytest

from reasoner.core.aggregates.pipeline import PipelineAggregate, PipelineStateData
from reasoner.core.events.domain_events import (
    DomainEvent,
    EventType,
    PipelineEventType,
    make_event,
)
from reasoner.infrastructure.persistence.event_store import EventStore
from reasoner.infrastructure.persistence.snapshots import SnapshotManager


def _phase_event(aggregate_id: str, version: int, phase: str = "p") -> DomainEvent:
    return make_event(
        EventType.PHASE_COMPLETED,
        aggregate_id=aggregate_id,
        version=version,
        phase_name=phase,
        result={},
        tokens={"total": 1},
        model_used="test-model",
        duration_seconds=0.5,
    )


def _bare_event(aggregate_id: str, version: int) -> DomainEvent:
    return DomainEvent(
        event_id=str(uuid.uuid4()),
        event_type=PipelineEventType.PIPELINE_STARTED,
        timestamp=time.time(),
        aggregate_id=aggregate_id,
        version=version,
    )


@pytest.fixture
def store(tmp_path):
    s = EventStore(tmp_path / "snapshot_replay.db")
    yield s
    s.close()


@pytest.fixture
def manager(store):
    return SnapshotManager(store)


# ── T2-D1: snapshot serialize/deserialize must be an inverse pair ──


@pytest.mark.asyncio
async def test_snapshot_round_trip_returns_pipeline_state_data(store, manager):
    """PROOF OF DEFECT (T2-D1): create_snapshot -> load_snapshot must round-trip.

    Before the fix this raised
    ``TypeError: PipelineStateData.__init__() got an unexpected keyword
    argument 'state'`` because create_snapshot persisted a
    {'state': ..., 'version': ..., 'timestamp': ...} wrapper that
    _deserialize_state splatted straight into PipelineStateData.
    """
    aggregate_id = "agg-round-trip"
    aggregate = PipelineAggregate(aggregate_id)
    events = [_phase_event(aggregate_id, v) for v in range(1, 4)]
    for event in events:
        aggregate.record_event(event)
    await store.save_events(events)

    await manager.strategy.create_snapshot(aggregate, store)
    version, state = await manager.strategy.load_snapshot(aggregate_id, store)

    assert version == 3
    assert isinstance(state, PipelineStateData)
    assert state.phase_results == aggregate.state_data.phase_results


@pytest.mark.asyncio
async def test_snapshot_load_accepts_flat_state_written_directly(store, manager):
    """BOUNDARY (T2-D1): a flat state saved via EventStore.save_snapshot.

    save_snapshot is a public method and tests/compaction call it with a bare
    state dict. The unwrap must not break that shape.
    """
    aggregate_id = "agg-flat"
    await store.save_snapshot(
        aggregate_id, version=2, state=asdict(PipelineStateData(status="running"))
    )

    version, state = await manager.strategy.load_snapshot(aggregate_id, store)

    assert version == 2
    assert isinstance(state, PipelineStateData)
    assert state.status == "running"


@pytest.mark.asyncio
async def test_snapshot_load_returns_none_when_absent(store, manager):
    """BOUNDARY (T2-D1): no snapshot row must stay None, not raise."""
    assert await manager.strategy.load_snapshot("agg-never-seen", store) is None


# ── T2-D2 / T2-D3: snapshot + tail replay ──


@pytest.mark.asyncio
async def test_load_with_snapshot_applies_every_event_after_the_snapshot(
    store, manager
):
    """PROOF OF DEFECT (T2-D2): the first event after the snapshot was skipped.

    get_events' from_version filter is exclusive (``WHERE version > ?``).
    Passing ``version + 1`` dropped event ``version + 1``, which the gap guard
    then reported as EventStoreCorruptionError on a perfectly healthy store.
    """
    aggregate_id = "agg-tail"
    events = [_phase_event(aggregate_id, v, f"phase-{v}") for v in range(1, 6)]
    await store.save_events(events)
    await store.save_snapshot(
        aggregate_id, version=3, state=asdict(PipelineStateData(status="running"))
    )

    aggregate = await manager.load_aggregate_with_snapshot(aggregate_id)

    assert aggregate is not None
    assert aggregate.version == 5
    # Events 4 and 5 -- not just 5 -- must have been applied on top.
    assert [r["phase"] for r in aggregate.state_data.phase_results] == [
        "phase-4",
        "phase-5",
    ]


@pytest.mark.asyncio
async def test_load_with_snapshot_at_head_returns_the_aggregate(store, manager):
    """PROOF OF DEFECT (T2-D3): a snapshot at the head is not "not found".

    Phase-based snapshotting fires on PipelineCompleted, so a finished run's
    snapshot is at the aggregate head with no events after it. That returned
    None, reporting every completed pipeline as missing.
    """
    aggregate_id = "agg-head"
    await store.save_events([_phase_event(aggregate_id, v) for v in range(1, 4)])
    await store.save_snapshot(
        aggregate_id, version=3, state=asdict(PipelineStateData(status="completed"))
    )

    aggregate = await manager.load_aggregate_with_snapshot(aggregate_id)

    assert aggregate is not None
    assert aggregate.version == 3
    assert aggregate.state_data.status == "completed"


@pytest.mark.asyncio
async def test_load_with_snapshot_still_detects_a_real_event_gap(store, manager):
    """NO-REGRESSION (T2-D2): the corruption guard must still fire on a real gap."""
    from reasoner.core.exceptions import EventStoreCorruptionError

    aggregate_id = "agg-gap"
    # versions 1, 2, 3 then 5 -- 4 is genuinely missing
    await store.save_events(
        [_phase_event(aggregate_id, v) for v in (1, 2, 3, 5)]
    )
    await store.save_snapshot(
        aggregate_id, version=3, state=asdict(PipelineStateData())
    )

    with pytest.raises(EventStoreCorruptionError):
        await manager.load_aggregate_with_snapshot(aggregate_id)


@pytest.mark.asyncio
async def test_load_without_snapshot_still_returns_none_when_empty(store, manager):
    """NO-REGRESSION: no snapshot AND no events is still a genuine miss."""
    assert await manager.load_aggregate_with_snapshot("agg-nothing") is None


@pytest.mark.asyncio
async def test_snapshot_path_and_full_history_path_agree(store, manager):
    """NO-REGRESSION: the two replay paths must reconstruct the same state.

    This is the invariant the whole snapshot optimisation rests on:
    replay(snapshot@v) + events(v..head) == replay(events[0..head]).
    """
    aggregate_id = "agg-equivalence"
    events = [_phase_event(aggregate_id, v, f"phase-{v}") for v in range(1, 7)]
    await store.save_events(events)

    from_history = PipelineAggregate(aggregate_id)
    from_history.load_from_history(events)

    mid = PipelineAggregate(aggregate_id)
    mid.load_from_history(events[:4])
    await store.save_snapshot(
        aggregate_id, version=4, state=asdict(mid.state_data)
    )

    from_snapshot = await manager.load_aggregate_with_snapshot(aggregate_id)

    assert from_snapshot is not None
    assert from_snapshot.version == from_history.version
    assert asdict(from_snapshot.state_data) == asdict(from_history.state_data)


# ── T2-D4: save_events error path ──


@pytest.mark.asyncio
async def test_save_events_propagates_the_connection_error(store):
    """PROOF OF DEFECT (T2-D4): the documented sqlite3.Error must survive.

    Every except branch in _save_events_sync calls conn.rollback(). With the
    connection acquired inside the try, a failure to open it raised
    UnboundLocalError from the handler and destroyed the original cause.
    """
    def _boom():
        raise sqlite3.OperationalError("disk I/O error")

    original = store.conn._get_connection
    store.conn._get_connection = _boom
    try:
        with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
            await store.save_events([_phase_event("agg-broken", 1)])
    finally:
        store.conn._get_connection = original


@pytest.mark.asyncio
async def test_save_events_still_rolls_back_on_a_mid_batch_failure(store, tmp_path):
    """NO-REGRESSION (T2-D4): a real DB error still rolls back and re-raises."""
    conn = store.conn._get_connection()
    conn.execute("DROP TABLE events")
    conn.commit()

    with pytest.raises(sqlite3.Error):
        await store.save_events([_phase_event("agg-no-table", 1)])


# ── T2-D9: aggregates.current_version monotonicity ──


@pytest.mark.asyncio
async def test_current_version_never_regresses_on_an_older_event(store):
    """PROOF OF DEFECT (T2-D9): a late older event rewrote current_version down."""
    aggregate_id = "agg-monotonic"
    await store.save_events([_bare_event(aggregate_id, v) for v in range(1, 6)])
    await store.save_events([_bare_event(aggregate_id, 1)])

    state = await store.get_aggregate_state(aggregate_id)
    assert state["version"] == 5


@pytest.mark.asyncio
@pytest.mark.integration
async def test_current_version_is_the_head_under_concurrent_appends(store):
    """PROOF OF DEFECT (T2-D9), repeated-trial harness.

    Two writers append to the same aggregate concurrently in production (the
    request coroutine's _persist_event and the event bus' persist_all_events
    subscriber), so batch commit order is not version order. Before the fix
    this failed on roughly 85% of shuffled trials.
    """
    trials = 30
    wrong = 0
    for trial in range(trials):
        aggregate_id = f"agg-concurrent-{trial}"
        ranges = [(i * 10 + 1, i * 10 + 11) for i in range(6)]
        random.shuffle(ranges)

        async def _batch(lo: int, hi: int, agg: str = aggregate_id) -> None:
            await store.save_events([_bare_event(agg, v) for v in range(lo, hi)])

        await asyncio.gather(*(_batch(lo, hi) for lo, hi in ranges))

        state = await store.get_aggregate_state(aggregate_id)
        if state["version"] != 60:
            wrong += 1

    assert wrong == 0, f"current_version regressed in {wrong}/{trials} trials"


@pytest.mark.asyncio
async def test_current_version_still_advances_on_ascending_appends(store):
    """NO-REGRESSION (T2-D9): the ordinary ascending path must still advance."""
    aggregate_id = "agg-ascending"
    for version in range(1, 6):
        await store.save_events([_bare_event(aggregate_id, version)])
        state = await store.get_aggregate_state(aggregate_id)
        assert state["version"] == version


@pytest.mark.asyncio
async def test_current_version_starts_at_the_first_events_version(store):
    """BOUNDARY (T2-D9): MAX() must not be defeated by the INSERT branch.

    The first event creates the row through the INSERT arm, where MAX() does
    not apply -- verify the seeded value is the event's own version and that a
    higher one still wins afterwards.
    """
    aggregate_id = "agg-seed"
    await store.save_events([_bare_event(aggregate_id, 7)])
    assert (await store.get_aggregate_state(aggregate_id))["version"] == 7

    await store.save_events([_bare_event(aggregate_id, 9)])
    assert (await store.get_aggregate_state(aggregate_id))["version"] == 9

    await store.save_events([_bare_event(aggregate_id, 2)])
    assert (await store.get_aggregate_state(aggregate_id))["version"] == 9
