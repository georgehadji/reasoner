"""Tests for POST /api/contact."""

import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-local-auth-adapter-only")

from reasoner.api import app  # noqa: E402
from reasoner.api.routes.contact import get_email_adapter  # noqa: E402
from reasoner.core.settings import settings  # noqa: E402

VALID = {
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "subject": "Pilot",
    "message": "We would like to scope a pilot.",
}


class FakeAdapter:
    def __init__(self, ok: bool = True):
        self.ok = ok
        self.sent = []

    async def send(self, message):
        self.sent.append(message)
        return self.ok


@pytest.fixture
def adapter():
    fake = FakeAdapter()
    app.dependency_overrides[get_email_adapter] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_email_adapter, None)


@pytest.fixture
def client():
    return TestClient(app)


def test_sends_to_configured_inbox(client, adapter, monkeypatch):
    monkeypatch.setattr(settings, "CONTACT_EMAIL", "inbox@example.org")
    resp = client.post("/api/contact", json=VALID)
    assert resp.status_code == 200
    assert resp.json() == {"status": "sent"}
    (msg,) = adapter.sent
    assert msg.to == "inbox@example.org"
    assert msg.reply_to == "ada@example.com"
    assert msg.subject == "[Contact] Pilot: Ada Lovelace"
    assert "We would like to scope a pilot." in msg.text_body


def test_503_when_no_inbox_configured(client, adapter, monkeypatch):
    monkeypatch.setattr(settings, "CONTACT_EMAIL", None)
    monkeypatch.setattr(settings, "NOTIFICATION_EMAIL", None)
    resp = client.post("/api/contact", json=VALID)
    assert resp.status_code == 503
    assert adapter.sent == []


def test_503_when_adapter_refuses(client, adapter, monkeypatch):
    monkeypatch.setattr(settings, "CONTACT_EMAIL", "inbox@example.org")
    adapter.ok = False
    assert client.post("/api/contact", json=VALID).status_code == 503


@pytest.mark.parametrize(
    "override",
    [
        {"email": "not-an-address"},
        {"email": "a@b.co\nBcc: x@y.z"},
        {"subject": "Something else"},
        {"message": "   "},
        {"name": "x" * 201},
    ],
)
def test_rejects_invalid_input(client, adapter, monkeypatch, override):
    monkeypatch.setattr(settings, "CONTACT_EMAIL", "inbox@example.org")
    resp = client.post("/api/contact", json={**VALID, **override})
    assert resp.status_code == 422
    assert adapter.sent == []


def test_name_line_breaks_are_flattened(client, adapter, monkeypatch):
    monkeypatch.setattr(settings, "CONTACT_EMAIL", "inbox@example.org")
    resp = client.post("/api/contact", json={**VALID, "name": "Ada\r\nBcc: x@y.z"})
    assert resp.status_code == 200
    assert "\n" not in adapter.sent[0].subject
