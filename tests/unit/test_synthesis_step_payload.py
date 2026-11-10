"""Every method's Synthesis step must put the answer on its phase payload.

Seven flows (multi_perspective, debate, jury, research, iterative_critique and
the five cognitive ones) once serialized their Synthesis step with ``_ser_5``,
which dispatches *method-specific* Phase 5 state and never reads
``state.final_solution``. Their Synthesis payload reached the browser and
``POST /api/agent/run/sync`` with no ``core_solution`` at all — and for CoVE and
ToT it repeated the earlier Final Revision / Backtrack payload instead.
"""

from __future__ import annotations

import pytest

from reasoner.application.flows.factory import WorkflowFactory
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.application.services.serializers import _ser_synthesis
from reasoner.domain.core_types import FinalSolution
from reasoner.domain.pipeline_state import PipelineState

# The article flow's last step publishes the article itself (writing_state),
# which its UI renders as a document; it is not a synthesis card.
_NOT_SYNTHESIS_ANSWER = {"article"}

_METHODS = sorted(set(WorkflowFactory()._strategies) - _NOT_SYNTHESIS_ANSWER)


def _finished_state() -> PipelineState:
    """State as it stands when a Synthesis step finishes, earlier phases included."""
    state = PipelineState(problem="How should we launch?", complexity="complex")
    state.final_solution = FinalSolution(
        core_solution="Ship the small version first.",
        critical_insights=["Scope is the risk"],
        action_blueprint=[{"step": "Week 1", "action": "Cut scope"}],
        open_questions=["Who owns QA?"],
        claim_labels={},
        meta_audit=None,
    )
    # What the method's own Phase 5 left behind; _ser_5 returned these first.
    state.cove_state = {"revised_answer": "Earlier revision."}
    state.tot_state = {"backtrack_decision": "Keep branch B."}
    return state


def _synthesis_steps(method: str, state: PipelineState) -> list:
    steps = WorkflowFactory().get_strategy(method).get_phases(state)
    return [s for s in steps if s.name == "Synthesis" or s.fn is run_synthesis_phase]


@pytest.mark.parametrize("method", _METHODS)
def test_synthesis_step_sends_the_answer(method: str) -> None:
    state = _finished_state()
    steps = _synthesis_steps(method, state)
    if not steps:
        pytest.skip(f"{method} has no Synthesis step (its last phase is the deliverable)")
    for step in steps:
        payload = step.serializer(state)
        assert payload.get("core_solution") == "Ship the small version first.", (
            f"{method}: Synthesis step serialized with {step.serializer.__name__} "
            f"sent {sorted(payload)}"
        )
        assert payload["action_blueprint"][0]["action"] == "Cut scope"


def test_synthesis_payload_sends_its_vetted_sources() -> None:
    """synthesis_phase filters sources to retrieved URLs; the UI's panel reads them."""
    state = _finished_state()
    source = {"title": "WHO", "url": "https://who.int"}
    state.final_solution.sources = [source]
    assert _ser_synthesis(state)["sources"] == [source]


def test_synthesis_payload_keeps_research_citations() -> None:
    """Research's citations rode the old Synthesis payload; they must not be lost."""
    state = _finished_state()
    citation = {"title": "WHO", "url": "https://who.int"}
    state.method_state = {"prism": {"citations": [citation]}}
    assert _ser_synthesis(state)["citations"] == [citation]


def test_method_state_without_prism_is_not_a_crash() -> None:
    """Every Synthesis step now reads citations; most methods never write "prism"."""
    state = _finished_state()
    state.method_state = {"debate": {"rounds": 2}}
    assert "citations" not in _ser_synthesis(state)


def test_failed_synthesis_still_sends_citations() -> None:
    """No final_solution (synthesis failed): keep what _ser_5 used to fall back to."""
    state = PipelineState(problem="q")
    citation = {"title": "WHO", "url": "https://who.int"}
    state.method_state = {"prism": {"citations": [citation]}}
    assert _ser_synthesis(state) == {"citations": [citation]}
