"""Tests for premium preset tier enforcement and real-tier resolution.

Contract (PRESET_TIER_ENFORCEMENT_ENABLED, default off):

* off -- every authenticated caller may reach every preset (SEC-017, no behaviour
  change); this must hold in production too.
* on  -- a caller below the preset's tier gets a 403 naming the required plan;
  free presets stay open; a subscription-store outage resolves to FREE, so it
  denies paid presets rather than granting them.

The tier-resolution tests cover the other call sites that used to hardcode the
free tier: /api/quota and the query-counter tier label (rate limiting is covered
in test_api_auth_deps.py).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from reasoner.api.dependencies import (
    check_preset_access,
    check_preset_access_if_authenticated,
    require_tier,
    tier_satisfies,
)
from reasoner.core.settings import settings
from reasoner.domain.saas import QuotaResult, SubscriptionTier, User

FREE, PRO, ENT = SubscriptionTier.FREE, SubscriptionTier.PRO, SubscriptionTier.ENTERPRISE


@pytest.fixture
def user() -> User:
    return User(id=UUID("11111111-1111-1111-1111-111111111111"), email="u@example.com")


def _as_tier(tier):
    return patch("reasoner.api.dependencies._resolve_user_tier", AsyncMock(return_value=tier))


@pytest.fixture
def enforcement_on(monkeypatch):
    monkeypatch.setattr(settings, "PRESET_TIER_ENFORCEMENT_ENABLED", True)


def test_enforcement_defaults_off():
    assert type(settings).__dict__["PRESET_TIER_ENFORCEMENT_ENABLED"] is False


def test_tier_ordering():
    assert tier_satisfies(PRO, PRO)
    assert tier_satisfies(ENT, PRO)
    assert tier_satisfies(FREE, FREE)
    assert not tier_satisfies(FREE, PRO)
    assert not tier_satisfies(PRO, ENT)


class TestEnforcementOff:
    """Default: nothing is gated, including under ENVIRONMENT=production."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("env", ["testing", "production"])
    async def test_free_user_allowed_premium_preset(self, user, monkeypatch, env):
        monkeypatch.setattr(settings, "PRESET_TIER_ENFORCEMENT_ENABLED", False)
        monkeypatch.setattr(settings, "ENVIRONMENT", env)
        with _as_tier(FREE) as resolve:
            assert await check_preset_access("debate-premium", user) is None
        resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_require_tier_passes_user_through(self, user, monkeypatch):
        monkeypatch.setattr(settings, "PRESET_TIER_ENFORCEMENT_ENABLED", False)
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        checker = require_tier(PRO)
        assert await checker(user) is user


