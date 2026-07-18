"""Shared Valkey connection pool — canonical replacement for redis/client.py.

Backward-compatible: get_redis / set_redis / close_redis are kept as
deprecated aliases that delegate to the new names and emit DeprecationWarning.
"""

from __future__ import annotations

import os
import warnings
from typing import Optional

import valkey.asyncio as aioredis

_pool: Optional[aioredis.Redis] = None


def get_valkey_pool() -> aioredis.Redis:
    """Get or create the shared Valkey connection pool.

    Reads VALKEY_URL (canonical) with fallback to REDIS_URL (deprecated).
    """
    global _pool
    if _pool is None:
        url = os.environ.get("VALKEY_URL") or os.environ.get(
            "REDIS_URL", "redis://localhost:6379/0"
        )
        max_conn = int(os.environ.get(
            "VALKEY_MAX_CONNECTIONS",
            os.environ.get("REDIS_MAX_CONNECTIONS", "100"),
        ))
        _pool = aioredis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
            max_connections=max_conn,
        )
    return _pool


def set_valkey_pool(client: aioredis.Redis) -> None:
    """Override the Valkey client (useful for tests)."""
    global _pool
    _pool = client


async def close_valkey_pool() -> None:
    """Close the shared Valkey connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ── Deprecated backward-compat aliases ──────────────────────────


def get_redis() -> aioredis.Redis:
    """Deprecated — use get_valkey_pool()."""
    warnings.warn("get_redis() is deprecated; use get_valkey_pool()", DeprecationWarning, stacklevel=2)
    return get_valkey_pool()


def set_redis(client: aioredis.Redis) -> None:
    """Deprecated — use set_valkey_pool()."""
    warnings.warn("set_redis() is deprecated; use set_valkey_pool()", DeprecationWarning, stacklevel=2)
    set_valkey_pool(client)


async def close_redis() -> None:
    """Deprecated — use close_valkey_pool()."""
    warnings.warn("close_redis() is deprecated; use close_valkey_pool()", DeprecationWarning, stacklevel=2)
    await close_valkey_pool()
