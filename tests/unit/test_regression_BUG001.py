"""
Regression test for BUG-001: Circuit breaker half-open slot leak.

When can_execute() is used with manual lifecycle management
(record_success / record_failure), half-open slots must be released
on every call completion. Previously, partial successes (those that
do not reach success_threshold) leaked the slot, permanently
exhausting half_open_max_calls.
"""

import pytest
from reasoner.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState


@pytest.mark.asyncio
async def test_half_open_slot_not_leaked_on_partial_success():
    """
    Reproduce BUG-001: with half_open_max_calls=2 and success_threshold=3,
    two partial successes should NOT exhaust the slot pool.
    Without the fix, the third can_execute() returns False.
    With the fix, it returns True because each record_success()
    decrements half_open_current_calls.
    """
    cb = CircuitBreaker(
        "test",
        config=CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=3,
            timeout_seconds=30.0,
            half_open_max_calls=2,
        ),
    )

    # Force circuit into OPEN state
    cb._state = CircuitState.OPEN
    cb._last_state_change = 0.0  # timeout immediately elapsed

    # Two partial successes (below threshold of 3)
    for _ in range(2):
        assert await cb.can_execute() is True
        await cb.record_success()

    # BUG-001: without the fix, half_open_current_calls would be 2,
    # so this assertion fails.
    assert await cb.can_execute() is True


@pytest.mark.asyncio
async def test_half_open_slot_released_on_record_failure():
    """
    Verify that record_failure() also resets slots when transitioning
    OPEN, and does not leak them.
    """
    cb = CircuitBreaker(
        "test",
        config=CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=3,
            timeout_seconds=30.0,
            half_open_max_calls=2,
        ),
    )

    # Force OPEN
    cb._state = CircuitState.OPEN
    cb._last_state_change = 0.0

    # One failure in HALF_OPEN should transition back to OPEN
    # and reset the counter.
    assert await cb.can_execute() is True
    await cb.record_failure()

    assert cb._state == CircuitState.OPEN
    assert cb._stats.half_open_current_calls == 0
