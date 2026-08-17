"""Unit tests for CachedSubscriptionRepository with mocked Redis.

The cache sits in front of the subscription read that gates every quota
check, so these tests pin both the caching behaviour and the fail-safe
contract: the cache may never invent a subscription, and a Redis outage
must degrade to the database rather than to a wrong tier.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from reasoner.domain.saas import Subscription, SubscriptionStatus, SubscriptionTier
from reasoner.infrastructure.persistence.cached_subscription_repo import (
    CACHE_TTL_SECONDS,
    CachedSubscriptionRepository,
    invalidate_subscription,
)

USER_ID = "11111111-1111-1111-1111-111111111111"


def _subscription(
    tier: SubscriptionTier = SubscriptionTier.PRO,
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE,
) -> Subscription:
    return Subscription(
        id=uuid4(),
        user_id=UUID(USER_ID),
        tier=tier,
        status=status,
        stripe_subscription_id="sub_123",
        stripe_customer_id="cus_123",
        current_period_end=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def underlying():
    return AsyncMock()


@pytest.fixture
def cached_repo(underlying, mock_redis):
    repo = CachedSubscriptionRepository(underlying)
    repo._redis = mock_redis
    return repo


@pytest.mark.asyncio
async def test_cache_miss_reads_db_and_populates_cache(cached_repo, mock_redis, underlying):
    mock_redis.get.return_value = None
    underlying.get_subscription_by_user.return_value = _subscription()

    sub = await cached_repo.get_subscription_by_user(USER_ID)

    assert sub.tier == SubscriptionTier.PRO
    underlying.get_subscription_by_user.assert_awaited_once_with(USER_ID)
    key, ttl, _payload = mock_redis.setex.call_args.args
    assert key == f"subscription:{USER_ID}"
    assert ttl == CACHE_TTL_SECONDS


@pytest.mark.asyncio
async def test_cache_hit_skips_db(cached_repo, mock_redis, underlying):
    now = datetime.now(timezone.utc)
    mock_redis.get.return_value = json.dumps({
        "id": str(uuid4()),
        "user_id": USER_ID,
        "tier": "enterprise",
        "status": "active",
        "stripe_subscription_id": "sub_123",
        "stripe_customer_id": "cus_123",
        "paypal_subscription_id": None,
        "current_period_end": now.isoformat(),
        "created_at": now.isoformat(),
    })

    sub = await cached_repo.get_subscription_by_user(USER_ID)

    assert sub.tier == SubscriptionTier.ENTERPRISE
    assert sub.status == SubscriptionStatus.ACTIVE
    underlying.get_subscription_by_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_roundtrip_preserves_subscription(cached_repo, mock_redis, underlying):
    """What we write to Redis must deserialize back to an equivalent object."""
    mock_redis.get.return_value = None
    original = _subscription(SubscriptionTier.PRO, SubscriptionStatus.TRIALING)
    underlying.get_subscription_by_user.return_value = original

    await cached_repo.get_subscription_by_user(USER_ID)
    _key, _ttl, payload = mock_redis.setex.call_args.args

    mock_redis.get.return_value = payload
    restored = await cached_repo.get_subscription_by_user(USER_ID)

    assert restored == original


@pytest.mark.asyncio
async def test_absent_subscription_is_cached(cached_repo, mock_redis, underlying):
    """The free-tier path (no subscription row) is the hot one — cache it."""
    mock_redis.get.return_value = None
    underlying.get_subscription_by_user.return_value = None

    assert await cached_repo.get_subscription_by_user(USER_ID) is None

    _key, _ttl, payload = mock_redis.setex.call_args.args
    mock_redis.get.return_value = payload
    underlying.get_subscription_by_user.reset_mock()

    assert await cached_repo.get_subscription_by_user(USER_ID) is None
    underlying.get_subscription_by_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_redis_read_failure_falls_back_to_db(cached_repo, mock_redis, underlying):
    mock_redis.get.side_effect = RuntimeError("redis down")
    underlying.get_subscription_by_user.return_value = _subscription()

    sub = await cached_repo.get_subscription_by_user(USER_ID)

    assert sub.tier == SubscriptionTier.PRO


@pytest.mark.asyncio
async def test_corrupt_cache_entry_falls_back_to_db(cached_repo, mock_redis, underlying):
    mock_redis.get.return_value = "{not json"
    underlying.get_subscription_by_user.return_value = _subscription()

    sub = await cached_repo.get_subscription_by_user(USER_ID)

    assert sub.tier == SubscriptionTier.PRO
    underlying.get_subscription_by_user.assert_awaited_once_with(USER_ID)


@pytest.mark.asyncio
async def test_redis_write_failure_still_returns_db_value(cached_repo, mock_redis, underlying):
    mock_redis.get.return_value = None
    mock_redis.setex.side_effect = RuntimeError("redis down")
    underlying.get_subscription_by_user.return_value = _subscription()

    sub = await cached_repo.get_subscription_by_user(USER_ID)

    assert sub.tier == SubscriptionTier.PRO


@pytest.mark.asyncio
async def test_db_error_propagates_to_caller(cached_repo, mock_redis, underlying):
    """The cache must not swallow DB errors — check_quota turns them into FREE."""
    mock_redis.get.return_value = None
    underlying.get_subscription_by_user.side_effect = RuntimeError("db down")

    with pytest.raises(RuntimeError):
        await cached_repo.get_subscription_by_user(USER_ID)


@pytest.mark.asyncio
async def test_invalidate_deletes_cache_key(monkeypatch):
    redis = AsyncMock()
    monkeypatch.setattr(
        "reasoner.infrastructure.persistence.cached_subscription_repo.get_valkey_pool",
        lambda: redis,
    )

    await invalidate_subscription(USER_ID)

    redis.delete.assert_awaited_once_with(f"subscription:{USER_ID}")


@pytest.mark.asyncio
async def test_invalidate_never_raises(monkeypatch):
    """A Redis outage must not fail the webhook that triggered invalidation."""
    redis = AsyncMock()
    redis.delete.side_effect = RuntimeError("redis down")
    monkeypatch.setattr(
        "reasoner.infrastructure.persistence.cached_subscription_repo.get_valkey_pool",
        lambda: redis,
    )

    await invalidate_subscription(USER_ID)
