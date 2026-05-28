"""Coding reasoning workflow strategy."""

from __future__ import annotations

from typing import Any, List
from reasoner.models import PipelineState
from reasoner.application.flows.base import WorkflowStrategy, WorkflowServices, PhaseStep
from reasoner.application.flows.coding_phases import (
    run_coding_spec_phase,
    run_coding_generate_phase,
    run_coding_review_phase,
    run_coding_tests_phase,
    run_coding_assemble_phase
)
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.api.serializers import _ser_2, _ser_3, _ser_4, _ser_5, _ser_synthesis

class CodingFlow(WorkflowStrategy):
    """
    Coding workflow:
    1. Spec
    2. Generate
    3. Review
    4. Tests
    5. Assemble
    6. Synthesis
    """
    
    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(2, "Spec Analysis", run_coding_spec_phase, _ser_2),
            PhaseStep(3, "Code Generation", run_coding_generate_phase, _ser_3),
            PhaseStep(3.5, "Security Review", run_coding_review_phase, _ser_3, critical=True),
            PhaseStep(4, "Test Generation", run_coding_tests_phase, _ser_4),
            PhaseStep(5, "Final Assembly", run_coding_assemble_phase, _ser_5),
            PhaseStep(6, "Synthesis", run_synthesis_phase, _ser_synthesis),
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
