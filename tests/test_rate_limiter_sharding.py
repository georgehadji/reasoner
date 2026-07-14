"""Tests for RateLimiter lock sharding."""

from __future__ import annotations

import asyncio
import pytest

from reasoner.rate_limiter import RateLimiter, RateLimitConfig


@pytest.mark.asyncio
async def test_sharded_locks_allow_concurrent_access():
    """
    With sharded locks enabled, concurrent checks for different client_ids
    should not block each other.
    """
    import os
    os.environ["ENABLE_SHARDED_LOCKS"] = "true"

    rl = RateLimiter(RateLimitConfig(requests_per_minute=100, burst_size=10))
    assert rl._sharded is True

    async def check(client_id: str):
        return await rl.is_allowed(client_id)

    # Run many concurrent checks for different clients
    tasks = [asyncio.create_task(check(f"client-{i}")) for i in range(64)]
    results = await asyncio.gather(*tasks)

    assert all(allowed for allowed, _ in results)

    del os.environ["ENABLE_SHARDED_LOCKS"]
