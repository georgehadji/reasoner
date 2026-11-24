"""
Tests for RunStateStore.

Covers add/remove/cancel/isolation and concurrent operations.
"""

import asyncio

import pytest

from reasoner.api.run_state import RunStateStore


class TestRunStateStore:
    """Unit tests for RunStateStore."""

    @pytest.mark.asyncio
    async def test_add_creates_event_and_marks_active(self):
        store = RunStateStore()
        event = await store.add("run-1")

        assert isinstance(event, asyncio.Event)
        assert store.is_active("run-1") is True
        assert "run-1" in store.active_runs
        await store.reset()

    @pytest.mark.asyncio
    async def test_remove_cleans_up_state(self):
        store = RunStateStore()
        await store.add("run-1")
        await store.remove("run-1")

        assert store.is_active("run-1") is False
        assert await store.get_cancel_event("run-1") is None
        await store.reset()

    @pytest.mark.asyncio
    async def test_request_cancel_sets_event(self):
        store = RunStateStore()
        event = await store.add("run-1")

        result = await store.request_cancel("run-1")
        assert result is True
        assert event.is_set() is True
        await store.reset()

    @pytest.mark.asyncio
    async def test_request_cancel_returns_false_for_missing_run(self):
        store = RunStateStore()
        result = await store.request_cancel("missing")
        assert result is False
        await store.reset()

    @pytest.mark.asyncio
    async def test_request_cancel_all_cancels_all_active(self):
        store = RunStateStore()
        event1 = await store.add("run-1")
        event2 = await store.add("run-2")
        event3 = await store.add("run-3")

        targets = await store.request_cancel_all()
        assert set(targets) == {"run-1", "run-2", "run-3"}
        assert event1.is_set() is True
        assert event2.is_set() is True
        assert event3.is_set() is True
        await store.reset()

    @pytest.mark.asyncio
    async def test_isolation_between_runs(self):
        store = RunStateStore()
        event1 = await store.add("run-1")
        event2 = await store.add("run-2")

        await store.request_cancel("run-1")
        assert event1.is_set() is True
        assert event2.is_set() is False
        await store.reset()

    @pytest.mark.asyncio
    async def test_reset_clears_all_state(self):
        store = RunStateStore()
        await store.add("run-1")
        await store.add("run-2")
        await store.add("run-3")

        await store.reset()
        assert store.active_runs == set()
        assert await store.get_cancel_event("run-1") is None

    @pytest.mark.asyncio
    async def test_concurrent_add_remove_no_race(self):
        store = RunStateStore()
        run_ids = [f"run-{i}" for i in range(50)]

        async def add_all():
            for rid in run_ids:
                await store.add(rid)

        async def remove_all():
            for rid in run_ids:
                await store.remove(rid)

        await asyncio.gather(add_all(), remove_all())

        # Final state should be consistent — no crashes, no leaked events
        assert store.active_runs.issubset(set(run_ids))
        await store.reset()

    @pytest.mark.asyncio
    async def test_get_cancel_event_returns_correct_event(self):
        store = RunStateStore()
        event = await store.add("run-1")

        fetched = await store.get_cancel_event("run-1")
        assert fetched is event
        await store.reset()

    @pytest.mark.asyncio
    async def test_remove_is_idempotent(self):
        store = RunStateStore()
        await store.add("run-1")
        await store.remove("run-1")
        await store.remove("run-1")
        await store.remove("run-1")

        assert store.is_active("run-1") is False
        await store.reset()


def test_run_windows_outlast_the_pipeline_cap():
    import inspect

    from reasoner.core.constants_limits import PIPELINE_ABSOLUTE_TIMEOUT_SECONDS as CAP
    from reasoner.infrastructure.redis.in_memory import RunStateStore
    from reasoner.infrastructure.redis.run_state import _run_state_manager as mgr

    assert RunStateStore._MAX_STALE_SECONDS > CAP
    assert inspect.signature(mgr.try_register).parameters["ttl"].default > CAP


# ── In-flight run slots (audit 8 WS5-2, D7) ────────────────────────────────


@pytest.fixture
def slot_manager(monkeypatch):
    """A run-state manager with Redis out of reach, installed as the process singleton.

    The in-memory twin of the Redis sorted set is the code under test here; the
    Lua script itself needs a live Valkey and is exercised by the integration lane.
    """
    import time

    from reasoner.infrastructure.redis import run_state

    manager = run_state.RunStateManager()
    manager._redis_ok = False
    manager._redis_last_fail = time.monotonic()
    manager._redis_cooldown_seconds = 1e9
    monkeypatch.setattr(run_state, "_run_state_manager", manager)
    return manager


