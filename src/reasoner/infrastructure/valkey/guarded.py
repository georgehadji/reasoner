"""A bounded, fast-failing view of the shared Valkey client.

The client's socket timeout is 2 s, so a hung Valkey cost every caller 2 s per
operation. For the cache-aside repositories that used up the whole tier-lookup
budget before the database was read, and for the Redis circuit breaker it added
seconds to each LLM call. `GuardedValkey` is a decorator over the client:

* every operation is bounded by ``op_timeout_s``;
* after any failure, operations raise `ValkeyUnavailableError` immediately for
  ``cooldown_s`` without touching the network, then the next call re-probes.

Callers keep their existing ``except Exception`` fallback; the guard only makes
that fallback arrive quickly. `ValkeyUnavailableError` is a `ConnectionError` so
those handlers need no change.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from reasoner.core.constants_limits import VALKEY_OP_TIMEOUT_S, VALKEY_RETRY_SECONDS
from reasoner.core.degrade import degraded
from reasoner.core.exceptions import ValkeyUnavailableError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class GuardedValkey:
    def __init__(
        self,
        client: Any,
        op_timeout_s: float = VALKEY_OP_TIMEOUT_S,
        cooldown_s: float = VALKEY_RETRY_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._op_timeout_s = op_timeout_s
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._last_fail: float | None = None

    @property
    def client(self) -> Any:
        return self._client

    async def run(self, op: Callable[[], Awaitable[T]]) -> T:
        """Run one client operation under the bound and the cooldown."""
        if self._last_fail is not None and self._clock() - self._last_fail < self._cooldown_s:
            raise ValkeyUnavailableError("Valkey is cooling down after a failure")
        try:
            result = await asyncio.wait_for(op(), timeout=self._op_timeout_s)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._last_fail = self._clock()
            degraded("valkey.guard", None, exc=exc)
            raise ValkeyUnavailableError(f"Valkey operation failed: {type(exc).__name__}") from exc
        self._last_fail = None
        return result

    async def get(self, key: str) -> Any:
        return await self.run(lambda: self._client.get(key))

    async def set(self, key: str, value: Any, **kwargs: Any) -> Any:
        return await self.run(lambda: self._client.set(key, value, **kwargs))

    async def setex(self, key: str, ttl: int, value: Any) -> Any:
        return await self.run(lambda: self._client.setex(key, ttl, value))

    async def delete(self, *keys: str) -> Any:
        return await self.run(lambda: self._client.delete(*keys))

    async def incr(self, key: str) -> Any:
        return await self.run(lambda: self._client.incr(key))

    async def expire(self, key: str, seconds: int) -> Any:
        return await self.run(lambda: self._client.expire(key, seconds))

    def register_script(self, source: str) -> Callable[..., Awaitable[Any]]:
        """A script callable that goes through the same bound and cooldown."""
        script = self._client.register_script(source)

        async def call(*args: Any, **kwargs: Any) -> Any:
            return await self.run(lambda: script(*args, **kwargs))

        return call


_guards: dict[int, GuardedValkey] = {}


def get_guarded_valkey(client: Any) -> GuardedValkey:
    """The one guard for *client*, so its cooldown is shared by every caller.

    Keyed by identity: a test that swaps the pool gets a fresh guard, and
    separate callers of the same pool see the same outage once.
    """
    guard = _guards.get(id(client))
    if guard is None or guard.client is not client:
        _guards.clear()
        guard = _guards[id(client)] = GuardedValkey(client)
    return guard
