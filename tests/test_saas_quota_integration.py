"""
SaaS Quota Integration Tests — Phase 3

Validates:
- Quota endpoint returns usage data
- Authenticated requests trigger quota checks
- Legacy anonymous requests bypass quota
"""

from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ENABLE_LEGACY_API_KEY", "true")
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-production")

from reasoner.infrastructure.auth.local_adapter import LocalAuthAdapter
from reasoner.infrastructure.auth import set_auth_adapter
from reasoner.api import app


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


def test_quota_endpoint_returns_status(client, auth_token, monkeypatch):
    from reasoner.api import dependencies
    from reasoner.domain.saas import QuotaResult

    async def mock_check(*args, **kwargs):
        return QuotaResult(allowed=True, remaining=15)

    monkeypatch.setattr(dependencies._get_quota_service(), "check", mock_check)

    response = client.get("/api/quota", headers={"Authorization": f"Bearer {auth_token}"})
    assert response.status_code == 200
    data = response.json()
    assert "used" in data
    assert "max" in data
    assert "remaining" in data


def test_run_with_exhausted_quota_returns_429(client, auth_token, monkeypatch):
    from reasoner.api import dependencies
    from fastapi import HTTPException

    async def mock_check_quota(*args, **kwargs):
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Quota exceeded",
                "message": "Exceeded",
                "remaining": 0,
                "retry_after": 3600,
                "upgrade_url": "/pricing",
            },
            headers={
                "Retry-After": "3600",
                "X-RateLimit-Remaining": "0",
            },
        )

    monkeypatch.setattr(dependencies, "check_quota", mock_check_quota)

    response = client.post(
        "/api/run",
        json={"problem": "test", "preset": "multi-perspective-budget"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 429


def test_run_without_auth_bypasses_quota_check(client):
    # Anonymous requests should not trigger quota checks
    response = client.post(
        "/api/run",
        json={"problem": "test", "preset": "multi-perspective-budget"},
    )
    assert response.status_code == 200
