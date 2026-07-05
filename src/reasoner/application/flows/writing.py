"""Writing reasoning workflow strategy."""

from __future__ import annotations

from typing import Any, List
from reasoner.domain.pipeline_state import PipelineState
from reasoner.application.flows.base import WorkflowStrategy, WorkflowServices, PhaseStep
from reasoner.application.flows.augmentation import run_augmentation
from reasoner.application.flows.writing_phases import (
    run_writing_source_retrieval_phase,
    run_writing_outline_phase,
    run_writing_draft_phase,
    run_writing_factcheck_phase,
    run_writing_assemble_phase
)
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.application.services.serializers import _ser_2, _ser_3, _ser_5, _ser_synthesis

class WritingFlow(WorkflowStrategy):
    """
    Writing workflow:
    0. [Augmentation] — debate/critique pre-processing for deep questions
    1. Source Retrieval
    2. Outline
    3. Draft
    3.5 Fact-Check
    4. Final Assembly
    5. Synthesis
    """
    
    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(1.5, "Source Retrieval", run_writing_source_retrieval_phase, _ser_2),
            PhaseStep(2, "Outline", run_writing_outline_phase, _ser_2),
            PhaseStep(3, "Draft", run_writing_draft_phase, _ser_3),
            PhaseStep(3.5, "Fact-Check", run_writing_factcheck_phase, _ser_3, critical=True),
            PhaseStep(4, "Final Assembly", run_writing_assemble_phase, _ser_5),
            PhaseStep(5, "Synthesis", run_synthesis_phase, _ser_synthesis),
        ]

    async def execute(
        self, 
        state: PipelineState, 
        services: WorkflowServices,
        config: Any = None
    ) -> PipelineState:
        # ── Pre-processing: run augmentation if depth-detected ──
        await run_augmentation(state, services.call_llm, services.log)

        for step in self.get_phases(state):
            success = await services.run_phase(step, state)
            if not success and step.critical:
                break
            
        return state
