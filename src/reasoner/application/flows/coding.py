"""Coding reasoning workflow strategy."""

from __future__ import annotations

from typing import Any, List
from reasoner.domain.pipeline_state import PipelineState
from reasoner.application.flows.base import WorkflowStrategy, WorkflowServices, PhaseStep
from reasoner.application.flows.coding_phases import (
    run_coding_library_search_phase,
    run_coding_cve_search_phase,
    run_coding_spec_phase,
    run_coding_generate_phase,
    run_coding_review_phase,
    run_coding_tests_phase,
    run_coding_assemble_phase
)
from reasoner.application.services.serializers import _ser_2, _ser_3, _ser_4, _ser_5

class CodingFlow(WorkflowStrategy):
    """
    Coding workflow:
    1. Spec
    2. Generate (parallel, semaphore-limited)
    3. Security Review
    4. Test Generation
    5. Final Assembly

    Synthesis is intentionally omitted: the assemble phase IS the synthesis
    for coding — adding another LLM synthesis pass would include all generated
    file content in the prompt (~100k tokens for a typical project) and overflow
    the context window of every model except those with multi-million token limits.
    The final_solution field is populated directly from the assembled files.
    """

    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(1.5, "Library Research", run_coding_library_search_phase, _ser_2),
            PhaseStep(2, "Spec Analysis", run_coding_spec_phase, _ser_2),
            PhaseStep(3, "Code Generation", run_coding_generate_phase, _ser_3),
            PhaseStep(3.4, "CVE Search", run_coding_cve_search_phase, _ser_3),
            PhaseStep(3.5, "Security Review", run_coding_review_phase, _ser_3, critical=True),
            PhaseStep(4, "Test Generation", run_coding_tests_phase, _ser_4),
            PhaseStep(5, "Final Assembly", run_coding_assemble_phase, _ser_5),
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
