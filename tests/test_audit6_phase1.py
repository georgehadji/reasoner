"""Audit 6, phase 1 (docs/plans/audit-remediation-6-2026-11-10.md).

Findings 7, 8 (backend half), 9 and 10: a dead webhook branch, exception text in
responses, an unchecked checkout `provider`, and global event stats open to every user.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from reasoner.api import billing_router, dependencies
from reasoner.api.dependencies import get_current_user, require_admin_scope
from reasoner.api.routes import pipelines
from reasoner.application.services.billing_service import BillingService
from reasoner.domain.saas import (
    BillingProvider,
    Subscription,
    SubscriptionStatus,
    SubscriptionTier,
    User,
)
from reasoner.infrastructure.persistence.subscription_repo import PostgresSubscriptionRepository

pytestmark = pytest.mark.unit


def _user(scopes: set[str] | None = None) -> User:
    return User(id=uuid4(), email="u@example.com", scopes=scopes or set())


# ── Finding 7: invoice.payment_succeeded is a no-op ───────────────────────────


@pytest.mark.asyncio
async def test_payment_succeeded_writes_nothing():
    repo = SimpleNamespace(
        set_subscription_status=AsyncMock(),
        upsert_subscription=AsyncMock(),
        sync_quota_for_subscription=AsyncMock(),
    )
    sub = Subscription(
        id=uuid4(),
        user_id=uuid4(),
        tier=SubscriptionTier.PRO,
        status=SubscriptionStatus.ACTIVE,
        stripe_subscription_id="sub_1",
    )
    await BillingService(port=None)._apply_webhook("invoice.payment_succeeded", sub, repo)
    repo.set_subscription_status.assert_not_called()
    repo.upsert_subscription.assert_not_called()
    repo.sync_quota_for_subscription.assert_not_called()


# ── Finding 8: no exception text in responses ────────────────────────────────


@pytest.mark.asyncio
async def test_auth_failure_detail_hides_the_exception(monkeypatch):
    monkeypatch.setattr(
        dependencies, "_resolve_auth_token", AsyncMock(side_effect=RuntimeError("password=hunter2"))
    )
    request = SimpleNamespace(state=SimpleNamespace())
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-key")
    with pytest.raises(HTTPException) as exc:
        await get_current_user(request, creds)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Authentication failed"


def _checkout_client(monkeypatch, service) -> TestClient:
    app = FastAPI()
    app.include_router(billing_router.router)
    app.dependency_overrides[get_current_user] = lambda: _user()
    monkeypatch.setattr(
        PostgresSubscriptionRepository, "get_subscription_by_user", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(billing_router, "_get_stripe_service", lambda: service)
    monkeypatch.setattr(billing_router, "_get_paypal_service", lambda: service)
    return TestClient(app)


def test_checkout_failure_returns_502_without_provider_text(monkeypatch):
    service = SimpleNamespace(create_checkout=AsyncMock(side_effect=RuntimeError("sk_live_secret")))
    res = _checkout_client(monkeypatch, service).post("/api/billing/checkout?tier=pro")
    assert res.status_code == 502
    assert "sk_live_secret" not in res.text


# ── Finding 9: provider is stripe or paypal ──────────────────────────────────


@pytest.mark.parametrize("provider", ["x&checkout=y", "STRIPE ", "", "venmo"])
def test_checkout_rejects_unknown_provider(monkeypatch, provider):
    service = SimpleNamespace(create_checkout=AsyncMock(return_value="https://pay.example/s"))
    res = _checkout_client(monkeypatch, service).post(
        "/api/billing/checkout", params={"tier": "pro", "provider": provider}
    )
    assert res.status_code == 422
    service.create_checkout.assert_not_called()


@pytest.mark.parametrize("provider", list(BillingProvider))
def test_checkout_accepts_both_providers(monkeypatch, provider):
    service = SimpleNamespace(create_checkout=AsyncMock(return_value="https://pay.example/s"))
    res = _checkout_client(monkeypatch, service).post(
        "/api/billing/checkout", params={"tier": "pro", "provider": provider.value}
    )
    assert res.status_code == 200
    assert res.json() == {"checkout_url": "https://pay.example/s", "provider": provider.value}
    assert f"provider={provider.value}" in service.create_checkout.call_args.kwargs["success_url"]


# ── Finding 10: event stats are admin only ───────────────────────────────────


@pytest.mark.asyncio
async def test_require_admin_scope_passes_admin_and_refuses_others():
    admin = _user({"admin"})
    assert await require_admin_scope(admin) is admin
    with pytest.raises(HTTPException) as exc:
        await require_admin_scope(_user({"read", "write"}))
    assert exc.value.status_code == 403


def test_event_stats_route_refuses_a_non_admin():
    app = FastAPI()
    app.include_router(pipelines.router)
    app.dependency_overrides[get_current_user] = lambda: _user({"read"})
    assert TestClient(app).get("/api/events/stats").status_code == 403
