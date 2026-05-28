"""Brainstorming reasoning workflow strategy."""

from __future__ import annotations

from typing import Any, List
from reasoner.models import PipelineState
from reasoner.application.flows.base import WorkflowStrategy, WorkflowServices, PhaseStep
from reasoner.application.flows.brainstorming_phases import (
    run_brainstorm_generate_phase,
    run_brainstorm_cluster_phase,
    run_brainstorm_develop_phase,
    run_brainstorm_synthesis_phase
)
from reasoner.api.serializers import _ser_2, _ser_3, _ser_4, _ser_synthesis

class BrainstormingFlow(WorkflowStrategy):
    """
    Brainstorming workflow:
    1. VS Idea Generation
    2. Cluster & Score
    3. Deep Development
    4. Synthesis
    """
    
    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(2, "VS Idea Generation", run_brainstorm_generate_phase, _ser_2),
            PhaseStep(3, "Cluster & Score", run_brainstorm_cluster_phase, _ser_3, critical=True),
            PhaseStep(4, "Deep Development", run_brainstorm_develop_phase, _ser_4),
            PhaseStep(5, "Synthesis", run_brainstorm_synthesis_phase, _ser_synthesis),
        ]

    async def execute(
        self, 
        state: PipelineState, 
        services: WorkflowServices,
        config: Any = None
    ) -> PipelineState:
        for step in self.get_phases(state):
            success = await services.run_phase(step, state)
            if not success and step.critical:
                break
            
        return state
