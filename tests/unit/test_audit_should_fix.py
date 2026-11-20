"""Audit should-fix findings 5-9: each test fails on the code before its fix."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.saas import SubscriptionTier

pytestmark = pytest.mark.unit


# ── 5: /api/run-with-context stops at the spend cap ─────────────────────────


@pytest.mark.asyncio
async def test_context_run_stops_at_the_spend_cap():
    from reasoner.api.routes.context import _cost_frames

    state = PipelineState(problem="p")
    ran: list[int] = []

    async def first():
        ran.append(1)
        state._spend_cap_exceeded = True
        state.spend_cap_hit = "per_run"

    async def second():
        ran.append(2)

    frames = [f async for f in _cost_frames(state, [first, second])]

    assert ran == [1]
    assert any("per_run spend cap" in e for e in state.errors)
    assert frames  # the done frame is still sent, so metered() settles


@pytest.mark.asyncio
async def test_context_run_reports_spend_to_metered_before_a_step_raises(monkeypatch):
    from reasoner.api.routes import context

    seen: list[float] = []
    state = PipelineState(problem="p")

    def capture(source):
        seen.append(source)

    async def spend_then_fail():
        state.total_cost_usd = 0.25
        raise RuntimeError("boom")

    monkeypatch.setattr(context, "track_run_spend", capture)
    with pytest.raises(RuntimeError):
        async for _ in context._cost_frames(state, [spend_then_fail]):
            pass
    assert seen and seen[0]() == 0.25


# ── 6: Neuro memory honours API key scopes ──────────────────────────────────


def _neuro_client(tmp_path, monkeypatch, scopes):
    import reasoner.neuro.server as ns
    from reasoner.api.dependencies import get_optional_user
    from reasoner.neuro.config import NeuroConfig, _apply_defaults

    monkeypatch.setattr(ns.settings, "COHERE_RERANK_ENABLED", False, raising=False)
    monkeypatch.delenv("NEURO_INTERNAL_KEY", raising=False)
    cfg = _apply_defaults(NeuroConfig())
    cfg.data_dir = str(tmp_path)
    app = FastAPI()
    app.include_router(ns.create_neuro_router(cfg))

    def key_user(request: Request):
        user = SimpleNamespace(id="u1", scopes=frozenset(scopes))
        request.state.user = user
        request.state.auth_method = "api_key"
        return user

    app.dependency_overrides[get_optional_user] = key_user
    return TestClient(app)


def test_a_narrow_key_cannot_read_or_write_memory(tmp_path, monkeypatch):
    client = _neuro_client(tmp_path, monkeypatch, {"preset:read"})

    assert client.post("/api/neuro/recall", json={"query": "q"}).status_code == 403
    learn = client.post("/api/neuro/learn", json={"prompt": "p", "response": "r"})
    assert learn.status_code == 403
    assert client.get("/api/neuro/sessions").status_code == 403


def test_a_key_with_history_read_may_list_sessions(tmp_path, monkeypatch):
    client = _neuro_client(tmp_path, monkeypatch, {"history:read"})

    assert client.get("/api/neuro/sessions").status_code == 200


# ── 7: a follow-up's agent_model is plan-checked ────────────────────────────


def test_a_premium_agent_model_needs_the_premium_plan():
    from reasoner.application.services import spend_limit_service as sls
    from reasoner.domain.preset_core import FOLLOWUP_AGENT_MODELS

    premium_model = FOLLOWUP_AGENT_MODELS["premium"]
    free = SubscriptionTier.FREE

    rejection = sls.check_run_allowed("debate-budget", free, agent_model=premium_model)
    assert rejection is not None and rejection.cap_type == "preset_tier"
    # The budget default stays open to every plan.
    budget_model = FOLLOWUP_AGENT_MODELS["budget"]
    assert sls.check_run_allowed("debate-budget", free, agent_model=budget_model) is None
    assert (
        sls.check_run_allowed("debate-budget", SubscriptionTier.PRO, agent_model=premium_model)
        is None
    )


# ── 8: an open circuit lets the direct lane run ─────────────────────────────


def test_circuit_open_and_empty_replies_count_as_provider_faults():
    from reasoner.core.exceptions import ProviderUnavailableError
    from reasoner.infrastructure.llm.base import LLMError, is_provider_fault

    # What router.py raises for an open circuit and an empty reply.
    assert is_provider_fault(ProviderUnavailableError("Circuit open for m"))
    # The residual bare LLMError with no cause is unchanged.
    assert not is_provider_fault(LLMError("unclassified"))


# ── 9: cascading accepts fenced JSON ────────────────────────────────────────


def test_fenced_json_is_valid_cascade_output():
    from reasoner.core.parsing import extract_json_any

    assert extract_json_any('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_any("[1, 2]") == [1, 2]
    assert extract_json_any("not json at all") is None
