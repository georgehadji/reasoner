"""The contact form must not claim to have sent a message it discarded.

The page previously ran a client-side handler that did nothing, then displayed
"our support team will get back to you within 24 hours". Every message was lost,
and no support address was published as a fallback — which also left GDPR
data-subject requests with no channel.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reasoner.api import app
from reasoner.core.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]

client = TestClient(app)

VALID = {
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "topic": "Billing Issue",
    "message": "I was charged twice this month.",
}


class TestDeliveryHonesty:
    def test_unconfigured_destination_returns_503_not_success(self, monkeypatch):
        """No destination means the message reaches nobody — say so."""
        monkeypatch.setattr(Settings, "NOTIFICATION_EMAIL", None)
        response = client.post("/api/contact", json=VALID)
        assert response.status_code == 503
        assert "status" not in response.json()

    def test_failed_send_returns_503_not_success(self, monkeypatch):
        """The adapter returns False when it didn't deliver; don't report sent."""
        monkeypatch.setattr(Settings, "NOTIFICATION_EMAIL", "ops@example.com")

        async def never_delivers(self, message):
            return False

        monkeypatch.setattr(
            "reasoner.infrastructure.email.resend_adapter.ResendEmailAdapter.send",
            never_delivers,
        )
        response = client.post("/api/contact", json=VALID)
        assert response.status_code == 503

    def test_successful_send_reports_sent(self, monkeypatch):
        monkeypatch.setattr(Settings, "NOTIFICATION_EMAIL", "ops@example.com")
        captured = {}

        async def delivers(self, message):
            captured["to"] = message.to
            captured["subject"] = message.subject
            captured["body"] = message.text_body
            return True

        monkeypatch.setattr(
            "reasoner.infrastructure.email.resend_adapter.ResendEmailAdapter.send", delivers
        )
        response = client.post("/api/contact", json=VALID)

        assert response.status_code == 200
        assert response.json()["status"] == "sent"
        assert captured["to"] == "ops@example.com"
        # The operator needs the reply-to address in the body to answer at all.
        assert "ada@example.com" in captured["body"]
        assert "charged twice" in captured["body"]


class TestValidation:
    @pytest.mark.parametrize(
        "bad_email", ["not-an-email", "@example.com", "ada@", "ada@example", ""]
    )
    def test_implausible_email_is_rejected(self, bad_email, monkeypatch):
        monkeypatch.setattr(Settings, "NOTIFICATION_EMAIL", "ops@example.com")
        response = client.post("/api/contact", json={**VALID, "email": bad_email})
        assert response.status_code == 422

    def test_unknown_topic_is_rejected(self, monkeypatch):
        monkeypatch.setattr(Settings, "NOTIFICATION_EMAIL", "ops@example.com")
        response = client.post("/api/contact", json={**VALID, "topic": "Nonsense"})
        assert response.status_code == 422

    def test_oversized_message_is_rejected(self, monkeypatch):
        monkeypatch.setattr(Settings, "NOTIFICATION_EMAIL", "ops@example.com")
        response = client.post("/api/contact", json={**VALID, "message": "x" * 5001})
        assert response.status_code == 422

    def test_extra_fields_are_rejected(self, monkeypatch):
        monkeypatch.setattr(Settings, "NOTIFICATION_EMAIL", "ops@example.com")
        response = client.post("/api/contact", json={**VALID, "is_admin": True})
        assert response.status_code == 422


class TestFrontendIsWired:
    def test_page_posts_instead_of_faking_success(self):
        page = (
            REPO_ROOT / "ui-next" / "src" / "app" / "contact" / "page.tsx"
        ).read_text(encoding="utf-8")
        assert "submitContact" in page, "the form must call the API"
        assert "Placeholder for actual form submission" not in page

    def test_refund_policy_exists_and_is_linked(self):
        """The pricing page advertises a 14-day guarantee."""
        assert (REPO_ROOT / "ui-next" / "src" / "app" / "refunds" / "page.tsx").exists()
        footer = (
            REPO_ROOT / "ui-next" / "src" / "components" / "layout" / "SiteFooter.tsx"
        ).read_text(encoding="utf-8")
        assert "/refunds" in footer
        assert "/cookies" in footer, "the cookie policy page was orphaned"
