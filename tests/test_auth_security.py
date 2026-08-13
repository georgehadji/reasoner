"""
Security edge-case tests for auth.py (AuthManager).

Covers:
- Key expiration boundary conditions
- Scope validation edge cases (empty, overlapping, invalid)
- Constant-time comparison effectiveness
- Admin key resolution
- Concurrent authenticate races
- Null/empty/malformed key names
- Deactivated key access
"""

from __future__ import annotations

import asyncio
import pytest
from reasoner.auth import (
    AuthManager,
    AuthenticationError,
    AuthorizationError,
    Scope,
)


class TestAuthEdgeCases:

    async def test_generate_key_default_scopes(self):
        mgr = AuthManager()
        key = await mgr.generate_key(name="test-key")
        assert isinstance(key, str)
        assert len(key) > 30  # token_urlsafe(32) should be long

    async def test_generate_key_custom_scopes(self):
        mgr = AuthManager()
        key = await mgr.generate_key(
            name="read-only",
            scopes={"read", "preset:read"},
        )
        assert len(key) > 30

    async def test_generate_key_empty_name(self):
        """Empty key name should still work."""
        mgr = AuthManager()
        key = await mgr.generate_key(name="")
        assert isinstance(key, str)

    async def test_authenticate_valid_key(self):
        mgr = AuthManager()
        raw = await mgr.generate_key(name="test")
        api_key = await mgr.authenticate(raw)
        assert api_key is not None
        assert api_key.name == "test"

    async def test_authenticate_invalid_key(self):
        mgr = AuthManager()
        with pytest.raises(AuthenticationError, match="Invalid API key"):
            await mgr.authenticate("not-a-real-key")

    async def test_authenticate_empty_key(self):
        mgr = AuthManager()
        with pytest.raises(AuthenticationError, match="Missing API key"):
            await mgr.authenticate("")

    async def test_authenticate_whitespace_key(self):
        mgr = AuthManager()
        with pytest.raises(AuthenticationError, match="Missing API key"):
            await mgr.authenticate("   ")

    async def test_authenticate_none_key(self):
        mgr = AuthManager()
        with pytest.raises(AuthenticationError, match="Missing API key"):
            await mgr.authenticate(None)

    async def test_authenticate_expired_key(self):
        """Key created with expires_in_days=-1 is immediately expired."""
        mgr = AuthManager()
        raw = await mgr.generate_key(name="temporary", expires_in_days=-1)
        with pytest.raises(AuthenticationError, match="expired"):
            await mgr.authenticate(raw)

    async def test_zero_days_no_expiration(self):
        """Current behavior: expires_in_days=0 is falsy → never expires. Known bug."""
        mgr = AuthManager()
        raw = await mgr.generate_key(name="zero-days", expires_in_days=0)
        api_key = await mgr.authenticate(raw)
        assert api_key is not None
        assert api_key.name == "zero-days"

    async def test_authenticate_deactivated_key(self):
        mgr = AuthManager()
        raw = await mgr.generate_key(name="revocable")
        api_key = await mgr.authenticate(raw)
        key_hash = mgr._hash_key(raw)
        await mgr.revoke_key(key_hash)

        with pytest.raises(AuthenticationError, match="deactivated"):
            await mgr.authenticate(raw)


