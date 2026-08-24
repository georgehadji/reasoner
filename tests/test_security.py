"""
Security Tests - Verify security fixes work correctly.
"""


import pytest

from reasoner.widgets import calculate_expression


class TestSafeExpressionEvaluator:
    """Test that eval() replacement is secure."""

    def test_basic_arithmetic(self):
        """Test basic arithmetic operations work."""
        result = calculate_expression("2 + 2")
        assert result["valid"] is True
        assert result["result"] == 4

    def test_complex_expression(self):
        """Test complex expressions work."""
        result = calculate_expression("(2 + 3) * 4 - 10 / 2")
        assert result["valid"] is True
        assert result["result"] == 15.0

    def test_constants(self):
        """Test mathematical constants work."""
        result = calculate_expression("pi * 2")
        assert result["valid"] is True
        assert abs(result["result"] - 6.283185307179586) < 0.0001

    def test_safe_functions(self):
        """Test safe functions work."""
        result = calculate_expression("abs(-5)")
        assert result["valid"] is True
        assert result["result"] == 5

    def test_division_by_zero_rejected(self):
        """Test division by zero is rejected."""
        result = calculate_expression("10 / 0")
        assert result["valid"] is False
        assert "Division by zero" in result["error"]

    def test_exponent_too_large_rejected(self):
        """Test excessive exponentiation is rejected."""
        result = calculate_expression("2 ** 1001")
        assert result["valid"] is False
        assert "Exponent too large" in result["error"]

    def test_code_injection_attempt_rejected(self):
        """Test code injection attempts are rejected."""
        # Try to inject Python code
        malicious = [
            "__import__('os').system('ls')",
            "import os",
            "eval('1+1')",
            "exec('print(1)')",
            "open('/etc/passwd').read()",
            "lambda: 1",
            "class Foo: pass",
            "def foo(): pass",
        ]

        for expr in malicious:
            result = calculate_expression(expr)
            assert result["valid"] is False, f"Should reject: {expr}"
            # Check that error message indicates rejection (varies by attack type)
            error = result.get("error", "")
            assert any(keyword in error for keyword in ["Unsafe", "Invalid", "Unsupported", "Function calls"]), f"Should have security error: {expr}"

    def test_attribute_access_rejected(self):
        """Test attribute access is rejected."""
        result = calculate_expression("(1).__class__")
        assert result["valid"] is False

    def test_subscript_access_rejected(self):
        """Test subscript access is rejected."""
        result = calculate_expression("[1,2,3][0]")
        assert result["valid"] is False


class TestRateLimiter:
    """Test rate limiter works correctly."""

    @pytest.mark.asyncio
    async def test_rate_limit_enforcement(self):
        """Test that rate limits are enforced."""
        from reasoner.rate_limiter import RateLimitConfig, RateLimiter

        limiter = RateLimiter(RateLimitConfig(
            requests_per_minute=3,
            requests_per_hour=100,
            burst_size=3,
        ))

        # First 3 requests should succeed
        for i in range(3):
            allowed, info = await limiter.is_allowed("test_client")
            assert allowed is True, f"Request {i+1} should be allowed"

        # 4th request should fail
        allowed, info = await limiter.is_allowed("test_client")
        assert allowed is False
        assert info["retry_after"] is not None

    @pytest.mark.asyncio
    async def test_different_clients_independent(self):
        """Test that different clients have independent limits."""
        from reasoner.rate_limiter import RateLimitConfig, RateLimiter

        limiter = RateLimiter(RateLimitConfig(
            requests_per_minute=2,
            requests_per_hour=100,
            burst_size=2,
        ))

        # Client 1 uses all tokens
        await limiter.is_allowed("client1")
        await limiter.is_allowed("client1")

        # Client 2 should still be allowed
        allowed, _ = await limiter.is_allowed("client2")
        assert allowed is True


class TestAuthManager:
    """Test authentication manager works correctly."""

    @pytest.mark.asyncio
    async def test_key_generation_and_auth(self):
        """Test key generation and authentication."""
        from reasoner.auth import AuthManager

        manager = AuthManager()

        # Generate a key
        raw_key = await manager.generate_key("test_key", expires_in_days=30, scopes={"read", "write"})

        # Authenticate with the key
        api_key = await manager.authenticate(raw_key)
        assert api_key is not None
        assert api_key.name == "test_key"
        assert "read" in api_key.scopes
        assert "write" in api_key.scopes

    @pytest.mark.asyncio
    async def test_invalid_key_rejected(self):
        """Test that invalid keys are rejected."""
        from reasoner.auth import AuthenticationError, AuthManager

        manager = AuthManager()

        with pytest.raises(AuthenticationError):
            await manager.authenticate("invalid_key")

    @pytest.mark.asyncio
    async def test_scope_authorization(self):
        """Test scope-based authorization."""
        from reasoner.auth import AuthManager, AuthorizationError

        manager = AuthManager()

        # Generate key with only 'read' scope
        raw_key = await manager.generate_key("read_only", scopes={"read"})
        api_key = await manager.authenticate(raw_key)

        # Read should succeed
        assert await manager.authorize(api_key, "read") is True

        # Write should fail
        with pytest.raises(AuthorizationError) as exc_info:
            await manager.authorize(api_key, "write")
        assert "Insufficient permissions" in str(exc_info.value)


class TestSecurityHeaders:
    """Test security headers are set correctly."""

    def test_security_headers_middleware(self):
        """Test security headers middleware."""
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        from reasoner.api import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        def test():
            return {"test": "test"}

        client = TestClient(app)
        response = client.get("/test")

        # Check security headers
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-XSS-Protection") == "1; mode=block"
        assert "Strict-Transport-Security" in response.headers


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
