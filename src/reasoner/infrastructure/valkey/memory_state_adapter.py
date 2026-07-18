"""InMemoryStateAdapter — implements DistributedStatePort backed by a local dict.

Used as fallback when Valkey is unavailable in single-worker/dev mode.
Lua scripts are not supported — execute_lua raises NotImplementedError.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from reasoner.core.ports.distributed_state_port import DistributedStatePort


class InMemoryStateAdapter:
    """In-memory distributed state adapter implementing DistributedStatePort.

    Suitable for single-worker development.  Not shared across workers.
    Lua script execution is NOT supported — callers must handle
    NotImplementedError for execute_lua / register_script.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}  # key → (value, expires_at)

    async def ping(self) -> bool:
        return True

    async def set_nx(self, key: str, value: str, ttl: int | None = None) -> bool:
        """Atomic SET-if-not-exists. Returns True if the key was set."""
        entry = self._store.get(key)
        if entry is not None:
            _, expires_at = entry
            if expires_at is None or time.monotonic() <= expires_at:
                return False
        expires_at = time.monotonic() + ttl if ttl is not None else None
        self._store[key] = (value, expires_at)
        return True

    async def set_ex(self, key: str, value: str, ttl: int) -> None:
        expires_at = time.monotonic() + ttl
        self._store[key] = (value, expires_at)

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at is not None and time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                count += 1
        return count

    async def keys(self, pattern: str) -> list[str]:
        import fnmatch
        return [k for k in self._store if fnmatch.fnmatch(k, pattern)]

    async def execute_lua(
        self,
        script_sha: str,
        keys: list[str],
        args: list[Any],
    ) -> Any:
        """Lua scripts are not supported by the in-memory adapter."""
        raise NotImplementedError(
            "InMemoryStateAdapter does not support Lua script execution. "
            "Use ValkeyStateAdapter for distributed atomic operations."
        )

    async def register_script(self, script_text: str) -> str:
        """Lua scripts are not supported by the in-memory adapter."""
        sha = hashlib.sha1(script_text.encode()).hexdigest()
        return sha


# Verify protocol conformance
_: DistributedStatePort = InMemoryStateAdapter()  # type: ignore[assignment]
