"""Duplicate-subscription refund, non-USD claw-back skip and PayPal refund events."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from reasoner.application.services import billing_service as bs
from reasoner.application.services.billing_service import PAYPAL_HANDLERS, BillingService
from reasoner.domain.saas import (
    SubscriptionStatus,
    SubscriptionTier,
    UnresolvedBillingOwnerError,
)
from reasoner.infrastructure.billing.paypal_adapter import (
    PAYPAL_EVENT_STATUS,
    PayPalBillingAdapter,
)

pytestmark = pytest.mark.unit


class _Port:
    def __init__(self):
        self.calls = []

    async def cancel_subscription(self, sid):
        self.calls.append(("cancel", sid))

    async def refund_latest_charge(self, sid):
        self.calls.append(("refund", sid))


class _Repo:
    def __init__(self, existing=None, paypal_user=None):
        self.existing, self.paypal_user = existing, paypal_user
        self.upserts = 0

    async def get_subscription_by_user(self, uid):
        return self.existing

    async def upsert_subscription(self, sub, at):
        self.upserts += 1
        return True

    async def sync_quota_for_subscription(self, sub):
        pass

    async def get_user_by_paypal_sub_id(self, pid):
        return self.paypal_user


class _Credits:
    def __init__(self):
        self.charges = []

    async def charge_usd(self, user_id, cost_usd, reference_id, **kw):
        self.charges.append((user_id, cost_usd, reference_id))


@pytest.fixture
def credits():
    svc = _Credits()
    bs.set_credit_service_provider(lambda: svc)
    yield svc
    bs.set_credit_service_provider(None)


def _sub(stripe_id):
    return SimpleNamespace(
        user_id=uuid4(), stripe_subscription_id=stripe_id, tier=SubscriptionTier.PRO,
        status=SubscriptionStatus.ACTIVE, paypal_subscription_id=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("event", ["checkout.session.completed", "customer.subscription.updated"])
async def test_duplicate_live_subscription_is_cancelled_and_refunded(event):
    port, live = _Port(), _sub("sub_old")
    repo = _Repo(existing=live)
    await BillingService(port)._apply_webhook(event, _sub("sub_dup"), repo, None)
    assert port.calls == [("cancel", "sub_dup"), ("refund", "sub_dup")]
    assert repo.upserts == 0


@pytest.mark.asyncio
async def test_same_subscription_update_is_not_a_duplicate():
    port = _Port()
    repo = _Repo(existing=_sub("sub_old"))
    await BillingService(port)._apply_webhook(
        "customer.subscription.updated", _sub("sub_old"), repo, None
    )
    assert port.calls == [] and repo.upserts == 1


@pytest.mark.asyncio
async def test_non_usd_refund_is_not_clawed_back(credits):
    obj = {"id": "ch_1", "amount_refunded": 5000, "currency": "eur"}
    await BillingService(_Port())._apply_webhook("charge.refunded", _sub("s"), _Repo(), None, obj)
    assert credits.charges == []
    obj["currency"] = "usd"
    await BillingService(_Port())._apply_webhook("charge.refunded", _sub("s"), _Repo(), None, obj)
    assert [c[1:] for c in credits.charges] == [(50.0, "refund:ch_1")]


def test_paypal_refund_events_are_rows_in_both_tables():
    for ev in ("PAYMENT.SALE.REFUNDED", "PAYMENT.SALE.REVERSED"):
        assert ev in PAYPAL_HANDLERS and ev in PAYPAL_EVENT_STATUS


@pytest.mark.asyncio
async def test_paypal_refund_claws_back_by_refund_id(credits):
    event = {
        "event_type": "PAYMENT.SALE.REFUNDED",
        "resource": {"id": "RF-1", "billing_agreement_id": "I-1",
                     "amount": {"total": "12.50", "currency": "USD"}},
    }
    sub = await PayPalBillingAdapter.__new__(PayPalBillingAdapter).sync_subscription(event)
    repo = _Repo(paypal_user="user-9")
    await BillingService(_Port())._apply_webhook(
        "PAYMENT.SALE.REFUNDED", sub, repo, None, event["resource"]
    )
    assert credits.charges == [("user-9", 12.5, "refund:RF-1")]


@pytest.mark.asyncio
async def test_paypal_refund_with_unknown_owner_is_unresolved(credits):
    sub = SimpleNamespace(paypal_subscription_id="I-x")
    with pytest.raises(UnresolvedBillingOwnerError):
        await bs._paypal_refund(sub, _Repo(paypal_user=None), None, {"id": "RF-2"})
