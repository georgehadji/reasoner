"""Shared cache port — key-value cache with TTL support.

Implemented by infrastructure.valkey.cache_adapter (Valkey) and
infrastructure.valkey.memory_cache_adapter (in-memory fallback).
The application layer depends on this port, not on the concrete
cache backend.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SharedCachePort(Protocol):
    """Port for shared key-value cache access.

    Used by quota repositories, subscription repositories, HyperGate L2
    decision cache, and account-deletion cache cleanup.  Concrete adapters
    provide Valkey-backed or in-memory storage.

    Implemented by:
      - infrastructure.valkey.cache_adapter.ValkeyCacheAdapter
      - infrastructure.valkey.memory_cache_adapter.InMemoryCacheAdapter
    """

    async def get(self, key: str) -> Any | None: ...

    async def set(self, key: str, value: Any, ttl: int | None = ...) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching *pattern*.  Returns count of keys removed."""
        ...

    async def exists(self, key: str) -> bool: ...

    async def close(self) -> None: ...
