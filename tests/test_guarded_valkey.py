"""PRV-2, PRV-4: every Valkey operation is bounded, and a failure starts a cooldown.

The socket timeout is 2 s. A hung Valkey therefore cost 2 s per operation, which
used up the 1 s tier-lookup budget before the database was read (a paying user
resolved to FREE) and added up to 4 s to each LLM call through the Redis
circuit breaker. `GuardedValkey` bounds each operation and, after one failure,
raises at once for a cooldown instead of touching the network again.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from reasoner.core.exceptions import ValkeyUnavailableError
from reasoner.infrastructure.valkey.guarded import GuardedValkey

pytestmark = pytest.mark.unit


class _Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


class _Client:
    """A client whose every call hangs, and counts how often it is called."""

    def __init__(self, hang_s: float = 5.0) -> None:
        self.calls = 0
        self.hang_s = hang_s
        self.store: dict[str, str] = {}

    async def get(self, key):
        self.calls += 1
        await asyncio.sleep(self.hang_s)
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.calls += 1
        await asyncio.sleep(self.hang_s)
        self.store[key] = value
        return True


async def test_hung_operation_raises_within_its_bound() -> None:
    guard = GuardedValkey(_Client(), op_timeout_s=0.05, cooldown_s=30.0)

    started = time.monotonic()
    with pytest.raises(ValkeyUnavailableError):
        await guard.get("k")

    assert time.monotonic() - started < 0.25


async def test_second_call_during_cooldown_never_touches_the_client() -> None:
    client = _Client()
    guard = GuardedValkey(client, op_timeout_s=0.05, cooldown_s=30.0)
    with pytest.raises(ValkeyUnavailableError):
        await guard.get("k")
    assert client.calls == 1

    started = time.monotonic()
    with pytest.raises(ValkeyUnavailableError):
        await guard.setex("k", 10, "v")

    assert client.calls == 1, "the cooldown must skip the network entirely"
    assert time.monotonic() - started < 0.05


async def test_client_is_probed_again_after_the_cooldown() -> None:
    clock = _Clock()
    client = _Client(hang_s=0.0)
    guard = GuardedValkey(client, op_timeout_s=0.05, cooldown_s=30.0, clock=clock)
    client.hang_s = 5.0
    with pytest.raises(ValkeyUnavailableError):
        await guard.get("k")

    clock.t += 31
    client.hang_s = 0.0
    client.store["k"] = "v"

    assert await guard.get("k") == "v"


async def test_healthy_client_passes_values_through() -> None:
    client = _Client(hang_s=0.0)
    guard = GuardedValkey(client, op_timeout_s=0.5, cooldown_s=30.0)

    assert await guard.setex("k", 10, "v") is True
    assert await guard.get("k") == "v"


def test_unavailable_is_a_connection_error() -> None:
    """Callers already `except Exception` around cache reads; keep that working."""
    assert issubclass(ValkeyUnavailableError, ConnectionError)


class _HungScriptClient:
    """register_script() works; running the script hangs."""

    def __init__(self) -> None:
        self.script_calls = 0

    def register_script(self, source):
        async def script(keys, args):
            self.script_calls += 1
            await asyncio.sleep(5.0)

        return script


async def test_redis_circuit_breaker_does_not_stall_llm_calls_on_a_hung_valkey(monkeypatch) -> None:
    """PRV-4: each breaker call used to wait out the 2 s socket timeout, twice per LLM call."""
    from reasoner.infrastructure.circuit_breaker import RedisCircuitBreaker

    client = _HungScriptClient()
    monkeypatch.setattr("reasoner.infrastructure.valkey.client.get_valkey_pool", lambda: client)
    breaker = RedisCircuitBreaker("llm:hung-test")

    started = time.monotonic()
    assert await breaker.can_execute() is True  # fail-open, as before
    await breaker.record_failure()
    await breaker.record_success()
    elapsed = time.monotonic() - started

    assert elapsed < 0.6, f"three breaker calls took {elapsed:.2f}s on a hung Valkey"
    assert client.script_calls == 1, "only the first call may reach the hung client"
