# tests/test_saas_domain.py
from uuid import uuid4

import pytest

from reasoner.domain.saas import (
    QuotaResult,
    SubscriptionTier,
    User,
)


class TestSubscriptionTier:
    def test_tier_values(self):
        assert SubscriptionTier.FREE.value == "free"
        assert SubscriptionTier.PRO.value == "pro"
        assert SubscriptionTier.ENTERPRISE.value == "enterprise"


class TestUser:
    def test_user_is_frozen(self):
        user = User(id=uuid4(), email="test@example.com")
        with pytest.raises(AttributeError):
            user.email = "other@example.com"


class TestQuotaResult:
    def test_allowed_result(self):
        qr = QuotaResult(allowed=True, remaining=5)
        assert qr.allowed is True
        assert qr.remaining == 5

    def test_denied_result(self):
        qr = QuotaResult(allowed=False, remaining=0, retry_after=3600, reason="Exceeded")
        assert qr.allowed is False
        assert qr.retry_after == 3600
