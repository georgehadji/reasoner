"""Tests for the DelphiMixin phase methods."""

import json
import pytest
from unittest.mock import AsyncMock

from reasoner.pipeline import ReasonerPipeline
from reasoner.models import PipelineState


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
    return ReasonerPipeline(router=FakeRouter(), preset_name="delphi-budget")


@pytest.fixture
def state():
    return PipelineState(problem="Test delphi problem")


@pytest.mark.asyncio
async def test_delphi_round1_populates_estimates(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"estimate_value": 42, "reasoning": "R1"}),
        {}
    ))
    await pipeline._phase_delphi_round1(state)
    assert "round_1_estimates" in state.delphi_state
    assert len(state.delphi_state["round_1_estimates"]) > 0


@pytest.mark.asyncio
async def test_delphi_aggregation_populates_stats(pipeline, state):
    state.delphi_state["round_1_estimates"] = [
        {"expert_id": "e1", "estimate_value": 40},
        {"expert_id": "e2", "estimate_value": 44},
    ]
    await pipeline._phase_delphi_aggregation(state)
    assert "aggregated_stats" in state.delphi_state
    assert state.delphi_state["aggregated_stats"]["median"] == 42.0


@pytest.mark.asyncio
async def test_delphi_round2_refines(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"revised_estimate": 41, "changes": ["c1"]}),
        {}
    ))
    state.delphi_state["round_1_estimates"] = [{"expert_id": "e1"}]
    await pipeline._phase_delphi_round2(state)
    assert "round_2_estimates" in state.delphi_state


@pytest.mark.asyncio
async def test_delphi_convergence_sets_final(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"converged": True, "final_answer": "Answer", "dissenters": []}),
        {}
    ))
    await pipeline._phase_delphi_convergence(state)
    assert state.delphi_state["converged"] is True
    assert state.delphi_state["consensus"]["final_answer"] == "Answer"


@pytest.mark.asyncio
async def test_delphi_dissent_records_analysis(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"dissent_analysis": "Minor wording differences."}),
        {}
    ))
    await pipeline._phase_delphi_dissent(state)
    assert "dissent" in state.delphi_state
