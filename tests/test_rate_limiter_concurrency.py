"""Concurrency tests for RateLimiter."""

import asyncio

import pytest

from reasoner.rate_limiter import RateLimitConfig, RateLimiter


class TestRateLimiterConcurrency:
    """Verify token-bucket semantics under concurrent burst."""

    @pytest.mark.asyncio
    async def test_burst_depletes_bucket(self):
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_hour=1000,
            burst_size=5,
        )
        limiter = RateLimiter(config)
        client_id = "burst-client"

        # First 5 should pass (burst allowance)
        results = await asyncio.gather(*[
            limiter.is_allowed(client_id)
            for _ in range(5)
        ])
        allowed = [r[0] for r in results]
        assert all(allowed), "All burst requests should be allowed"

        # 6th should be rejected
        allowed6, info6 = await limiter.is_allowed(client_id)
        assert allowed6 is False

    @pytest.mark.asyncio
    async def test_concurrent_burst_no_overcount(self):
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_hour=1000,
            burst_size=10,
        )
        limiter = RateLimiter(config)
        client_id = "concurrent-client"

        # Fire 20 requests concurrently
        results = await asyncio.gather(*[
            limiter.is_allowed(client_id)
            for _ in range(20)
        ])

        allowed_count = sum(1 for allowed, _ in results if allowed)
        # At most burst_size should be allowed; due to race conditions
        # we allow a small tolerance, but it should never exceed 10.
        assert allowed_count <= 10, f"Expected <=10 allowed, got {allowed_count}"

    @pytest.mark.asyncio
    async def test_different_clients_isolated(self):
        config = RateLimitConfig(
            requests_per_minute=100,
            requests_per_hour=1000,
            burst_size=3,
        )
        limiter = RateLimiter(config)

        # Client A uses all its burst
        for _ in range(3):
            await limiter.is_allowed("client-a")

        # Client A's 4th request should be rejected (burst exhausted)
        allowed_a, _ = await limiter.is_allowed("client-a")
        assert allowed_a is False

        # Client B should still have full burst allowance
        allowed, info = await limiter.is_allowed("client-b")
        assert allowed is True
        assert info["remaining_minute"] == 99
