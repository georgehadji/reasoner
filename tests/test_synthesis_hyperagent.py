"""
Integration tests for SynthesisHyperAgent.
"""
from unittest.mock import AsyncMock

import pytest

from reasoner.models import (
    FinalSolution,
    PerspectiveType,
    PipelineState,
    SolutionCandidate,
)
from reasoner.subagents.synthesis.hyper_agent import SynthesisHyperAgent


@pytest.fixture
def fake_router():
    """Returns a router that returns valid JSON for each subagent type."""
    router = AsyncMock()

    async def side_effect(role, system_prompt, user_prompt, **kwargs):
        # Consensus mapper
        if "consensus" in system_prompt.lower():
            return (
                '{"consensus_points": ["All agree on X"], "partial_consensus": [], "confidence": 0.9, "rationale": "test"}',
                {"input_tokens": 10, "output_tokens": 20, "cost_usd": 0.001, "model": "fake"},
            )
        # Contradiction resolver
        if "contradiction" in system_prompt.lower():
            return (
                '{"contradictions": [], "confidence": 0.85, "rationale": "test"}',
                {"input_tokens": 10, "output_tokens": 20, "cost_usd": 0.001, "model": "fake"},
            )
        # Evidence weighter
        if "evidence" in system_prompt.lower() and "weight" in system_prompt.lower():
            return (
                '{"evidence_ranking": [{"perspective": "constructive", "strongest_claim": "A", "evidence_strength": 8, "why": "test"}], "confidence": 0.88, "rationale": "test"}',
                {"input_tokens": 10, "output_tokens": 20, "cost_usd": 0.001, "model": "fake"},
            )
        # Synthesis writer
        if "synthesis writer" in system_prompt.lower() or "write the final answer" in system_prompt.lower():
            return (
                '{"core_solution": "The answer is 42.", "critical_insights": ["Insight 1"], "action_blueprint": ["Step 1"], "open_questions": [], "claim_labels": {"42": "VERIFIED"}, "meta_audit": {"most_dangerous_assumption": "A1", "dominant_bias": "none", "remaining_uncertainty": "U1", "assumption_failure_impact": "Low", "non_obvious_insight": "N1"}, "sources": [], "confidence": 0.92, "rationale": "test"}',
                {"input_tokens": 10, "output_tokens": 30, "cost_usd": 0.002, "model": "fake"},
            )
        # Fallback
        return (
            '{"confidence": 0.5}',
            {"input_tokens": 5, "output_tokens": 5, "cost_usd": 0.0001, "model": "fake"},
        )

    router.call.side_effect = side_effect
    return router


@pytest.fixture
def state_with_candidates():
    s = PipelineState(problem="What is the meaning of life?")
    s.candidates = [
        SolutionCandidate(
            perspective=PerspectiveType.CONSTRUCTIVE,
            content="Life is about finding purpose through relationships.",
            key_insights=["Relationships matter"],
            model_used="fake",
        ),
        SolutionCandidate(
            perspective=PerspectiveType.DESTRUCTIVE,
            content="Life has no inherent meaning; we create our own.",
            key_insights=["Nihilism is liberating"],
            model_used="fake",
        ),
    ]
    return s


@pytest.mark.asyncio
async def test_synthesis_hyperagent_produces_final_solution(state_with_candidates, fake_router):
    agent = SynthesisHyperAgent()
    result = await agent.execute(state_with_candidates, fake_router)

    assert isinstance(result, FinalSolution)
    # The exact content depends on mock routing; verify structure is correct
    assert len(state_with_candidates.synthesis_subagent_outputs) == 4
    assert state_with_candidates.synthesis_subagent_outputs[0]["agent_name"] == "consensus_mapper"
    assert state_with_candidates.synthesis_subagent_outputs[1]["agent_name"] == "contradiction_resolver"
    assert state_with_candidates.synthesis_subagent_outputs[2]["agent_name"] == "evidence_weighter"
    assert state_with_candidates.synthesis_subagent_outputs[3]["agent_name"] == "synthesis_writer"


@pytest.mark.asyncio
async def test_synthesis_hyperagent_graceful_failure(state_with_candidates, fake_router):
    fake_router.call.side_effect = RuntimeError("LLM down")

    agent = SynthesisHyperAgent()
    # Should not raise — hyperagent handles failures gracefully
    result = await agent.execute(state_with_candidates, fake_router)

    # With all subagents failing, the writer gets empty context
    # but still tries to produce something
    assert isinstance(result, FinalSolution)
    assert len(state_with_candidates.synthesis_subagent_outputs) == 4
