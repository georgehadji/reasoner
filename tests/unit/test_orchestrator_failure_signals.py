"""Orchestrator guards and provenance that used to fail without a trace.

P5, docs/plans/root-cause-remediation-2026-09-07.md.

- ``_synthesis_model_of`` returning "" is not free. A Neuro chunk written
  without model attribution cannot be revoked by lineage, so it is dropped on
  recall rather than replayed -- losing provenance silently means losing the
  memory write silently, one recall later.
- ``_observe_propagation_shape`` is the only reading taken at the boundary
  where a synthesis becomes something future runs read back
  (docs/MIND_VIRUS_MITIGATION.md). A detector that has stopped scoring
  reported the same nothing as traffic that is clean.
"""

from __future__ import annotations

import logging

from reasoner.application import orchestrator
from reasoner.domain.pipeline_state import PipelineState


class _HostileCostState:
    """A cost_state whose model map raises when read."""

    @property
    def _phase_models_by_key(self):
        raise RuntimeError("cost state is not what we thought")


def test_lost_provenance_is_reported(caplog):
    state = PipelineState(problem="x")
    state.cost_state = _HostileCostState()

    with caplog.at_level(logging.WARNING):
        model = orchestrator._synthesis_model_of(state)

    assert model == "", "provenance must never be load-bearing on the run"
    assert any(
        "orchestrator.synthesis_provenance" in r.message for r in caplog.records
    ), f"the memory write lost its lineage silently: {[r.message for r in caplog.records]}"
    assert any("orchestrator.synthesis_provenance" in d for d in state.degradations), (
        f"the run's own output does not mention it: {state.degradations}"
    )


def test_a_readable_cost_state_reports_nothing(caplog):
    state = PipelineState(problem="x")
    state.cost_state._phase_models_by_key = {"synthesis": ["anthropic/claude-sonnet-5"]}

    with caplog.at_level(logging.WARNING):
        model = orchestrator._synthesis_model_of(state)

    assert model == "anthropic/claude-sonnet-5"
    assert state.degradations == []


def test_a_broken_propagation_detector_is_reported(monkeypatch, caplog):
    import reasoner.core.propagation_signals as signals

    def _boom(_text):
        raise ValueError("scorer regex no longer compiles")

    monkeypatch.setattr(signals, "score_propagation_shape", _boom)

    with caplog.at_level(logging.WARNING):
        orchestrator._observe_propagation_shape("some synthesis", "run-1")

    assert any(
        "orchestrator.propagation_signal" in r.message for r in caplog.records
    ), (
        f"the propagation detector stopped scoring silently: "
        f"{[r.message for r in caplog.records]}"
    )
