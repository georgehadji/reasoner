# tests/test_saas_quota_service.py

import pytest

from reasoner.application.services.quota_service import QuotaService
from reasoner.domain.saas import QuotaResult, SubscriptionTier, UsageQuota


class FakeQuotaRepository:
    def __init__(self, quota: UsageQuota):
        self.quota = quota

    async def get_quota(self, user_id: str) -> UsageQuota:
        return self.quota

    async def check_and_increment(self, user_id: str, preset: str) -> QuotaResult:
        remaining = max(0, self.quota.max_queries - self.quota.used_queries)
        allowed = remaining > 0
        return QuotaResult(allowed=allowed, remaining=remaining)

    async def reset_monthly(self, user_id: str) -> None:
        # Note: UsageQuota is frozen, so we'd normally replace it.
        # But for this simple fake we can just keep it as is or mock replace logic.
        # In a real test we might want to use a non-frozen fake if we need to mutate.
        pass


@pytest.mark.asyncio
async def test_quota_service_enterprise_unlimited():
    repo = FakeQuotaRepository(
        UsageQuota(user_id="u1", tier=SubscriptionTier.ENTERPRISE, max_queries=-1)
    )
    service = QuotaService(repo)
    result = await service.check("u1", SubscriptionTier.ENTERPRISE)
    assert result.allowed is True
    assert result.remaining == -1


@pytest.mark.asyncio
async def test_quota_service_free_blocks_when_exhausted():
    repo = FakeQuotaRepository(
        UsageQuota(user_id="u1", tier=SubscriptionTier.FREE, used_queries=20, max_queries=20)
    )
    service = QuotaService(repo)
    result = await service.check("u1", SubscriptionTier.FREE)
    assert result.allowed is False
    assert result.remaining == 0
    assert result.reason is not None


@pytest.mark.asyncio
async def test_quota_service_free_allows_when_under_limit():
    repo = FakeQuotaRepository(
        UsageQuota(user_id="u1", tier=SubscriptionTier.FREE, used_queries=5, max_queries=20)
    )
    service = QuotaService(repo)
    result = await service.check("u1", SubscriptionTier.FREE)
    assert result.allowed is True
    assert result.remaining == 15
