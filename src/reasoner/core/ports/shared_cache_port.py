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


# ── Dependency injection for application → infrastructure boundary ────────
# Mirrors model_registry_port.set_model_registry_port(), with one deliberate
# difference: the getter returns None instead of raising when nothing has been
# injected. A missing registry is a bug -- nothing can route without it. A
# missing cache is a degraded mode: every consumer here is an optimisation and
# must still answer correctly with no backend at all. Raising would turn a cold
# cache into a 500.
_SHARED_CACHE_PORT: SharedCachePort | None = None


def set_shared_cache_port(port: SharedCachePort | None) -> None:
    """Inject the concrete cache adapter. Called once at startup.

    Accepts None so a test can restore the uninjected state.
    """
    global _SHARED_CACHE_PORT
    _SHARED_CACHE_PORT = port


def get_shared_cache_port() -> SharedCachePort | None:
    """Return the injected cache port, or None if there is no cache.

    Callers MUST treat None as "no caching this run", never as an error.
    """
    return _SHARED_CACHE_PORT
