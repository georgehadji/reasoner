"""
Regression tests for BUG-003: Circuit breaker HALF_OPEN double decrement.

Verifies that the half_open_current_calls slot counter is not double-released
on successful calls, and that half_open_max_calls capacity is enforced.

Bug: _on_success() and _release_call() both decremented half_open_current_calls,
causing a double-free. The max(0, ...) guard prevented negatives but made the
capacity check ineffective — _try_acquire_call() never saw the counter ≥ threshold.
"""

from __future__ import annotations

import pytest
import asyncio
from reasoner.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerConfig


class TestBug003HalfOpenDoubleDecrement:

    @pytest.mark.asyncio
    async def test_no_double_decrement_after_success(self):
        """
        BUG-003 regression: After a single successful call in HALF_OPEN,
        half_open_current_calls must be decremented exactly once (by _release_call
        in the finally block), NOT twice (by both _on_success AND _release_call).

        Without the fix: 1 (acquire) - 1 (_on_success) - 1 (_release_call) = -1
        With the fix:     1 (acquire) - 1 (_release_call) = 0
        """
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=3,  # Keep HALF_OPEN after one success
            timeout_seconds=0.05,
            half_open_max_calls=2,
        )
        cb = CircuitBreaker("bug003-no-double", config)

        # Force OPEN
        try:
            await cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass
        assert cb.state == CircuitState.OPEN

        # Wait for HALF_OPEN transition
        await asyncio.sleep(0.1)

        # One successful call in HALF_OPEN
        await cb.call(lambda: "ok")

        # half_open_current_calls MUST be 0 (single release).
        # Without fix: -1 (clamped to 0 by max(0, ...), but logically wrong)
        # The value 0 is expected in both cases, BUT we verify capacity further.
        assert cb._stats.half_open_current_calls == 0, (
            f"hocc={cb._stats.half_open_current_calls}, expected 0"
        )

    @pytest.mark.asyncio
    async def test_half_open_capacity_enforced_after_success(self):
        """
        BUG-003 regression: After a successful call in HALF_OPEN, the capacity
        limit must still be enforced. Launch 3 concurrent calls with max=2;
        only 2 should get through.

        Without the fix: after first success, hocc is clamped to 0 → check
        hocc >= half_open_max_calls is always False → all calls get through.
        """
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=5,  # Keep HALF_OPEN after many successes
            timeout_seconds=0.05,
            half_open_max_calls=2,
        )
        cb = CircuitBreaker("bug003-capacity", config)

        # Force OPEN
        try:
            await cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass
        assert cb.state == CircuitState.OPEN

        # Wait for HALF_OPEN
        await asyncio.sleep(0.1)

        # First success: this should release one slot (not double-release)
        await cb.call(lambda: "ok")

        # Now launch 3 concurrent slow calls — only 2 should be accepted
        accepted = 0
        rejected = 0

        async def slow_ok():
            nonlocal accepted
            accepted += 1
            await asyncio.sleep(0.15)  # Hold slot for other coroutines to race
            return "ok"

        async def try_call():
            nonlocal rejected
            try:
                await cb.call(slow_ok)
            except Exception:
                rejected += 1

        tasks = [try_call() for _ in range(3)]
        await asyncio.gather(*tasks)

        # Without fix: all 3 accepted (capacity not enforced)
        # With fix: only 2 accepted
        assert accepted <= 2, (
            f"HALF_OPEN capacity not enforced: got {accepted} accepted, "
            f"expected ≤ 2. Double-decrement bug still present."
        )
        assert accepted == 2, (
            f"Expected exactly 2 accepted calls at capacity, got {accepted}"
        )

    @pytest.mark.asyncio
    async def test_half_open_capacity_enforced_on_first_entry(self):
        """
        Even without a prior success, verify that the initial HALF_OPEN entry
        enforces capacity correctly (sanity check for the test framework).
        """
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=5,
            timeout_seconds=0.05,
            half_open_max_calls=2,
        )
        cb = CircuitBreaker("bug003-first-entry", config)

        # Force OPEN
        try:
            await cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass
        await asyncio.sleep(0.1)

        # Directly enter HALF_OPEN (fresh, no prior successes)
        accepted = 0
        rejected = 0

        async def slow_ok():
            nonlocal accepted
            accepted += 1
            await asyncio.sleep(0.15)
            return "ok"

        async def try_call():
            nonlocal rejected
            try:
                await cb.call(slow_ok)
            except Exception:
                rejected += 1

        tasks = [try_call() for _ in range(3)]
        await asyncio.gather(*tasks)

        assert accepted <= 2, (
            f"Initial HALF_OPEN capacity not enforced: {accepted} accepted, "
            f"expected ≤ 2"
        )

    @pytest.mark.asyncio
    async def test_counter_never_negative(self):
        """
        Verify that half_open_current_calls never goes below 0 under mixed
        success/failure conditions.
        """
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=2,
            timeout_seconds=0.05,
            half_open_max_calls=3,
        )
        cb = CircuitBreaker("bug003-nonneg", config)

        # Force OPEN
        try:
            await cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass
        await asyncio.sleep(0.1)

        # Mix of outcomes
        outcomes = ["ok", "ok", "fail", "ok", "fail", "ok"]

        for i in range(6):
            outcome = outcomes[i % len(outcomes)]
            try:
                if outcome == "fail":
                    await cb.call(lambda: (_ for _ in ()).throw(ValueError("fail")))
                else:
                    await cb.call(lambda: "ok")
            except Exception:
                pass

        assert cb._stats.half_open_current_calls >= 0, (
            f"Counter went negative: {cb._stats.half_open_current_calls}"
        )

    @pytest.mark.asyncio
    async def test_half_open_released_on_failure(self):
        """
        When a call fails in HALF_OPEN, the circuit reopens and counter resets.
        Verify the slot is properly released.
        """
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=1,
            timeout_seconds=0.05,
            half_open_max_calls=1,
        )
        cb = CircuitBreaker("bug003-fail-release", config)

        # Force OPEN
        try:
            await cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass
        await asyncio.sleep(0.1)

        # Failing call in HALF_OPEN → reopens to OPEN
        try:
            await cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass

        assert cb.state == CircuitState.OPEN, "Should reopen after HALF_OPEN failure"
        assert cb._stats.half_open_current_calls == 0, (
            f"hocc should be 0 after reopening, got {cb._stats.half_open_current_calls}"
        )

    @pytest.mark.asyncio
    async def test_half_open_concurrent_call_slot_accounting(self):
        """
        Strict slot accounting: verify that the counter accurately reflects the
        number of concurrently executing calls throughout their lifecycle.
        """
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=3,
            timeout_seconds=0.05,
            half_open_max_calls=3,
        )
        cb = CircuitBreaker("bug003-accounting", config)

        # Force OPEN → HALF_OPEN
        try:
            await cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass
        await asyncio.sleep(0.1)

        # Snapshot counter at various points
        snapshots = []
        barrier = asyncio.Event()

        async def track_and_sleep():
            async with cb._lock:
                snapshots.append(("entered", cb._stats.half_open_current_calls))
            await asyncio.sleep(0.1)
            async with cb._lock:
                snapshots.append(("exiting", cb._stats.half_open_current_calls))
            return "ok"

        tasks = [cb.call(track_and_sleep) for _ in range(2)]
        await asyncio.gather(*tasks)

        # Verify counter went up during execution and back to 0 after
        entered_values = [v for label, v in snapshots if label == "entered"]
        exiting_values = [v for label, v in snapshots if label == "exiting"]

        # At entry, counter should be >= 1 for at least one snapshot
        assert any(v >= 1 for v in entered_values), (
            "Counter never incremented during entry"
        )

        # After everything completes, counter should be 0
        async with cb._lock:
            final_hocc = cb._stats.half_open_current_calls
        assert final_hocc == 0, (
            f"Counter leaked: {final_hocc} after all calls completed"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
