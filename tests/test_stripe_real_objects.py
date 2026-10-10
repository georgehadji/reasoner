"""The Stripe adapter driven by real StripeObject instances, not dicts or mocks.

stripe-python 15.0 made StripeObject stop inheriting from dict: no `.get()`,
no `dict(obj)`. Every other billing test mocks `retrieve` with a dict or a
MagicMock, so the adapter broke on the 15.x bump with no red test. These
build the objects the SDK actually returns, via `construct_from`, and need no
network.

They also pin the two fields API version 2025-03-31 moved, which the adapter
must read from either place (webhook payloads follow the endpoint's API
version, `retrieve` follows the SDK's):
- `current_period_end`: subscription -> subscription item
- `subscription` on an invoice: top level -> `parent.subscription_details`
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import stripe

from reasoner.domain.saas import SubscriptionStatus, SubscriptionTier
from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter

USER = "12345678-1234-5678-1234-567812345678"
KEY = "sk_test_fake"
PERIOD_END = 1893456000


def _subscription(**overrides) -> stripe.Subscription:
    data = {
        "id": "sub_1",
        "object": "subscription",
        "customer": "cus_1",
        "status": "active",
        "items": {
            "object": "list",
            "data": [{
                "id": "si_1",
                "object": "subscription_item",
                "price": {"id": "price_pro", "object": "price"},
                "current_period_end": PERIOD_END,
            }],
        },
    }
    data.update(overrides)
    return stripe.Subscription.construct_from(data, KEY)


def _customer() -> stripe.Customer:
    return stripe.Customer.construct_from(
        {"id": "cus_1", "object": "customer", "metadata": {"reasoner_user_id": USER}}, KEY,
    )


@pytest.fixture(autouse=True)
def _prices(monkeypatch):
    monkeypatch.setenv("STRIPE_PRO_PRICE_ID", "price_pro")
    monkeypatch.setenv("STRIPE_ENTERPRISE_PRICE_ID", "price_ent")


@pytest.fixture
def adapter() -> StripeBillingAdapter:
    return StripeBillingAdapter(api_key=KEY)


async def test_checkout_completed_with_a_real_subscription(adapter):
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": USER, "subscription": "sub_1"}},
    }
    with patch("stripe.Subscription.retrieve", return_value=_subscription()):
        sub = await adapter.sync_subscription(event)

    assert sub.tier is SubscriptionTier.PRO
    assert sub.status is SubscriptionStatus.ACTIVE
    assert sub.stripe_customer_id == "cus_1"
    assert sub.current_period_end is not None, "read from the subscription item"


async def test_current_period_end_still_read_from_a_legacy_subscription(adapter):
    legacy = _subscription(current_period_end=PERIOD_END)
    legacy_items = legacy.to_dict()
    legacy_items["items"]["data"][0].pop("current_period_end")
    legacy = stripe.Subscription.construct_from(legacy_items, KEY)
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": USER, "subscription": "sub_1"}},
    }
    with patch("stripe.Subscription.retrieve", return_value=legacy):
        sub = await adapter.sync_subscription(event)

    assert sub.current_period_end is not None


async def test_subscription_updated_reads_metadata_from_a_real_customer(adapter):
    event = {
        "type": "customer.subscription.updated",
        "data": {"object": _subscription().to_dict()},
    }
    with patch("stripe.Customer.retrieve", return_value=_customer()):
        sub = await adapter.sync_subscription(event)

    assert str(sub.user_id) == USER
    assert sub.tier is SubscriptionTier.PRO


async def test_subscription_deleted_reads_metadata_from_a_real_customer(adapter):
    event = {
        "type": "customer.subscription.deleted",
        "data": {"object": _subscription(status="canceled").to_dict()},
    }
    with patch("stripe.Customer.retrieve", return_value=_customer()):
        sub = await adapter.sync_subscription(event)

    assert str(sub.user_id) == USER
    assert sub.status is SubscriptionStatus.CANCELLED


@pytest.mark.parametrize("invoice", [
    {"id": "in_1", "parent": {
        "type": "subscription_details",
        "subscription_details": {"subscription": "sub_1"},
    }},
    {"id": "in_1", "subscription": "sub_1"},  # pre-2025-03-31 payload shape
], ids=["parent", "legacy-top-level"])
async def test_payment_failed_finds_the_subscription(adapter, invoice):
    event = {"type": "invoice.payment_failed", "data": {"object": invoice}}
    with patch("stripe.Subscription.retrieve", return_value=_subscription()) as retrieve, \
         patch("stripe.Customer.retrieve", return_value=_customer()):
        sub = await adapter.sync_subscription(event)

    retrieve.assert_called_once_with("sub_1")
    assert str(sub.user_id) == USER
    assert sub.status is SubscriptionStatus.PAST_DUE


async def test_portal_matches_a_real_customer_by_metadata(adapter):
    customers = stripe.ListObject.construct_from({
        "object": "list",
        "url": "/v1/customers",
        "has_more": False,
        "data": [
            {"id": "cus_other", "object": "customer", "metadata": {}},
            {"id": "cus_1", "object": "customer", "metadata": {"reasoner_user_id": USER}},
        ],
    }, KEY)
    portal = stripe.billing_portal.Session.construct_from({"url": "https://portal.example"}, KEY)
    with patch("stripe.Customer.list", return_value=customers), \
         patch("stripe.billing_portal.Session.create", return_value=portal) as create:
        url = await adapter.create_portal_session(USER, "https://app.example")

    assert url == "https://portal.example"
    assert create.call_args.kwargs["customer"] == "cus_1"


async def test_checkout_uses_allowed_payment_method_types(adapter):
    session = stripe.checkout.Session.construct_from({"url": "https://checkout.example"}, KEY)
    with patch("stripe.checkout.Session.create", return_value=session) as create:
        url = await adapter.create_checkout_session(
            USER, SubscriptionTier.PRO, "https://ok.example", "https://cancel.example",
        )

    assert url == "https://checkout.example"
    kwargs = create.call_args.kwargs
    # stripe-python 16 removed payment_method_types from checkout sessions.
    assert "payment_method_types" not in kwargs
    assert kwargs["allowed_payment_method_types"] == ["card", "link"]
