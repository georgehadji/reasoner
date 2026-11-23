"""
SaaS Auth Integration Tests — Phase 2

Validates:
- JWT authentication via LocalAuthAdapter
- Legacy API key fallback
- Unified auth resolver
- Auth endpoints (/api/auth/me, /api/auth/me/optional)
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# Ensure legacy API keys are enabled for compat tests
os.environ.setdefault("ALLOW_ANONYMOUS_RUNS", "true")
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-production")

from reasoner.api import app
from reasoner.api.dependencies import _reset_quota_service
from reasoner.application.services.quota_service import QuotaService
from reasoner.core.settings import settings
from reasoner.infrastructure.auth import set_auth_adapter
from reasoner.infrastructure.auth.local_adapter import LocalAuthAdapter


class _FakeQuotaRepository:
    async def get_quota(self, user_id: str):
        from reasoner.domain.saas import SubscriptionTier, UsageQuota
        return UsageQuota(user_id=user_id, tier=SubscriptionTier.FREE, used_queries=0, max_queries=20)

    async def check_and_increment(self, user_id: str, preset: str):
        from reasoner.domain.saas import QuotaResult
        return QuotaResult(allowed=True, remaining=20)

    async def reset_monthly(self, user_id: str):
        pass

    async def log_query(self, user_id: str, preset: str, method: str, tokens_in: int, tokens_out: int, cost_usd: float):
        pass


@pytest.fixture(autouse=True)
def mock_quota_service(monkeypatch):
    _reset_quota_service()
    fake_service = QuotaService(_FakeQuotaRepository())
    monkeypatch.setattr("reasoner.api.dependencies._quota_service", fake_service)
    yield
    _reset_quota_service()


@pytest.fixture(autouse=True)
def bypass_credit_gate():
    """This file tests auth, not billing. Without it, an authenticated caller
    hits require_credits_if_authenticated -> a fresh in-memory ledger with a
    zero balance -> 402, which has nothing to do with what these tests check
    (docs/plans/pre-existing-fixes.md #4)."""
    from reasoner.api.dependencies import require_credits_if_authenticated

    app.dependency_overrides[require_credits_if_authenticated] = lambda: None
    yield
    app.dependency_overrides.pop(require_credits_if_authenticated, None)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def local_adapter():
    adapter = LocalAuthAdapter(secret="test-secret-key-for-local-auth-adapter-only")
    set_auth_adapter(adapter)
    yield adapter
    set_auth_adapter(None)


@pytest.fixture
def auth_token(local_adapter):
    return local_adapter.create_token(
        user_id="12345678-1234-5678-1234-567812345678",
        email="test@example.com",
        display_name="Test User",
    )


def test_auth_me_without_token_returns_401(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_auth_me_with_valid_token(client, auth_token):
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"
    assert data["display_name"] == "Test User"


def test_auth_me_optional_without_token(client):
    response = client.get("/api/auth/me/optional")
    assert response.status_code == 200
    assert response.json() == {"authenticated": False}


def test_auth_me_optional_with_valid_token(client, auth_token):
    response = client.get(
        "/api/auth/me/optional",
        headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert data["email"] == "test@example.com"


def test_run_pipeline_with_auth_token(client, auth_token):
    response = client.post(
        "/api/run",
        json={"problem": "What is 2+2?", "preset": "multi-perspective-budget"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200


def test_run_pipeline_without_auth_still_works_in_legacy_mode(client, monkeypatch):
    # When ALLOW_ANONYMOUS_RUNS=true, anonymous requests are allowed.
    #
    # The module-level os.environ.setdefault("ALLOW_ANONYMOUS_RUNS", "true")
    # above (line 18) can't actually reach this: Settings reads os.getenv()
    # once at class-body-execution time when reasoner.core.settings is first
    # imported, and by the time this test module is collected, conftest.py's
    # own imports have already triggered that (see settings.py's module
    # docstring -- it is the only module that reads the environment).
    # monkeypatch.setattr on the settings singleton is the pattern that
    # actually reaches a fresh read (as test_run_pipeline_without_auth_
    # rejected_when_legacy_disabled below already does for the False case).
    monkeypatch.setattr(settings, "ALLOW_ANONYMOUS_RUNS", True)
    response = client.post(
        "/api/run",
        json={"problem": "What is 2+2?", "preset": "multi-perspective-budget"},
    )
    assert response.status_code == 200


def test_run_pipeline_without_auth_rejected_when_legacy_disabled(client, monkeypatch):
    """SEC-005: Anonymous requests to /api/run are rejected when legacy API keys are disabled."""
    monkeypatch.setattr(settings, "ALLOW_ANONYMOUS_RUNS", False)
    response = client.post(
        "/api/run",
        json={"problem": "What is 2+2?", "preset": "multi-perspective-budget"},
    )
    assert response.status_code == 401


def test_opaque_bearer_token_is_401_even_when_anonymous_runs_allowed(client, monkeypatch):
    # Legacy admin-key auth is gone: a bearer that is neither a JWT nor an rsn_
    # key is a bad credential, not an anonymous caller.
    monkeypatch.setattr(settings, "ALLOW_ANONYMOUS_RUNS", True)
    response = client.post(
        "/api/run",
        json={"problem": "What is 2+2?", "preset": "multi-perspective-budget"},
        headers={"Authorization": "Bearer test-admin-key-12345"},
    )
    assert response.status_code == 401
