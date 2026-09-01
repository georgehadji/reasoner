"""QuotaService.check() must honour the *entitlement* tier it is handed.

BUG-502 (tests/test_quota_tier_lookup.py) fixed half of a two-part bug: it made
``check_quota`` resolve the real subscription tier and pass it to
``QuotaService.check``. But ``check`` never used that argument — it sized
``remaining`` from the persisted ``usage_quotas.max_queries`` row instead. The
two disagree in production whenever a subscription stops entitling its tier
without the quota row being re-synced, which is exactly what
``invoice.payment_failed`` / ``BILLING.SUBSCRIPTION.SUSPENDED`` do: they set the
subscription to ``past_due`` and never call ``sync_quota_for_subscription``.

These tests pin the composed rule: the effective ceiling is the *stricter* of
the entitlement tier's limit and the persisted row, and a quota row that has
never been through a monthly reset (``period_start`` is NULL — the column is
nullable and neither INSERT path sets it) must not blow up the check.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from reasoner.application.services.quota_service import QuotaService
from reasoner.domain.saas import QuotaResult, SubscriptionTier, UsageQuota

pytestmark = pytest.mark.unit


class FakeQuotaRepository:
    """Records resets so a test can tell an auto-reset from a silent pass."""

    def __init__(self, quota: UsageQuota):
        self.quota = quota
        self.resets: list[str] = []

    async def get_quota(self, user_id: str) -> UsageQuota:
        return self.quota

    async def check_and_increment(self, user_id: str, preset: str) -> QuotaResult:
        remaining = max(0, self.quota.max_queries - self.quota.used_queries)
        return QuotaResult(allowed=remaining > 0, remaining=remaining)

    async def reset_monthly(self, user_id: str) -> None:
        self.resets.append(user_id)


def _quota(**overrides) -> UsageQuota:
    defaults = dict(
        user_id=uuid4(),
        tier=SubscriptionTier.PRO,
        used_queries=0,
        max_queries=500,
        period_start=datetime.now(UTC).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ),
    )
    defaults.update(overrides)
    return UsageQuota(**defaults)


# ── proof of defect ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_lapsed_pro_row_does_not_grant_pro_quota_to_a_free_tier_caller():
    """The past_due path: entitlement says FREE, the stale row says PRO.

    ``resolve_user_tier`` returns FREE for a past_due subscription, but
    ``invoice.payment_failed`` leaves ``usage_quotas.max_queries`` at 500. The
    caller has already used 100 queries — more than the FREE ceiling of 20 — so
    the run must be refused.
    """
    repo = FakeQuotaRepository(_quota(used_queries=100, max_queries=500))
    service = QuotaService(repo)

    result = await service.check("u1", SubscriptionTier.FREE)

    assert result.allowed is False
    assert result.remaining == 0


@pytest.mark.asyncio
async def test_a_quota_row_with_no_period_start_is_reset_rather_than_crashing():
    """Fresh rows carry period_start = NULL.

    ``usage_quotas.period_start`` is nullable with no default and neither
    INSERT path (``get_quota``'s lazy create, ``sync_quota_for_subscription``'s
    new-user branch) sets it. Comparing None to a datetime raised TypeError,
    which ``check_quota`` swallowed into its "emergency limits" fall-back —
    quota silently stopped being enforced for every new account.
    """
    repo = FakeQuotaRepository(_quota(period_start=None, used_queries=0))
    service = QuotaService(repo)

    result = await service.check("u1", SubscriptionTier.FREE)

    assert result.allowed is True
    assert repo.resets == ["u1"]  # treated as a stale period, not a crash


# ── boundary ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_persisted_row_still_binds_when_it_is_the_stricter_of_the_two():
    """Tier is a ceiling, not a floor: a row capped below the tier wins."""
    repo = FakeQuotaRepository(_quota(used_queries=4, max_queries=5))
    service = QuotaService(repo)

    result = await service.check("u1", SubscriptionTier.PRO)

    assert result.allowed is True
    assert result.remaining == 1


@pytest.mark.asyncio
async def test_an_unlimited_row_is_still_bounded_by_a_non_unlimited_tier():
    """max_queries = -1 must not read as "less than everything" nor as unlimited.

    A downgraded enterprise row keeps -1 until it is re-synced. Under FREE
    entitlement the sentinel must resolve to the FREE ceiling, not to a
    negative ceiling (which denies) and not to unlimited (which fails open).
    """
    repo = FakeQuotaRepository(_quota(used_queries=3, max_queries=-1))
    service = QuotaService(repo)

    result = await service.check("u1", SubscriptionTier.FREE)

    assert result.allowed is True
    assert result.remaining == 17  # 20 - 3


@pytest.mark.asyncio
async def test_enterprise_entitlement_short_circuits_before_any_repository_read():
    repo = FakeQuotaRepository(_quota(used_queries=10_000, max_queries=20))
    service = QuotaService(repo)

    result = await service.check("u1", SubscriptionTier.ENTERPRISE)

    assert result.allowed is True
    assert result.remaining == -1


@pytest.mark.asyncio
async def test_an_unknown_tier_falls_back_to_the_free_ceiling():
    repo = FakeQuotaRepository(_quota(used_queries=25, max_queries=500))
    service = QuotaService(repo)

    result = await service.check("u1", "not-a-tier")  # type: ignore[arg-type]

    assert result.allowed is False


# ── no-regression ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_an_entitled_pro_subscriber_keeps_the_full_pro_allowance():
    """The BUG-502 case must not regress into a FREE-sized ceiling."""
    repo = FakeQuotaRepository(_quota(used_queries=100, max_queries=500))
    service = QuotaService(repo)

    result = await service.check("u1", SubscriptionTier.PRO)

    assert result.allowed is True
    assert result.remaining == 400


@pytest.mark.asyncio
async def test_a_stale_period_still_triggers_the_monthly_auto_reset():
    repo = FakeQuotaRepository(
        _quota(used_queries=20, period_start=datetime.now(UTC) - timedelta(days=60))
    )
    service = QuotaService(repo)

    await service.check("u1", SubscriptionTier.PRO)

    assert repo.resets == ["u1"]


# ── retry_after ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_after_points_at_the_start_of_next_month_not_the_current_clock_time():
    """Retry-After told an exhausted caller to come back up to a day late.

    ``now.replace(day=1) + 32 days`` carries the current time-of-day through to
    the next-month boundary, so the header overshot midnight on the 1st by
    however far into the day the request landed.
    """
    repo = FakeQuotaRepository(_quota(used_queries=20, max_queries=20))
    service = QuotaService(repo)

    result = await service.check("u1", SubscriptionTier.FREE)

    assert result.allowed is False
    now = datetime.now(UTC)
    next_month = (now.replace(day=1) + timedelta(days=32)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    expected = int((next_month - now).total_seconds())
    assert result.retry_after is not None
    assert abs(result.retry_after - expected) <= 2
