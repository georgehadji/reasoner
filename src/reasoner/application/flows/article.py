"""Article reasoning workflow strategy."""

from __future__ import annotations

from typing import List
from reasoner.domain.pipeline_state import PipelineState
from reasoner.application.flows.base import WorkflowStrategy, WorkflowServices, PhaseStep
from reasoner.application.flows.article_phases import (
    run_article_retrieve_sources_phase,
    run_article_draft_phase,
    run_article_adversarial_verify_phase,
    run_article_refine_phase
)
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.application.services.serializers import _ser_2, _ser_3, _ser_4, _ser_5

class ArticleFlow(WorkflowStrategy):
    """
    Article workflow:
    1. Retrieve Sources
    2. Draft
    3. Adversarial Verify
    4. Refine
    5. Synthesis
    """
    
    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(2, "Retrieve Sources", run_article_retrieve_sources_phase, _ser_2),
            PhaseStep(3, "Draft", run_article_draft_phase, _ser_3),
            PhaseStep(4, "Adversarial Verify", run_article_adversarial_verify_phase, _ser_4),
            PhaseStep(4.5, "Refine", run_article_refine_phase, _ser_4),
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
