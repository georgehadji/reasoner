"""Audit 9 LLM/infra findings: one test each."""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import openai
import pytest

pytestmark = pytest.mark.unit


def test_f1_client_400_is_not_provider_fault():
    from reasoner.infrastructure.llm.base import is_provider_fault
    from reasoner.infrastructure.llm.providers.openai_compat import _translate

    req = httpx.Request("POST", "https://x.test/v1")
    raw = openai.BadRequestError("bad", response=httpx.Response(400, request=req), body=None)
    try:
        raise _translate("m", raw) from raw
    except Exception as err:
        assert is_provider_fault(err) is False
    server = openai.InternalServerError("boom", response=httpx.Response(500, request=req), body=None)
    try:
        raise _translate("m", server) from server
    except Exception as err:
        assert is_provider_fault(err) is True


@pytest.mark.asyncio
async def test_f2_direct_chain_skips_unaffordable():
    from reasoner.infrastructure.llm import router as r

    tried = []

    class P:
        def __init__(self, name):
            self.model = name

        async def complete(self, **kw):
            tried.append(self.model)
            return "ok"

    with patch("reasoner.core.settings.settings") as st, \
         patch("reasoner.infrastructure.llm.providers.direct.build_fallback_provider",
               side_effect=lambda n: P(n)), \
         patch.object(r.ProviderRouter, "_affordable_fallback",
                      staticmethod(lambda role, a, c: c.model != "anthropic")):
        st.MULTI_PROVIDER_FALLBACK_ENABLED = True
        out = await r._walk_direct_fallback_chain(
            "role", "s", "u", RuntimeError("x"), 10, 0.1, None, P("cheap"))
    assert tried == ["openai"] and out[0] == "ok"


@pytest.mark.asyncio
async def test_f3_empty_attempt_cost_carried_forward():
    from reasoner.infrastructure.llm.router import ProviderRouter

    class Empty:
        model = "a"
        last_input_tokens = 10
        last_output_tokens = 0
        last_cost_usd = 0.5

    class Good:
        model = "b"
        last_input_tokens = 20
        last_output_tokens = 5
        last_cost_usd = 0.25

    router = ProviderRouter.__new__(ProviderRouter)
    router.get = lambda role: Empty()
    router._timeout_for_role = lambda role, t: 5
    router._resolve_fallback = lambda role, a: Good()
    router.on_fallback = None
    seen = []

    async def attempt(role, provider, *a, **k):
        seen.append(provider.model)
        return "" if provider.model == "a" else "answer"

    router._attempt_call_and_record = attempt
    with patch("reasoner.infrastructure.llm.router._per_call", lambda p: p):
        _, meta = await router.call("role", "s", "u")
    assert seen == ["a", "b"]
    assert meta["cost_usd"] == pytest.approx(0.75)
    assert meta["input_tokens"] == 30


@pytest.mark.asyncio
async def test_f3_truncation_retry_empty_adds_cost():
    from reasoner.infrastructure.llm.executor import LLMExecutor

    ex = LLMExecutor.__new__(LLMExecutor)
    ex.router = MagicMock()
    ex.router.call = AsyncMock(return_value=("", {"cost_usd": 0.3, "input_tokens": 4}))
    with patch("reasoner.infrastructure.llm.executor._requests_strict_json", return_value=True):
        raw, meta = await ex._retry_after_truncation(
            "role", "json", "u", {"max_tokens": 100}, "cut", {"model": "m", "cost_usd": 0.2})
    assert raw == "cut" and meta["cost_usd"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_f4_near_miss_prompt_does_not_hit():
    from reasoner.infrastructure.token_cache import TokenAwareCache

    c = TokenAwareCache(max_tokens=10_000)
    await c.set("p", "ph", "m", "how to sort a list in python", "A", 10)
    assert await c.get("p", "ph", "m", "how to sort a list in python language") is None
    assert await c.get("p", "ph", "m", "how to sort a list in python") == "A"


@pytest.mark.asyncio
async def test_f5_active_set_ttl_covers_pipeline_timeout():
    from reasoner.core.constants_limits import PIPELINE_ABSOLUTE_TIMEOUT_SECONDS
    from reasoner.infrastructure.redis import run_state as rs

    assert rs.ACTIVE_TTL_SECONDS > PIPELINE_ABSOLUTE_TIMEOUT_SECONDS
    redis = MagicMock()
    for m in ("set", "sadd", "expire"):
        setattr(redis, m, AsyncMock())
    store = rs.RunStateManager.__new__(rs.RunStateManager)
    store._get_redis = lambda: redis
    await store._add_redis("r1", "u")
    redis.expire.assert_any_await(rs.ACTIVE_SET, rs.ACTIVE_TTL_SECONDS)


def test_f6_openai_sdk_retries_disabled():
    from reasoner.infrastructure.llm.providers.openai_compat import OpenAICompatibleProvider

    p = OpenAICompatibleProvider(api_key="k", base_url="https://x.test/v1", model="m")
    assert p.client.max_retries == 0


@pytest.mark.asyncio
async def test_f7_cron_removes_idle_tenant_only_inside_root(tmp_path):
    from reasoner.api.cron import _expire_tenant_dir, run_neuro_maintenance

    root = tmp_path / "agents"
    old, fresh = root / "old", root / "fresh"
    for d in (old, fresh):
        d.mkdir(parents=True)
        (d / "f.json").write_text("{}")
    past = time.time() - 91 * 86400
    os.utime(old / "f.json", (past, past))
    os.utime(old, (past, past))
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "f").write_text("x")
    os.utime(outside / "f", (past, past))
    assert _expire_tenant_dir(outside, root, 90) is False and outside.exists()

    cfg = MagicMock(data_dir=str(tmp_path))
    svc = MagicMock()
    svc.tenants.is_erased.return_value = False
    with patch("reasoner.neuro.config.load_config", return_value=cfg), \
         patch("reasoner.neuro.server.get_neuro_service", return_value=svc), \
         patch("reasoner.neuro.sessions.SessionManager") as sm:
        sm.return_value.archive_hot_sessions = AsyncMock(return_value=[])
        sm.return_value.archive_warm_to_cold.return_value = []
        result = await run_neuro_maintenance()
    assert not old.exists() and fresh.exists()
    assert result["expired_tenants"] == 1
