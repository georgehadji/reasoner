"""
Tests for tier-based agent model override in follow-up runs.
Uses fakes — no OPENROUTER_API_KEY required.
"""

import json
from unittest.mock import patch

import pytest

from reasoner.api import RunRequest, run_stream
from reasoner.models import ConversationState, PipelineState


class FakeProvider:
    def __init__(self, model="fake"):
        self.model = model

    async def complete_with_retry(self, system_prompt, user_prompt, max_tokens=2048, temperature=0.7):
        return "fake"


class FakeRouter:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []
        self._primary = FakeProvider()

    def get(self, role):
        return self._primary

    async def call(self, role, system_prompt, user_prompt, **kwargs):
        self.calls.append((role, system_prompt, user_prompt))
        return self.responses.get(role, "{}"), {"model": "fake", "input_tokens": 10, "output_tokens": 10}

    def describe(self):
        return {"[primary]": "fake"}


def _capture_router_call(*args, **kwargs):
    """Side-effect that records the routing dict and returns a FakeRouter."""
    _capture_router_call.last_routing = kwargs.get("routing", {})
    _capture_router_call.last_primary = kwargs.get("primary_id")
    return FakeRouter()


@pytest.mark.asyncio
async def test_followup_budget_uses_kimi_for_persona_roles():
    """
    When initial_state.agent_model is 'kimi-k2-5', the router should use it
    for synthesis, classification, and decomposition.
    """
    req = RunRequest(problem="test followup budget", preset="multi-perspective-budget")
    state = PipelineState(
        problem=req.problem,
        preset_name=req.preset,
        conversation_state=ConversationState(agent_model="kimi-k2-5"),
    )

    with patch("reasoner.llm.ProviderRouter.from_model_ids", side_effect=_capture_router_call):
        with patch("reasoner.pipeline.ReasonerPipeline._phase_synthesis", return_value=None):
            events = []
            async for line in run_stream(req, initial_state=state):
                if line.startswith("data:"):
                    events.append(json.loads(line.removeprefix("data: ").strip()))

    routing = _capture_router_call.last_routing
    assert routing.get("synthesis") == "kimi-k2-5"
    assert routing.get("classification") == "kimi-k2-5"
    assert routing.get("decomposition") == "kimi-k2-5"
    # Other roles should remain as defined by the preset
    assert "constructive" in routing
    assert "destructive" in routing


@pytest.mark.asyncio
async def test_followup_premium_uses_grok_for_persona_roles():
    """
    When initial_state.agent_model is 'grok-4.3', the router should use it
    for synthesis, classification, and decomposition.
    """
    req = RunRequest(problem="test followup premium", preset="multi-perspective-premium")
    state = PipelineState(
        problem=req.problem,
        preset_name=req.preset,
        conversation_state=ConversationState(agent_model="grok-4.3"),
    )

    with patch("reasoner.llm.ProviderRouter.from_model_ids", side_effect=_capture_router_call):
        with patch("reasoner.pipeline.ReasonerPipeline._phase_synthesis", return_value=None):
            events = []
            async for line in run_stream(req, initial_state=state):
                if line.startswith("data:"):
                    events.append(json.loads(line.removeprefix("data: ").strip()))

    routing = _capture_router_call.last_routing
    assert routing.get("synthesis") == "grok-4.3"
    assert routing.get("classification") == "grok-4.3"
    assert routing.get("decomposition") == "grok-4.3"


@pytest.mark.asyncio
async def test_initial_run_does_not_override_routing():
    """
    When initial_state is None (first turn), the preset routing must remain untouched.

    Expectations are read from the live preset rather than hardcoded model
    names: the preset's own routing table has been re-tuned repeatedly
    (synthesis is "gpt-5.6-luna" for cross-bloc diversity as of this
    writing, not the "qwen3-max"/"gpt-4o-mini"/"deepseek-v3" this test
    originally hardcoded), and separate "classification"/"decomposition"
    routing entries no longer exist at all — both were merged into a single
    "fusion" role (application/pipeline.py::_phase_fusion). Hardcoding a
    snapshot of preset values here would just go stale again next tune;
    what this test actually needs to guard is the invariant that a run with
    no initial_state leaves the preset's routing untouched.
    """
    from reasoner.presets import get_preset

    preset = get_preset("multi-perspective-budget")
    req = RunRequest(problem="test initial run", preset="multi-perspective-budget")

    with patch("reasoner.llm.ProviderRouter.from_model_ids", side_effect=_capture_router_call):
        with patch("reasoner.pipeline.ReasonerPipeline._phase_synthesis", return_value=None):
            events = []
            async for line in run_stream(req, initial_state=None):
                if line.startswith("data:"):
                    events.append(json.loads(line.removeprefix("data: ").strip()))

    routing = _capture_router_call.last_routing
    assert routing.get("synthesis") == preset.routing.get("synthesis")
    # Not overridden -> not invented: the preset defines no separate
    # classification/decomposition roles, so an un-overridden run must not
    # have them either.
    assert "classification" not in preset.routing
    assert "decomposition" not in preset.routing
    assert routing.get("classification") == preset.routing.get("classification")
    assert routing.get("decomposition") == preset.routing.get("decomposition")