class TestInflightSlots:
    @pytest.mark.asyncio
    async def test_owner_cap_refuses_then_frees_on_release(self, slot_manager):
        from reasoner.infrastructure.redis.run_state import SLOT_OK, SLOT_OWNER_FULL

        take = lambda m: slot_manager.acquire_run_slot("u1", m, limit=1, worker_limit=50)  # noqa: E731
        assert await take("r1") == SLOT_OK
        assert await take("r2") == SLOT_OWNER_FULL
        await slot_manager.release_run_slot("u1", "r1")
        assert await take("r2") == SLOT_OK

    @pytest.mark.asyncio
    async def test_release_twice_frees_once(self, slot_manager):
        from reasoner.infrastructure.redis.run_state import SLOT_OK, SLOT_OWNER_FULL

        take = lambda m: slot_manager.acquire_run_slot("u1", m, limit=2, worker_limit=50)  # noqa: E731
        assert await take("r1") == SLOT_OK
        assert await take("r2") == SLOT_OK
        await slot_manager.release_run_slot("u1", "r1")
        await slot_manager.release_run_slot("u1", "r1")
        assert await take("r3") == SLOT_OK
        assert await take("r4") == SLOT_OWNER_FULL  # r2 and r3 still held

    @pytest.mark.asyncio
    async def test_owners_do_not_share_a_cap(self, slot_manager):
        from reasoner.infrastructure.redis.run_state import SLOT_OK

        assert await slot_manager.acquire_run_slot("u1", "r1", limit=1, worker_limit=50) == SLOT_OK
        assert await slot_manager.acquire_run_slot("u2", "r2", limit=1, worker_limit=50) == SLOT_OK

    @pytest.mark.asyncio
    async def test_worker_cap_counts_every_owner_and_a_refusal_holds_nothing(self, slot_manager):
        from reasoner.infrastructure.redis.run_state import (
            SLOT_OK,
            SLOT_OWNER_FULL,
            SLOT_WORKER_FULL,
        )

        assert await slot_manager.acquire_run_slot("u1", "r1", limit=5, worker_limit=2) == SLOT_OK
        assert await slot_manager.acquire_run_slot("u2", "r2", limit=5, worker_limit=2) == SLOT_OK
        assert (
            await slot_manager.acquire_run_slot("u3", "r3", limit=5, worker_limit=2)
            == SLOT_WORKER_FULL
        )
        await slot_manager.release_run_slot("u1", "r1")
        # u3's refusal left no owner slot behind, so a limit of 1 still admits it.
        assert await slot_manager.acquire_run_slot("u3", "r3", limit=1, worker_limit=2) == SLOT_OK
        # An owner-cap refusal must not leave a worker slot behind either.
        got = await slot_manager.acquire_run_slot("u3", "r4", limit=1, worker_limit=3)
        assert got == SLOT_OWNER_FULL
        assert await slot_manager.acquire_run_slot("u4", "r5", limit=1, worker_limit=3) == SLOT_OK

    @pytest.mark.asyncio
    async def test_a_dead_workers_slot_expires(self, slot_manager):
        from reasoner.infrastructure.redis.run_state import SLOT_OK, SLOT_OWNER_FULL

        got = await slot_manager.acquire_run_slot("u1", "r1", limit=1, worker_limit=50, ttl=0)
        assert got == SLOT_OK
        # ttl 0: the member is already past its expiry, as after a crash and the TTL.
        assert await slot_manager.acquire_run_slot("u1", "r2", limit=1, worker_limit=50) == SLOT_OK
        got = await slot_manager.acquire_run_slot("u1", "r3", limit=1, worker_limit=50)
        assert got == SLOT_OWNER_FULL


def test_tier_table_follows_decision_d7():
    from reasoner.domain.saas import SubscriptionTier
    from reasoner.domain.spend_limits import max_inflight_runs

    assert max_inflight_runs(SubscriptionTier.FREE) == 1
    assert max_inflight_runs(SubscriptionTier.PRO) == 3
    assert max_inflight_runs(SubscriptionTier.ENTERPRISE) == 10
    assert max_inflight_runs(None) == 1
    assert max_inflight_runs("not-a-tier") == 1
