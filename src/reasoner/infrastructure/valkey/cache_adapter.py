"""ValkeyCacheAdapter — implements SharedCachePort backed by Valkey.

Used for quota caching, subscription caching, HyperGate L2 decision cache,
and account-deletion cache cleanup.
"""

from __future__ import annotations

import json
import logging
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
