"""security-remediation-plan.md Phase 5: shared admin-key primitive,
bounded error-report/feedback schemas, and cache invalidation gated in
every environment (not just production) once a key is configured.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from reasoner.api.admin_auth import verify_admin_key
from reasoner.core.settings import settings

pytestmark = pytest.mark.unit


# ── shared admin-key primitive ──────────────────────────────────────


def test_no_key_configured_never_matches(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", None)
    assert verify_admin_key("anything") is False
    assert verify_admin_key("") is False
    assert verify_admin_key(None) is False


def test_correct_key_matches(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "secret-key")
    assert verify_admin_key("secret-key") is True


def test_wrong_key_does_not_match(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "secret-key")
    assert verify_admin_key("wrong-key") is False
    assert verify_admin_key(None) is False


# ── bounded schemas ──────────────────────────────────────────────────


def test_error_report_rejects_oversized_message():
    from reasoner.api.routes.errors import ClientErrorReport

    with pytest.raises(ValidationError):
        ClientErrorReport(message="x" * 5_000)


def test_error_report_rejects_oversized_stack():
    from reasoner.api.routes.errors import ClientErrorReport

    with pytest.raises(ValidationError):
        ClientErrorReport(message="ok", stack="x" * 20_000)


def test_error_report_accepts_bounded_fields():
    from reasoner.api.routes.errors import ClientErrorReport

    report = ClientErrorReport(message="ok", stack="short trace", url="/page")
    assert report.message == "ok"


def test_feedback_rejects_oversized_comment():
    from reasoner.api.routes.feedback import FeedbackRequest

    with pytest.raises(ValidationError):
        FeedbackRequest(
            conversation_id="c1", message_id="m1", rating="up", comment="x" * 5_000
        )


def test_feedback_accepts_bounded_fields():
    from reasoner.api.routes.feedback import FeedbackRequest

    fb = FeedbackRequest(conversation_id="c1", message_id="m1", rating="up", comment="nice")
    assert fb.rating == "up"


# ── cache invalidation gated in every environment ───────────────────


def test_cache_clear_requires_key_outside_production_when_key_is_configured(monkeypatch):
    """The concrete Phase 5 fix: previously this was wide open whenever
    ENVIRONMENT != "production", regardless of whether an admin key was
    configured."""
    from fastapi.testclient import TestClient

    from reasoner.api import app

    monkeypatch.setattr(settings, "ADMIN_API_KEY", "secret-key")
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    client = TestClient(app)

    response = client.delete("/api/cache")

    assert response.status_code == 403


def test_cache_clear_still_frictionless_when_no_key_configured(monkeypatch):
    """Preserves existing dev/CLI convenience when no operator has set up
    an admin key at all."""
    from fastapi.testclient import TestClient

    from reasoner.api import app

    monkeypatch.setattr(settings, "ADMIN_API_KEY", None)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    client = TestClient(app)

    response = client.delete("/api/cache")

    assert response.status_code == 200
