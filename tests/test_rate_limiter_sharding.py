"""Tests for RateLimiter lock sharding."""

from __future__ import annotations

import asyncio
import pytest

from reasoner.rate_limiter import RateLimiter, RateLimitConfig


@pytest.mark.asyncio
async def test_concurrent_access_across_clients_is_allowed():
    """
    Concurrent checks for distinct client_ids must not starve each other.

    Lock sharding was removed when the limiter moved to Redis (which serialises
    per-client state server-side) with a single in-memory fallback lock. The
    behaviour under test is unchanged: distinct clients each get their own bucket,
    so a burst of concurrent first-requests is allowed regardless of backend.
    """
    rl = RateLimiter(RateLimitConfig(requests_per_minute=100, burst_size=10))

    async def check(client_id: str):
        return await rl.is_allowed(client_id)

    # Run many concurrent checks for different clients
    tasks = [asyncio.create_task(check(f"client-{i}")) for i in range(64)]
    results = await asyncio.gather(*tasks)

    assert all(allowed for allowed, _ in results)
