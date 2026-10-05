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

import asyncio
from enum import Enum
from types import SimpleNamespace
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


def _req():
    """A bare request stand-in: the tier memo only needs ``.state``."""
    return SimpleNamespace(state=SimpleNamespace())


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


class _Platinum(str, Enum):
    """A tier value the ranking has never heard of."""

    PLATINUM = "platinum"


def test_unknown_required_tier_fails_closed():
    """An unrecognised required tier must not be satisfiable, even by ENTERPRISE."""
    assert not tier_satisfies(ENT, _Platinum.PLATINUM)
    assert not tier_satisfies(FREE, _Platinum.PLATINUM)


def test_auto_premium_alias_requires_pro():
    """auto-premium is not a registered preset (it resolves to one after admission);
    the early gate must treat it as PRO, matching what it resolves to at runtime."""
    from reasoner.application.services.spend_limit_service import required_tier_for

    assert required_tier_for("auto-premium") is PRO
    assert required_tier_for("auto-budget") is FREE
    assert required_tier_for("no-such-preset") is FREE


def test_runtime_gate_refuses_unknown_required_tier(monkeypatch):
    """check_run_allowed shares tier_satisfies, so it fails closed too."""
    from reasoner.application.services import spend_limit_service as svc

    monkeypatch.setattr(svc, "required_tier_for", lambda _preset: _Platinum.PLATINUM)
    rejection = svc.check_run_allowed("whatever", ENT)
    assert rejection is not None and rejection.cap_type == "preset_tier"


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
        assert await checker(_req(), user) is user


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
            patch("reasoner.api.dependencies.required_tier_for", return_value=ENT),
            pytest.raises(HTTPException) as exc,
        ):
            await check_preset_access("fake-enterprise-preset", user)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_enterprise_user_allowed_enterprise_preset(self, user):
        with _as_tier(ENT), patch("reasoner.api.dependencies.required_tier_for", return_value=ENT):
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
    async def test_free_user_blocked_from_auto_premium(self, user):
        with _as_tier(FREE), pytest.raises(HTTPException) as exc:
            await check_preset_access("auto-premium", user)
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
            await checker(_req(), user)
        assert exc.value.status_code == 403
        with _as_tier(PRO):
            assert await checker(_req(), user) is user


class TestTierResolutionIsBoundedAndMemoised:
    """The tier is needed by the rate limiter, quota, gate and run label on one
    request; each lookup can block on a cold cache + slow Postgres."""

    @pytest.mark.asyncio
    async def test_resolved_once_per_request(self, user):
        from reasoner.api.dependencies import resolve_request_tier

        request = _req()
        with _as_tier(PRO) as resolve:
            assert await resolve_request_tier(request, user) is PRO
            assert await resolve_request_tier(request, user) is PRO
            assert await resolve_request_tier(request, user) is PRO
        assert resolve.await_count == 1

    @pytest.mark.asyncio
    async def test_memo_is_not_shared_across_requests_or_users(self, user):
        from reasoner.api.dependencies import resolve_request_tier

        other = User(id=uuid4(), email="o@example.com")
        request = _req()
        with _as_tier(PRO) as resolve:
            await resolve_request_tier(request, user)
            await resolve_request_tier(request, other)
            await resolve_request_tier(_req(), user)
        assert resolve.await_count == 3

    @pytest.mark.asyncio
    async def test_gate_and_quota_share_one_lookup(self, enforcement_on, user):
        from reasoner.api.dependencies import check_quota

        request = _req()
        service = AsyncMock()
        service.check.return_value = QuotaResult(allowed=True, remaining=5)
        with (
            _as_tier(PRO) as resolve,
            patch("reasoner.api.dependencies._get_quota_service", return_value=service),
        ):
            await check_quota(user, request)
            await check_preset_access("debate-premium", user, request)
            await check_preset_access_if_authenticated("debate-premium", user, request)
        assert resolve.await_count == 1

    @pytest.mark.asyncio
    async def test_slow_lookup_times_out_to_free_with_warning(self, user, monkeypatch, caplog):
        import logging

        from reasoner.application.services import spend_limit_service as svc

        class _Hang:
            async def get_subscription_by_user(self, _uid):
                await asyncio.sleep(30)

        monkeypatch.setattr(svc, "TIER_LOOKUP_TIMEOUT_S", 0.05)
        monkeypatch.setattr(svc, "_get_subscription_repo", lambda: _Hang())
        with caplog.at_level(logging.WARNING, logger=svc.logger.name):
            tier = await asyncio.wait_for(svc.resolve_user_tier(str(user.id)), timeout=5)
        assert tier is FREE
        assert any(
            r.levelno >= logging.WARNING and "timed out" in r.getMessage()
            for r in caplog.records
        )


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
        assert response.status_code == 200, response.text

    @pytest.mark.asyncio
    async def test_pro_user_allowed_premium_when_on(self, monkeypatch):
        monkeypatch.setattr(settings, "PRESET_TIER_ENFORCEMENT_ENABLED", True)
        response = await self._post(
            "/api/run", {"problem": "x", "preset": "debate-premium", "no_cache": True}, PRO
        )
        assert response.status_code == 200, response.text

    @pytest.mark.asyncio
    async def test_403_does_not_lock_the_client_run_id(self, monkeypatch):
        """The gate runs before register_run_or_error, so a refused run's
        client_run_id stays usable (it used to be locked for an hour)."""
        monkeypatch.setattr(settings, "PRESET_TIER_ENFORCEMENT_ENABLED", True)
        body = {
            "problem": "x", "preset": "debate-premium", "no_cache": True,
            "client_run_id": "run-gated-1",
        }
        with patch(
            "reasoner.api.idempotency_http.register_run_or_error", AsyncMock()
        ) as register:
            response = await self._post("/api/run", body, FREE)
            assert response.status_code == 403, response.text
            register.assert_not_awaited()

            response = await self._post("/api/run", body, PRO)
            assert response.status_code == 200, response.text
            register.assert_awaited_once_with("run-gated-1")