@pytest.mark.usefixtures("enforcement_on")
class TestEnforcementOn:
    @pytest.mark.asyncio
    async def test_free_user_blocked_from_premium_preset(self, user):
        with _as_tier(FREE), pytest.raises(HTTPException) as exc:
            await check_preset_access("debate-premium", user)
        assert exc.value.status_code == 403
        assert "pro" in exc.value.detail and "debate-premium" in exc.value.detail

    @pytest.mark.asyncio
    async def test_free_presets_stay_open_without_a_tier_lookup(self, user):
        with _as_tier(FREE) as resolve:
            assert await check_preset_access("debate-budget", user) is None
        resolve.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tier", [PRO, ENT])
    async def test_paid_user_allowed_premium_preset(self, user, tier):
        with _as_tier(tier):
            assert await check_preset_access("debate-premium", user) is None

    @pytest.mark.asyncio
    async def test_pro_user_blocked_from_enterprise_preset(self, user):
        with (
            _as_tier(PRO),
            patch("reasoner.api.dependencies.get_preset_tier", return_value=ENT),
            pytest.raises(HTTPException) as exc,
        ):
            await check_preset_access("fake-enterprise-preset", user)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_enterprise_user_allowed_enterprise_preset(self, user):
        with _as_tier(ENT), patch("reasoner.api.dependencies.get_preset_tier", return_value=ENT):
            assert await check_preset_access("fake-enterprise-preset", user) is None

    @pytest.mark.asyncio
    async def test_subscription_store_outage_denies_paid_preset(self, user):
        """Real resolver, broken store: falls back to FREE, so premium is denied."""
        with patch(
            "reasoner.application.services.spend_limit_service._get_subscription_repo",
            side_effect=Exception("DB down"),
        ), pytest.raises(HTTPException) as exc:
            await check_preset_access("debate-premium", user)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_cancelled_subscription_is_not_entitled(self, user):
        from reasoner.domain.saas import Subscription, SubscriptionStatus

        repo = AsyncMock()
        repo.get_subscription_by_user.return_value = Subscription(
            id=uuid4(), user_id=user.id, tier=PRO, status=SubscriptionStatus.CANCELLED,
        )
        with patch(
            "reasoner.application.services.spend_limit_service._get_subscription_repo",
            return_value=repo,
        ), pytest.raises(HTTPException) as exc:
            await check_preset_access("debate-premium", user)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_anonymous_caller_is_not_checked(self):
        with _as_tier(FREE) as resolve:
            assert await check_preset_access_if_authenticated("debate-premium", None) is None
        resolve.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_require_tier_blocks_and_allows(self, user):
        checker = require_tier(PRO)
        with _as_tier(FREE), pytest.raises(HTTPException) as exc:
            await checker(user)
        assert exc.value.status_code == 403
        with _as_tier(PRO):
            assert await checker(user) is user


class TestPresetGateOnRunRoutes:
    """The gate must be wired into /api/run and /api/run-followup."""

    @staticmethod
    async def _post(path, body, tier):
        import reasoner.api as api
        from reasoner.api.dependencies import (
            check_quota_if_authenticated,
            get_optional_user,
            require_credits_if_authenticated,
        )

        u = User(id=uuid4(), email="route@test.local")
        # Credits/quota are not under test; stub them so a fresh in-memory
        # ledger (balance 0) does not turn every run into a 402.
        overrides = {
            get_optional_user: lambda: u,
            check_quota_if_authenticated: lambda: None,
            require_credits_if_authenticated: lambda: None,
        }
        api.app.dependency_overrides.update(overrides)

        async def fake_stream(*args, **kwargs):
            yield 'data: {"type":"done"}\n\n'

        try:
            with (
                _as_tier(tier),
                patch("reasoner.api.run_stream_cached", fake_stream),
                patch("reasoner.api.run_followup_stream", fake_stream),
                patch("reasoner.api.dependencies.reserve_or_402", AsyncMock(return_value=0)),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=api.app), base_url="http://test"
                ) as client:
                    return await client.post(path, json=body)
        finally:
            for dep in overrides:
                api.app.dependency_overrides.pop(dep, None)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,body", [
        ("/api/run", {"problem": "x", "preset": "debate-premium", "no_cache": True}),
        ("/api/run-followup", {"question": "x", "preset": "debate-premium", "conversation_id": "c1", "history": [], "previous_synthesis": "s"}),
    ])
    async def test_free_user_gets_403_when_on(self, monkeypatch, path, body):
        monkeypatch.setattr(settings, "PRESET_TIER_ENFORCEMENT_ENABLED", True)
        response = await self._post(path, body, FREE)
        assert response.status_code == 403, response.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,body", [
        ("/api/run", {"problem": "x", "preset": "debate-premium", "no_cache": True}),
        ("/api/run-followup", {"question": "x", "preset": "debate-premium", "conversation_id": "c1", "history": [], "previous_synthesis": "s"}),
    ])
    async def test_free_user_not_blocked_when_off(self, monkeypatch, path, body):
        monkeypatch.setattr(settings, "PRESET_TIER_ENFORCEMENT_ENABLED", False)
        response = await self._post(path, body, FREE)
        assert response.status_code != 403, response.text

    @pytest.mark.asyncio
    async def test_pro_user_allowed_premium_when_on(self, monkeypatch):
        monkeypatch.setattr(settings, "PRESET_TIER_ENFORCEMENT_ENABLED", True)
        response = await self._post(
            "/api/run", {"problem": "x", "preset": "debate-premium", "no_cache": True}, PRO
        )
        assert response.status_code != 403, response.text


