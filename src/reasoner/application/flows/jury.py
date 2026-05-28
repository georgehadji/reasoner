"""Jury reasoning workflow strategy."""

from __future__ import annotations

from typing import List
from reasoner.models import PipelineState
from reasoner.application.flows.base import WorkflowStrategy, WorkflowServices, PhaseStep
from reasoner.application.flows.jury_phases import (
    run_jury_generate_phase,
    run_jury_critique_phase,
    run_jury_verify_and_meta_eval_phase,
    run_jury_weighted_ranking_phase
)
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.api.serializers import _ser_2, _ser_3, _ser_4, _ser_5

class JuryFlow(WorkflowStrategy):
    """Jury reasoning workflow."""

    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(2, "Generation Pool", run_jury_generate_phase, _ser_2),
            PhaseStep(3, "Critic Pool", run_jury_critique_phase, _ser_3, critical=True),
            PhaseStep(4, "Verification & Meta", run_jury_verify_and_meta_eval_phase, _ser_4),
            PhaseStep(4.5, "Weighted Ranking", run_jury_weighted_ranking_phase, _ser_4),
            PhaseStep(5, "Synthesis", run_synthesis_phase, _ser_5)
        ]

    async def execute(
        self, 
        state: PipelineState, 
        services: WorkflowServices,
    ) -> PipelineState:
        for step in self.get_phases(state):
            await services.run_phase(step, state)
        return state
