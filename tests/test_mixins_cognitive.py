"""Tests for the CognitiveMixin phase methods (CoVe, SoT, ToT, PoT, Self-Discover)."""

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
    return ReasonerPipeline(router=FakeRouter(), preset_name="cove-budget")


@pytest.fixture
def state():
    return PipelineState(problem="Test cognitive problem")


# ── CoVe ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cove_draft_populates_state(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"draft_answer": "Draft", "claims": ["C1"]}), {}
    ))
    await pipeline._phase_cove_draft(state)
    assert state.cove_state["draft_answer"] == "Draft"


@pytest.mark.asyncio
async def test_cove_verify_populates_questions(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"verification_questions": ["Q1"]}), {}
    ))
    await pipeline._phase_cove_verify(state)
    assert state.cove_state["verification_questions"] == ["Q1"]


@pytest.mark.asyncio
async def test_cove_answer_populates_answers(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"answers": ["A1"]}), {}
    ))
    await pipeline._phase_cove_answer(state)
    assert state.cove_state["verification_answers"] == ["A1"]


@pytest.mark.asyncio
async def test_cove_revise_populates_revised(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"revised_answer": "Revised", "changes_made": ["M1"]}), {}
    ))
    await pipeline._phase_cove_revise(state)
    assert state.cove_state["revised_answer"] == "Revised"


# ── SoT ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sot_skeleton_populates_sub_problems(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"sub_problems": [{"id": "sp1", "description": "Sub"}]}), {}
    ))
    await pipeline._phase_sot_skeleton(state)
    assert len(state.sot_state["sub_problems"]) == 1


@pytest.mark.asyncio
async def test_sot_assemble_populates_answer(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"assembled_answer": "Assembled", "transitions": []}), {}
    ))
    state.sot_state["sub_problems"] = [{"id": "sp1"}]
    state.sot_state["solutions"] = [{"sub_problem_id": "sp1", "solution": "Sol"}]
    await pipeline._phase_sot_assemble(state)
    assert state.sot_state["assembled_answer"] == "Assembled"


# ── ToT ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tot_decompose_populates_decision_points(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"decision_points": [{"id": "dp1"}]}), {}
    ))
    await pipeline._phase_tot_decompose(state)
    assert len(state.tot_state["decision_points"]) == 1


@pytest.mark.asyncio
async def test_tot_backtrack_sets_decision(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"decision": "terminate", "final_path": []}), {}
    ))
    await pipeline._phase_tot_backtrack(state)
    assert state.tot_state["backtrack_decision"] == "terminate"


# ── PoT ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pot_generate_populates_code(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"code": "print(42)", "explanation": "Exp"}), {}
    ))
    await pipeline._phase_pot_generate(state)
    assert state.pot_state["code"] == "print(42)"


@pytest.mark.asyncio
async def test_pot_execute_populates_output(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"output": "42", "success": True}), {}
    ))
    state.pot_state["code"] = "print(42)"
    await pipeline._phase_pot_execute(state)
    # The phase runs the code for real now, so the value is raw stdout (with its
    # trailing newline) rather than an LLM-reported string.
    assert state.pot_state["execution_output"].strip() == "42"


@pytest.mark.asyncio
async def test_pot_interpret_populates_answer(pipeline, state):
    state.pot_state["execution_success"] = True
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"interpretation": "The answer is 42", "answer": "42", "caveats": []}), {}
    ))
    await pipeline._phase_pot_interpret(state)
    assert state.pot_state["computed_answer"] == "42"


# ── Self-Discover ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sd_select_populates_modules(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"selected_modules": ["M1"], "composition_strategy": "seq"}), {}
    ))
    await pipeline._phase_sd_select(state)
    assert state.self_discover_state["selected_modules"] == ["M1"]


@pytest.mark.asyncio
async def test_sd_implement_populates_final(pipeline, state):
    pipeline._call_llm_cached = AsyncMock(return_value=(
        json.dumps({"module_outputs": [{"output": "O1"}], "final_answer": "Final"}), {}
    ))
    await pipeline._phase_sd_implement(state)
    assert state.self_discover_state["final_answer"] == "Final"
