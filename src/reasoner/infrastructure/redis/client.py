"""Shared Redis connection pool for all Redis-backed features."""

from __future__ import annotations

import os
from typing import Optional

import redis.asyncio as aioredis

_pool: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    """Get or create shared Redis client."""
    global _pool
    if _pool is None:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        # Add timeouts to prevent long hangs when Redis is unreachable (Critical for local dev)
        max_conn = int(os.environ.get("REDIS_MAX_CONNECTIONS", "100"))
        _pool = aioredis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
            max_connections=max_conn,
        )
    return _pool


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
