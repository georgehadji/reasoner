"""ValkeyStateAdapter — implements DistributedStatePort backed by Valkey.

Used for rate limiter (token-bucket Lua), circuit breaker (state-transition
Lua), run-state manager (SET NX), and Stripe webhook idempotency (SET NX).
"""

from __future__ import annotations

import logging
from typing import Any

from reasoner.core.ports.distributed_state_port import DistributedStatePort
from reasoner.infrastructure.valkey.client import get_valkey_pool

logger = logging.getLogger(__name__)


class ValkeyStateAdapter:
    """Distributed state adapter backed by Valkey (Redis-compatible)."""

    def __init__(self) -> None:
        self._client = get_valkey_pool()
        self._scripts: dict[str, Any] = {}

    async def ping(self) -> bool:
        try:
            return await self._client.ping()
        except Exception as exc:
            logger.debug("Valkey ping failed: %s", exc)
            return False

    async def set_nx(self, key: str, value: str, ttl: int | None = None) -> bool:
        """Atomic SET-if-not-exists. Returns True if the key was set."""
        try:
            if ttl is not None:
                # SET key value NX EX ttl
                result = await self._client.set(key, value, nx=True, ex=ttl)
            else:
                result = await self._client.set(key, value, nx=True)
            return bool(result)
        except Exception as exc:
            logger.debug("Valkey set_nx(%s) failed: %s", key, exc)
            return False

    async def set_ex(self, key: str, value: str, ttl: int) -> None:
        try:
            await self._client.setex(key, ttl, value)
        except Exception as exc:
            logger.debug("Valkey set_ex(%s) failed: %s", key, exc)

    async def get(self, key: str) -> str | None:
        try:
            return await self._client.get(key)
        except Exception as exc:
            logger.debug("Valkey get(%s) failed: %s", key, exc)
            return None

    async def delete(self, *keys: str) -> int:
        """Delete one or more keys. Returns count removed."""
        try:
            if keys:
                return await self._client.delete(*keys)
            return 0
        except Exception as exc:
            logger.debug("Valkey delete(%s) failed: %s", keys, exc)
            return 0

    async def keys(self, pattern: str) -> list[str]:
        try:
            return [k async for k in self._client.scan_iter(match=pattern)]
        except Exception as exc:
            logger.debug("Valkey keys(%s) failed: %s", pattern, exc)
            return []

    async def execute_lua(
        self,
        script_sha: str,
        keys: list[str],
        args: list[Any],
    ) -> Any:
        """Execute a pre-loaded Lua script by SHA digest."""
        try:
            return await self._client.evalsha(script_sha, len(keys), *keys, *args)
        except Exception as exc:
            logger.debug("Valkey execute_lua failed: %s", exc)
            raise

    async def register_script(self, script_text: str) -> str:
        """Register a Lua script and return its SHA digest."""
        try:
            script = self._client.register_script(script_text)
            sha = script.sha
            self._scripts[sha] = script
            return sha
        except Exception as exc:
            logger.debug("Valkey register_script failed: %s", exc)
            raise


# Verify protocol conformance at import time
_: DistributedStatePort = ValkeyStateAdapter()  # type: ignore[assignment]
