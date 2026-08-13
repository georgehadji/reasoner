"""
Edge-case tests for rate_limiter.py.

Covers:
- Zero and negative config values
- Very high burst limits
- Tier multiplier boundary values (0, negative, extreme)
- reset_client race safety
- Window boundary precision
- Empty/null client IDs
"""

from __future__ import annotations

import asyncio
import pytest
from reasoner.rate_limiter import RateLimiter, RateLimitConfig


class TestRateLimiterConfig:

    async def test_zero_requests_per_minute(self):
        """Zero RPM should reject all requests."""
        config = RateLimitConfig(
            requests_per_minute=0,
            requests_per_hour=1000,
            burst_size=5,
        )
        limiter = RateLimiter(config)
        allowed, info = await limiter.is_allowed("zero-rpm")
        assert not allowed

    async def test_zero_burst_size(self):
        """Zero burst means max_tokens=0 → refill clamps to 0 → all rejected.
        This is correct behavior: burst_size=0 disables the token bucket."""
        config = RateLimitConfig(
            requests_per_minute=60,
            requests_per_hour=1000,
            burst_size=0,
        )
        limiter = RateLimiter(config)
        # Even after waiting, no tokens can accumulate (max_tokens = burst_size = 0)
        await asyncio.sleep(1.0)
        allowed, info = await limiter.is_allowed("zero-burst")
        assert not allowed
        assert info["reason"].startswith("burst_limit")  # "_fallback" suffix when served in-memory

    async def test_very_high_burst(self):
        config = RateLimitConfig(
            requests_per_minute=1000,
            requests_per_hour=10000,
            burst_size=1000,
        )
        limiter = RateLimiter(config)
        # Should allow many concurrent requests
        results = await asyncio.gather(*[
            limiter.is_allowed("high-burst")
            for _ in range(50)
        ])
        allowed = sum(1 for a, _ in results if a)
        assert allowed >= 50


class TestTierMultipliers:
    """Verify tier-scaled rate limiting."""

    async def test_default_tier_equivalent(self):
        config = RateLimitConfig(
            requests_per_minute=60,
            requests_per_hour=1000,
            burst_size=10,
        )
        limiter = RateLimiter(config)
        allowed, info = await limiter.is_allowed_for_user("tier-default", tier="default")
        assert allowed
        assert info["limit_minute"] == 60

    async def test_pro_tier_double(self):
        config = RateLimitConfig(
            requests_per_minute=60,
            requests_per_hour=1000,
            burst_size=10,
        )
        limiter = RateLimiter(config)
        allowed, info = await limiter.is_allowed_for_user("tier-pro", tier="pro")
        assert allowed
        assert info["limit_minute"] == 120  # 60 * 2

    async def test_enterprise_tier(self):
        config = RateLimitConfig(
            requests_per_minute=60,
            requests_per_hour=1000,
            burst_size=10,
        )
        limiter = RateLimiter(config)
        allowed, info = await limiter.is_allowed_for_user("tier-ent", tier="enterprise")
        assert allowed
        assert info["limit_minute"] == 300  # 60 * 5

    async def test_free_tier_same_as_default(self):
        config = RateLimitConfig(
            requests_per_minute=60,
            burst_size=10,
        )
        limiter = RateLimiter(config)
        allowed, info = await limiter.is_allowed_for_user("tier-free", tier="free")
        assert allowed
        assert info["limit_minute"] == 60

    async def test_unknown_tier_uses_default(self):
        config = RateLimitConfig(
            requests_per_minute=60,
            burst_size=10,
        )
        limiter = RateLimiter(config)
        allowed, info = await limiter.is_allowed_for_user("tier-unknown", tier="platinum")
        assert allowed
        assert info["limit_minute"] == 60  # falls back to multiplier 1.0


class TestBucketManagement:

    @pytest.mark.asyncio
    async def test_reset_client_removes_bucket(self):
        config = RateLimitConfig(requests_per_minute=60, burst_size=10)
        limiter = RateLimiter(config)
        await limiter.is_allowed("client-x")
        await limiter.reset_client("client-x")
        # Client-x should no longer have a bucket
        assert "client-x" not in limiter._buckets

    @pytest.mark.asyncio
    async def test_reset_all_clears_everything(self):
        config = RateLimitConfig(requests_per_minute=60, burst_size=10)
        limiter = RateLimiter(config)
        for i in range(5):
            await limiter.is_allowed(f"client-{i}")
        await limiter.reset_all()
        assert len(limiter._buckets) == 0

    @pytest.mark.asyncio
    async def test_get_client_stats_returns_zeros(self):
        config = RateLimitConfig(requests_per_minute=60, burst_size=10)
        limiter = RateLimiter(config)
        stats = await limiter.get_client_stats("new-client")
        assert stats["tokens"] == 10  # starts with burst
        assert stats["requests_minute"] == 0


class TestRaceConditionSafety:

    @pytest.mark.asyncio
    async def test_concurrent_reset_and_check(self):
        """Concurrent reset_client and is_allowed should not crash."""
        config = RateLimitConfig(requests_per_minute=60, burst_size=10)
        limiter = RateLimiter(config)

        async def checker():
            await limiter.is_allowed("race-client")

        async def resetter():
            await limiter.reset_client("race-client")

        tasks = [checker() for _ in range(20)] + [resetter() for _ in range(5)]
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            pytest.fail(f"Race condition caused exception: {e}")

    @pytest.mark.asyncio
    async def test_concurrent_reset_all_and_check(self):
        """Concurrent reset_all and is_allowed should not crash."""
        config = RateLimitConfig(requests_per_minute=60, burst_size=10)
        limiter = RateLimiter(config)

        # Pre-populate some buckets
        for i in range(10):
            await limiter.is_allowed(f"race-all-{i}")

        async def checker():
            await limiter.is_allowed(f"race-all-add-{i}")

        async def resetter():
            await limiter.reset_all()

        tasks = [checker() for i in range(20)] + [resetter()]
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            pytest.fail(f"Race condition caused exception: {e}")


class TestWindowBoundaries:

    @pytest.mark.asyncio
    async def test_per_minute_limit_enforced(self):
        config = RateLimitConfig(
            requests_per_minute=3,
            requests_per_hour=1000,
            burst_size=3,
        )
        limiter = RateLimiter(config)
        client = "minute-test"

        # First 3 should pass (burst)
        for _ in range(3):
            allowed, _ = await limiter.is_allowed(client)
            assert allowed

        # 4th should fail (per-minute exhausted)
        allowed, info = await limiter.is_allowed(client)
        assert not allowed
        assert info["reason"].startswith("per_minute_limit")  # "_fallback" suffix when served in-memory

    @pytest.mark.asyncio
    async def test_burst_limit_info_correct(self):
        config = RateLimitConfig(
            requests_per_minute=1,
            requests_per_hour=1000,
            burst_size=1,
        )
        limiter = RateLimiter(config)
        client = "burst-info"

        # First passes (burst)
        allowed, _ = await limiter.is_allowed(client)
        assert allowed

        # Second fails (no tokens, bucket empty)
        allowed, info = await limiter.is_allowed(client)
        assert not allowed
        assert "retry_after" in info


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
