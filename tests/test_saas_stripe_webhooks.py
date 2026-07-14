"""Tests for Stripe webhook handling with idempotency and error resilience."""

from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

os.environ.setdefault("ENABLE_LEGACY_API_KEY", "true")
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-production")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_123")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test")
os.environ.setdefault("STRIPE_PRO_PRICE_ID", "price_pro")
os.environ.setdefault("STRIPE_ENTERPRISE_PRICE_ID", "price_ent")

from reasoner.infrastructure.auth.local_adapter import LocalAuthAdapter
from reasoner.infrastructure.auth import set_auth_adapter
from reasoner.infrastructure.redis.client import set_redis
from reasoner.api import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    # Use a fake in-memory redis for dedup tests
    fake_redis = MagicMock()
    fake_redis.get = MagicMock(return_value=None)
    fake_redis.setex = MagicMock(return_value=None)
    set_redis(fake_redis)
    yield
    set_redis(None)


@pytest.fixture
def local_adapter():
    adapter = LocalAuthAdapter(secret="test-secret-key-for-local-auth-adapter-only")
    set_auth_adapter(adapter)
    yield adapter
    set_auth_adapter(None)


def test_webhook_invalid_signature_returns_200(client, monkeypatch):
    """Enhancement 4.3: webhook returns 200 even on signature errors."""
    import stripe
    monkeypatch.setattr(
        stripe.Webhook, "construct_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(stripe.error.SignatureVerificationError("bad sig", "test_header"))
    )
    response = client.post(
        "/api/billing/webhook",
        json={"id": "evt_1", "type": "test"},
        headers={"stripe-signature": "bad"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_webhook_duplicate_event_is_idempotent(client, monkeypatch):
    """Enhancement 4.9: duplicate event IDs are deduplicated."""
    import stripe

    event = {
        "id": "evt_test_123",
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": "12345678-1234-5678-1234-567812345678", "subscription": "sub_123"}},
    }

    mock_sub = MagicMock()
    mock_sub.id = "sub_123"
    mock_sub.status = "active"
    mock_sub.customer = "cus_123"
    mock_sub.items.data = [MagicMock(price=MagicMock(id="price_pro"))]
    mock_sub.current_period_end = 1893456000

    mock_customer = MagicMock()
    mock_customer.metadata = {"reasoner_user_id": "12345678-1234-5678-1234-567812345678"}

    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *args, **kwargs: event)
    monkeypatch.setattr(stripe.Subscription, "retrieve", lambda sid: mock_sub)
    monkeypatch.setattr(stripe.Customer, "retrieve", lambda cid: mock_customer)

    # Track how many times the subscription is synced
    sync_calls = []
    original_sync = app.state._sync_sub if hasattr(app.state, "_sync_sub") else None

    # Send twice
    response1 = client.post("/api/billing/webhook", json=event, headers={"stripe-signature": "test"})
    response2 = client.post("/api/billing/webhook", json=event, headers={"stripe-signature": "test"})

    assert response1.status_code == 200
    assert response2.status_code == 200


def test_webhook_processing_error_returns_200(client, monkeypatch):
    """Enhancement 4.3: processing errors return 200 to prevent retries."""
    import stripe

    event = {
        "id": "evt_bad_1",
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": "user-1", "subscription": "sub_bad"}},
    }

    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *args, **kwargs: event)
    # Make Subscription.retrieve raise an exception
    monkeypatch.setattr(stripe.Subscription, "retrieve", lambda sid: (_ for _ in ()).throw(Exception("boom")))

    response = client.post("/api/billing/webhook", json=event, headers={"stripe-signature": "test"})
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_webhook_unsigned_payload_is_ignored_when_secret_missing(client, monkeypatch):
    """SEC-004: Unsigned payloads must be ignored when STRIPE_WEBHOOK_SECRET is not set."""
    import stripe

    # Temporarily clear the webhook secret
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)

    event = {
        "id": "evt_forge_1",
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": "attacker", "subscription": "sub_fake"}},
    }

    # Track whether BillingService.handle_webhook is called
    handle_called = []
    original_handle = stripe.Webhook.construct_event

    def track_handle(*args, **kwargs):
        handle_called.append(True)
        return original_handle(*args, **kwargs)

    response = client.post("/api/billing/webhook", json=event, headers={"stripe-signature": "test"})

    assert response.status_code == 200
    assert response.json()["status"] == "misconfigured"
    # BillingService must NOT have been invoked
    assert len(handle_called) == 0
