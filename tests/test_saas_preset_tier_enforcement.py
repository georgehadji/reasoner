"""Tests for premium preset tier enforcement (SEC-017).

Premium presets are open to all users by default, so check_preset_access must
never raise regardless of subscription tier unless an operator opts in via
PRESET_TIER_ENFORCEMENT_ENABLED. See TestPresetTierEnforcement in
test_saas_preset_tiers.py for the enabled behaviour.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from reasoner.api.dependencies import check_preset_access
from reasoner.domain.saas import Subscription, SubscriptionStatus, SubscriptionTier, User


@pytest.fixture
def free_user() -> User:
    return User(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        email="free@example.com",
    )


@pytest.fixture
def pro_user() -> User:
    return User(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        email="pro@example.com",
    )


@pytest.fixture
def enterprise_user() -> User:
    return User(
        id=UUID("33333333-3333-3333-3333-333333333333"),
        email="enterprise@example.com",
    )


@pytest.mark.asyncio
async def test_free_preset_accessible_to_all(free_user):
    """Free-tier presets are accessible to all users."""
    result = await check_preset_access("auto-budget", user=free_user)
    assert result is None


@pytest.mark.asyncio
async def test_premium_preset_allowed_for_free_user(free_user):
    """Free users can access premium-tier presets."""
    with patch(
        "reasoner.infrastructure.persistence.subscription_repo.PostgresSubscriptionRepository"
    ) as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_subscription_by_user.return_value = None
        mock_repo_cls.return_value = mock_repo

        result = await check_preset_access("debate-premium", user=free_user)
        assert result is None


@pytest.mark.asyncio
async def test_premium_preset_allowed_for_pro_user(pro_user):
    """Pro users can access premium-tier presets."""
    with patch(
        "reasoner.infrastructure.persistence.subscription_repo.PostgresSubscriptionRepository"
    ) as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_subscription_by_user.return_value = Subscription(
            id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            user_id=pro_user.id,
            tier=SubscriptionTier.PRO,
            status=SubscriptionStatus.ACTIVE,
        )
        mock_repo_cls.return_value = mock_repo

        result = await check_preset_access("debate-premium", user=pro_user)
        assert result is None


@pytest.mark.asyncio
async def test_enterprise_preset_allowed_for_pro_user(pro_user):
    """Pro users can access enterprise-tier presets."""
    with patch(
        "reasoner.infrastructure.persistence.subscription_repo.PostgresSubscriptionRepository"
    ) as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_subscription_by_user.return_value = Subscription(
            id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            user_id=pro_user.id,
            tier=SubscriptionTier.PRO,
            status=SubscriptionStatus.ACTIVE,
        )
        mock_repo_cls.return_value = mock_repo

        with patch(
            "reasoner.api.dependencies.get_preset_tier",
            return_value=SubscriptionTier.ENTERPRISE,
        ):
            result = await check_preset_access("fake-enterprise-preset", user=pro_user)
            assert result is None


@pytest.mark.asyncio
async def test_enterprise_preset_allowed_for_enterprise_user(enterprise_user):
    """Enterprise users can access enterprise-tier presets."""
    with patch(
        "reasoner.infrastructure.persistence.subscription_repo.PostgresSubscriptionRepository"
    ) as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_subscription_by_user.return_value = Subscription(
            id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            user_id=enterprise_user.id,
            tier=SubscriptionTier.ENTERPRISE,
            status=SubscriptionStatus.ACTIVE,
        )
        mock_repo_cls.return_value = mock_repo

        with patch(
            "reasoner.api.dependencies.get_preset_tier",
            return_value=SubscriptionTier.ENTERPRISE,
        ):
            result = await check_preset_access("fake-enterprise-preset", user=enterprise_user)
            assert result is None


@pytest.mark.asyncio
async def test_cancelled_subscription_allowed(free_user):
    """A cancelled subscription does not block preset access."""
    with patch(
        "reasoner.infrastructure.persistence.subscription_repo.PostgresSubscriptionRepository"
    ) as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_subscription_by_user.return_value = Subscription(
            id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            user_id=free_user.id,
            tier=SubscriptionTier.PRO,
            status=SubscriptionStatus.CANCELLED,
        )
        mock_repo_cls.return_value = mock_repo

        result = await check_preset_access("debate-premium", user=free_user)
        assert result is None


@pytest.mark.asyncio
async def test_db_unavailable_still_allows_access(free_user):
    """If the subscription DB is unavailable, preset access is still allowed."""
    with patch(
        "reasoner.infrastructure.persistence.subscription_repo.PostgresSubscriptionRepository",
        side_effect=Exception("DB down"),
    ):
        result = await check_preset_access("debate-premium", user=free_user)
        assert result is None
