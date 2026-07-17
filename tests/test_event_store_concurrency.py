"""
Tests for EventStore concurrency safety.

Verifies that threading.Lock + ThreadPoolExecutor correctly serialize
SQLite writes under concurrent async tasks.
"""

import asyncio

import pytest

from reasoner.core.events.domain_events import EventType, make_event
from reasoner.infrastructure.persistence.event_store import EventStore


@pytest.fixture
def temp_event_store(tmp_path):
    """An EventStore on an isolated temp SQLite file, closed after the test.

    Was referenced by every test in this class but never defined anywhere
    in the repo -- those tests errored on collection regardless of any
    other change (pre-existing, unrelated to the connection/close() fixes
    in this file's git history).
    """
    store = EventStore(db_path=tmp_path / "concurrency_test.db")
    yield store
    store.close()


class TestEventStoreConcurrency:
    """Integration tests for EventStore thread safety."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_event_appends_no_corruption(self, temp_event_store):
        store = temp_event_store
        aggregate_id = "agg-concurrent"
        num_tasks = 10
        events_per_task = 100

        async def append_batch(task_idx: int):
            events = []
            for i in range(events_per_task):
                event = make_event(
                    EventType.PHASE_COMPLETED,
                    aggregate_id=aggregate_id,
                    version=task_idx * events_per_task + i + 1,
                    phase_name="test",
                    result={},
                    tokens={},
                    model_used="test",
                    duration_seconds=1.0,
                )
                events.append(event)
            await store.save_events(events)

        await asyncio.gather(*(append_batch(i) for i in range(num_tasks)))

        all_events = await store.get_events(aggregate_id)
        assert len(all_events) == num_tasks * events_per_task

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_snapshot_writes(self, temp_event_store):
        store = temp_event_store
        aggregate_id = "agg-snapshot"

        async def write_snapshot(version: int):
            await store.save_snapshot(
                aggregate_id,
                version=version,
                state={"version": version, "data": "x" * 100},
            )

        await asyncio.gather(*(write_snapshot(i) for i in range(1, 6)))

        snapshot = await store.get_snapshot(aggregate_id)
        assert snapshot is not None
        version, state = snapshot
        assert "version" in state

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_delete_aggregate_during_concurrent_writes(self, temp_event_store):
        store = temp_event_store
        aggregate_id = "agg-delete-during-write"

        async def append_loop():
            for i in range(50):
                event = make_event(
                    EventType.PHASE_COMPLETED,
                    aggregate_id=aggregate_id,
                    version=i + 1,
                    phase_name="test",
                    result={},
                    tokens={},
                    model_used="test",
                    duration_seconds=1.0,
                )
                try:
                    await store.save_events([event])
                except Exception:
                    pass
                await asyncio.sleep(0)

        async def delete_midway():
            await asyncio.sleep(0.01)
            await store.delete_aggregate(aggregate_id)

        await asyncio.gather(append_loop(), delete_midway())

        # Should not raise; aggregate may or may not exist depending on timing
        events = await store.get_events(aggregate_id)
        assert isinstance(events, list)

    @pytest.mark.asyncio
    async def test_executor_shutdown_releases_resources(self, tmp_path):
        from reasoner.infrastructure.persistence.event_store import EventStore

        db_path = tmp_path / "test_events.db"
        store = EventStore(db_path=str(db_path))

        event = make_event(
            EventType.PHASE_COMPLETED,
            aggregate_id="test",
            version=1,
            phase_name="test",
            result={},
            tokens={},
            model_used="test",
            duration_seconds=1.0,
        )
        await store.save_events([event])
        store.close()

        # After close, the executor should be shut down. The executor lives
        # on store.conn (EventStoreConnection), not on store itself -- see
        # EventStore.close()'s docstring for why this used to be checked in
        # the wrong place too.
        assert store.conn._executor is None or store.conn._executor._shutdown
