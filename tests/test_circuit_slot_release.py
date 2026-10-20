"""Cancelled calls give back half-open slots; calls keep their state private (RUN-3, RUN-4).

RUN-3: ``can_execute()`` takes a HALF_OPEN slot, and the router's
``except asyncio.CancelledError: raise`` skipped both record calls, so the
slot was never released. HALF_OPEN had no timeout either. Three cancelled
probes wedged the model until restart.

RUN-4: the router merged ``extra_body`` into the shared, process-wide
provider around a network await. The guarding semaphore counts to 30, so it
is not a mutex, and a concurrent call sent another run's reasoning effort.
See docs/plans/audit-remediation-2026-10-20.md, RUN-3 and RUN-4.
"""

from __future__ import annotations

import asyncio

import pytest

from reasoner.infrastructure.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from reasoner.infrastructure.llm import router as router_mod


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def monotonic(self) -> float:
        return self.t

    def time(self) -> float:
        return self.t


async def _half_open(clock: _Clock) -> CircuitBreaker:
    cb = CircuitBreaker("t", CircuitBreakerConfig(failure_threshold=1, timeout_seconds=30,
                                                  half_open_max_calls=3), clock=clock)
    assert await cb.can_execute()
    await cb.record_failure()  # CLOSED -> OPEN
    clock.t += 31  # past the open timeout: next can_execute moves to HALF_OPEN
    return cb


@pytest.mark.asyncio
async def test_release_returns_the_half_open_slot():
    cb = await _half_open(_Clock())
    for _ in range(3):
        assert await cb.can_execute()
    assert cb.state is CircuitState.HALF_OPEN
    assert not await cb.can_execute(), "three probes fill half-open"

    await cb.release()
    assert await cb.can_execute(), "a released slot is usable again"


@pytest.mark.asyncio
async def test_abandoned_probes_expire_after_the_timeout():
    clock = _Clock()
    cb = await _half_open(clock)
    for _ in range(3):
        assert await cb.can_execute()  # three probes, never resolved
    assert not await cb.can_execute()

    clock.t += 31
    assert await cb.can_execute(), "stale probes must not wedge the model forever"


class _Provider:
    """A provider whose call blocks until released, capturing extra_body."""

    def __init__(self, model: str):
        self.model = model
        self.extra_body: dict = {}
        self.gate = asyncio.Event()
        self.started = asyncio.Event()
        self.seen: list[dict] = []

    async def complete_with_retry(self, system_prompt, user_prompt, max_tokens, temperature):
        self.started.set()
        await self.gate.wait()
        self.seen.append(dict(self.extra_body))
        return "ok"


@pytest.mark.asyncio
async def test_cancelled_router_call_releases_its_slot(monkeypatch):
    clock = _Clock()
    cb = await _half_open(clock)
    monkeypatch.setattr("reasoner.circuit_breaker.get_circuit_breaker", lambda name: cb)
    provider = _Provider("m-cancel")

    calls = [asyncio.create_task(router_mod._call_with_circuit(
        provider, "s", "u", 10, 0.0, 30.0)) for _ in range(3)]
    await asyncio.sleep(0.01)
    assert not await cb.can_execute(), "three in-flight probes hold all slots"

    for t in calls:
        t.cancel()
    await asyncio.gather(*calls, return_exceptions=True)

    assert cb.stats.half_open_current_calls == 0
    assert await cb.can_execute(), "cancelled probes must give their slots back"


@pytest.mark.asyncio
async def test_concurrent_calls_do_not_share_extra_body(monkeypatch):
    shared = _Provider("m-shared")
    shared.extra_body = {"configured": True}
    router = router_mod.ProviderRouter(primary=shared)

    async def call(effort):
        return await router.call("primary", "s", "u", extra_body={"reasoning": {"effort": effort}})

    a = asyncio.create_task(call("high"))
    await shared.started.wait()
    b = asyncio.create_task(call("minimal"))
    await asyncio.sleep(0.01)
    shared.gate.set()
    await asyncio.gather(a, b)

    # Each call sent its own effort (the old code sent "minimal" twice), on top
    # of the configured body, and the shared instance is left as configured.
    assert sorted(s["reasoning"]["effort"] for s in shared.seen) == ["high", "minimal"]
    assert all(s.get("configured") for s in shared.seen)
    assert shared.extra_body == {"configured": True}
