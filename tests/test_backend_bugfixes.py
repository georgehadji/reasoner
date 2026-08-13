"""Regression tests for CRITICAL and HIGH bugs found in proactive backend scan.

Bugs covered:
- BUG-001: NameError in RateLimiter.is_allowed() for anonymous users
- BUG-002: WebSocket stop uses wrong RunStateStore instance
- BUG-003: Health-check Postgres pool leak on failure
- BUG-005: Stripe adapter crashes on missing env var / FREE tier
- BUG-006: Stripe adapter crashes on None user_id
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest


class TestRateLimiterAnonymous:
    """BUG-001 regression: is_allowed must not raise NameError on anonymous requests."""

    @pytest.mark.asyncio
    async def test_is_allowed_anonymous_no_nameerror(self):
        from reasoner.rate_limiter import RateLimiter, RateLimitConfig

        limiter = RateLimiter(RateLimitConfig(
            requests_per_minute=10,
            requests_per_hour=100,
            burst_size=5,
        ))
        # This must not raise NameError on 'multiplier'
        allowed, info = await limiter.is_allowed("anon:1234")
        assert allowed is True
        assert "remaining_minute" in info

    @pytest.mark.asyncio
    async def test_is_allowed_anonymous_respects_burst_limit(self):
        from reasoner.rate_limiter import RateLimiter, RateLimitConfig

        limiter = RateLimiter(RateLimitConfig(
            requests_per_minute=10,
            requests_per_hour=100,
            burst_size=2,
        ))
        # Exhaust burst
        for _ in range(2):
            await limiter.is_allowed("anon:1234")

        # Third call should be rejected (burst exhausted)
        allowed, info = await limiter.is_allowed("anon:1234")
        assert allowed is False
        assert info["reason"].startswith("burst_limit")  # "_fallback" suffix when served in-memory


class TestWebSocketCancelPropagation:
    """BUG-002 regression: WebSocket stop must cancel the actual pipeline run."""

    @pytest.mark.asyncio
    async def test_websocket_cancel_uses_same_run_state_manager(self):
        from reasoner.infrastructure.redis.run_state import _run_state_manager
        from reasoner.infrastructure.websocket.manager import handle_websocket_message

        manager = MagicMock()
        manager.send_to_connection = AsyncMock()
        run_id = "test-run-123"

        # Register run via the same manager that streaming.py uses
        cancel_event = await _run_state_manager.add(run_id, user_id=None)
        assert not cancel_event.is_set()

        # Simulate WebSocket stop message
        await handle_websocket_message(
            manager,
            connection_id="conn-1",
            message={"type": "stop", "pipeline_id": run_id},
        )

        # Cancel must have propagated to the actual event
        assert cancel_event.is_set()

        await _run_state_manager.remove(run_id)


class TestHealthCheckPoolReset:
    """BUG-003 regression: Failed health-check DB call must reset the pool."""

    @pytest.mark.asyncio
    async def test_health_check_resets_pool_on_failure(self):
        from reasoner.api.routes.health import health_check

        # Ensure pool starts clean
        import reasoner.api.routes.health as api_mod
        original_pool = api_mod._health_postgres_pool
        api_mod._health_postgres_pool = None

        # The postgres branch is skipped entirely when DATABASE_URL is unset
        # (as in CI), so pin one for the duration of this test.
        original_dsn = api_mod.settings.DATABASE_URL
        api_mod.settings.DATABASE_URL = "postgresql+asyncpg://u:p@localhost:5432/test"

        request = MagicMock()
        request.headers = {}

        # Patch create_pool to fail on first call
        call_count = 0
        async def fake_create_pool(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("DB is down")

        with patch("asyncpg.create_pool", side_effect=fake_create_pool):
            result = await health_check(request)

        assert result["checks"]["postgres"]["status"] == "error"
        # Pool must be reset to None so next health check retries
        assert api_mod._health_postgres_pool is None

        # Restore
        api_mod._health_postgres_pool = original_pool
        api_mod.settings.DATABASE_URL = original_dsn


class TestStripeAdapterRobustness:
    """BUG-005 / BUG-006 regression: Stripe adapter handles edge cases gracefully."""

    def test_price_id_for_free_tier_returns_empty(self):
        from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter
        from reasoner.domain.saas import SubscriptionTier

        adapter = StripeBillingAdapter(api_key="sk_test_dummy")
        result = adapter._price_id_for_tier(SubscriptionTier.FREE)
        assert result == ""

    def test_price_id_for_tier_with_missing_env(self):
        from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter
        from reasoner.domain.saas import SubscriptionTier

        with patch.dict(os.environ, {}, clear=True):
            adapter = StripeBillingAdapter(api_key="sk_test_dummy")
            assert adapter._price_id_for_tier(SubscriptionTier.PRO) == ""
            assert adapter._price_id_for_tier(SubscriptionTier.ENTERPRISE) == ""

    @pytest.mark.asyncio
    async def test_handle_checkout_completed_missing_client_reference_id(self):
        from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter

        adapter = StripeBillingAdapter(api_key="sk_test_dummy")
        session = {"client_reference_id": None, "subscription": "sub_123"}

        with pytest.raises(ValueError, match="Missing client_reference_id"):
            await adapter._handle_checkout_completed(session)

    @pytest.mark.asyncio
    async def test_handle_subscription_updated_missing_user_id(self):
        from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter

        adapter = StripeBillingAdapter(api_key="sk_test_dummy")
        stripe_sub = {"customer": "cus_123"}

        # Mock stripe.Customer.retrieve to return customer without metadata
        fake_customer = MagicMock()
        fake_customer.metadata = {}
        with patch("stripe.Customer.retrieve", return_value=fake_customer):
            with pytest.raises(ValueError, match="Missing reasoner_user_id"):
                await adapter._handle_subscription_updated(stripe_sub)

    @pytest.mark.asyncio
    async def test_handle_subscription_deleted_missing_user_id(self):
        from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter
        from reasoner.domain.saas import SubscriptionTier, SubscriptionStatus

        adapter = StripeBillingAdapter(api_key="sk_test_dummy")
        stripe_sub = {"id": "sub_123", "customer": "cus_123"}

        # Mock stripe.Customer.retrieve to return customer without metadata
        fake_customer = MagicMock()
        fake_customer.metadata = {}
        with patch("stripe.Customer.retrieve", return_value=fake_customer):
            result = await adapter._handle_subscription_deleted(stripe_sub)

        # Should NOT crash; uses random UUID for user_id
        assert result.tier == SubscriptionTier.FREE
        assert result.status == SubscriptionStatus.CANCELLED
        assert isinstance(result.user_id, UUID)
