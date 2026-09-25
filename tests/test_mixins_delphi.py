"""Tests for the DelphiMixin phase methods."""

import json
from unittest.mock import AsyncMock

import pytest

from reasoner.application.flows.delphi_phases import (
    run_delphi_aggregation_phase,
    run_delphi_convergence_phase,
    run_delphi_dissent_phase,
    run_delphi_round1_phase,
    run_delphi_round2_phase,
)
from reasoner.application.flows.services import PipelineWorkflowServices
from reasoner.models import PipelineState
from reasoner.pipeline import ReasonerPipeline


def _svc(pipeline):
    """The WorkflowServices a phase function takes, bound to this pipeline."""
    return PipelineWorkflowServices(pipeline)


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
    await run_delphi_round1_phase(state, _svc(pipeline))
    assert "round_1_estimates" in state.delphi_state
    assert len(state.delphi_state["round_1_estimates"]) > 0


@pytest.mark.asyncio
async def test_delphi_aggregation_populates_stats(pipeline, state):
    state.delphi_state["round_1_estimates"] = [
        {"expert_id": "e1", "estimate_value": 40},
        {"expert_id": "e2", "estimate_value": 44},
    ]
    await run_delphi_aggregation_phase(state, _svc(pipeline))
    assert "aggregated_stats" in state.delphi_state
    assert state.delphi_state["aggregated_stats"]["median"] == 42.0


@pytest.mark.asyncio
async def test_delphi_round2_refines(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"revised_estimate": 41, "changes": ["c1"]}),
        {}
    ))
    state.delphi_state["round_1_estimates"] = [{"expert_id": "e1"}]
    await run_delphi_round2_phase(state, _svc(pipeline))
    assert "round_2_estimates" in state.delphi_state


@pytest.mark.asyncio
async def test_delphi_convergence_sets_final(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"converged": True, "final_answer": "Answer", "dissenters": []}),
        {}
    ))
    await run_delphi_convergence_phase(state, _svc(pipeline))
    assert state.delphi_state["converged"] is True
    assert state.delphi_state["consensus"]["final_answer"] == "Answer"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("returned", "converged"),
    [
        # The bug: the prompt asked for "<true|false>" in quotes, the code tested
        # truthiness, and the string "false" is truthy.
        ("false", False), ("False", False), (" false ", False),
        ("true", True), ("True", True), ("yes", True),
        (True, True), (False, False),
        # Anything unrecognised is not converged: dissent runs, costing one call.
        (None, False), ("maybe", False), (1, False),
    ],
)
async def test_delphi_convergence_reads_the_answer_as_a_real_bool(pipeline, state, returned, converged):
    pipeline._call_llm_cached = AsyncMock(return_value=(json.dumps({"converged": returned}), {}))
    await run_delphi_convergence_phase(state, _svc(pipeline))
    assert state.delphi_state["converged"] is converged
    assert state.delphi_state["consensus"]["converged"] is converged


@pytest.mark.asyncio
async def test_delphi_a_string_false_no_longer_skips_dissent(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(json.dumps({"converged": "false"}), {}))
    await run_delphi_convergence_phase(state, _svc(pipeline))

    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"dissent_analysis": "Expert 3 still disagrees."}), {}
    ))
    await run_delphi_dissent_phase(state, _svc(pipeline))
    assert pipeline._call_llm_cached.await_count == 1
    assert "dissent" in state.delphi_state


def test_delphi_convergence_prompt_asks_for_a_json_boolean(state):
    from reasoner.phases.delphi import delphi_convergence_prompt

    prompt = delphi_convergence_prompt(state)
    assert '"converged": "<' not in prompt  # no quoted placeholder
    assert "JSON boolean" in prompt


@pytest.mark.asyncio
async def test_delphi_dissent_records_analysis(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"dissent_analysis": "Minor wording differences."}),
        {}
    ))
    await run_delphi_dissent_phase(state, _svc(pipeline))
    assert "dissent" in state.delphi_state
