"""
Tests for tier-based agent model override in follow-up runs.
Uses fakes — no OPENROUTER_API_KEY required.
"""

import json
import pytest
from unittest.mock import patch

from reasoner.api import run_stream, RunRequest
from reasoner.api.streaming import run_followup_stream
from reasoner.api.schemas import FollowupRequest
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
    # Follow-ups run through run_followup_stream, which is where agent_model is
    # resolved and pushed into the routing table.
    req = FollowupRequest(
        question="test followup budget",
        preset="multi-perspective-budget",
        conversation_id="conv-1",
        history=[],
        previous_synthesis="earlier answer",
        agent_model="kimi-k2-5",
    )

    with patch("reasoner.llm.ProviderRouter.from_model_ids", side_effect=_capture_router_call):
        with patch("reasoner.pipeline.ReasonerPipeline._phase_synthesis", return_value=None):
            events = []
            async for line in run_followup_stream(req):
                if line.startswith("data:"):
                    events.append(json.loads(line.removeprefix("data: ").strip()))

    routing = _capture_router_call.last_routing
    assert routing.get("synthesis") == "kimi-k2-5"
    # classification+decomposition are one "fusion" phase now
    assert routing.get("fusion") == "kimi-k2-5"
    # Other roles should remain as defined by the preset
    assert "constructive" in routing
    assert "destructive" in routing


@pytest.mark.asyncio
async def test_followup_premium_uses_grok_for_persona_roles():
    """
    When initial_state.agent_model is 'grok-4.20', the router should use it
    for synthesis, classification, and decomposition.
    """
    req = FollowupRequest(
        question="test followup premium",
        preset="multi-perspective-premium",
        conversation_id="conv-2",
        history=[],
        previous_synthesis="earlier answer",
        agent_model="grok-4.20",
    )

    with patch("reasoner.llm.ProviderRouter.from_model_ids", side_effect=_capture_router_call):
        with patch("reasoner.pipeline.ReasonerPipeline._phase_synthesis", return_value=None):
            events = []
            async for line in run_followup_stream(req):
                if line.startswith("data:"):
                    events.append(json.loads(line.removeprefix("data: ").strip()))

    routing = _capture_router_call.last_routing
    assert routing.get("synthesis") == "grok-4.20"
    assert routing.get("fusion") == "grok-4.20"


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
    # Roles must remain exactly what the preset declares.
    from reasoner.presets import get_preset

    preset = get_preset("multi-perspective-budget")
    assert routing.get("synthesis") == preset.routing["synthesis"]
    assert routing.get("fusion") == preset.routing["fusion"]


@pytest.mark.asyncio
async def test_followup_initial_state_reaches_pipeline():
    """Follow-up context must survive run_stream's command construction.

    Regression: run_stream accepted initial_state but never forwarded it to the
    command handler, and the handler never forwarded it to execute_run. Follow-ups
    therefore ran as brand-new questions — no conversation history, no previous
    synthesis, and no agent_model override.
    """
    from reasoner.application.orchestrator import PipelineOrchestrator

    seen = {}
    original = PipelineOrchestrator.preflight

    async def spy(self, req, initial_state=None, *args, **kwargs):
        seen["history"] = getattr(initial_state, "conversation_history", None)
        seen["previous_synthesis"] = getattr(initial_state, "previous_synthesis", None)
        seen["agent_model"] = getattr(initial_state, "agent_model", None)
        return await original(self, req, initial_state, *args, **kwargs)

    req = FollowupRequest(
        question="and then?",
        preset="multi-perspective-budget",
        conversation_id="conv-regression",
        history=[
            {"role": "user", "content": "first question"},
            {"role": "assistant", "content": "first answer"},
        ],
        previous_synthesis="PRIOR SYNTHESIS",
        agent_model="kimi-k2-5",
    )

    with patch.object(PipelineOrchestrator, "preflight", spy):
        async for _ in run_followup_stream(req):
            pass

    assert seen["history"] == [
        {"role": "user", "content": "first question"},
        {"role": "assistant", "content": "first answer"},
    ]
    assert seen["previous_synthesis"] == "PRIOR SYNTHESIS"
    assert seen["agent_model"] == "kimi-k2-5"
