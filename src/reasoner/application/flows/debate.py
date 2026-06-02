"""Debate reasoning workflow strategy."""

from __future__ import annotations

from typing import List
from reasoner.domain.pipeline_state import PipelineState
from reasoner.application.flows.base import WorkflowStrategy, WorkflowServices, PhaseStep
from reasoner.application.flows.debate_phases import (
    run_debate_opening_phase,
    run_debate_rebuttal_phase,
    run_debate_cross_examine_phase,
    run_debate_judge_phase
)
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.application.services.serializers import _ser_2, _ser_3, _ser_4, _ser_5

class DebateFlow(WorkflowStrategy):
    """
    Debate workflow:
    1. Opening Statements
    2. Rebuttals
    3. Cross-Examination
    4. Judging
    5. Synthesis
    """
    
    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(2, "Opening Statements", run_debate_opening_phase, _ser_2),
            PhaseStep(3, "Rebuttals", run_debate_rebuttal_phase, _ser_3),
            PhaseStep(4, "Cross-Examination", run_debate_cross_examine_phase, _ser_4),
            PhaseStep(4.5, "Judging", run_debate_judge_phase, _ser_3),
            PhaseStep(5, "Synthesis", run_synthesis_phase, _ser_5),
        ]

    async def execute(
        self, 
        state: PipelineState, 
        services: WorkflowServices,
    ) -> PipelineState:
        for step in self.get_phases(state):
            success = await services.run_phase(step, state)
            if not success and step.critical:
                break
        return state
