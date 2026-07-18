"""InMemoryCacheAdapter — implements SharedCachePort backed by a local dict.

Used as fallback when Valkey is unavailable in single-worker/dev mode.
"""

from __future__ import annotations

import time
from typing import Any

from reasoner.core.ports.shared_cache_port import SharedCachePort


class InMemoryCacheAdapter:
    """In-memory cache adapter implementing SharedCachePort.

    Suitable for single-worker development or as fallback when Valkey
    is unreachable. Not shared across workers.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float | None]] = {}  # value, expires_at

    async def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        expires_at = time.monotonic() + ttl if ttl is not None else None
        self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def delete_pattern(self, pattern: str) -> int:
        """Simple glob-style pattern matching. Returns count removed."""
        import fnmatch
        to_delete = [k for k in self._store if fnmatch.fnmatch(k, pattern)]
        for k in to_delete:
            del self._store[k]
        return len(to_delete)

    async def exists(self, key: str) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return False
        _, expires_at = entry
        if expires_at is not None and time.monotonic() > expires_at:
            del self._store[key]
            return False
        return True

    async def close(self) -> None:
        self._store.clear()


# Verify protocol conformance
_: SharedCachePort = InMemoryCacheAdapter()  # type: ignore[assignment]
