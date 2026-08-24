"""Unit tests for CachedQuotaRepository with mocked Redis."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from reasoner.domain.saas import QuotaResult, SubscriptionTier, UsageQuota
from reasoner.infrastructure.persistence.cached_quota_repo import CachedQuotaRepository


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def underlying():
    repo = AsyncMock()
    return repo


@pytest.fixture
def cached_repo(underlying, mock_redis, monkeypatch):
    repo = CachedQuotaRepository(underlying)
    repo._redis = mock_redis
    return repo


@pytest.mark.asyncio
async def test_get_quota_cache_hit(cached_repo, mock_redis):
    now = datetime.now(UTC)
    mock_redis.get.return_value = json.dumps({
        "user_id": "11111111-1111-1111-1111-111111111111",
        "tier": "free",
        "used_queries": 5,
        "max_queries": 20,
        "period_start": now.isoformat(),
        "updated_at": now.isoformat(),
    })
    quota = await cached_repo.get_quota("user-1")
    assert quota.used_queries == 5
    assert quota.tier == SubscriptionTier.FREE


@pytest.mark.asyncio
async def test_get_quota_cache_miss(cached_repo, mock_redis, underlying):
    mock_redis.get.return_value = None
    now = datetime.now(UTC)
    underlying.get_quota.return_value = UsageQuota(
        user_id="11111111-1111-1111-1111-111111111111",
        tier=SubscriptionTier.PRO,
        used_queries=10,
        max_queries=500,
        period_start=now,
        updated_at=now,
    )
    quota = await cached_repo.get_quota("user-1")
    assert quota.used_queries == 10
    assert quota.tier == SubscriptionTier.PRO
    mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_check_and_increment_invalidates_cache(cached_repo, mock_redis, underlying):
    underlying.check_and_increment.return_value = QuotaResult(allowed=True, remaining=5)
    result = await cached_repo.check_and_increment("user-1", "preset")
    assert result.allowed is True
    mock_redis.delete.assert_called_once_with("quota:user-1")


@pytest.mark.asyncio
async def test_reset_monthly_invalidates_cache(cached_repo, mock_redis, underlying):
    await cached_repo.reset_monthly("user-1")
    mock_redis.delete.assert_called_once_with("quota:user-1")
