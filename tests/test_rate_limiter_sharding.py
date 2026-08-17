"""Tests for RateLimiter concurrent access safety.

Per-client lock sharding (ENABLE_SHARDED_LOCKS / RateLimiter._sharded) was
removed when the limiter moved to a Redis token-bucket script as primary,
with a single in-memory lock (_fallback_lock) only for the fallback path.
"""

from __future__ import annotations

import asyncio
import pytest

from reasoner.rate_limiter import RateLimiter, RateLimitConfig


@pytest.mark.asyncio
async def test_concurrent_checks_for_different_clients_all_succeed():
    """Concurrent is_allowed calls for distinct clients must not deadlock
    or corrupt each other's bucket state under the shared fallback lock."""
    rl = RateLimiter(RateLimitConfig(requests_per_minute=100, burst_size=10))

    async def check(client_id: str):
        return await rl.is_allowed(client_id)

    tasks = [asyncio.create_task(check(f"client-{i}")) for i in range(64)]
    results = await asyncio.gather(*tasks)

    assert all(allowed for allowed, _ in results)
