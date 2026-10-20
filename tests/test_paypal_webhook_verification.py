"""PayPal webhooks must be verified by PayPal before anything is applied (SEC-1).

The old check accepted any non-empty ``paypal-transmission-sig`` header. A
forged ``BILLING.SUBSCRIPTION.ACTIVATED`` then granted any tier, and a forged
``CANCELLED`` downgraded a paying customer. A verification exception was
logged and processing went on anyway.
See docs/plans/audit-remediation-2026-10-20.md, SEC-1.
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from reasoner.domain.saas import SubscriptionTier
from reasoner.infrastructure.billing import paypal_adapter as paypal_mod
from reasoner.infrastructure.billing import webhooks
from reasoner.infrastructure.billing.paypal_adapter import PayPalBillingAdapter

_EVENT = {
    "id": "WH-1",
    "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
    "resource": {"id": "I-1", "custom_id": "12345678-1234-5678-1234-567812345678"},
}
_HEADERS = {
    "paypal-auth-algo": "SHA256withRSA",
    "paypal-cert-url": "https://api.paypal.com/cert.pem",
    "paypal-transmission-id": "tid-1",
    "paypal-transmission-sig": "forged",
    "paypal-transmission-time": "2026-10-20T00:00:00Z",
}


def _request(body: dict, headers: dict) -> Request:
    raw = json.dumps(body).encode()

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/billing/paypal/webhook",
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
    }
    return Request(scope, receive)


@pytest.fixture
def paypal_api(monkeypatch):
    """Route the adapter's httpx calls to a fake PayPal; record what it sent."""
    sent: list[dict] = []
    answer = {"verification_status": "SUCCESS"}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=answer)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        paypal_mod.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )

    async def token(self):
        return "tok"

    monkeypatch.setattr(PayPalBillingAdapter, "_get_access_token", token)
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-ID")
    return sent, answer


# ── adapter ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_success_answer_verifies_and_sends_webhook_id(paypal_api):
    sent, _ = paypal_api
    ok = await PayPalBillingAdapter().verify_webhook_signature(_HEADERS, json.dumps(_EVENT))
    assert ok is True
    assert sent[0]["webhook_id"] == "WH-ID"
    assert sent[0]["transmission_sig"] == "forged"
    assert sent[0]["webhook_event"] == _EVENT


@pytest.mark.asyncio
async def test_failure_answer_does_not_verify(paypal_api):
    _, answer = paypal_api
    answer["verification_status"] = "FAILURE"
    assert await PayPalBillingAdapter().verify_webhook_signature(_HEADERS, json.dumps(_EVENT)) is False


@pytest.mark.asyncio
async def test_signature_header_alone_is_not_enough(paypal_api):
    """The old check: a lone non-empty signature header passed."""
    sent, _ = paypal_api
    only_sig = {"paypal-transmission-sig": "anything"}
    assert await PayPalBillingAdapter().verify_webhook_signature(only_sig, json.dumps(_EVENT)) is False
    assert sent == [], "must not call PayPal when headers are missing"


def test_missing_plan_id_is_not_pro(monkeypatch):
    """None == os.environ.get(unset) used to map a missing plan_id to PRO."""
    monkeypatch.delenv("PAYPAL_PRO_PLAN_ID", raising=False)
    monkeypatch.delenv("PAYPAL_ENTERPRISE_PLAN_ID", raising=False)
    assert PayPalBillingAdapter()._tier_from_plan(None) is SubscriptionTier.FREE


# ── webhook handler ──────────────────────────────────────────────────────────


@pytest.fixture
def applied(monkeypatch):
    """Record events that reach BillingService; stub the dedup guards."""
    from reasoner.application.services.billing_service import BillingService

    seen: list[dict] = []

    async def handle(self, event):
        seen.append(event)

    async def claim(event_id, provider):
        return True

    class _Valkey:
        async def get(self, *a):
            return None

        async def set(self, *a, **k):
            return True

        async def setex(self, *a):
            return None

        async def delete(self, *a):
            return None

    monkeypatch.setattr(BillingService, "handle_webhook", handle)
    monkeypatch.setattr(webhooks, "_db_claim_webhook", claim)
    monkeypatch.setattr(webhooks, "get_valkey_pool", lambda: _Valkey())
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-ID")
    return seen


def _verify_returns(monkeypatch, result):
    async def verify(self, headers, body):
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(PayPalBillingAdapter, "verify_webhook_signature", verify)


@pytest.mark.asyncio
async def test_forged_event_is_not_applied(monkeypatch, applied):
    _verify_returns(monkeypatch, False)
    out = await webhooks.handle_paypal_webhook(_request(_EVENT, _HEADERS))
    assert out == {"status": "ok"}
    assert applied == []


@pytest.mark.asyncio
async def test_verification_error_is_not_applied_and_asks_for_retry(monkeypatch, applied):
    _verify_returns(monkeypatch, httpx.ConnectError("paypal down"))
    with pytest.raises(HTTPException) as exc:
        await webhooks.handle_paypal_webhook(_request(_EVENT, _HEADERS))
    assert exc.value.status_code == 503
    assert applied == []


@pytest.mark.asyncio
async def test_unconfigured_webhook_id_ignores_event(monkeypatch, applied):
    monkeypatch.delenv("PAYPAL_WEBHOOK_ID")
    _verify_returns(monkeypatch, True)
    out = await webhooks.handle_paypal_webhook(_request(_EVENT, _HEADERS))
    assert out == {"status": "misconfigured"}
    assert applied == []


@pytest.mark.asyncio
async def test_verified_event_is_applied(monkeypatch, applied):
    _verify_returns(monkeypatch, True)
    await webhooks.handle_paypal_webhook(_request(_EVENT, _HEADERS))
    assert [e["id"] for e in applied] == ["WH-1"]
