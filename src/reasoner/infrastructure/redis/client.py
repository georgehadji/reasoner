"""Shared Redis connection pool for all Redis-backed features."""

from __future__ import annotations

import valkey.asyncio as aioredis

_pool: aioredis.Redis | None = None


def set_redis(client: aioredis.Redis) -> None:
    """Override Redis client (useful for tests)."""
    global _pool
    _pool = client


async def close_redis() -> None:
    """Close the shared Redis connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
