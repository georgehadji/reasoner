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
from reasoner.application.flows.augmentation import (
    is_deep_question,
    DEFAULT_AUGMENTATION_METHODS,
    AUGMENTATION_PROMPTS,
    AUGMENTATION_ROLES,
    run_augmentation,
)
from reasoner.application.services.serializers import _ser_2, _ser_3, _ser_4, _ser_5


class ArticleFlow(WorkflowStrategy):
    """
    Publication-grade editorial pipeline:
    1.  [Augmentation] — debate/critique pre-processing for deep questions
    2.  Evidence Collection
    2.5 Argument Map / Outline
    3.  First Draft
    4.  Fact Check + Claim Ledger
    4.5 Structural Adversarial Review
    5.  Developmental Edit
    6.  Style + Copy Edit
    7.  Final Editorial Audit
    8.  Synthesis
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
        # ── Pre-processing: run augmentation if depth-detected ──
        await run_augmentation(state, services.call_llm, services.log)

        # ── Adapter-based pipeline (Phase 1) ──
        # Build initial ArticleContext from current state
        from reasoner.domain.core_types import ArticleContext, Ok, Err
        from reasoner.application.flows.article_adapters import (
            article_pipeline, _compute_surface_signals,
        )

        ws = state.writing_state

        ctx = ArticleContext(
            problem=state.problem,
            language=getattr(state, "language", "English"),
            preset_name=getattr(state, "preset_name", "article-budget"),
            content_class="blog",
            sources=tuple(ws.get("retrieved_sources") or ()),
            source_metadata=tuple(ws.get("source_metadata") or ()),
            pre_research_summary=ws.get("pre_research_summary", ""),
            gaps_noted=list(ws.get("gaps_noted") or []),
            style_brief=ws.get("style_brief"),
        )
        # Note: PipelineState stores style_brief via writing_state dict, not as an attr.
        # The ws.get() on line 87 already captures it correctly.

        # Run the adapter pipeline — with_retry handles re-running on audit failure
        result = await article_pipeline(ctx, services)

        if isinstance(result, Ok):
            ctx = result.value
            # Compute surface signals for the frontend
            from reasoner.application.flows.article_adapters import _compute_surface_signals
            signals = _compute_surface_signals(ctx)
            if signals:
                ctx = ctx.replace(surface_signals=signals)
        elif isinstance(result, Err) and result.fallback is not None:
            ctx = result.fallback
            services.log("WRITING", f"Phase degraded: {result.error}", state)

        # Sync back into PipelineState for serializers
        ctx.sync_to(state)
        return state
