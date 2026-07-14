"""Verifies RunStateStore eviction works and does not cancel active runs prematurely."""
import asyncio
import pytest


@pytest.mark.asyncio
async def test_runstate_remove_preserves_other_runs():
    from reasoner.infrastructure.redis.in_memory import RunStateStore

    store = RunStateStore()
    e1 = await store.add("run-1", user_id="user-1")
    e2 = await store.add("run-2", user_id="user-2")
    assert store.is_active("run-1") is True
    assert store.is_active("run-2") is True

    await store.remove("run-1")
    assert store.is_active("run-1") is False
    assert store.is_active("run-2") is True, "run-2 should still be active"
    assert not e1.is_set(), "removed run event should not be set"
    assert not e2.is_set(), "other run event should not be set"


@pytest.mark.asyncio
async def test_runstate_max_entries_eviction():
    """Store with MAX_ENTRIES should evict oldest entries when full."""
    from reasoner.infrastructure.redis.in_memory import RunStateStore

    store = RunStateStore()
    store._MAX_ENTRIES = 5

    for i in range(10):
        await store.add(f"run-{i}")
        # Set old timestamps so eviction kicks in on the next add
        store._created_at[f"run-{i}"] = 0.0

    await store.add("run-final")
    # Should have at most MAX_ENTRIES + 1 (before next eviction)
    assert len(store._active_runs) <= 6
    assert store.is_active("run-final") is True
