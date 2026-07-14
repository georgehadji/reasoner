"""Tests for authentication and authorization FastAPI dependencies."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from reasoner.api.auth_deps import (
    _get_auth_manager_instance_auth_deps,
    _get_rate_limiter_instance_auth_deps,
    check_rate_limit,
    require_auth,
    optional_auth,
    require_csrf,
)


class TestAuthManagerInstance:
    """Test auth manager singleton factory."""

    def test_returns_same_instance(self):
        instance1 = _get_auth_manager_instance_auth_deps()
        instance2 = _get_auth_manager_instance_auth_deps()
        assert instance1 is instance2

    def test_has_required_methods(self):
        auth_manager = _get_auth_manager_instance_auth_deps()
        assert hasattr(auth_manager, "authenticate")
        assert hasattr(auth_manager, "generate_key")


class TestRateLimiterInstance:
    """Test rate limiter singleton factory."""

    def test_returns_same_instance(self):
        instance1 = _get_rate_limiter_instance_auth_deps()
        instance2 = _get_rate_limiter_instance_auth_deps()
        assert instance1 is instance2

    def test_has_required_methods(self):
        rate_limiter = _get_rate_limiter_instance_auth_deps()
        assert hasattr(rate_limiter, "is_allowed")


class TestRequireAuth:
    """Test require_auth dependency."""

    @pytest.mark.asyncio
    async def test_missing_credentials_raises_401(self):
        from fastapi.security import HTTPAuthorizationCredentials
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(None)  # type: ignore[arg-type]
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_credentials_raises_401(self):
        from fastapi.security import HTTPAuthorizationCredentials
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid-token")
        with pytest.raises(HTTPException) as exc_info:
            await require_auth(creds)
        assert exc_info.value.status_code == 401


class TestOptionalAuth:
    """Test optional_auth dependency."""

    @pytest.mark.asyncio
    async def test_no_credentials_returns_none(self):
        result = await optional_auth(None)  # type: ignore[arg-type]
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_credentials_returns_none(self):
        from fastapi.security import HTTPAuthorizationCredentials
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid-token")
        result = await optional_auth(creds)
        assert result is None


class TestRequireCSRF:
    """Test CSRF token validation dependency."""

    @pytest.mark.asyncio
    async def test_missing_csrf_token_raises_403(self, monkeypatch):
        from unittest.mock import MagicMock
        monkeypatch.setenv("CSRF_ENFORCE_BACKEND", "true")
        # Re-import to pick up the new env var
        from reasoner.core.settings import settings
        monkeypatch.setattr(settings, "CSRF_ENFORCE_BACKEND", True)

        request = MagicMock()
        request.headers = {}
        with pytest.raises(HTTPException) as exc_info:
            await require_csrf(request)
        assert exc_info.value.status_code == 403


class TestCheckRateLimit:
    """Test rate limiting dependency."""

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_after_threshold(self):
        from unittest.mock import MagicMock, AsyncMock
        request = MagicMock()
        request.headers = {"User-Agent": "test"}
        request.client.host = "127.0.0.1"

        rate_limiter = _get_rate_limiter_instance_auth_deps()
        original = rate_limiter.is_allowed

        async def reject(*args, **kwargs):
            return False, {"retry_after": 60, "limit_minute": 60, "remaining_minute": 0}

        rate_limiter.is_allowed = reject
        try:
            with pytest.raises(HTTPException) as exc_info:
                await check_rate_limit(request, None)
            assert exc_info.value.status_code == 429
            assert "Rate limit" in str(exc_info.value.detail)
        finally:
            rate_limiter.is_allowed = original
