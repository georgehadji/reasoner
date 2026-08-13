"""Tests for Redis-backed RunStateManager with in-memory fallback.

Critical Enhancements:
- 9.1: cancel_all_active uses Redis Sets (O(1) per member) not SCAN.
- 9.2: pop_cancelled is atomic via Lua script.
- 9.3: No .decode() — decode_responses=True.
- 9.7: Graceful fallback to in-memory when Redis is down.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def run_state_manager():
    """Provide a fresh RunStateManager for each test."""
    from reasoner.infrastructure.redis.run_state import RunStateManager
    manager = RunStateManager()
    await manager.reset()
    yield manager
    await manager.reset()


class TestRunStateManager:
    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_register_and_is_active(self, run_state_manager):
        await run_state_manager.register("run-1")
        assert run_state_manager.is_active("run-1")
        assert not run_state_manager.is_active("run-2")

    @pytest.mark.asyncio
    async def test_unregister_removes_active(self, run_state_manager):
        await run_state_manager.register("run-1")
        await run_state_manager.unregister("run-1")
        assert not run_state_manager.is_active("run-1")

    @pytest.mark.asyncio
    async def test_cancel_and_is_cancelled(self, run_state_manager):
        await run_state_manager.register("run-1")
        await run_state_manager.cancel("run-1")
        assert await run_state_manager.is_cancelled("run-1")
        assert not await run_state_manager.is_cancelled("run-2")

    @pytest.mark.asyncio
    async def test_pop_cancelled_is_atomic(self, run_state_manager):
        """9.2: pop_cancelled should atomically check and clear."""
        await run_state_manager.register("run-1")
        await run_state_manager.cancel("run-1")

        # First pop should return True
        assert await run_state_manager.pop_cancelled("run-1") is True
        # Second pop should return False (already cleared)
        assert await run_state_manager.pop_cancelled("run-1") is False

    @pytest.mark.asyncio
    async def test_pop_cancelled_nonexistent(self, run_state_manager):
        assert await run_state_manager.pop_cancelled("run-does-not-exist") is False

    @pytest.mark.asyncio
    async def test_cancel_all_active(self, run_state_manager):
        """9.1: cancel_all_active should use Sets, not SCAN."""
        await run_state_manager.register("run-1")
        await run_state_manager.register("run-2")
        await run_state_manager.register("run-3")

        count = await run_state_manager.cancel_all_active()
        assert count == 3

        # All should be cancelled
        assert await run_state_manager.is_cancelled("run-1")
        assert await run_state_manager.is_cancelled("run-2")
        assert await run_state_manager.is_cancelled("run-3")

        # Still active until explicitly unregistered (streaming finally block does this)
        assert run_state_manager.is_active("run-1")

    @pytest.mark.asyncio
    async def test_add_returns_cancel_event(self, run_state_manager):
        event = await run_state_manager.add("run-1")
        assert isinstance(event, asyncio.Event)
        assert not event.is_set()

        await run_state_manager.request_cancel("run-1")
        assert event.is_set()

    @pytest.mark.asyncio
    async def test_active_runs_property(self, run_state_manager):
        await run_state_manager.register("run-a")
        await run_state_manager.register("run-b")
        active = run_state_manager.active_runs
        assert "run-a" in active
        assert "run-b" in active

    @pytest.mark.asyncio
    async def test_reset_clears_all(self, run_state_manager):
        await run_state_manager.register("run-1")
        await run_state_manager.cancel("run-1")
        await run_state_manager.reset()
        assert not run_state_manager.is_active("run-1")
        assert not await run_state_manager.is_cancelled("run-1")

    @pytest.mark.asyncio
    async def test_fallback_on_redis_failure(self, run_state_manager):
        """9.7: When Redis fails, operations should fall back to in-memory."""
        # Simulate Redis failure by breaking the internal client
        original_redis = run_state_manager._redis
        run_state_manager._redis = None
        run_state_manager._redis_ok = False
        run_state_manager._redis_last_fail = asyncio.get_event_loop().time()

        try:
            # These should still work via in-memory fallback
            await run_state_manager.register("fallback-run")
            assert run_state_manager.is_active("fallback-run")

            await run_state_manager.cancel("fallback-run")
            assert await run_state_manager.pop_cancelled("fallback-run")
        finally:
            run_state_manager._redis = original_redis
            run_state_manager._redis_ok = True

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_cross_process_cancel_via_redis(self, run_state_manager):
        """Two managers sharing Redis should see each other's cancels.

        Requires a live Redis/Valkey: the in-memory fallback is per-instance (and
        refuses to run in production precisely because it cannot be shared), so
        without a real server the two managers cannot observe each other by design.
        """
        from reasoner.infrastructure.redis.run_state import RunStateManager

        manager_a = RunStateManager()
        manager_b = RunStateManager()
        await manager_a.reset()
        await manager_b.reset()

        try:
            # Manager A registers a run
            await manager_a.register("shared-run")

            # Manager B cancels it
            await manager_b.cancel("shared-run")

            # Manager A should see the cancellation
            assert await manager_a.is_cancelled("shared-run")
        finally:
            await manager_a.reset()
            await manager_b.reset()
