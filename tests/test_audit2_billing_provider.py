"""PR 3 of docs/plans/audit-remediation-2-2026-10-20.md: BIL-13, BIL-14, BIL-19, SEC-6.

The database-backed rows (BIL-14 rows, BIL-15 ordering, BIL-16 ledger race) are
in tests/integration/test_audit2_billing_pg.py.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import stripe

from reasoner.application.ports.billing_port import UnresolvedBillingOwnerError
from reasoner.domain.saas import (
    CheckoutDecision,
    Subscription,
    SubscriptionStatus,
    SubscriptionTier,
    checkout_allowed,
)
from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter

KEY = "sk_test_123"
USER = str(uuid4())
REPO = "reasoner.infrastructure.billing.stripe_adapter._subscription_repo"


def _customer(metadata=None):
    return stripe.Customer.construct_from({"id": "cus_1", "metadata": metadata or {}}, KEY)


def _stripe_sub(status="active", metadata=None):
    return stripe.Subscription.construct_from({
        "id": "sub_1", "customer": "cus_1", "status": status, "metadata": metadata or {},
        "items": {"data": [{"price": {"id": "price_x"}}]},
    }, KEY)


def _repo(user_id=None):
    return SimpleNamespace(get_user_by_stripe_sub_id=AsyncMock(return_value=user_id))


# ── BIL-13: the owner comes from us, or nobody ─────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_type", ["customer.subscription.updated", "customer.subscription.deleted"],
)
async def test_customer_without_metadata_resolves_through_our_table(event_type):
    event = {"type": event_type, "data": {"object": _stripe_sub().to_dict()}}
    with (
        patch("stripe.Customer.retrieve", return_value=_customer()),
        patch("stripe.Subscription.retrieve", return_value=_stripe_sub()),
        patch(REPO, return_value=_repo(USER)),
    ):
        sub = await StripeBillingAdapter(KEY).sync_subscription(event)
    assert str(sub.user_id) == USER


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ["customer.subscription.deleted", "invoice.payment_failed"])
async def test_unknown_owner_is_unresolved_never_a_random_user(event_type):
    obj = (
        {"subscription": "sub_1"} if event_type == "invoice.payment_failed"
        else _stripe_sub().to_dict()
    )
    event = {"type": event_type, "data": {"object": obj}}
    with (
        patch("stripe.Customer.retrieve", return_value=_customer()),
        patch("stripe.Subscription.retrieve", return_value=_stripe_sub()),
        patch(REPO, return_value=_repo(None)),
    ):
        with pytest.raises(UnresolvedBillingOwnerError):
            await StripeBillingAdapter(KEY).sync_subscription(event)


@pytest.mark.asyncio
async def test_checkout_writes_our_user_id_where_the_resolvers_read_it():
    session = stripe.checkout.Session.construct_from({"url": "https://checkout.example"}, KEY)
    with patch("stripe.checkout.Session.create", return_value=session) as create:
        await StripeBillingAdapter(KEY).create_checkout_session(
            USER, SubscriptionTier.PRO, "https://ok", "https://cancel",
        )
    kwargs = create.call_args.kwargs
    assert kwargs["subscription_data"]["metadata"]["reasoner_user_id"] == USER
    assert kwargs["metadata"]["reasoner_user_id"] == USER


@pytest.mark.asyncio
async def test_checkout_completed_tags_the_customer():
    event = {"type": "checkout.session.completed", "data": {"object": {
        "client_reference_id": USER, "subscription": "sub_1", "customer": "cus_1",
    }}}
    with (
        patch("stripe.Subscription.retrieve", return_value=_stripe_sub()),
        patch("stripe.Customer.modify") as modify,
    ):
        await StripeBillingAdapter(KEY).sync_subscription(event)
    modify.assert_called_once_with("cus_1", metadata={"reasoner_user_id": USER})


@pytest.mark.asyncio
async def test_unresolved_webhook_is_dead_lettered_and_acknowledged(monkeypatch):
    from reasoner.infrastructure.billing import webhooks

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_x")
    event = {"id": "evt_1", "type": "customer.subscription.deleted", "data": {"object": {}}}
    valkey = SimpleNamespace(
        get=AsyncMock(return_value=None), set=AsyncMock(return_value=True),
        setex=AsyncMock(), delete=AsyncMock(),
    )
    record = AsyncMock()
    request = SimpleNamespace(body=AsyncMock(return_value=b"{}"), headers={"stripe-signature": "s"})
    with (
        patch("stripe.Webhook.construct_event", return_value=event),
        patch.object(webhooks, "_db_claim_webhook", AsyncMock(return_value=True)),
        patch.object(webhooks, "_db_release_webhook", AsyncMock()) as release,
        patch.object(webhooks, "get_valkey_pool", return_value=valkey),
        patch.object(webhooks, "_record_webhook_failure", record),
        patch(
            "reasoner.application.services.billing_service.BillingService.handle_webhook",
            AsyncMock(side_effect=UnresolvedBillingOwnerError("nobody")),
        ),
    ):
        assert await webhooks.handle_stripe_webhook(request) == {"status": "ok"}
    record.assert_awaited_once()
    release.assert_not_awaited()  # the claim stays: no retry can do better


# ── BIL-14: one live subscription per user ─────────────────────────────


def _sub(tier, status=SubscriptionStatus.ACTIVE):
    return Subscription(id=uuid4(), user_id=uuid4(), tier=tier, status=status)


@pytest.mark.parametrize("existing,target,expected", [
    (None, SubscriptionTier.PRO, CheckoutDecision.ALLOW),
    (_sub(SubscriptionTier.PRO, SubscriptionStatus.CANCELLED), SubscriptionTier.PRO,
     CheckoutDecision.ALLOW),
    (_sub(SubscriptionTier.FREE), SubscriptionTier.PRO, CheckoutDecision.ALLOW),
    (_sub(SubscriptionTier.PRO), SubscriptionTier.PRO, CheckoutDecision.SAME_PLAN),
    (_sub(SubscriptionTier.PRO), SubscriptionTier.ENTERPRISE, CheckoutDecision.USE_PORTAL),
    (_sub(SubscriptionTier.PRO, SubscriptionStatus.PAST_DUE), SubscriptionTier.ENTERPRISE,
     CheckoutDecision.USE_PORTAL),
])
def test_checkout_policy(existing, target, expected):
    assert checkout_allowed(existing, target) is expected


# ── BIL-19: cancelling what is already cancelled succeeds ──────────────


@pytest.mark.asyncio
async def test_stripe_cancel_of_a_cancelled_subscription_is_a_no_op():
    with (
        patch("stripe.Subscription.retrieve", return_value=_stripe_sub(status="canceled")),
        patch("stripe.Subscription.cancel") as cancel,
    ):
        await StripeBillingAdapter(KEY).cancel_subscription("sub_1")
    cancel.assert_not_called()


@pytest.mark.asyncio
async def test_stripe_cancel_of_a_missing_subscription_succeeds():
    missing = stripe.InvalidRequestError("No such subscription", "id", code="resource_missing")
    with patch("stripe.Subscription.retrieve", side_effect=missing):
        await StripeBillingAdapter(KEY).cancel_subscription("sub_gone")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,text", [(404, "not found"), (422, '{"name":"SUBSCRIPTION_STATUS_INVALID"}')],
)
async def test_paypal_cancel_of_a_gone_subscription_succeeds(status, text):
    from reasoner.infrastructure.billing.paypal_adapter import PayPalBillingAdapter

    response = MagicMock(status_code=status, text=text)
    response.raise_for_status.side_effect = AssertionError("must not raise")
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=response)
    adapter = PayPalBillingAdapter.__new__(PayPalBillingAdapter)
    adapter.base_url = "https://api-m.sandbox.paypal.com"
    adapter._get_access_token = AsyncMock(return_value="t")
    adapter._headers = lambda token: {}
    with patch("httpx.AsyncClient", return_value=client):
        await adapter.cancel_subscription("I-1")


# ── SEC-6: the admin principal ──────────────────────────────────────────


def test_admin_scopes_follow_the_allowlist():
    from reasoner.domain.api_keys import admin_scopes

    uid = uuid4()
    assert admin_scopes(uid, f" other , {str(uid).upper()} ") == frozenset({"admin"})
    assert admin_scopes(uid, "someone-else") == frozenset()
    assert admin_scopes(uid, "") == frozenset()


@pytest.mark.asyncio
@pytest.mark.parametrize("listed,expected", [(True, {"admin"}), (False, set())])
async def test_jwt_login_carries_admin_only_for_allowlisted_users(monkeypatch, listed, expected):
    from reasoner.api import dependencies as deps
    from reasoner.domain.saas import User

    user = User(id=uuid4(), email="a@t.local")
    monkeypatch.setattr(deps.settings, "ADMIN_USER_IDS", str(user.id) if listed else "")
    service = SimpleNamespace(authenticate=AsyncMock(return_value=user))
    with (
        patch.object(deps, "get_auth_adapter", return_value=object()),
        patch.object(deps, "AuthService", return_value=service),
    ):
        resolved = await deps._resolve_auth_token("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.sig")
    assert set(resolved.scopes) == expected


def test_admin_route_accepts_the_allowlisted_principal_in_production(monkeypatch):
    from fastapi import HTTPException

    from reasoner.api.routes import admin

    monkeypatch.setattr(admin.settings, "ENVIRONMENT", "production")
    with patch("reasoner.api.admin_auth.verify_admin_key", return_value=True):
        ok = SimpleNamespace(headers={"X-Admin-Key": "k"}, state=SimpleNamespace(
            user=SimpleNamespace(scopes={"admin"})))
        admin._require_admin(ok)
        plain = SimpleNamespace(headers={"X-Admin-Key": "k"}, state=SimpleNamespace(
            user=SimpleNamespace(scopes=set())))
        with pytest.raises(HTTPException) as denied:
            admin._require_admin(plain)
    assert denied.value.status_code == 403
