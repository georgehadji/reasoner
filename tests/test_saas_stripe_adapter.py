"""Unit tests for StripeBillingAdapter with mocked stripe module."""

from __future__ import annotations

import os
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from reasoner.domain.saas import SubscriptionTier, SubscriptionStatus
from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter


@pytest.fixture
def adapter():
    os.environ["STRIPE_SECRET_KEY"] = "sk_test_123"
    os.environ["STRIPE_PRO_PRICE_ID"] = "price_pro_123"
    os.environ["STRIPE_ENTERPRISE_PRICE_ID"] = "price_ent_123"
    return StripeBillingAdapter()


@pytest.mark.asyncio
async def test_create_checkout_session(adapter):
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/test"

    with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
        url = await adapter.create_checkout_session(
            user_id="user-1",
            tier=SubscriptionTier.PRO,
            success_url="http://localhost/success",
            cancel_url="http://localhost/cancel",
        )
        assert url == "https://checkout.stripe.com/test"
        mock_create.assert_called_once()
        kwargs = mock_create.call_args.kwargs
        assert kwargs["client_reference_id"] == "user-1"
        assert kwargs["mode"] == "subscription"
        assert kwargs["allow_promotion_codes"] is True


@pytest.mark.asyncio
async def test_create_portal_session(adapter):
    mock_customer = MagicMock()
    mock_customer.id = "cus_123"
    mock_customer.metadata = {"reasoner_user_id": "user-1"}

    mock_customer_list = MagicMock()
    mock_customer_list.auto_paging_iter = lambda: iter([mock_customer])

    mock_portal = MagicMock()
    mock_portal.url = "https://billing.stripe.com/test"

    with patch("stripe.Customer.list", return_value=mock_customer_list) as mock_list, \
         patch("stripe.billing_portal.Session.create", return_value=mock_portal) as mock_create:
        url = await adapter.create_portal_session("user-1", "http://localhost/dashboard")
        assert url == "https://billing.stripe.com/test"
        mock_list.assert_called_once()
        mock_create.assert_called_once_with(customer="cus_123", return_url="http://localhost/dashboard")


@pytest.mark.asyncio
async def test_sync_subscription_checkout_completed(adapter):
    # Pass a plain dict to avoid MagicMock dict-conversion quirks
    mock_sub = {
        "id": "sub_123",
        "status": "active",
        "customer": "cus_123",
        "items": {"data": [{"price": {"id": "price_pro_123"}}]},
        "current_period_end": 1893456000,
    }

    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "12345678-1234-5678-1234-567812345678",
                "subscription": "sub_123",
            }
        },
    }

    with patch("stripe.Subscription.retrieve", return_value=mock_sub), \
         patch.object(adapter, "_tier_from_price", return_value=SubscriptionTier.PRO):
        sub = await adapter.sync_subscription(event)
        assert sub.tier == SubscriptionTier.PRO
        assert sub.status == SubscriptionStatus.ACTIVE
        assert str(sub.user_id) == "12345678-1234-5678-1234-567812345678"
        assert sub.stripe_subscription_id == "sub_123"
        assert sub.current_period_end is not None


@pytest.mark.asyncio
async def test_sync_subscription_deleted(adapter):
    mock_customer = MagicMock()
    mock_customer.metadata = {"reasoner_user_id": "12345678-1234-5678-1234-567812345678"}

    event = {
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_123",
                "customer": "cus_123",
                "status": "canceled",
            }
        },
    }

    with patch("stripe.Customer.retrieve", return_value=mock_customer):
        sub = await adapter.sync_subscription(event)
        assert sub.tier == SubscriptionTier.FREE
        assert sub.status == SubscriptionStatus.CANCELLED
        assert sub.stripe_subscription_id == "sub_123"


@pytest.mark.asyncio
async def test_tier_from_price_unknown(adapter):
    assert adapter._tier_from_price("price_unknown") == SubscriptionTier.FREE


def test_timestamp_to_datetime(adapter):
    ts = 1893456000
    dt = adapter._timestamp_to_datetime(ts)
    assert dt is not None
    assert dt.tzinfo is not None


def test_timestamp_to_datetime_none(adapter):
    assert adapter._timestamp_to_datetime(None) is None
