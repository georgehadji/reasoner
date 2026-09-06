"""CachedQuotaRepository must not change the type of UsageQuota.tier.

T2 persistence defect hunt (docs/reports/defect-hunt-2026-09-01/
T2-persistence.md), defect T2-D6: the cache-hit path rebuilt UsageQuota with
``tier=data["tier"]`` -- a plain ``str`` -- while ``UsageQuota.tier`` is
declared ``SubscriptionTier`` and the cache-miss path returns the enum. A
warm cache therefore handed callers a differently-typed object than a cold
one, and any ``quota.tier.value`` raised AttributeError.

Only the Redis transport is faked here; the serialize/deserialize pair under
test runs for real.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from reasoner.domain.saas import SubscriptionTier, UsageQuota


class _FakeRedis:
    """Minimal get/setex/delete stand-in for the Valkey pool."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


class _StubQuotaRepo:
    """Underlying repository that always returns an enum-typed quota."""

    def __init__(self, quota: UsageQuota) -> None:
        self.quota = quota
        self.calls = 0

    async def get_quota(self, user_id: str) -> UsageQuota:
        self.calls += 1
        return self.quota

    async def check_and_increment(self, user_id: str, preset: str): ...
    async def reset_monthly(self, user_id: str) -> None: ...
    async def log_query(self, *args, **kwargs) -> None: ...


@pytest.fixture
def quota() -> UsageQuota:
    now = datetime.now(UTC)
    return UsageQuota(
        user_id=uuid4(),
        tier=SubscriptionTier.PRO,
        used_queries=3,
        max_queries=100,
        period_start=now,
        updated_at=now,
    )


@pytest.fixture
def cached_repo(monkeypatch, quota):
    fake = _FakeRedis()
    monkeypatch.setattr(
        "reasoner.infrastructure.valkey.client.get_valkey_pool", lambda: fake
    )
    monkeypatch.setattr(
        "reasoner.infrastructure.persistence.cached_quota_repo.get_valkey_pool",
        lambda: fake,
    )
    from reasoner.infrastructure.persistence.cached_quota_repo import (
        CachedQuotaRepository,
    )

    underlying = _StubQuotaRepo(quota)
    return CachedQuotaRepository(underlying), underlying, fake


@pytest.mark.asyncio
async def test_cache_hit_returns_the_same_tier_type_as_a_cache_miss(
    cached_repo, quota
):
    """PROOF OF DEFECT (T2-D6): cache hit must yield SubscriptionTier, not str."""
    repo, underlying, _fake = cached_repo
    user_id = str(quota.user_id)

    miss = await repo.get_quota(user_id)      # populates the cache
    hit = await repo.get_quota(user_id)       # served from the cache

    assert underlying.calls == 1, "second read should have been served from cache"
    assert isinstance(miss.tier, SubscriptionTier)
    assert isinstance(hit.tier, SubscriptionTier)
    assert type(hit.tier) is type(miss.tier)
    assert hit.tier.value == miss.tier.value == "pro"


@pytest.mark.asyncio
async def test_cached_quota_round_trips_every_field(cached_repo, quota):
    """BOUNDARY (T2-D6): the rest of the payload must survive the round trip."""
    repo, _underlying, _fake = cached_repo
    user_id = str(quota.user_id)

    await repo.get_quota(user_id)
    hit = await repo.get_quota(user_id)

    assert hit.user_id == quota.user_id
    assert hit.used_queries == quota.used_queries
    assert hit.max_queries == quota.max_queries
    assert hit.period_start == quota.period_start
    assert hit.updated_at == quota.updated_at


@pytest.mark.asyncio
async def test_free_tier_round_trips(monkeypatch, quota):
    """BOUNDARY (T2-D6): the default tier, whose value differs from its name."""
    fake = _FakeRedis()
    monkeypatch.setattr(
        "reasoner.infrastructure.persistence.cached_quota_repo.get_valkey_pool",
        lambda: fake,
    )
    from reasoner.infrastructure.persistence.cached_quota_repo import (
        CachedQuotaRepository,
    )

    free = UsageQuota(
        user_id=quota.user_id,
        tier=SubscriptionTier.FREE,
        period_start=quota.period_start,
        updated_at=quota.updated_at,
    )
    repo = CachedQuotaRepository(_StubQuotaRepo(free))
    user_id = str(free.user_id)

    await repo.get_quota(user_id)
    hit = await repo.get_quota(user_id)

    assert hit.tier is SubscriptionTier.FREE


@pytest.mark.asyncio
async def test_unreadable_cache_entry_falls_back_to_the_database(
    monkeypatch, cached_repo, quota
):
    """NO-REGRESSION (T2-D6): a corrupt cache entry must not raise.

    SubscriptionTier(<garbage>) raises ValueError, which the existing
    try/except in get_quota must keep absorbing into a DB read.
    """
    repo, underlying, fake = cached_repo
    user_id = str(quota.user_id)

    await repo.get_quota(user_id)
    key = f"quota:{user_id}"
    fake.store[key] = fake.store[key].replace('"pro"', '"not-a-tier"')

    result = await repo.get_quota(user_id)

    assert isinstance(result.tier, SubscriptionTier)
    assert underlying.calls == 2, "corrupt entry should have forced a DB read"


@pytest.mark.asyncio
async def test_write_paths_still_invalidate_the_cache(cached_repo, quota):
    """NO-REGRESSION: invalidation behaviour is untouched by the type fix."""
    repo, _underlying, fake = cached_repo
    user_id = str(quota.user_id)

    await repo.get_quota(user_id)
    assert f"quota:{user_id}" in fake.store

    await repo.reset_monthly(user_id)
    assert f"quota:{user_id}" not in fake.store
