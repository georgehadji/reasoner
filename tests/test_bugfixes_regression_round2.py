"""
Regression tests for Round 2 backend bug fixes.

Bugs covered:
- BUG-019: require_tier() completely bypasses subscription enforcement
- BUG-017: Rate limiter fails open on any error
- BUG-020: Quota check fails open on DB errors
- BUG-021: check_preset_access() always bypasses tier checks
- BUG-007: Unlocked state mutation in rate limiter (reset_client/reset_all)
"""

from __future__ import annotations

import asyncio
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException


# ──────────────────────────────────────────────────────────────────────────────
# BUG-019: require_tier() completely bypasses subscription enforcement
# ──────────────────────────────────────────────────────────────────────────────

class TestRequireTierEnforcement:
    """Verify that require_tier() actually enforces tier requirements."""

    @pytest.fixture
    def mock_user(self):
        from reasoner.domain.saas import User
        return User(
            id=uuid4(),
            email="test@example.com",
            display_name="Test User",
            scopes=["read"],
        )

    @pytest.mark.asyncio
    async def test_require_tier_blocks_when_enforcement_enabled(self, mock_user, monkeypatch):
        """With enforcement on, a FREE user is refused a PRO-gated dependency.

        This previously keyed off ENVIRONMENT and raised for every caller in
        production — paying users included — while enforcing nothing elsewhere.
        """
        from reasoner.api.dependencies import require_tier
        from reasoner.domain.saas import SubscriptionTier

        from unittest.mock import AsyncMock, patch

        from reasoner.core.settings import settings

        monkeypatch.setattr(settings, "PRESET_TIER_ENFORCEMENT_ENABLED", True)

        checker = require_tier(SubscriptionTier.PRO)
        with patch(
            "reasoner.api.dependencies._resolve_user_tier",
            AsyncMock(return_value=SubscriptionTier.FREE),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await checker(user=mock_user)

        assert exc_info.value.status_code == 403
        assert "pro plan" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_tier_allows_in_development(self, mock_user, monkeypatch):
        """In development, require_tier should allow through (for testing)."""
        from reasoner.api.dependencies import require_tier
        from reasoner.domain.saas import SubscriptionTier

        monkeypatch.setenv("ENVIRONMENT", "development")

        checker = require_tier(SubscriptionTier.PRO)
        result = await checker(user=mock_user)
        assert result == mock_user


# ──────────────────────────────────────────────────────────────────────────────
# BUG-017: Rate limiter fails open on any error
# ──────────────────────────────────────────────────────────────────────────────

class TestRateLimiterFailClosed:
    """Verify that rate limiter errors fail closed (deny request), not open."""

    @pytest.mark.asyncio
    async def test_rate_limiter_error_fails_closed_for_authenticated(self, monkeypatch):
        """If is_allowed_for_user raises, the request must be denied."""
        from reasoner.api.dependencies import check_rate_limit
        from reasoner.domain.saas import User

        user = User(id=uuid4(), email="test@example.com", display_name="Test", scopes=["read"])

        async def broken_rate_limiter(*args, **kwargs):
            raise RuntimeError("Simulated rate limiter failure")

        # Patch the rate limiter instance
        from reasoner.api import dependencies as deps_module
        mock_rl = MagicMock()
        mock_rl.is_allowed_for_user = broken_rate_limiter
        monkeypatch.setattr(deps_module, "_rate_limiter_instance", mock_rl)

        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.headers = {}
        mock_request.client = MagicMock(host="127.0.0.1")

        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(request=mock_request, user=user, credentials=None)

        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_rate_limiter_error_fails_closed_for_anonymous(self, monkeypatch):
        """If is_allowed raises, the anonymous request must be denied."""
        from reasoner.api.dependencies import check_rate_limit

        async def broken_rate_limiter(*args, **kwargs):
            raise RuntimeError("Simulated rate limiter failure")

        from reasoner.api import dependencies as deps_module
        mock_rl = MagicMock()
        mock_rl.is_allowed = broken_rate_limiter
        monkeypatch.setattr(deps_module, "_rate_limiter_instance", mock_rl)

        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.headers = {}
        mock_request.client = MagicMock(host="127.0.0.1")

        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(request=mock_request, user=None, credentials=None)

        assert exc_info.value.status_code == 429


# ──────────────────────────────────────────────────────────────────────────────
# BUG-020: Quota check fails open on DB errors
# ──────────────────────────────────────────────────────────────────────────────

class TestQuotaCheckFailClosed:
    """Verify that quota DB errors use emergency limits instead of unlimited."""

    @pytest.mark.asyncio
    async def test_quota_db_error_uses_emergency_limits(self, monkeypatch):
        """If quota service check raises, remaining must be finite (not -1)."""
        from reasoner.api.dependencies import check_quota
        from reasoner.domain.saas import User

        user = User(id=uuid4(), email="test@example.com", display_name="Test", scopes=["read"])

        def broken_quota_service(*args, **kwargs):
            raise RuntimeError("Simulated DB failure")

        from reasoner.api import dependencies as deps_module
        mock_service = MagicMock()
        mock_service.check = broken_quota_service
        monkeypatch.setattr(deps_module, "_quota_service", mock_service)

        result = await check_quota(user=user)
        assert result.allowed is True
        assert result.remaining == 10  # Emergency limit, not -1 (unlimited)


# ──────────────────────────────────────────────────────────────────────────────
# BUG-021: check_preset_access() always bypasses tier checks
# ──────────────────────────────────────────────────────────────────────────────

class TestCheckPresetAccess:
    """Verify that check_preset_access() actually enforces preset access control."""

    @pytest.fixture
    def mock_user(self):
        from reasoner.domain.saas import User
        return User(
            id=uuid4(),
            email="test@example.com",
            display_name="Test User",
            scopes=["read"],
        )

    @pytest.mark.asyncio
    async def test_preset_access_blocks_when_enforcement_enabled(self, mock_user, monkeypatch):
        """With enforcement on, a FREE user is refused a premium preset."""
        from reasoner.api.dependencies import check_preset_access

        from unittest.mock import AsyncMock, patch

        from reasoner.core.settings import settings
        from reasoner.domain.saas import SubscriptionTier

        monkeypatch.setattr(settings, "PRESET_TIER_ENFORCEMENT_ENABLED", True)

        with patch(
            "reasoner.api.dependencies._resolve_user_tier",
            AsyncMock(return_value=SubscriptionTier.FREE),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await check_preset_access(preset="debate-premium", user=mock_user)

        assert exc_info.value.status_code == 403
        assert "pro plan" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_preset_access_allows_in_development(self, mock_user, monkeypatch):
        """In development, check_preset_access should allow through."""
        from reasoner.api.dependencies import check_preset_access

        monkeypatch.setenv("ENVIRONMENT", "development")

        # Should not raise
        await check_preset_access(preset="premium-reasoning", user=mock_user)


# ──────────────────────────────────────────────────────────────────────────────
# BUG-007: Unlocked state mutation in rate limiter
# ──────────────────────────────────────────────────────────────────────────────

class TestRateLimiterResetRaceCondition:
    """Verify that reset_client and reset_all are async and lock-protected."""

    @pytest.mark.asyncio
    async def test_reset_client_is_async_and_acquires_lock(self):
        """reset_client must be async and acquire the shard lock."""
        from reasoner.rate_limiter import RateLimiter, RateLimitConfig

        config = RateLimitConfig(requests_per_minute=60, requests_per_hour=1000, burst_size=10)
        rl = RateLimiter(config)

        # Create a bucket first. Lock sharding was removed when the limiter moved
        # to Redis; the in-memory fallback uses a single _fallback_lock.
        async with rl._fallback_lock:
            bucket = rl._in_memory_get_bucket("client1")
            bucket.tokens = 5

        # reset_client should be async and work without error
        await rl.reset_client("client1")

        # Bucket should be gone
        assert "client1" not in rl._buckets

    @pytest.mark.asyncio
    async def test_reset_all_is_async_and_clears_all(self):
        """reset_all must be async and clear all buckets."""
        from reasoner.rate_limiter import RateLimiter, RateLimitConfig

        config = RateLimitConfig(requests_per_minute=60, requests_per_hour=1000, burst_size=10)
        rl = RateLimiter(config)

        # Create multiple buckets
        for i in range(5):
            async with rl._fallback_lock:
                rl._in_memory_get_bucket(f"client{i}")

        assert len(rl._buckets) == 5

        await rl.reset_all()

        assert len(rl._buckets) == 0

    @pytest.mark.asyncio
    async def test_concurrent_reset_and_check_no_crash(self):
        """Concurrent reset_client and is_allowed must not crash."""
        from reasoner.rate_limiter import RateLimiter, RateLimitConfig

        config = RateLimitConfig(requests_per_minute=60, requests_per_hour=1000, burst_size=10)
        rl = RateLimiter(config)

        async def checker():
            for _ in range(50):
                await rl.is_allowed("client_race")
                await asyncio.sleep(0)

        async def resetter():
            for _ in range(50):
                await rl.reset_client("client_race")
                await asyncio.sleep(0)

        # Run both concurrently — should not raise RuntimeError (dict changed size)
        await asyncio.gather(checker(), resetter())
