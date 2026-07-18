"""Distributed state port — atomic operations and Lua scripting.

Implemented by infrastructure.valkey.state_adapter (Valkey) and
infrastructure.valkey.memory_state_adapter (in-memory fallback).
The application layer depends on this port, not on the concrete
state backend.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DistributedStatePort(Protocol):
    """Port for distributed atomic state operations.

    Used by the rate limiter (token-bucket Lua), circuit breaker (state-transition
    Lua), run-state manager (SET NX for active-run tracking), and Stripe webhook
    idempotency (SET NX dedup).  Concrete adapters provide Valkey-backed or
    in-memory storage.

    Implemented by:
      - infrastructure.valkey.state_adapter.ValkeyStateAdapter
      - infrastructure.valkey.memory_state_adapter.InMemoryStateAdapter
    """

    async def ping(self) -> bool:
        """Health check — returns True if the backend is reachable."""
        ...

    async def set_nx(self, key: str, value: str, ttl: int | None = ...) -> bool:
        """Atomic SET-if-not-exists.  Returns True if the key was set."""
        ...

    async def set_ex(self, key: str, value: str, ttl: int) -> None:
        """Set a key with a TTL in seconds."""
        ...

    async def get(self, key: str) -> str | None: ...

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys.  Returns count of keys removed."""
        ...

    async def keys(self, pattern: str) -> list[str]:
        """Return keys matching *pattern*."""
        ...

    async def execute_lua(
        self,
        script_sha: str,
        keys: list[str],
        args: list[Any],
    ) -> Any:
        """Execute a pre-loaded Lua script by SHA digest."""
        ...

    async def register_script(self, script_text: str) -> str:
        """Register a Lua script and return its SHA digest."""
        ...
