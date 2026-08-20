"""
Tests for tier-based agent model override in follow-up runs.
Uses fakes — no OPENROUTER_API_KEY required.
"""

import json
import pytest
from unittest.mock import patch

from reasoner.api import run_stream, RunRequest
from reasoner.models import PipelineState, ConversationState


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
    """
    req = RunRequest(problem="test initial run", preset="multi-perspective-budget")

    with patch("reasoner.llm.ProviderRouter.from_model_ids", side_effect=_capture_router_call):
        with patch("reasoner.pipeline.ReasonerPipeline._phase_synthesis", return_value=None):
            events = []
            async for line in run_stream(req, initial_state=None):
                if line.startswith("data:"):
                    events.append(json.loads(line.removeprefix("data: ").strip()))

    routing = _capture_router_call.last_routing
    # synthesis should remain the preset default (qwen3-max for budget)
    assert routing.get("synthesis") == "qwen3-max"
    assert routing.get("classification") == "gpt-4o-mini"
    assert routing.get("decomposition") == "deepseek-v3"
