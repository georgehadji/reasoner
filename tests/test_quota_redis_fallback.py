"""Tests for CachedQuotaRepository Redis fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reasoner.domain.saas import SubscriptionTier, UsageQuota
from reasoner.infrastructure.cached_quota_repo import CachedQuotaRepository


@pytest.mark.asyncio
async def test_redis_down_falls_back_to_db():
    """
    When Redis raises ConnectionError, get_quota should still succeed
    by falling back to the underlying repository.
    """
    fake_redis = AsyncMock()
    fake_redis.get.side_effect = ConnectionError("redis is down")
    fake_redis.setex = AsyncMock()
    fake_redis.delete = AsyncMock()

    expected_quota = UsageQuota(
        user_id="user-1",
        tier=SubscriptionTier.PRO,
        max_queries=1000,
        used_queries=42,
    )
    fallback = AsyncMock()
    fallback.get_quota = AsyncMock(return_value=expected_quota)

    repo = CachedQuotaRepository(fake_redis, fallback)
    quota = await repo.get_quota("user-1")

    assert quota.used_queries == 42
    fallback.get_quota.assert_awaited_once_with("user-1")
