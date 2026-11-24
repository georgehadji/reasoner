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

    async def list_ledger(self, user_id, limit=50, offset=0):
        return [SimpleNamespace(reference_id=c[2]) for c in self.charges]


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
    assert [c[1:] for c in credits.charges] == [(50.0, "refund:ch_1:5000")]


class _StatusRepo(_Repo):
    def __init__(self, existing):
        super().__init__(existing=existing)
        self.statuses = []

    async def set_subscription_status(self, sid, status, at):
        self.statuses.append((sid, status))
        return True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("charge_sub", "expected", "clawed"),
    [
        # Refunded duplicate: it bought no credits and the live one is left alone.
        ("sub_dup", [], []),
        ("sub_live", [("sub_live", "past_due")], [(20.0, "refund:ch_1:2000")]),  # genuine refund
        (None, [("sub_live", "past_due")], [(20.0, "refund:ch_1:2000")]),  # unknown: as before
    ],
)
async def test_full_refund_flips_only_the_subscription_it_paid_for(
    credits, charge_sub, expected, clawed
):
    repo = _StatusRepo(_sub("sub_live"))
    event = SimpleNamespace(user_id=repo.existing.user_id, stripe_subscription_id=charge_sub)
    obj = {"id": "ch_1", "amount_refunded": 2000, "currency": "usd", "refunded": True}
    await BillingService(_Port())._apply_webhook("charge.refunded", event, repo, None, obj)
    assert repo.statuses == expected
    assert [c[1:] for c in credits.charges] == clawed


@pytest.mark.asyncio
async def test_partial_refund_does_not_flip_status():
    repo = _StatusRepo(_sub("sub_live"))
    event = SimpleNamespace(user_id=repo.existing.user_id, stripe_subscription_id="sub_live")
    obj = {"id": "ch_2", "amount_refunded": 500, "currency": "usd", "refunded": False}
    await BillingService(_Port())._apply_webhook("charge.refunded", event, repo, None, obj)
    assert repo.statuses == []


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


def _ended_sub(stripe_id):
    sub = _sub(stripe_id)
    sub.status = SubscriptionStatus.CANCELLED
    return sub


@pytest.mark.asyncio
async def test_update_for_an_ended_subscription_does_not_refund_the_live_one():
    """WS3-1: subscription.updated for ended A while B is live cancels and refunds nothing."""
    port = _Port()
    repo = _Repo(existing=_sub("sub_live"))
    await BillingService(port)._apply_webhook(
        "customer.subscription.updated", _ended_sub("sub_old"), repo, None
    )
    assert port.calls == []


@pytest.mark.asyncio
async def test_second_partial_refund_on_one_charge_is_clawed_back(credits):
    """WS3-3: amount_refunded is cumulative; the second event debits only the new part."""
    sub = _sub("s")
    svc = BillingService(_Port())
    for cents in (500, 2900):
        obj = {"id": "ch_9", "amount_refunded": cents, "currency": "usd"}
        await svc._apply_webhook("charge.refunded", sub, _Repo(), None, obj)
    assert [c[1:] for c in credits.charges] == [
        (5.0, "refund:ch_9:500"),
        (24.0, "refund:ch_9:2900"),
    ]


@pytest.mark.asyncio
async def test_replayed_refund_event_moves_nothing_twice(credits):
    sub = _sub("s")
    obj = {"id": "ch_8", "amount_refunded": 500, "currency": "usd"}
    svc = BillingService(_Port())
    await svc._apply_webhook("charge.refunded", sub, _Repo(), None, obj)
    await svc._apply_webhook("charge.refunded", sub, _Repo(), None, obj)
    assert len(credits.charges) == 1


async def test_refunded_total_is_found_past_the_first_ledger_page():
    """A first partial refund buried under 200+ newer rows still counts."""
    rows = [SimpleNamespace(reference_id=f"run:{i}") for i in range(250)]
    rows.append(SimpleNamespace(reference_id="refund:ch_p:500"))

    class _Ledger:
        async def list_ledger(self, user_id, limit=50, offset=0):
            return rows[offset : offset + limit]

    bs.set_credit_service_provider(lambda: _Ledger())
    try:
        assert await bs._refunded_cents_so_far("u", "ch_p", 2900) == 500
    finally:
        bs.set_credit_service_provider(None)
