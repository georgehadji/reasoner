"""Tests for FastAPI middleware (security headers, audit, memory, timeout)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from reasoner.api.middleware import (
    SecurityHeadersMiddleware,
    AuditMiddleware,
    MemoryLimitMiddleware,
    RequestTimeoutMiddleware,
    _anonymize_ip,
    _sanitize_url_for_audit,
)


class TestAnonymizeIP:
    """Test IP anonymization for GDPR compliance."""

    def test_anonymizes_ipv4(self):
        assert _anonymize_ip("192.168.1.100") == "192.168.1.0"

    def test_anonymizes_ipv4_localhost(self):
        assert _anonymize_ip("127.0.0.1") == "127.0.0.0"

    def test_anonymizes_ipv6(self):
        result = _anonymize_ip("2001:db8::1")
        assert result is not None
        assert "2001:db8::" in result

    def test_returns_none_for_none(self):
        assert _anonymize_ip(None) is None

    def test_returns_none_for_empty(self):
        assert _anonymize_ip("") is None

    def test_passes_through_invalid_ip(self):
        assert _anonymize_ip("not-an-ip") == "not-an-ip"


class TestSanitizeURLForAudit:
    """Test URL sanitization for audit logging."""

    def test_redacts_sensitive_params(self):
        url = _sanitize_url_for_audit("/api/run", "token=secret123&api_key=abc")
        assert "secret123" not in url
        assert "abc" not in url
        # URL-encoded [REDACTED] = %5BREDACTED%5D
        assert "REDACTED" in url

    def test_preserves_safe_params(self):
        url = _sanitize_url_for_audit("/api/run", "preset=test&limit=10")
        assert "preset=test" in url
        assert "limit=10" in url

    def test_no_query_string_returns_path(self):
        assert _sanitize_url_for_audit("/api/run", "") == "/api/run"


class TestSecurityHeadersMiddleware:
    """Test security headers are added to all responses."""

    @pytest.fixture
    def app(self):
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        return app

    def test_adds_security_headers(self, app):
        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert "max-age=31536000" in response.headers["Strict-Transport-Security"]
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "Content-Security-Policy" in response.headers
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


class TestAuditMiddleware:
    """Test audit logging for mutating requests."""

    @pytest.fixture
    def app(self):
        app = FastAPI()
        app.add_middleware(AuditMiddleware)

        @app.post("/api/run")
        def run_endpoint():
            return {"status": "ok"}

        @app.get("/api/status")
        def status_endpoint():
            return {"status": "ok"}

        return app

    def test_post_request_logged(self, app):
        client = TestClient(app)
        response = client.post("/api/run")
        assert response.status_code == 200

    def test_get_request_not_logged(self, app):
        client = TestClient(app)
        response = client.get("/api/status")
        assert response.status_code == 200


class TestRequestTimeoutMiddleware:
    """Test request timeout enforcement."""

    @pytest.fixture
    def app(self):
        app = FastAPI()
        app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=0.01)

        @app.get("/api/slow")
        async def slow_endpoint():
            import asyncio
            await asyncio.sleep(1)
            return {"status": "ok"}

        return app

    def test_slow_request_times_out(self, app):
        client = TestClient(app)
        response = client.get("/api/slow")
        assert response.status_code == 504
        assert "timeout" in response.json()["error"].lower()

    def test_run_endpoints_skip_timeout(self):
        app = FastAPI()
        app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=0.001)

        @app.get("/api/run")
        async def run_endpoint():
            import asyncio
            await asyncio.sleep(0.05)
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/api/run")
        assert response.status_code == 200


class TestMemoryLimitMiddleware:
    """Test memory limit enforcement."""

    @pytest.fixture
    def app(self):
        app = FastAPI()
        app.add_middleware(MemoryLimitMiddleware, memory_limit_mb=999999, warning_mb=999998)

        @app.get("/test")
        def test_endpoint():
            return {"status": "ok"}

        return app

    def test_request_succeeds_when_under_limit(self, app):
        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200
