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


@pytest.fixture
def quota_exceeded_sink(monkeypatch):
    """Install a recording quota-exceeded hook; monkeypatch restores the previous one."""
    recorded: list[str] = []
    monkeypatch.setattr(metrics_port, "_QUOTA_EXCEEDED_COUNTER", recorded.append)
    return recorded


@pytest.mark.asyncio
async def test_check_does_not_count_a_denial_it_only_reports(quota_exceeded_sink):
    """GET /quota calls QuotaService.check() as a read-only status query (with a
    fixed tier). check() therefore must not emit reasoner_quota_exceeded_total;
    only the point of rejection (api.dependencies.check_quota) counts.
    """
    repo = FakeQuotaRepository(
        UsageQuota(user_id="u1", tier=SubscriptionTier.FREE, used_queries=20, max_queries=20)
    )
    service = QuotaService(repo)
    result = await service.check("u1", SubscriptionTier.FREE)
    assert result.allowed is False
    assert quota_exceeded_sink == []


@pytest.mark.asyncio
async def test_quota_allowed_does_not_touch_the_metrics_port_hook(quota_exceeded_sink):
    repo = FakeQuotaRepository(
        UsageQuota(user_id="u1", tier=SubscriptionTier.FREE, used_queries=5, max_queries=20)
    )
    service = QuotaService(repo)
    result = await service.check("u1", SubscriptionTier.FREE)
    assert result.allowed is True
    assert quota_exceeded_sink == []


def _check_quota_with(monkeypatch, tier, result):
    """Run api.dependencies.check_quota with a stubbed tier and QuotaService result."""
    from unittest.mock import AsyncMock, MagicMock
    from uuid import uuid4

    from reasoner.api import dependencies
    from reasoner.domain.saas import User

    async def _resolve(_user_id: str):
        return tier

    service = MagicMock()
    service.check = AsyncMock(return_value=result)
    monkeypatch.setattr(dependencies, "_resolve_user_tier", _resolve)
    monkeypatch.setattr(dependencies, "_get_quota_service", lambda: service)
    user = User(id=uuid4(), email="t@example.com", display_name="T", scopes=["read"])
    return dependencies.check_quota(user)


@pytest.mark.asyncio
async def test_check_quota_counts_a_real_rejection_with_the_resolved_tier(
    monkeypatch, quota_exceeded_sink
):
    """The 429 path records the metric once, labelled with the user's real tier."""
    from fastapi import HTTPException

    denied = QuotaResult(allowed=False, remaining=0, retry_after=60, reason="used up")
    with pytest.raises(HTTPException) as exc:
        await _check_quota_with(monkeypatch, SubscriptionTier.PRO, denied)
    assert exc.value.status_code == 429
    assert quota_exceeded_sink == ["pro"]


@pytest.mark.asyncio
async def test_check_quota_does_not_count_an_allowed_request(monkeypatch, quota_exceeded_sink):
    allowed = QuotaResult(allowed=True, remaining=5)
    await _check_quota_with(monkeypatch, SubscriptionTier.FREE, allowed)
    assert quota_exceeded_sink == []
