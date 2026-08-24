"""
SaaS Rate Limit User Bucketing Tests — Phase 2

Validates:
- RateLimiter.is_allowed_for_user applies tier multipliers
- Authenticated requests use user:{id} bucket key
"""

from __future__ import annotations

import pytest

from reasoner.rate_limiter import RateLimitConfig, RateLimiter


@pytest.fixture
def rate_limiter():
    return RateLimiter(
        RateLimitConfig(
            requests_per_minute=10,
            requests_per_hour=100,
            burst_size=5,
        )
    )


@pytest.mark.asyncio
async def test_is_allowed_for_user_default_tier(rate_limiter):
    allowed, info = await rate_limiter.is_allowed_for_user("user-123", tier="default")
    assert allowed is True
    assert info["limit_minute"] == 10


@pytest.mark.asyncio
async def test_is_allowed_for_user_pro_tier(rate_limiter):
    allowed, info = await rate_limiter.is_allowed_for_user("user-123", tier="pro")
    assert allowed is True
    assert info["limit_minute"] == 20  # 2x multiplier


@pytest.mark.asyncio
async def test_is_allowed_for_user_enterprise_tier(rate_limiter):
    allowed, info = await rate_limiter.is_allowed_for_user("user-123", tier="enterprise")
    assert allowed is True
    assert info["limit_minute"] == 50  # 5x multiplier


@pytest.mark.asyncio
async def test_is_allowed_for_user_restores_config(rate_limiter):
    original = rate_limiter.config
    await rate_limiter.is_allowed_for_user("user-123", tier="pro")
    # Config should be restored to original after the call
    assert rate_limiter.config.requests_per_minute == original.requests_per_minute
    assert rate_limiter.config.requests_per_hour == original.requests_per_hour
    assert rate_limiter.config.burst_size == original.burst_size


@pytest.mark.asyncio
async def test_user_bucket_is_separate_from_anonymous(rate_limiter):
    # Exhaust anonymous bucket
    for _ in range(5):
        await rate_limiter.is_allowed("anon-1")

    # User bucket should still be fresh
    allowed, _ = await rate_limiter.is_allowed_for_user("user-456", tier="default")
    assert allowed is True
