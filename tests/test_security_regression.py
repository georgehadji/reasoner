"""
Security Regression Tests — Protocol v2.0
Covers BUG-001, BUG-002, BUG-003 fixes.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from reasoner.api import app
from reasoner.auth import AuthManager
from reasoner.infrastructure.auth.local_adapter import LocalAuthAdapter

import os
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-local-auth-adapter-only")
_adapter = LocalAuthAdapter()
_test_token = _adapter.create_token("11111111-1111-1111-1111-111111111111", "test@example.com")
_admin_token = _adapter.create_token(
    "11111111-1111-1111-1111-111111111111",
    "admin@example.com",
    scopes=["admin"],
)
client = TestClient(app, headers={"Authorization": f"Bearer {_test_token}"})


class TestBug001AdminEndpointHardening:
    """BUG-001: Admin endpoint must use constant-time compare + rate limiting."""

    def test_admin_stats_wrong_key_returns_401(self, monkeypatch):
        """Wrong admin key must 401 (existing behavior preserved)."""
        from reasoner.core.settings import Settings
        monkeypatch.setattr(Settings, "ADMIN_API_KEY", "real-admin-key")

        admin_client = TestClient(app, headers={"Authorization": f"Bearer {_admin_token}"})
        response = admin_client.get(
            "/api/admin/feedback-stats",
            headers={"X-Admin-Key": "wrong-key"},
        )
        assert response.status_code == 401

    def test_admin_stats_no_key_returns_401(self, monkeypatch):
        """Missing admin key must 401."""
        from reasoner.core.settings import Settings
        monkeypatch.setattr(Settings, "ADMIN_API_KEY", "real-admin-key")

        admin_client = TestClient(app, headers={"Authorization": f"Bearer {_admin_token}"})
        response = admin_client.get("/api/admin/feedback-stats")
        assert response.status_code == 401

    def test_admin_stats_rate_limited(self, monkeypatch):
        """Rapid requests to admin endpoint must be rate limited (429)."""
        from reasoner.core.settings import Settings
        monkeypatch.setattr(Settings, "ADMIN_API_KEY", "real-admin-key")

        # Monkey-patch rate limiter to reject immediately
        from reasoner.api.dependencies import _get_rate_limiter_instance
        rate_limiter = _get_rate_limiter_instance()
        original_is_allowed = rate_limiter.is_allowed
        original_is_allowed_for_user = rate_limiter.is_allowed_for_user

        async def reject_all(*args, **kwargs):
            return False, {"retry_after": 60, "limit_minute": 60, "remaining_minute": 0}

        rate_limiter.is_allowed = reject_all
        rate_limiter.is_allowed_for_user = reject_all
        try:
            admin_client = TestClient(app, headers={"Authorization": f"Bearer {_admin_token}"})
            response = admin_client.get(
                "/api/admin/feedback-stats",
                headers={"X-Admin-Key": "real-admin-key"},
            )
            assert response.status_code == 429
            data = response.json()
            assert "error" in data or "Rate limit" in str(data)
        finally:
            rate_limiter.is_allowed = original_is_allowed
            rate_limiter.is_allowed_for_user = original_is_allowed_for_user

    def test_admin_stats_authorized_still_works(self, monkeypatch):
        """Correct admin key must still succeed."""
        from reasoner.core.settings import Settings
        monkeypatch.setattr(Settings, "ADMIN_API_KEY", "real-admin-key")

        admin_client = TestClient(app, headers={"Authorization": f"Bearer {_admin_token}"})
        response = admin_client.get(
            "/api/admin/feedback-stats?days=7",
            headers={"X-Admin-Key": "real-admin-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_entries" in data


class TestBug002KeyValidationRequiresAuth:
    """BUG-002: /api/keys/validate must require authentication."""

    @pytest.fixture
    async def valid_bearer_token(self):
        """Generate a real bearer token for tests."""
        manager = AuthManager()
        token = await manager.generate_key("test-token", scopes={"read"})
        return token

    def test_validate_keys_no_auth_returns_401(self):
        """Unauthenticated POST to /api/keys/validate must 401."""
        response = client.post("/api/keys/validate")
        assert response.status_code == 401

    def test_validate_keys_invalid_auth_returns_401(self):
        """Invalid bearer token must 401."""
        response = client.post(
            "/api/keys/validate",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401

    def test_validate_keys_with_auth_returns_summary(self, monkeypatch):
        """Authenticated request must return summary without burning quota."""
        import asyncio
        from reasoner.api.auth_deps import _get_auth_manager_instance_auth_deps

        # Use the app's singleton auth manager so the key is recognized
        auth_manager = _get_auth_manager_instance_auth_deps()
        loop = asyncio.new_event_loop()
        try:
            token = loop.run_until_complete(
                auth_manager.generate_key("test-token", scopes={"read"})
            )
        finally:
            loop.close()

        # Mock build_provider to avoid actual LLM calls
        with patch("reasoner.api.routes.keys.build_provider") as mock_build:
            mock_provider = MagicMock()
            mock_provider.complete = MagicMock(return_value="ok")
            mock_build.return_value = mock_provider

            response = client.post(
                "/api/keys/validate",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "summary" in data
        assert "valid" in data["summary"]
        assert "total" in data["summary"]


class TestBug003ErrorMessageSanitization:
    """BUG-003: Exception details must not leak to API clients."""

    def test_context_error_is_generic(self):
        """Context route errors must not leak internals."""
        secret = "SECRET_CONTEXT_PATH"
        with patch("reasoner.api.routes.context.ReasonerPipeline") as mock_pipe:
            mock_pipe.side_effect = RuntimeError(secret)
            response = client.post(
                "/api/run-with-context",
                json={"problem": "x", "preset": "auto-budget", "context": []},
            )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is False
        assert secret not in data.get("error", "")
        assert "Internal server error" in data.get("error", "")

    def test_image_error_is_generic(self):
        """Image route errors must not leak internals."""
        secret = "SECRET_IMAGE_PATH"
        with patch("reasoner.api.routes.images.generate_images") as mock_gen:
            mock_gen.side_effect = RuntimeError(secret)
            response = client.post(
                "/api/generate-image",
                json={"prompt": "x", "preset": "image-gen-budget"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is False
        assert secret not in data.get("error", "")
        assert "Internal server error" in data.get("error", "")

    def test_widget_error_is_generic(self):
        """Widget route errors must not leak internals."""
        secret = "SECRET_WIDGET_PATH"
        with patch("reasoner.api.get_architecture_components") as mock_comp:
            mock_comp.side_effect = RuntimeError(secret)
            response = client.post(
                "/api/widget/execute",
                json={"query": "x", "widget_type": "calc"},
            )
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert secret not in data["error"]
        assert "Internal server error" in data["error"]

    def test_calculate_error_is_generic(self):
        """Calculate route errors must not leak internals."""
        secret = "SECRET_CALC_PATH"
        with patch("reasoner.widgets.calculate_expression") as mock_calc:
            mock_calc.side_effect = RuntimeError(secret)
            response = client.post("/api/calculate", json={"expression": "1+1"})
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert secret not in data["error"]
        assert "Internal server error" in data["error"]

    def test_discover_error_is_generic(self):
        """Discover route errors must not leak internals."""
        secret = "SECRET_DISCOVER_PATH"
        with patch("reasoner.widgets.get_discover_content") as mock_disc:
            mock_disc.side_effect = RuntimeError(secret)
            response = client.get("/api/discover", params={"topic": "tech"})
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        assert secret not in data["error"]
        assert "Internal server error" in data["error"]

    def test_pipelines_error_is_generic(self):
        """Pipeline route errors must not leak internals."""
        secret = "SQLITE_SECRET_PATH"

        with patch("reasoner.api.get_architecture_components") as mock_get:
            mock_get.side_effect = RuntimeError(secret)
            response = client.get("/api/pipelines")

        assert response.status_code == 500  # FastAPI exception handler returns 500
        data = response.json()
        assert "error" in data
        assert secret not in data["error"]
        assert "Internal server error" in data["error"]

    def test_upload_error_is_generic(self, monkeypatch):
        """Upload route errors must not leak internals."""
        # uploads.py now depends on dependencies.check_rate_limit directly
        # (docs/plans/pre-existing-fixes.md #3, strangler commit 2) — the
        # override must key on that object, not the retired auth_deps shim.
        from reasoner.api.dependencies import check_rate_limit

        secret = "UPLOAD_SECRET_PATH"

        # Bypass rate limiting for this test
        original_override = app.dependency_overrides.get(check_rate_limit)
        app.dependency_overrides[check_rate_limit] = lambda: True
        try:
            with patch("reasoner.api.routes.uploads.save_uploaded_file") as mock_save:
                mock_save.side_effect = RuntimeError(secret)
                response = client.post("/api/upload", files={"file": ("test.txt", b"test")})
        finally:
            if original_override is not None:
                app.dependency_overrides[check_rate_limit] = original_override
            else:
                del app.dependency_overrides[check_rate_limit]

        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is False
        assert secret not in data.get("error", "")
        assert "Internal server error" in data.get("error", "")
