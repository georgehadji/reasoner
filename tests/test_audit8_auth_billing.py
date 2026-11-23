"""Audit 8: auth scope gaps and billing state transitions."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest
from fastapi import HTTPException

from reasoner.api import dependencies as deps
from reasoner.application.services.billing_service import BillingService
from reasoner.domain.api_keys import ACCOUNT_EXPORT_SCOPE, ASSIGNABLE_SCOPES, key_allows
from reasoner.domain.saas import Subscription, SubscriptionStatus, SubscriptionTier, User
from reasoner.infrastructure.billing.paypal_adapter import PayPalBillingAdapter
from reasoner.infrastructure.persistence.subscription_repo import PostgresSubscriptionRepository

pytestmark = pytest.mark.unit


class _Req:
    def __init__(self, auth_method):
        self.state = type("S", (), {"auth_method": auth_method})()


# 1. export needs a scope no key can hold -------------------------------------


def test_export_scope_is_session_only():
    assert not key_allows(ASSIGNABLE_SCOPES, ACCOUNT_EXPORT_SCOPE)


@pytest.mark.asyncio
async def test_run_only_key_is_refused_export_but_jwt_passes():
    guard = deps.require_key_scope(ACCOUNT_EXPORT_SCOPE)
    key_user = User(
        id=uuid4(), email="k@example.com", scopes={"read", "run"}, auth_provider="api_key"
    )
    with pytest.raises(HTTPException) as exc:
        await guard(_Req("api_key"), key_user)
    assert exc.value.status_code == 403
    jwt_user = User(id=uuid4(), email="j@example.com")
    assert await guard(_Req("bearer"), jwt_user) is jwt_user


# 2. a non-JWT, non-rsn_ token is no longer a credential ---------------------


def test_auth_method_is_key_or_bearer():
    assert deps._auth_method("rsn_live_abc") == "api_key"
    assert deps._auth_method("aaaa.bbbb.cccc") == "bearer"


@pytest.mark.asyncio
async def test_read_only_key_cannot_pass_a_delete_guard():
    guard = deps.require_key_scope("account:delete")
    user = User(id=uuid4(), email="l@internal", scopes={"read"})
    with pytest.raises(HTTPException) as exc:
        await guard(_Req("api_key"), user)
    assert exc.value.status_code == 403


@pytest.mark.parametrize("anonymous", [True, False])
@pytest.mark.asyncio
async def test_opaque_bearer_token_is_rejected_even_when_anonymous_runs_allowed(
    monkeypatch, anonymous
):
    monkeypatch.setattr(deps.settings, "ALLOW_ANONYMOUS_RUNS", anonymous)
    with pytest.raises(HTTPException) as exc:
        await deps._resolve_auth_token("legacy-secret")
    assert exc.value.status_code == 401


# 3. email clash is a clear 409 ------------------------------------------------


@pytest.mark.asyncio
async def test_email_clash_fails_the_request_with_409(monkeypatch):
    pool = SimpleNamespace(
        fetchval=AsyncMock(return_value=None),
        execute=AsyncMock(side_effect=asyncpg.UniqueViolationError("users_email_key")),
    )
    monkeypatch.setattr(deps, "_get_provision_pool", AsyncMock(return_value=pool))
    deps._provisioned_user_ids.clear()
    user = User(id=uuid4(), email="taken@example.com")
    with pytest.raises(HTTPException) as exc:
        await deps._ensure_user_in_db(user)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "email_conflict"
    assert user.id not in deps._provisioned_user_ids


# 4. PayPal past_due recovers on a successful retry ------------------------------


class _PayPalRepo:
    def __init__(self, status):
        self.status = status
        self.synced = []

    async def reactivate_past_due_by_paypal(self, paypal_id, at):
        assert paypal_id == "I-9"
        if self.status != "past_due":
            return None
        self.status = "active"
        return SimpleNamespace(user_id=uuid4(), tier=SubscriptionTier.PRO)

    async def sync_quota_for_subscription(self, sub):
        self.synced.append(sub)


async def _deliver_sale(repo):
    adapter = PayPalBillingAdapter.__new__(PayPalBillingAdapter)
    event = {
        "event_type": "PAYMENT.SALE.COMPLETED",
        "resource": {"id": "SALE-1", "billing_agreement_id": "I-9"},
    }
    sub = await adapter.sync_subscription(event)
    await BillingService(adapter)._apply_webhook("PAYMENT.SALE.COMPLETED", sub, repo, None)


@pytest.mark.asyncio
async def test_sale_completed_lifts_past_due_and_resyncs_quota():
    repo = _PayPalRepo("past_due")
    await _deliver_sale(repo)
    assert repo.status == "active"
    assert len(repo.synced) == 1


@pytest.mark.asyncio
async def test_sale_completed_on_an_active_subscription_writes_nothing():
    repo = _PayPalRepo("active")
    await _deliver_sale(repo)
    assert repo.synced == []


# 5. a second completed checkout is cancelled, not stored -----------------------


def _stripe_sub(user_id, sub_id):
    return Subscription(
        id=uuid4(), user_id=user_id, tier=SubscriptionTier.PRO,
        status=SubscriptionStatus.ACTIVE, stripe_subscription_id=sub_id,
    )


def _dup_repo(existing):
    return SimpleNamespace(
        get_subscription_by_user=AsyncMock(return_value=existing),
        upsert_subscription=AsyncMock(return_value=True),
        sync_quota_for_subscription=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_second_live_checkout_is_cancelled_at_the_provider():
    uid = uuid4()
    port = SimpleNamespace(cancel_subscription=AsyncMock(), refund_latest_charge=AsyncMock())
    repo = _dup_repo(_stripe_sub(uid, "sub_old"))
    await BillingService(port)._apply_webhook(
        "checkout.session.completed", _stripe_sub(uid, "sub_new"), repo, None
    )
    port.cancel_subscription.assert_awaited_once_with("sub_new")
    repo.upsert_subscription.assert_not_called()


@pytest.mark.asyncio
async def test_redelivery_of_the_same_checkout_still_upserts():
    uid = uuid4()
    port = SimpleNamespace(cancel_subscription=AsyncMock(), refund_latest_charge=AsyncMock())
    repo = _dup_repo(_stripe_sub(uid, "sub_1"))
    await BillingService(port)._apply_webhook(
        "checkout.session.completed", _stripe_sub(uid, "sub_1"), repo, None
    )
    port.cancel_subscription.assert_not_called()
    repo.upsert_subscription.assert_awaited_once()


# 6. quota follows the latest live subscription, not the event's ----------------


class _Conn:
    def __init__(self):
        self.executed = []

    async def fetchrow(self, *_a):
        return {"tier": "pro", "used_queries": 3}

    async def execute(self, sql, *args):
        self.executed.append(args)

    @asynccontextmanager
    async def transaction(self):
        yield


@pytest.mark.asyncio
@pytest.mark.parametrize(("live", "expected"), [("pro", "pro"), (None, "free")])
async def test_late_cancel_does_not_downgrade_a_user_with_a_live_plan(monkeypatch, live, expected):
    conn = _Conn()

    @asynccontextmanager
    async def acquire(timeout=None):
        yield conn

    pool = SimpleNamespace(fetchval=AsyncMock(return_value=live), acquire=acquire)
    monkeypatch.setattr(
        "reasoner.infrastructure.persistence.subscription_repo.get_shared_pool",
        AsyncMock(return_value=pool),
    )
    cancelled_old = Subscription(
        id=uuid4(), user_id=uuid4(), tier=SubscriptionTier.FREE,
        status=SubscriptionStatus.CANCELLED, stripe_subscription_id="sub_old",
    )
    await PostgresSubscriptionRepository("dsn").sync_quota_for_subscription(cancelled_old)
    assert conn.executed[-1][1] == expected


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"ENABLE_LEGACY_API_KEY": "true"}, "True"),  # pre-rename deploys keep working
        ({"ENABLE_LEGACY_API_KEY": "true", "ALLOW_ANONYMOUS_RUNS": "false"}, "False"),
        ({}, "False"),
    ],
)
def test_old_env_var_still_enables_anonymous_runs(env, expected):
    import subprocess
    import sys

    base = {k: v for k, v in os.environ.items() if k not in ("ENABLE_LEGACY_API_KEY", "ALLOW_ANONYMOUS_RUNS")}
    out = subprocess.run(
        [sys.executable, "-c", "from reasoner.core.settings import settings; print(settings.ALLOW_ANONYMOUS_RUNS)"],
        env={**base, **env}, capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == expected
