"""Regression tests for BUG-502: check_quota hardcoded every user to FREE.

Billing (Stripe/PayPal webhooks -> subscriptions table) was fully wired, but
check_quota ignored it and passed SubscriptionTier.FREE to QuotaService for
everyone. Paying customers were charged and still got free-tier limits.

These tests pin the entitlement rules:
  - entitled statuses (active/trialing) grant the subscription's tier
  - every other outcome (no row, cancelled, past_due, lookup error) -> FREE
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4, UUID

import pytest

from reasoner.domain.saas import (
    QuotaResult,
    Subscription,
    SubscriptionStatus,
    SubscriptionTier,
    User,
)


def _user() -> User:
    return User(id=uuid4(), email="t@example.com", display_name="T", scopes=["read"])


def _subscription(user_id: UUID, tier: SubscriptionTier, status: SubscriptionStatus) -> Subscription:
    return Subscription(
        id=uuid4(),
        user_id=user_id,
        tier=tier,
        status=status,
        current_period_end=datetime.now(timezone.utc),
    )


@pytest.fixture
def captured_tier(monkeypatch):
    """Capture the tier check_quota passes to QuotaService.check()."""
    from reasoner.api import dependencies

    seen: dict[str, SubscriptionTier] = {}

    async def _check(user_id: str, tier: SubscriptionTier) -> QuotaResult:
        seen["tier"] = tier
        return QuotaResult(allowed=True, remaining=100)

    service = MagicMock()
    service.check = AsyncMock(side_effect=_check)
    monkeypatch.setattr(dependencies, "_get_quota_service", lambda: service)
    return seen


def _stub_repo(monkeypatch, *, returns=None, raises=None):
    from reasoner.api import dependencies

    repo = MagicMock()
    if raises is not None:
        repo.get_subscription_by_user = AsyncMock(side_effect=raises)
    else:
        repo.get_subscription_by_user = AsyncMock(return_value=returns)
    monkeypatch.setattr(dependencies, "_get_subscription_repo", lambda: repo)
    return repo


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING],
)
async def test_entitled_subscription_grants_its_tier(monkeypatch, captured_tier, status):
    """An active or trialing PRO subscriber is quota-checked as PRO, not FREE."""
    from reasoner.api.dependencies import check_quota

    user = _user()
    _stub_repo(monkeypatch, returns=_subscription(user.id, SubscriptionTier.PRO, status))

    await check_quota(user=user)

    assert captured_tier["tier"] == SubscriptionTier.PRO


@pytest.mark.asyncio
async def test_enterprise_tier_is_passed_through(monkeypatch, captured_tier):
    from reasoner.api.dependencies import check_quota

    user = _user()
    _stub_repo(
        monkeypatch,
        returns=_subscription(user.id, SubscriptionTier.ENTERPRISE, SubscriptionStatus.ACTIVE),
    )

    await check_quota(user=user)

    assert captured_tier["tier"] == SubscriptionTier.ENTERPRISE


@pytest.mark.asyncio
async def test_no_subscription_falls_back_to_free(monkeypatch, captured_tier):
    from reasoner.api.dependencies import check_quota

    _stub_repo(monkeypatch, returns=None)

    await check_quota(user=_user())

    assert captured_tier["tier"] == SubscriptionTier.FREE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [SubscriptionStatus.CANCELLED, SubscriptionStatus.PAST_DUE],
)
async def test_unentitled_status_falls_back_to_free(monkeypatch, captured_tier, status):
    """A cancelled/past_due PRO row must not keep granting PRO.

    get_subscription_by_user() returns the newest row with no status filter,
    so the status check has to happen here.
    """
    from reasoner.api.dependencies import check_quota

    user = _user()
    _stub_repo(monkeypatch, returns=_subscription(user.id, SubscriptionTier.PRO, status))

    await check_quota(user=user)

    assert captured_tier["tier"] == SubscriptionTier.FREE


@pytest.mark.asyncio
async def test_lookup_error_falls_back_to_free(monkeypatch, captured_tier):
    """A DB failure must never accidentally grant a paid tier."""
    from reasoner.api.dependencies import check_quota

    _stub_repo(monkeypatch, raises=RuntimeError("db down"))

    await check_quota(user=_user())

    assert captured_tier["tier"] == SubscriptionTier.FREE
