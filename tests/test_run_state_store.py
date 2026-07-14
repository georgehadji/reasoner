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
