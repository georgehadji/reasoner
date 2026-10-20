"""PostgreSQLEventStore against a real Postgres (PER-1, PER-4).

The existing Postgres tests mock the pool, so none of this ever ran. The DDL
was invalid (a unique constraint on a partitioned table without the partition
key), so the store could never initialize. Nothing initialized it anyway.

Runs only when REASONER_TEST_PG_DSN points at a disposable database, for
example:
    docker run -d -e POSTGRES_PASSWORD=test -e POSTGRES_DB=reasoner_test \
        -p 55499:5432 postgres:16
    REASONER_TEST_PG_DSN=postgresql://postgres:test@localhost:55499/reasoner_test
"""

from __future__ import annotations

import os
import uuid

import contextlib

import pytest

DSN = os.environ.get("REASONER_TEST_PG_DSN")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DSN, reason="REASONER_TEST_PG_DSN not set"),
]


@contextlib.asynccontextmanager
async def _store():
    """Open and close inside the test's own event loop (a fixture's teardown ran
    on a closed loop)."""
    from reasoner.infrastructure.persistence.postgres_store import PostgreSQLEventStore

    s = PostgreSQLEventStore(connection_string=DSN, pool_size=2)
    try:
        yield s
    finally:
        await s.close()


def _event(event_type, aggregate_id, version, **kw):
    from reasoner.core.events.domain_events import make_event

    return make_event(event_type, aggregate_id=aggregate_id, version=version, **kw)


async def _aggregate_row(store, aggregate_id):
    pool = await store._ready()
    return await pool.fetchrow(
        "SELECT status, current_version FROM aggregates WHERE aggregate_id = $1", aggregate_id
    )


@pytest.mark.asyncio
async def test_store_initializes_on_first_use_and_round_trips():
    async with _store() as store:
        from reasoner.core.events.domain_events import PipelineEventType as T

        run = f"run-{uuid.uuid4().hex[:8]}"
        # No initialize() call: the first save must set the pool up itself.
        await store.save_events([_event(T.PIPELINE_STARTED, run, 1, problem="p", preset="x")])
        await store.save_events([_event(T.PHASE_COMPLETED, run, 2, phase_name="Synthesis")])

        events = await store.get_events(run)
        assert [e.version for e in events] == [1, 2]
        assert events[0].problem == "p"


@pytest.mark.asyncio
async def test_initialize_is_idempotent():
    async with _store() as store:
        await store.initialize()
        pool = store._pool
        await store.initialize()
        assert store._pool is pool, "a second initialize must not open a second pool"


@pytest.mark.asyncio
async def test_saving_the_same_event_twice_stores_it_once():
    async with _store() as store:
        from reasoner.core.events.domain_events import PipelineEventType as T

        run = f"run-{uuid.uuid4().hex[:8]}"
        ev = _event(T.PIPELINE_STARTED, run, 1, problem="p")
        await store.save_events([ev])
        await store.save_events([ev])
        assert len(await store.get_events(run)) == 1


@pytest.mark.asyncio
async def test_saas_events_have_a_partition():
    async with _store() as store:
        from reasoner.core.events.domain_events import SaaSEventType

        await store.save_events([_event(SaaSEventType.USER_REGISTERED, f"user-{uuid.uuid4().hex[:8]}", 1)])


@pytest.mark.asyncio
async def test_a_late_event_does_not_reopen_a_completed_run():
    async with _store() as store:
        """PER-4: the upsert overwrote status with "running" and the version with a lower one."""
        from reasoner.core.events.domain_events import PipelineEventType as T

        run = f"run-{uuid.uuid4().hex[:8]}"
        await store.save_events([_event(T.PIPELINE_STARTED, run, 1, problem="p")])
        await store.save_events([_event(T.PIPELINE_COMPLETED, run, 5)])
        await store.save_events([_event(T.PHASE_COMPLETED, run, 3, phase_name="late")])

        row = await _aggregate_row(store, run)
        assert row["status"] == "completed"
        assert row["current_version"] == 5