class TestQuotaEndpointUsesRealTier:
    """/api/quota hardcoded FREE, so a Pro user saw max=20."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tier,expected_max,remaining,expected_used", [
        (FREE, 20, 15, 5),
        (PRO, 500, 400, 100),
        (ENT, -1, -1, 0),
    ])
    async def test_quota_reports_tier_limit(self, tier, expected_max, remaining, expected_used):
        import reasoner.api as api
        from reasoner.api.dependencies import get_current_user

        service = AsyncMock()
        service.check.return_value = QuotaResult(allowed=True, remaining=remaining)
        api.app.dependency_overrides[get_current_user] = lambda: User(id=uuid4(), email="q@t.local")
        try:
            with (
                patch("reasoner.api.saas_router.resolve_user_tier", AsyncMock(return_value=tier)),
                patch("reasoner.api.saas_router._get_quota_service", return_value=service),
            ):
                async with AsyncClient(
                    transport=ASGITransport(app=api.app), base_url="http://test"
                ) as client:
                    response = await client.get("/api/quota")
        finally:
            api.app.dependency_overrides.pop(get_current_user, None)

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["max"] == expected_max
        assert data["used"] == expected_used
        assert service.check.await_args.args[1] == tier


class TestQueryMetricTierLabel:
    """The run context (and so the Prometheus query counter) carried "free" for everyone."""

    @staticmethod
    async def _captured_tier(stream_fn, req, user, tier):
        import reasoner.api as api

        captured = {}

        async def fake_metered(stream, ctx, sink, observer):
            captured["ctx_tier"] = ctx.tier
            captured["observer_tier"] = observer._tier
            async for chunk in stream:
                yield chunk

        async def fake_stream(*args, **kwargs):
            yield 'data: {"type":"done"}\n\n'

        with (
            patch(
                "reasoner.application.services.spend_limit_service.resolve_user_tier",
                AsyncMock(return_value=tier),
            ),
            patch("reasoner.application.services.run_metering.metered", fake_metered),
            patch("reasoner.api.run_stream_cached", fake_stream),
            patch("reasoner.api.run_followup_stream", fake_stream),
        ):
            gen = (
                api._run_stream_with_metrics(
                    req, None, user, None, None, reference_id="r", reserved_credits=0
                )
                if stream_fn == "run"
                else api._run_followup_stream_with_metrics(
                    req, None, user, reference_id="r", reserved_credits=0
                )
            )
            async for _ in gen:
                pass
        return captured

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stream_fn", ["run", "followup"])
    @pytest.mark.parametrize("tier", [FREE, PRO, ENT])
    async def test_label_is_resolved_tier(self, stream_fn, tier):
        from reasoner.api.schemas import FollowupRequest, RunRequest

        req = (
            RunRequest(problem="x", preset="debate-budget")
            if stream_fn == "run"
            else FollowupRequest(
                question="x", preset="debate-budget",
                conversation_id="c1", history=[], previous_synthesis="s",
            )
        )
        user = User(id=uuid4(), email="m@t.local")
        got = await self._captured_tier(stream_fn, req, user, tier)
        assert got == {"ctx_tier": tier.value, "observer_tier": tier.value}

    @pytest.mark.asyncio
    async def test_anonymous_label_unchanged_and_no_lookup(self):
        from reasoner.api.schemas import RunRequest

        req = RunRequest(problem="x", preset="debate-budget")
        got = await self._captured_tier("run", req, None, PRO)
        assert got["ctx_tier"] == "anonymous"
