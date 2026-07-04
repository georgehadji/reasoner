"""Article reasoning workflow strategy."""

from __future__ import annotations

from typing import List
from reasoner.domain.pipeline_state import PipelineState
from reasoner.application.flows.base import WorkflowStrategy, WorkflowServices, PhaseStep
from reasoner.application.flows.article_phases import (
    run_article_retrieve_sources_phase,
    run_article_outline_phase,
    run_article_draft_phase,
    run_article_adversarial_verify_phase,
    run_article_structural_review_phase,
    run_article_developmental_edit_phase,
    run_article_style_copy_edit_phase,
    run_article_final_audit_phase,
)
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.application.services.serializers import _ser_2, _ser_3, _ser_4, _ser_5

class ArticleFlow(WorkflowStrategy):
    """
    Publication-grade editorial pipeline:
    1.  Evidence Collection
    2.  Argument Map / Outline (NEW)
    3.  First Draft
    4.  Fact Check + Claim Ledger
    5.  Structural Adversarial Review (NEW)
    6.  Developmental Edit (NEW)
    7.  Style + Copy Edit (NEW)
    8.  Final Editorial Audit (NEW)
    9.  Synthesis
    """
    
    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(2,   "Evidence Collection",     run_article_retrieve_sources_phase,    _ser_2),
            PhaseStep(2.5, "Argument Map / Outline",   run_article_outline_phase,             _ser_2),
            PhaseStep(3,   "First Draft",              run_article_draft_phase,               _ser_3),
            PhaseStep(4,   "Fact Check + Ledger",      run_article_adversarial_verify_phase,  _ser_4),
            PhaseStep(4.5, "Structural Review",         run_article_structural_review_phase,   _ser_4),
            PhaseStep(5,   "Developmental Edit",        run_article_developmental_edit_phase,  _ser_4),
            PhaseStep(6,   "Style + Copy Edit",        run_article_style_copy_edit_phase,     _ser_5),
            PhaseStep(7,   "Final Audit",              run_article_final_audit_phase,         _ser_5),
            PhaseStep(8,   "Synthesis",                run_synthesis_phase,                   _ser_5),
        ]

    async def execute(
        self, 
        state: PipelineState, 
        services: WorkflowServices,
    ) -> PipelineState:
        phases = self.get_phases(state)
        audit_retried = False
        
        for step in phases:
            await services.run_phase(step, state)
            
            # E2: If final audit fails, retry developmental edit + re-audit once
            if not audit_retried and "Final Audit" in str(step.label):
                audit = state.writing_state.get("editorial_audit", {})
                # Default to False if audit data is empty (parse failure = failed audit)
                if not audit.get("passes_audit", False):
                    services.log("WRITING", "Audit failed — retrying developmental edit and re-audit...", state)
                    audit_retried = True
                    # Re-run developmental edit
                    await services.run_phase(
                        PhaseStep(5, "Developmental Edit (retry)", run_article_developmental_edit_phase, _ser_4),
                        state,
                    )
                    # Re-run style + copy edit
                    await services.run_phase(
                        PhaseStep(6, "Style + Copy Edit (retry)", run_article_style_copy_edit_phase, _ser_5),
                        state,
                    )
                    # Re-run audit
                    await services.run_phase(
                        PhaseStep(7, "Final Audit (retry)", run_article_final_audit_phase, _ser_5),
                        state,
                    )
        return state