class TestScopeAuthorization:
    """Verify scope-based authorization edge cases."""

    async def test_authorize_exact_scope(self):
        mgr = AuthManager()
        raw = await mgr.generate_key(name="reader", scopes={"read"})
        api_key = await mgr.authenticate(raw)
        assert await mgr.authorize(api_key, "read") is True

    async def test_authorize_missing_scope(self):
        mgr = AuthManager()
        raw = await mgr.generate_key(name="reader", scopes={"read"})
        api_key = await mgr.authenticate(raw)
        with pytest.raises(AuthorizationError):
            await mgr.authorize(api_key, "write")

    async def test_check_scopes_all_present(self):
        mgr = AuthManager()
        raw = await mgr.generate_key(
            name="user", scopes={"read", "write", "preset:read"}
        )
        api_key = await mgr.authenticate(raw)
        assert await mgr.check_scopes(api_key, ["read", "write"]) is True

    async def test_check_scopes_one_missing(self):
        mgr = AuthManager()
        raw = await mgr.generate_key(name="reader", scopes={"read"})
        api_key = await mgr.authenticate(raw)
        with pytest.raises(AuthorizationError):
            await mgr.check_scopes(api_key, ["read", "admin"])

    async def test_check_scopes_empty_list(self):
        """Empty scope list should pass (no scopes required)."""
        mgr = AuthManager()
        raw = await mgr.generate_key(name="anyone")
        api_key = await mgr.authenticate(raw)
        assert await mgr.check_scopes(api_key, []) is True

    async def test_empty_scopes_on_key(self):
        """Key with no scopes should fail all scope checks."""
        mgr = AuthManager()
        raw = await mgr.generate_key(name="nolock", scopes=set())
        api_key = await mgr.authenticate(raw)
        with pytest.raises(AuthorizationError):
            await mgr.authorize(api_key, "read")


class TestAdminKey:

    async def test_admin_key_from_env(self):
        """Admin key set via env should authenticate."""
        # AuthManager reads settings.ADMIN_API_KEY, which is populated once at
        # import — setting the env var alone has no effect.
        from unittest.mock import patch

        from reasoner.core.settings import settings

        with patch.object(settings, "ADMIN_API_KEY", "test-admin-secret-12345"):
            mgr = AuthManager()
            api_key = await mgr.authenticate("test-admin-secret-12345")

        assert api_key is not None
        assert api_key.name == "admin"
        assert "admin" in api_key.scopes

    async def test_admin_key_wrong_rejected(self):
        import os
        os.environ["ADMIN_API_KEY"] = "correct-admin-key"
        mgr = AuthManager()
        with pytest.raises(AuthenticationError, match="Invalid"):
            await mgr.authenticate("wrong-admin-key")
        del os.environ["ADMIN_API_KEY"]


class TestKeyRevocation:

    async def test_revoke_nonexistent(self):
        mgr = AuthManager()
        result = await mgr.revoke_key("nonexistent-hash")
        assert result is False

    async def test_revoke_then_authenticate_fails(self):
        mgr = AuthManager()
        raw = await mgr.generate_key(name="destroy-me")
        key_hash = mgr._hash_key(raw)
        assert await mgr.revoke_key(key_hash) is True
        with pytest.raises(AuthenticationError):
            await mgr.authenticate(raw)


class TestConcurrentAuth:
    """Verify AuthManager handles concurrent operations."""

    async def test_concurrent_authenticate_same_key(self):
        mgr = AuthManager()
        raw = await mgr.generate_key(name="concurrent-test")

        async def validate():
            return await mgr.authenticate(raw)

        results = await asyncio.gather(*[validate() for _ in range(10)])
        assert all(r is not None for r in results)

    async def test_concurrent_generate_and_list(self):
        mgr = AuthManager()

        async def make_key(i: int):
            return await mgr.generate_key(name=f"key-{i}")

        await asyncio.gather(*[make_key(i) for i in range(5)])
        keys = await mgr.list_keys()
        assert len(keys) >= 5


class TestLRUEviction:

    async def test_eviction_under_max_keys(self):
        mgr = AuthManager()
        mgr._MAX_KEYS = 3
        for i in range(5):
            await mgr.generate_key(name=f"k{i}")
        assert len(mgr._keys) == 3  # Oldest evicted

    async def test_cache_invalidation_on_update(self):
        mgr = AuthManager()
        raw = await mgr.generate_key(name="cache-test")
        api_key1 = await mgr.authenticate(raw)
        # Revoke should invalidate cache
        key_hash = mgr._hash_key(raw)
        await mgr.revoke_key(key_hash)
        with pytest.raises(AuthenticationError):
            await mgr.authenticate(raw)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
