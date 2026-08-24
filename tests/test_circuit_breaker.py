"""Tests for circuit breaker race condition fix (BUG-001 regression)."""

import asyncio

import pytest

from reasoner.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState


class TestCircuitBreakerConcurrency:
    """BUG-001 regression tests: Circuit breaker must handle concurrent calls safely."""

    @pytest.mark.asyncio
    async def test_half_open_concurrent_call_limit(self):
        """Test that HALF_OPEN state enforces max concurrent calls."""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            timeout_seconds=0.1,  # Short timeout for testing
            half_open_max_calls=2  # Only 2 concurrent calls allowed
        )
        cb = CircuitBreaker("test", config)

        # Force circuit to OPEN state
        for _ in range(2):
            try:
                await cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
            except Exception:
                pass

        assert cb.state == CircuitState.OPEN

        # Wait for timeout to allow HALF_OPEN transition
        await asyncio.sleep(0.15)

        # Try to make 5 concurrent calls - only 2 should succeed
        call_count = 0
        rejected_count = 0

        async def mock_success():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)  # Simulate work
            return "success"

        async def try_call():
            nonlocal rejected_count
            try:
                await cb.call(mock_success)
            except Exception:
                rejected_count += 1

        # Launch 5 concurrent calls
        tasks = [try_call() for _ in range(5)]
        await asyncio.gather(*tasks)

        # Only 2 should have been allowed (half_open_max_calls)
        # Note: This test may be flaky due to timing, but demonstrates the concept
        assert call_count <= 2, f"Expected <= 2 calls, got {call_count}"

    @pytest.mark.asyncio
    async def test_atomic_open_to_half_open_transition(self):
        """Test that OPEN→HALF_OPEN transition is atomic."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=1,
            timeout_seconds=0.05,
            half_open_max_calls=1
        )
        cb = CircuitBreaker("test", config)

        # Force circuit to OPEN
        try:
            await cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass

        assert cb.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.1)

        # Multiple concurrent calls should all see consistent state
        states_seen = []

        async def check_and_call():
            # This will trigger the transition inside the lock
            try:
                await cb.call(lambda: "success")
                states_seen.append(cb.state)
            except Exception:
                states_seen.append(cb.state)

        # Launch concurrent calls
        tasks = [check_and_call() for _ in range(3)]
        await asyncio.gather(*tasks)

        # All should see HALF_OPEN or CLOSED (after success)
        # None should see OPEN (transition should have happened)
        assert CircuitState.OPEN not in states_seen or states_seen.count(CircuitState.OPEN) == 0

    @pytest.mark.asyncio
    async def test_call_slot_released_on_success(self):
        """Test that call slot is released after successful call."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=2,
            timeout_seconds=0.05,
            half_open_max_calls=1
        )
        cb = CircuitBreaker("test", config)

        # Force OPEN
        try:
            await cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass

        # Wait for HALF_OPEN
        await asyncio.sleep(0.1)

        # First call should succeed and move toward CLOSED
        result = await cb.call(lambda: "success")
        assert result == "success"

        # Counter should be reset after success leading to CLOSED
        assert cb._stats.half_open_current_calls == 0

    @pytest.mark.asyncio
    async def test_call_slot_released_on_failure(self):
        """Test that call slot is released even when call fails."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=1,
            timeout_seconds=0.05,
            half_open_max_calls=1
        )
        cb = CircuitBreaker("test", config)

        # Force OPEN
        try:
            await cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass

        # Wait for HALF_OPEN
        await asyncio.sleep(0.1)

        # Call that fails - slot should still be released
        try:
            await cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass

        # Counter should be reset (circuit went back to OPEN)
        assert cb._stats.half_open_current_calls == 0

    @pytest.mark.asyncio
    async def test_call_slot_released_on_exception(self):
        """Test that call slot is released when exception is raised."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=1,
            timeout_seconds=0.05,
            half_open_max_calls=1
        )
        cb = CircuitBreaker("test", config)

        # Force OPEN
        try:
            await cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass

        # Wait for HALF_OPEN
        await asyncio.sleep(0.1)

        # Call that raises unhandled exception
        async def failing_call():
            raise ValueError("unexpected error")

        try:
            await cb.call(failing_call)
        except ValueError:
            pass

        # Slot should still be released (finally block)
        async with cb._lock:
            assert cb._stats.half_open_current_calls == 0


class TestCircuitBreakerStatsTracking:
    """Test circuit breaker statistics tracking."""

    def test_half_open_current_calls_initial_value(self):
        """Test that half_open_current_calls starts at 0."""
        cb = CircuitBreaker("test")
        assert cb._stats.half_open_current_calls == 0

    @pytest.mark.asyncio
    async def test_stats_reset_on_close(self):
        """Test that half_open_current_calls resets when circuit closes."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=1,
            timeout_seconds=0.05,
            half_open_max_calls=2
        )
        cb = CircuitBreaker("test", config)

        # Force OPEN
        try:
            await cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass

        # Wait for HALF_OPEN
        await asyncio.sleep(0.1)

        # Successful call should close circuit
        await cb.call(lambda: "success")
        await cb.call(lambda: "success")  # Second success to meet threshold

        assert cb.state == CircuitState.CLOSED
        assert cb._stats.half_open_current_calls == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