class TestQuotaEndpointUsesRealTier:
    """/api/quota hardcoded FREE, so a Pro user saw max=20."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tier,expected_max,remaining,expected_used", [
        (FREE, 20, 15, 5),
        (PRO, 500, 400, 100),
        (ENT, None, -1, 0),
    ])
    async def test_quota_reports_tier_limit(self, tier, expected_max, remaining, expected_used):
        import reasoner.api as api
        from reasoner.api.dependencies import get_current_user

        service = AsyncMock()
        service.check.return_value = QuotaResult(allowed=True, remaining=remaining)
        api.app.dependency_overrides[get_current_user] = lambda: User(id=uuid4(), email="q@t.local")
        try:
            with (
                _as_tier(tier),
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
        # Unlimited is an explicit signal, never the internal -1 sentinel as a limit.
        assert data["unlimited"] is (tier is ENT)
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
            _as_tier(tier),
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


class TestAgentRouteTierLabel:
    """The agent HTTP routes hardcoded tier="free" in the run context and observer."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tier", [FREE, PRO, ENT])
    async def test_agent_stream_carries_resolved_tier(self, user, tier):
        from reasoner.api.routes import agent

        captured = {}

        async def fake_metered(stream, ctx, sink, observer):
            captured["ctx_tier"] = ctx.tier
            captured["observer_tier"] = observer._tier
            async for chunk in stream:
                yield chunk

        async def fake_stream(*args, **kwargs):
            yield 'data: {"type":"done"}\n\n'

        with (
            _as_tier(tier),
            patch.object(agent, "metered", fake_metered),
            patch("reasoner.api.streaming.run_stream_cached", fake_stream),
        ):
            async for _ in agent._metered_agent_stream(
                SimpleNamespace(), _req(), user, None, None,
                preset="debate-budget", interface="agent_http",
                reference_id="r", reserved_credits=0,
            ):
                pass
        assert captured == {"ctx_tier": tier.value, "observer_tier": tier.value}


@pytest.fixture(autouse=True)
def _clear_tier_fallback_cache():
    from reasoner.application.services import spend_limit_service as svc

    getattr(svc, "_fallback_until", {}).clear()
    yield
    getattr(svc, "_fallback_until", {}).clear()


class _SlowRepo:
    """Subscription repo whose lookup outlasts the timeout; counts calls."""

    def __init__(self, delay: float, result=None):
        self.delay = delay
        self.result = result
        self.calls = 0

    async def get_subscription_by_user(self, _uid):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return self.result


