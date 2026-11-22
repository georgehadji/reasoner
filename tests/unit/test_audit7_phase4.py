"""Audit 7 phase 4: paid widgets are charged, the contact form is rate limited."""

from __future__ import annotations

import os

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-local-auth-adapter-only")

from reasoner.api import app  # noqa: E402
from reasoner.core.constants_limits import SEARCH_ESTIMATED_COST_USD  # noqa: E402

pytestmark = pytest.mark.unit


class _Handlers:
    def __init__(self, success: bool = True):
        self.success = success

    async def handle_command(self, command):
        return {"detected": True, "widgets": [{"success": self.success}]}


@pytest.fixture
def charges(monkeypatch):
    """Record admit_flat_charge and close_flat_charge calls on the widget route."""
    import reasoner.api as api
    from reasoner.api.routes import widgets

    log: dict = {"admitted": [], "closed": [], "handlers": _Handlers()}

    async def admit(request, *, user, cost_usd, kind):
        log["admitted"].append((kind, cost_usd))
        if log.get("refuse"):
            raise HTTPException(status_code=402, detail="no credits")
        return object()

    async def close(charge, *, served):
        log["closed"].append(served)

    monkeypatch.setattr(widgets, "admit_flat_charge", admit)
    monkeypatch.setattr(widgets, "close_flat_charge", close)
    monkeypatch.setattr(api, "get_architecture_components", lambda: (None, log["handlers"]))
    return log


def _post(widget_type: str):
    return TestClient(app).post(
        "/api/widget/execute",
        json={"widget_type": widget_type, "params": {}, "auto_detect": False, "query": "latest news"},
    )


@pytest.mark.parametrize("widget", ["discover", "image_search", "video_search"])
def test_a_paid_widget_is_charged_the_search_price(charges, widget):
    assert _post(widget).status_code == 200
    assert charges["admitted"] == [(f"widget-{widget}", SEARCH_ESTIMATED_COST_USD)]
    assert charges["closed"] == [True]


def test_a_free_widget_is_not_charged(charges):
    assert _post("calculator").status_code == 200
    assert charges["admitted"] == [] and charges["closed"] == []


def test_a_failed_paid_widget_gives_the_hold_back(charges):
    charges["handlers"] = _Handlers(success=False)
    _post("image_search")
    assert charges["closed"] == [False]


def test_a_refused_charge_is_a_402_not_a_swallowed_error(charges):
    charges["refuse"] = True
    assert _post("video_search").status_code == 402


# ── finding 20 ──────────────────────────────────────────────────────────────


def test_the_sixth_contact_message_in_the_window_is_a_429(monkeypatch):
    from reasoner.api.routes import contact
    from reasoner.core.constants_limits import CONTACT_RATE_LIMIT_PER_HOUR
    from reasoner.core.settings import settings

    class _Adapter:
        async def send(self, message):
            return True

    monkeypatch.setattr(contact, "_contact_limiter", None)
    monkeypatch.setattr(settings, "CONTACT_EMAIL", "inbox@example.org")
    app.dependency_overrides[contact.get_email_adapter] = lambda: _Adapter()
    body = {"name": "Ada", "email": "ada@example.com", "subject": "Pilot", "message": "hi"}
    try:
        client = TestClient(app)
        codes = [client.post("/api/contact", json=body).status_code
                 for _ in range(CONTACT_RATE_LIMIT_PER_HOUR + 1)]
    finally:
        app.dependency_overrides.pop(contact.get_email_adapter, None)

    assert codes[:CONTACT_RATE_LIMIT_PER_HOUR] == [200] * CONTACT_RATE_LIMIT_PER_HOUR
    assert codes[-1] == 429
