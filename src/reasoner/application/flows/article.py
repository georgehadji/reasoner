"""Article reasoning workflow strategy."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reasoner.domain.article_domain import Context

from reasoner.application.flows.article_phases import (
    run_article_adversarial_verify_phase,
    run_article_developmental_edit_phase,
    run_article_draft_phase,
    run_article_final_audit_phase,
    run_article_outline_phase,
    run_article_retrieve_sources_phase,
    run_article_structural_review_phase,
    run_article_style_copy_edit_phase,
)
from reasoner.application.flows.augmentation import (
    run_augmentation,
)
from reasoner.application.flows.base import PhaseStep, WorkflowServices, WorkflowStrategy
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.application.services.serializers import _ser_2, _ser_3, _ser_4, _ser_5
from reasoner.domain.pipeline_state import PipelineState

logger = logging.getLogger(__name__)

# Feature flag: set ARTICLE_USE_ADAPTERS=1 to use the 11-phase adapter pipeline
# with Gap Retrieval, Surface Signals, and budget guards.
_USE_ADAPTERS = os.environ.get("ARTICLE_USE_ADAPTERS", "0") == "1"


async def _adapter_bridge(adapter_fn, state: PipelineState, services: WorkflowServices, **kwargs):
    """Bridge from adapter (Context, Deps) -> Result back to PhaseStep.fn (state, services) -> None."""
    from reasoner.application.flows.article_adapters import (
        AdapterDeps,
    )
    from reasoner.domain.article_domain import Context

    # Build Context from current PipelineState
    ctx = Context(
        problem=state.problem,
        content_class=state.meta.preset_name or "article",
        language=state.language,
        preset_name=state.meta.preset_name or "",
    )
    # Populate from writing_state
    ws = state.writing_state.copy() if hasattr(state, "writing_state") else {}
    if ws:
        try:
            ctx = context_to_writing_state_reverse(ctx, ws)
        except Exception:
            pass

    deps = AdapterDeps(services=services)
    try:
        result = await adapter_fn(ctx, deps)
    except Exception as exc:
        logger.warning("Adapter '%s' crashed: %s", getattr(adapter_fn, "__name__", "?"), exc, exc_info=True)
        return

    from reasoner.domain.article_domain import Err, Ok
    if isinstance(result, Ok):
        new_ctx = result.value
        # Write back to state
        if new_ctx.doc is not None:
            state.writing_state["final_article"] = new_ctx.doc.markdown
            state.writing_state["suggested_title"] = new_ctx.doc.title
        if new_ctx.sources:
            state.writing_state["retrieved_sources"] = list(new_ctx.sources)
        if new_ctx.ledger:
            state.writing_state["claim_ledger"] = [
                {"claim": c.text, "source": c.sources[0] if c.sources else None, "status": c.verdict.value}
                for c in new_ctx.ledger
            ]
        if new_ctx.verification is not None:
            state.writing_state["verification"] = new_ctx.verification
        if new_ctx.editorial_audit is not None:
            state.writing_state["editorial_audit"] = new_ctx.editorial_audit
        if new_ctx.structural_critique is not None:
            state.writing_state["structural_critique"] = new_ctx.structural_critique
        if new_ctx.errors:
            state.errors.extend(new_ctx.errors)
    elif isinstance(result, Err):
        logger.warning("Adapter '%s' returned error: %s", getattr(adapter_fn, "__name__", "?"), result.error.value)
        if result.fallback is not None and isinstance(result.fallback, Context):
            fb = result.fallback
            if fb.doc is not None:
                state.writing_state["final_article"] = fb.doc.markdown


def context_to_writing_state_reverse(ctx: Context, ws: dict) -> Context:
    """Minimal reverse conversion: populate Context fields from writing_state dict."""
    from dataclasses import replace

    from reasoner.domain.article_domain import Document

    doc = ctx.doc
    if ws.get("final_article"):
        doc = Document(
            version=(doc.version + 1) if doc else 1,
            markdown=ws["final_article"],
            title=ws.get("suggested_title", doc.title if doc else ""),
            produced_by="adapter_bridge",
        )
    sources = tuple(ws.get("retrieved_sources", [])) if ws.get("retrieved_sources") else ctx.sources
    return replace(ctx, doc=doc, sources=sources)


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

    def get_phases(self, state: PipelineState) -> list[PhaseStep]:
        if _USE_ADAPTERS:
            return self._get_phases_adapter(state)
        return self._get_phases_legacy(state)

    def _get_phases_legacy(self, state: PipelineState) -> list[PhaseStep]:
        """Original 9-phase sequence (direct phase functions, no adapters)."""
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

    def _get_phases_adapter(self, state: PipelineState) -> list[PhaseStep]:
        """11-phase adapter-based sequence with Gap Retrieval, Surface Signals, budget guards."""
        from reasoner.application.flows.article_adapters import (
            adapter_build_outline,
            adapter_developmental_edit,
            adapter_draft,
            adapter_fact_check,
            adapter_final_audit,
            adapter_gap_retrieval,
            adapter_retrieve_sources,
            adapter_structural_review,
            adapter_style_copy_edit,
            adapter_surface_signals,
            adapter_synthesis,
        )

        def bridge(adapter_fn):
            async def wrapped(state, services, **kwargs):
                await _adapter_bridge(adapter_fn, state, services, **kwargs)
            wrapped.__name__ = f"adapter_bridge_{adapter_fn.__name__}"
            return wrapped

        return [
            PhaseStep(2,   "Evidence Collection",      bridge(adapter_retrieve_sources),    _ser_2),
            PhaseStep(2.5, "Argument Map / Outline",    bridge(adapter_build_outline),      _ser_2),
            PhaseStep(3,   "First Draft",               bridge(adapter_draft),              _ser_3),
            PhaseStep(4,   "Fact Check + Ledger",       bridge(adapter_fact_check),         _ser_4),
            PhaseStep(4.5, "Gap Retrieval",             bridge(adapter_gap_retrieval),      _ser_2),
            PhaseStep(5,   "Structural Review",          bridge(adapter_structural_review),  _ser_4),
            PhaseStep(5.5, "Developmental Edit",         bridge(adapter_developmental_edit), _ser_4),
            PhaseStep(6,   "Style + Copy Edit",         bridge(adapter_style_copy_edit),    _ser_5),
            PhaseStep(7,   "Final Audit",               bridge(adapter_final_audit),        _ser_5),
            PhaseStep(7.5, "Surface Signals",           bridge(adapter_surface_signals),    _ser_5),
            PhaseStep(8,   "Synthesis",                 bridge(adapter_synthesis),          _ser_5),
        ]

    async def execute(
        self,
        state: PipelineState,
        services: WorkflowServices,
    ) -> PipelineState:
        # Augmentation and the audit-failure retry used to live here. They now
        # sit inside run_article_retrieve_sources_phase and
        # run_article_final_audit_phase (article_phases.py), because this method
        # is only ever reached by the CLI: the SSE driver at
        # api/execution/pipeline.py builds a flat list from get_phases() and
        # calls the phase functions itself, so everything held here was dead for
        # every user of the website. What is left is the same loop every other
        # flow uses.
        for step in self.get_phases(state):
            success = await services.run_phase(step, state)
            if not success and step.critical:
                break
        return state
