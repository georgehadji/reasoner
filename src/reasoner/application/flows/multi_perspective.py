"""Multi-perspective reasoning workflow strategy."""

from __future__ import annotations

from typing import List
from reasoner.models import PipelineState
from reasoner.application.flows.base import WorkflowStrategy, WorkflowServices, PhaseStep
from reasoner.application.flows.perspective_phases import (
    run_perspectives_phase,
    run_critique_phase,
    run_stress_test_phase
)
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.api.serializers import _ser_2, _ser_3, _ser_4, _ser_5

class MultiPerspectiveFlow(WorkflowStrategy):
    """
    Standard multi-perspective workflow:
    1. Perspectives generation
    2. Critique & Scoring
    3. Stress Testing (optional based on complexity)
    4. Synthesis
    """
    
    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        phases = [
            PhaseStep(2, "Perspectives", run_perspectives_phase, _ser_2),
            PhaseStep(3, "Critique & Pruning", run_critique_phase, _ser_3, critical=True),
        ]
        
        if state.complexity != "simple":
            phases.append(PhaseStep(4, "Stress Testing", run_stress_test_phase, _ser_4))
            
        phases.append(PhaseStep(5, "Synthesis", run_synthesis_phase, _ser_5))
        return phases

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
