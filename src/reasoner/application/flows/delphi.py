"""Delphi method reasoning workflow strategy."""

from __future__ import annotations

from reasoner.application.flows.base import PhaseStep, WorkflowStrategy
from reasoner.application.flows.delphi_phases import (
    run_delphi_aggregation_phase,
    run_delphi_convergence_phase,
    run_delphi_dissent_phase,
    run_delphi_round1_phase,
    run_delphi_round2_phase,
)
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.application.services.serializers import _ser_2, _ser_3, _ser_4, _ser_5, _ser_synthesis
from reasoner.domain.pipeline_state import PipelineState


class DelphiFlow(WorkflowStrategy):
    """Delphi method reasoning workflow."""

    def get_phases(self, state: PipelineState) -> list[PhaseStep]:
        phases = [
            PhaseStep(2, "Round 1 Estimates", run_delphi_round1_phase, _ser_2),
            PhaseStep(3, "Aggregation", run_delphi_aggregation_phase, _ser_3),
            PhaseStep(4, "Round 2 Estimates", run_delphi_round2_phase, _ser_4),
            PhaseStep(5, "Convergence Analysis", run_delphi_convergence_phase, _ser_5),
        ]

        # We always include Dissent in the plan, the phase itself can skip if converged
        phases.append(PhaseStep(5.5, "Dissent Capture", run_delphi_dissent_phase, _ser_5))
        phases.append(PhaseStep(6, "Synthesis", run_synthesis_phase, _ser_synthesis))
        return phases
