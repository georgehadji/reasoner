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
os.environ.setdefault("ENABLE_LEGACY_API_KEY", "true")


@pytest.fixture(autouse=True)
def _enable_legacy_api_key(monkeypatch):
    """settings is built at first import, so the env var above only takes effect
    when this module happens to be imported first. Patch the attribute the request
    path reads so anonymous access is allowed regardless of test ordering."""
    from reasoner.core.settings import settings

    monkeypatch.setattr(settings, "ENABLE_LEGACY_API_KEY", True)
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-production")

from reasoner.infrastructure.auth.local_adapter import LocalAuthAdapter
from reasoner.infrastructure.auth import set_auth_adapter, get_auth_adapter
from reasoner.api import app
from reasoner.api.dependencies import _reset_quota_service
from reasoner.application.services.quota_service import QuotaService
from reasoner.core.settings import settings


class _FakeQuotaRepository:
    async def get_quota(self, user_id: str):
        from reasoner.domain.saas import UsageQuota, SubscriptionTier
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


def test_run_pipeline_without_auth_still_works_in_legacy_mode(client):
    # When ENABLE_LEGACY_API_KEY=true, anonymous requests are allowed
    response = client.post(
        "/api/run",
        json={"problem": "What is 2+2?", "preset": "multi-perspective-budget"},
    )
    assert response.status_code == 200


def test_run_pipeline_without_auth_rejected_when_legacy_disabled(client, monkeypatch):
    """SEC-005: Anonymous requests to /api/run are rejected when legacy API keys are disabled."""
    monkeypatch.setattr(settings, "ENABLE_LEGACY_API_KEY", False)
    response = client.post(
        "/api/run",
        json={"problem": "What is 2+2?", "preset": "multi-perspective-budget"},
    )
    assert response.status_code == 401


def test_legacy_api_key_still_works(client):
    # Set a known admin key for this test
    original = os.environ.get("ADMIN_API_KEY")
    os.environ["ADMIN_API_KEY"] = "test-admin-key-12345"
    try:
        response = client.post(
            "/api/run",
            json={"problem": "What is 2+2?", "preset": "multi-perspective-budget"},
            headers={"Authorization": "Bearer test-admin-key-12345"},
        )
        assert response.status_code == 200
    finally:
        if original is None:
            os.environ.pop("ADMIN_API_KEY", None)
        else:
            os.environ["ADMIN_API_KEY"] = original
