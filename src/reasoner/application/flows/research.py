"""Research reasoning workflow strategy."""

from __future__ import annotations

from typing import List
from reasoner.models import PipelineState
from reasoner.application.flows.base import WorkflowStrategy, WorkflowServices, PhaseStep
from reasoner.application.flows.research_phases import run_research_web_search_phase
from reasoner.application.flows.perspective_phases import run_critique_phase
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.api.serializers import _ser_2, _ser_3, _ser_5

class ResearchFlow(WorkflowStrategy):
    """
    Research workflow:
    1. Deep Iterative Web Search
    2. Critique (Vetting)
    3. Synthesis
    """
    
    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(2, "Deep Research", run_research_web_search_phase, _ser_2),
            PhaseStep(3, "Critique & Pruning", run_critique_phase, _ser_3, critical=True),
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
