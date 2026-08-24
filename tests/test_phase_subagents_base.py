"""
Unit tests for PhaseSubAgent base class.
"""
from unittest.mock import AsyncMock

import pytest

from reasoner.models import PipelineState
from reasoner.subagents.base import PhaseSubAgent
from reasoner.subagents.models import PhaseSubAgentOutput


class MockSubAgent(PhaseSubAgent):
    """Concrete sub-agent for testing."""
    AGENT_NAME = "mock"
    ROLE = "synthesis"
    MAX_TOKENS = 256

    def _build_prompt(self, state):
        return ("system", f"user: {state.problem}")

    def _parse_result(self, raw):
        import json
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        return {
            "answer": data.get("answer", raw),
            "confidence": data.get("confidence", 0.5),
            "rationale": data.get("rationale", "mock rationale"),
        }


@pytest.fixture
def fresh_state():
    return PipelineState(problem="test problem")


@pytest.fixture
def fake_router():
    router = AsyncMock()
    router.call.return_value = (
        '{"answer": "ok", "confidence": 0.95, "rationale": "test"}',
        {"input_tokens": 10, "output_tokens": 20, "cost_usd": 0.001, "model": "fake-model"},
    )
    return router


@pytest.mark.asyncio
async def test_execute_returns_output(fresh_state, fake_router):
    agent = MockSubAgent()
    out = await agent.execute(fresh_state, fake_router)

    assert isinstance(out, PhaseSubAgentOutput)
    assert out.agent_name == "mock"
    assert out.confidence == 0.95
    assert out.reasoning == "test"
    assert out.tokens_in == 10
    assert out.tokens_out == 20
    assert out.model == "fake-model"
    assert out.error is None


@pytest.mark.asyncio
async def test_execute_tracks_costs(fresh_state, fake_router):
    agent = MockSubAgent()
    await agent.execute(fresh_state, fake_router)

    assert fresh_state.total_cost_usd == 0.001
    assert fresh_state.phase_costs.get("synthesis") == 0.001
    assert fresh_state.detailed_token_usage["synthesis"]["input"] == 10
    assert fresh_state.detailed_token_usage["synthesis"]["output"] == 20
    assert fresh_state.phase_models["synthesis"] == "fake-model"


@pytest.mark.asyncio
async def test_caching(fresh_state, fake_router):
    agent = MockSubAgent()

    # First call → cache miss
    out1 = await agent.execute(fresh_state, fake_router)
    assert fake_router.call.call_count == 1

    # Second call with same state → cache hit
    out2 = await agent.execute(fresh_state, fake_router)
    assert fake_router.call.call_count == 1  # no extra LLM call
    assert out1.result == out2.result


@pytest.mark.asyncio
async def test_graceful_failure(fresh_state, fake_router):
    fake_router.call.side_effect = RuntimeError("LLM exploded")

    agent = MockSubAgent()
    out = await agent.execute(fresh_state, fake_router)

    assert out.error == "LLM exploded"
    assert out.confidence == 0.0
    assert out.result == {}


@pytest.mark.asyncio
async def test_low_confidence_not_cached(fresh_state, fake_router):
    fake_router.call.return_value = (
        '{"answer": "maybe", "confidence": 0.1}',
        {"input_tokens": 5, "output_tokens": 5, "cost_usd": 0.0001, "model": "fake"},
    )

    agent = MockSubAgent()
    await agent.execute(fresh_state, fake_router)

    # Second call should trigger LLM again because low confidence wasn't cached
    await agent.execute(fresh_state, fake_router)
    assert fake_router.call.call_count == 2


def test_cache_key_changes_with_problem():
    agent = MockSubAgent()
    s1 = PipelineState(problem="A")
    s2 = PipelineState(problem="B")

    assert agent._cache_key(s1) != agent._cache_key(s2)