class TestFallbackCacheAndLookupBudget:
    @pytest.mark.asyncio
    async def test_timeout_fallback_is_remembered_so_outage_costs_one_wait(
        self, user, monkeypatch
    ):
        from reasoner.application.services import spend_limit_service as svc

        repo = _SlowRepo(delay=30)
        monkeypatch.setattr(svc, "TIER_LOOKUP_TIMEOUT_S", 0.05)
        monkeypatch.setattr(svc, "_get_subscription_repo", lambda: repo)

        assert await svc.resolve_user_tier(str(user.id)) is FREE
        assert repo.calls == 1
        # Within the window: answered from memory, no second wait, no second call.
        loop = asyncio.get_running_loop()
        started = loop.time()
        assert await svc.resolve_user_tier(str(user.id)) is FREE
        assert loop.time() - started < 0.04
        assert repo.calls == 1

    @pytest.mark.asyncio
    async def test_fallback_memory_expires(self, user, monkeypatch):
        from reasoner.application.services import spend_limit_service as svc

        repo = _SlowRepo(delay=30)
        monkeypatch.setattr(svc, "TIER_LOOKUP_TIMEOUT_S", 0.02)
        monkeypatch.setattr(svc, "FALLBACK_CACHE_TTL_S", 0.0)
        monkeypatch.setattr(svc, "_get_subscription_repo", lambda: repo)

        await svc.resolve_user_tier(str(user.id))
        await svc.resolve_user_tier(str(user.id))
        assert repo.calls == 2

    @pytest.mark.asyncio
    async def test_a_real_answer_is_never_negative_cached(self, user, monkeypatch):
        from reasoner.application.services import spend_limit_service as svc

        repo = _SlowRepo(delay=0, result=None)
        monkeypatch.setattr(svc, "_get_subscription_repo", lambda: repo)
        await svc.resolve_user_tier(str(user.id))
        await svc.resolve_user_tier(str(user.id))
        assert repo.calls == 2  # "no subscription" is an answer, not a fallback

    @pytest.mark.asyncio
    async def test_run_gate_budget_outlasts_request_budget_and_bypasses_memory(
        self, user, monkeypatch
    ):
        from reasoner.application.services import spend_limit_service as svc
        from reasoner.domain.saas import Subscription, SubscriptionStatus

        sub = Subscription(
            id=uuid4(), user_id=user.id, tier=PRO, status=SubscriptionStatus.ACTIVE,
        )
        repo = _SlowRepo(delay=0.2, result=sub)
        monkeypatch.setattr(svc, "TIER_LOOKUP_TIMEOUT_S", 0.05)
        monkeypatch.setattr(svc, "_get_subscription_repo", lambda: repo)

        # Request path gives up and remembers FREE ...
        assert await svc.resolve_user_tier(str(user.id)) is FREE
        # ... but the run gate, with a longer budget and no memory, still sees PRO.
        got = await svc.resolve_user_tier(
            str(user.id), timeout=2.0, use_fallback_cache=False
        )
        assert got is PRO

    def test_run_gate_call_site_uses_the_longer_budget(self):
        import inspect

        from reasoner.api.execution import pipeline
        from reasoner.application.services import spend_limit_service as svc

        assert svc.RUN_TIER_LOOKUP_TIMEOUT_S > svc.TIER_LOOKUP_TIMEOUT_S
        src = inspect.getsource(pipeline)
        assert "timeout=RUN_TIER_LOOKUP_TIMEOUT_S" in src
        assert "use_fallback_cache=False" in src


class TestSubscriptionPoolSurvivesTimeout:
    """A first connect slower than the tier-lookup timeout must not be cancelled
    (it used to be, leaving every user FREE for as long as connect stayed slow)."""

    @pytest.fixture
    def repo_cls(self, monkeypatch):
        from reasoner.infrastructure.persistence import subscription_repo as mod

        cls = mod.PostgresSubscriptionRepository
        monkeypatch.setattr(cls, "_pool", None)
        monkeypatch.setattr(cls, "_pool_task", None, raising=False)
        return mod, cls

    @pytest.mark.asyncio
    async def test_slow_first_connect_completes_in_background(self, repo_cls, monkeypatch):
        mod, cls = repo_cls
        sentinel = object()
        calls = {"n": 0, "cancelled": False}

        async def slow_create_pool(*args, **kwargs):
            calls["n"] += 1
            try:
                await asyncio.sleep(0.2)
            except asyncio.CancelledError:
                calls["cancelled"] = True
                raise
            return sentinel

        monkeypatch.setattr(mod.asyncpg, "create_pool", slow_create_pool)
        repo = cls("postgresql://x")

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(repo._get_pool(), timeout=0.05)
        assert calls["cancelled"] is False

        await asyncio.sleep(0.3)  # connect finishes in the background
        assert cls._pool is sentinel
        assert await repo._get_pool() is sentinel
        assert calls["n"] == 1

    @pytest.mark.asyncio
    async def test_concurrent_callers_share_one_connect(self, repo_cls, monkeypatch):
        mod, cls = repo_cls
        sentinel = object()
        calls = {"n": 0}

        async def create_pool(*args, **kwargs):
            calls["n"] += 1
            await asyncio.sleep(0.05)
            return sentinel

        monkeypatch.setattr(mod.asyncpg, "create_pool", create_pool)
        repo = cls("postgresql://x")
        pools = await asyncio.gather(*(repo._get_pool() for _ in range(5)))
        assert all(p is sentinel for p in pools)
        assert calls["n"] == 1

    @pytest.mark.asyncio
    async def test_failed_connect_is_retried(self, repo_cls, monkeypatch):
        mod, cls = repo_cls
        sentinel = object()
        attempts = {"n": 0}

        async def flaky_create_pool(*args, **kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise OSError("connection refused")
            return sentinel

        monkeypatch.setattr(mod.asyncpg, "create_pool", flaky_create_pool)
        repo = cls("postgresql://x")
        with pytest.raises(OSError):
            await repo._get_pool()
        assert await repo._get_pool() is sentinel
        assert attempts["n"] == 2
