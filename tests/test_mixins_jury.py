"""Tests for the JuryMixin phase methods."""

import json
import pytest
from unittest.mock import AsyncMock

from reasoner.pipeline import ReasonerPipeline
from reasoner.models import PipelineState, GenerationCandidate, CriticScore, CritiqueScore, PerspectiveType


class FakeRouter:
    def __init__(self):
        self._primary = self
        self.model = "fake"

    def get(self, role: str):
        return self

    async def call(self, role: str, system_prompt: str, user_prompt: str, **kwargs):
        return "{}", {"model": "fake", "input_tokens": 10, "output_tokens": 10}

    def describe(self):
        return {"[primary]": "fake"}


@pytest.fixture
def pipeline():
    return ReasonerPipeline(router=FakeRouter(), preset_name="jury-budget")


@pytest.fixture
def state():
    return PipelineState(problem="Test jury problem")


@pytest.mark.asyncio
async def test_jury_generate_populates_candidates(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({
            "generator_id": "g1",
            "solution": "Sol",
            "confidence": 0.8,
            "key_claims": [],
            "approach_summary": "Summary",
        }),
        {}
    ))
    await pipeline._phase_jury_generate(state)
    assert len(state.generation_candidates) > 0


@pytest.mark.asyncio
async def test_jury_critique_populates_scores(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({
            "critic_id": "c1",
            "critic_model": "fake",
            "candidate_scores": {"g1": {"factuality": 8, "reasoning": 8, "completeness": 8, "novelty": 8}},
            "ranking": ["g1"],
            "dissenting_note": "",
        }),
        {}
    ))
    state.generation_candidates = [GenerationCandidate(
        generator_id="g1", model_used="fake", solution="S", confidence=0.8,
        key_claims=[], approach_summary="A"
    )]
    await pipeline._phase_jury_critique(state)
    assert len(state.critic_scores) > 0


@pytest.mark.asyncio
async def test_jury_verify_populates_results(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(side_effect=[
        (json.dumps({"verifications": [{"claim": "C1", "verdict": "SUPPORTED", "confidence": 0.9}]}), {}),
        (json.dumps({"critic_reliability": {}, "bias_analysis": {}, "agreement_rate": 0.8}), {}),
    ])
    await pipeline._phase_jury_verify_and_meta_eval(state)
    assert len(state.verification_results) == 1
    assert state.verification_results[0].claim == "C1"
    assert state.meta_evaluation is not None


@pytest.mark.asyncio
async def test_jury_ranking_populates_ranking(pipeline, state):
    state.scores = [CritiqueScore(
        perspective=PerspectiveType.CONSTRUCTIVE,
        logical_consistency=8,
        evidence_support=7,
        failure_resilience=7,
        feasibility=7,
        bias_flags=[],
        steel_man="",
    )]
    state.candidates = [type("C", (), {"perspective": PerspectiveType.CONSTRUCTIVE})()]
    state.meta_evaluation = type("ME", (), {"critic_reliability": {}})()
    await pipeline._phase_jury_weighted_ranking(state)
    assert isinstance(state.jury_weighted_ranking, list)
