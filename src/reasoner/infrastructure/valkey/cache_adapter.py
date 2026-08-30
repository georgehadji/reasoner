"""ValkeyCacheAdapter — implements SharedCachePort backed by Valkey.

Used for quota caching, subscription caching, HyperGate L2 decision cache,
and account-deletion cache cleanup.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from reasoner.core.ports.shared_cache_port import SharedCachePort
from reasoner.infrastructure.valkey.client import get_valkey_pool

logger = logging.getLogger(__name__)


class ValkeyCacheAdapter:
    """Shared cache adapter backed by Valkey (Redis-compatible)."""

    def __init__(self) -> None:
        self._client = get_valkey_pool()

    async def get(self, key: str) -> Any | None:
        try:
            raw = await self._client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.debug("Valkey cache get(%s) failed: %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        try:
            raw = json.dumps(value, default=str)
            if ttl is not None:
                await self._client.setex(key, ttl, raw)
            else:
                await self._client.set(key, raw)
        except Exception as exc:
            logger.debug("Valkey cache set(%s) failed: %s", key, exc)

    async def delete(self, key: str) -> None:
        try:
            await self._client.delete(key)
        except Exception as exc:
            logger.debug("Valkey cache delete(%s) failed: %s", key, exc)

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching *pattern*. Returns count of keys removed."""
        try:
            keys = [k async for k in self._client.scan_iter(match=pattern)]
            if keys:
                return await self._client.delete(*keys)
            return 0
        except Exception as exc:
            logger.debug("Valkey cache delete_pattern(%s) failed: %s", pattern, exc)
            return 0

    async def exists(self, key: str) -> bool:
        try:
            return bool(await self._client.exists(key))
        except Exception as exc:
            logger.debug("Valkey cache exists(%s) failed: %s", key, exc)
            return False

    async def close(self) -> None:
        # Pool is shared — no individual close needed
        pass


# Verify protocol conformance at import time
_: SharedCachePort = ValkeyCacheAdapter()  # type: ignore[assignment]


async def inject_shared_cache_port() -> None:
    """Pick a cache backend and install it as the process-wide SharedCachePort.

    Lives here rather than in the API lifespan because choosing between these
    two adapters is this module's business, and because api/__init__.py is
    under a pinned line-count cap whose rule is to shrink the module before
    growing it (tests/architecture/test_layer_boundaries.py).

    Valkey is probed rather than assumed: ValkeyCacheAdapter swallows its own
    connection errors and reports a miss, so an unreachable Valkey would leave
    every lookup paying the client's 2s socket timeout for a guaranteed miss --
    strictly worse than no cache at all. The in-memory fallback is per-worker,
    which is still the fix for what it was written for: a HyperGate cache that
    did not survive a single request.

    Never raises. A process with no cache answers correctly, just slower.
    """
    from reasoner.core.ports.shared_cache_port import set_shared_cache_port
    from reasoner.infrastructure.valkey.memory_cache_adapter import InMemoryCacheAdapter

    try:
        if not (os.environ.get("VALKEY_URL") or os.environ.get("REDIS_URL")):
            # get_valkey_pool() defaults to redis://localhost:6379/0 when neither
            # is set, so probing would spend two 2s connect timeouts on every dev
            # startup to learn what the unset variables already say.
            raise RuntimeError("no VALKEY_URL/REDIS_URL configured")
        port = ValkeyCacheAdapter()
        await port.set("_shared_cache_probe", "1", ttl=10)
        if await port.get("_shared_cache_probe") is None:
            raise RuntimeError("Valkey cache probe did not round-trip")
        set_shared_cache_port(port)
        logger.info("SharedCachePort injected: ValkeyCacheAdapter")
        return
    except Exception as exc:
        reason = exc

    try:
        set_shared_cache_port(InMemoryCacheAdapter())
        logger.info(
            "SharedCachePort injected: InMemoryCacheAdapter (Valkey unavailable: "
            "%s). Per-worker, not shared.", reason,
        )
    except Exception as exc:
        logger.warning("Failed to inject SharedCachePort: %s", exc)
