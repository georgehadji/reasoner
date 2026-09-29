# tests/test_saas_quota_service.py

import pytest

from reasoner.application.services.quota_service import QuotaService
from reasoner.core.ports import metrics_port
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


@pytest.mark.asyncio
async def test_quota_exceeded_reaches_the_metrics_port_hook():
    """reasoner_quota_exceeded_total (QuotaExceededSpike, alerts.yml) was
    defined and alerted on but never incremented. QuotaService.check() must
    call the core metrics-port hook on the denial path -- not import
    infrastructure.metrics directly, since application/ may not depend on
    infrastructure concretes.
    """
    recorded: list[str] = []
    metrics_port.set_quota_exceeded_counter(recorded.append)
    try:
        repo = FakeQuotaRepository(
            UsageQuota(user_id="u1", tier=SubscriptionTier.FREE, used_queries=20, max_queries=20)
        )
        service = QuotaService(repo)
        result = await service.check("u1", SubscriptionTier.FREE)
        assert result.allowed is False
        assert recorded == ["free"]
    finally:
        metrics_port.set_quota_exceeded_counter(None)


@pytest.mark.asyncio
async def test_quota_exceeded_with_an_unrecognized_tier_still_records_a_metric():
    """test_quota_tier_enforcement.py exercises the free-ceiling fallback with a
    plain string tier (not a SubscriptionTier member). count_quota_exceeded()
    must not assume `.value` exists.
    """
    recorded: list[str] = []
    metrics_port.set_quota_exceeded_counter(recorded.append)
    try:
        repo = FakeQuotaRepository(
            UsageQuota(user_id="u1", tier=SubscriptionTier.FREE, used_queries=20, max_queries=500)
        )
        service = QuotaService(repo)
        result = await service.check("u1", "not-a-tier")  # type: ignore[arg-type]
        assert result.allowed is False
        assert recorded == ["not-a-tier"]
    finally:
        metrics_port.set_quota_exceeded_counter(None)


@pytest.mark.asyncio
async def test_quota_allowed_does_not_touch_the_metrics_port_hook():
    recorded: list[str] = []
    metrics_port.set_quota_exceeded_counter(recorded.append)
    try:
        repo = FakeQuotaRepository(
            UsageQuota(user_id="u1", tier=SubscriptionTier.FREE, used_queries=5, max_queries=20)
        )
        service = QuotaService(repo)
        result = await service.check("u1", SubscriptionTier.FREE)
        assert result.allowed is True
        assert recorded == []
    finally:
        metrics_port.set_quota_exceeded_counter(None)
