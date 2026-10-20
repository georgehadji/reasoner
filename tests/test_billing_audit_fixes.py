"""Billing correctness fixes from the 2026-10-20 audit (BIL-3, BIL-4, BIL-6, BIL-8).

See docs/plans/audit-remediation-2026-10-20.md. Each test names the item it pins.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from reasoner.application.services.credit_service import CreditService
from reasoner.application.services.run_metering import extract_run_cost
from reasoner.domain.credits import allowance_steps, monthly_allowance
from reasoner.domain.saas import SubscriptionTier, User
from reasoner.infrastructure.persistence.credit_repo_memory import InMemoryCreditRepository

_USER = "12345678-1234-5678-1234-567812345678"


def _frame(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


# ── BIL-3: a cache replay is free ────────────────────────────────────────────


def test_replayed_cost_frames_are_not_billed():
    live = {"type": "done", "total_cost_usd": 0.19}
    assert extract_run_cost(_frame(live)) == pytest.approx(0.19)
    assert extract_run_cost(_frame({**live, "cached": True})) is None
    assert extract_run_cost(_frame({"type": "phase_complete", "total_cost_usd": 0.1,
                                    "cached": True})) is None


# ── BIL-6: the allowance follows the tier ────────────────────────────────────


def test_allowance_steps_sum_to_the_tier_allowance():
    for tier in SubscriptionTier:
        assert sum(c for _, c in allowance_steps(tier)) == monthly_allowance(tier)


@pytest.mark.asyncio
async def test_mid_period_upgrade_grants_the_difference_once():
    service = CreditService(InMemoryCreditRepository())
    nov = datetime(2026, 11, 5, tzinfo=UTC)

    await service.ensure_monthly_allowance(_USER, SubscriptionTier.FREE, now=nov)
    assert (await service.get_balance(_USER)).balance == monthly_allowance(SubscriptionTier.FREE)

    await service.ensure_monthly_allowance(_USER, SubscriptionTier.PRO, now=nov)
    await service.ensure_monthly_allowance(_USER, SubscriptionTier.PRO, now=nov)  # idempotent
    assert (await service.get_balance(_USER)).balance == monthly_allowance(SubscriptionTier.PRO)

    await service.ensure_monthly_allowance(_USER, SubscriptionTier.FREE, now=nov)  # downgrade
    assert (await service.get_balance(_USER)).balance == monthly_allowance(SubscriptionTier.PRO)


@pytest.mark.asyncio
async def test_periods_before_the_cutover_keep_the_single_grant():
    """This period's existing grants used the bare key at the full tier amount;
    switching keys mid-period would double-grant paid users."""
    service = CreditService(InMemoryCreditRepository())
    oct_ = datetime(2026, 10, 20, tzinfo=UTC)
    await service.ensure_monthly_allowance(_USER, SubscriptionTier.PRO, now=oct_)
    await service.ensure_monthly_allowance(_USER, SubscriptionTier.PRO, now=oct_)
    assert (await service.get_balance(_USER)).balance == monthly_allowance(SubscriptionTier.PRO)


@pytest.mark.asyncio
async def test_require_credits_tops_up_the_allowance_once_per_tier(monkeypatch):
    """API-key and MCP accounts never call GET /api/credits, so they never got one."""
    from reasoner.api import dependencies as deps

    calls: list[str] = []

    class _Service:
        async def ensure_monthly_allowance(self, user_id, tier):
            calls.append(tier.value)

    tier = {"v": SubscriptionTier.FREE}

    async def fake_tier(user_id):
        return tier["v"]

    monkeypatch.setattr(deps, "_resolve_user_tier", fake_tier)
    deps._allowance_checked.clear()
    await deps._top_up_allowance(_Service(), _USER)
    await deps._top_up_allowance(_Service(), _USER)
    tier["v"] = SubscriptionTier.PRO  # upgraded mid-period
    await deps._top_up_allowance(_Service(), _USER)
    assert calls == ["free", "pro"]


# ── BIL-4: a failed webhook can be retried and replayed ──────────────────────


class _Valkey:
    async def get(self, *a):
        return None

    async def set(self, *a, **k):
        return True

    async def setex(self, *a):
        return None

    async def delete(self, *a):
        return None


def _stripe_request(event: dict):
    raw = json.dumps(event).encode()

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    from starlette.requests import Request

    return Request({"type": "http", "method": "POST", "path": "/api/billing/webhook",
                    "headers": [(b"stripe-signature", b"sig")]}, receive)


@pytest.mark.asyncio
async def test_failed_stripe_webhook_releases_its_claim_and_asks_for_retry(monkeypatch):
    import stripe

    from reasoner.application.services.billing_service import BillingService
    from reasoner.infrastructure.billing import webhooks

    event = {"id": "evt_1", "type": "checkout.session.completed", "data": {"object": {}}}
    released: list[tuple] = []

    async def claim(event_id, provider):
        return True

    async def release(event_id, provider):
        released.append((event_id, provider))

    async def boom(self, ev):
        raise TimeoutError("stripe api timed out")

    async def record(*a, **k):
        return None

    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **k: event)
    monkeypatch.setattr(webhooks, "_db_claim_webhook", claim)
    monkeypatch.setattr(webhooks, "_db_release_webhook", release)
    monkeypatch.setattr(webhooks, "_record_webhook_failure", record)
    monkeypatch.setattr(webhooks, "get_valkey_pool", lambda: _Valkey())
    monkeypatch.setattr(BillingService, "handle_webhook", boom)

    with pytest.raises(HTTPException) as exc:
        await webhooks.handle_stripe_webhook(_stripe_request(event))
    assert exc.value.status_code == 500
    assert released == [("evt_1", "stripe")], "the retry must be able to claim it again"


@pytest.mark.asyncio
async def test_replay_applies_dead_letters_once(monkeypatch):
    from reasoner.application.ports.billing_deadletter_port import FailedWebhookEvent
    from reasoner.application.services.billing_service import BillingService
    from reasoner.infrastructure.billing import webhooks

    failures = [
        FailedWebhookEvent("stripe", "x", {"id": "evt_new"}, "boom", id="f1"),
        FailedWebhookEvent("stripe", "x", {"id": "evt_done"}, "boom", id="f2"),
    ]
    marked: list[str] = []

    class _Repo:
        async def list_failures(self, **kw):
            return failures

        async def mark_replayed(self, failure_id):
            marked.append(failure_id)
            return True

    async def repo():
        return _Repo()

    async def claim(event_id, provider):
        return event_id == "evt_new"  # evt_done was applied by a provider retry

    applied: list[str] = []

    async def handle(self, ev):
        applied.append(ev["id"])

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_123")
    monkeypatch.setattr(webhooks, "_get_dead_letter_repo", repo)
    monkeypatch.setattr(webhooks, "_db_claim_webhook", claim)
    monkeypatch.setattr(BillingService, "handle_webhook", handle)

    result = await webhooks.replay_failed_webhooks()

    assert applied == ["evt_new"]
    assert sorted(marked) == ["f1", "f2"]
    assert result == {"available": True, "replayed": 1, "skipped": 1, "failed": 0}


# ── BIL-8: deleting the account never orphans a paid subscription ────────────


class _Pool:
    def __init__(self, rows):
        self.rows = rows
        self.deleted = False

    async def fetch(self, *a):
        return self.rows

    def acquire(self):
        pool = self

        class _Conn:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            def transaction(self):
                return self

            async def execute(self, sql, *a):
                if sql.startswith("DELETE FROM users"):
                    pool.deleted = True

        return _Conn()


@pytest.mark.asyncio
async def test_a_failed_cancel_aborts_the_deletion(monkeypatch):
    from reasoner.api import saas_router
    from reasoner.core.settings import settings
    from reasoner.infrastructure.billing.paypal_adapter import PayPalBillingAdapter
    from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter

    pool = _Pool([
        {"stripe_sub_id": "sub_active", "paypal_sub_id": None},
        {"stripe_sub_id": "sub_past_due", "paypal_sub_id": None},  # was skipped by LIMIT 1
    ])
    cancelled: list[str] = []

    async def cancel(self, sub_id):
        if sub_id == "sub_past_due":
            raise TimeoutError("stripe down")
        cancelled.append(sub_id)

    class _Repo:
        def __init__(self, *a, **k):
            pass

        async def _get_pool(self):
            return pool

    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://x/y")
    monkeypatch.setattr(
        "reasoner.infrastructure.persistence.quota_repo_postgres.PostgresQuotaRepository", _Repo
    )
    monkeypatch.setattr(StripeBillingAdapter, "__init__", lambda self: None)
    monkeypatch.setattr(StripeBillingAdapter, "cancel_subscription", cancel)
    monkeypatch.setattr(PayPalBillingAdapter, "cancel_subscription", cancel)

    request = SimpleNamespace(client=None, headers={})
    with pytest.raises(HTTPException) as exc:
        await saas_router.delete_account(request, user=User(id=uuid4(), email="a@b.c"), _=None)

    assert exc.value.status_code == 502
    assert cancelled == ["sub_active"], "every live subscription is attempted"
    assert pool.deleted is False, "the user row must survive a failed cancel"
