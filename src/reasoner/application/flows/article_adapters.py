"""
Adapter layer between the immutable Context (article_domain) and existing
mutable PipelineState-based article phases.

Each adapter function wraps one existing phase from article_phases.py:
  - Takes Context + Dependencies
  - Converts to PipelineState via context_to_writing_state
  - Runs the original phase
  - Extracts results back into a new Context
  - Returns Result[Context, PhaseError]

The existing phase code is NOT modified — this is the Strangler Fig pattern
(Phase 1 of the migration roadmap).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any, Callable

from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.article_domain import (
    Context,
    Document,
    Claim,
    Verdict,
    Budget,
    PhaseError,
    Ok,
    Err,
    Result,
)
from reasoner.application.flows.base import WorkflowServices
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

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════════════════════════
# Dependencies bundle
# ═════════════════════════════════════════════════════════════════════

@dataclass
class AdapterDeps:
    """Dependencies injected into adapter functions.

    This is the "imperative shell" — services, primitives, and stateful
    objects that adapter functions reach through.
    """
    services: WorkflowServices
    call_llm: Callable = None  # shorthand for services.call_llm

    def __post_init__(self):
        if self.call_llm is None:
            self.call_llm = self.services.call_llm


# ═════════════════════════════════════════════════════════════════════
# Context ↔ PipelineState conversion helpers
# ═════════════════════════════════════════════════════════════════════

def _build_minimal_state(ctx: Context) -> PipelineState:
    """Build a minimal PipelineState from Context fields."""
    return PipelineState(
        problem=ctx.problem,
        language=ctx.language,
        preset_name=ctx.preset_name,
        method="article",
    )


def context_to_writing_state(ctx: Context) -> dict[str, Any]:
    """Extract writing_state-format dict from an immutable Context.

    This converts the typed Context fields back into the freeform dict
    format that existing phase functions expect.
    """
    ws: dict[str, Any] = {}

    # Document → final_article
    if ctx.doc is not None:
        ws["final_article"] = ctx.doc.markdown
        ws["suggested_title"] = ctx.doc.title

    # Sources
    if ctx.sources:
        ws["retrieved_sources"] = list(ctx.sources)
        # Build source_metadata if sources have the right structure
        metadata = []
        for s in ctx.sources:
            meta = {
                "title": str(s.get("title", "")),
                "url": str(s.get("url", "")),
                "author": str(s.get("author", "")),
                "date": str(s.get("date", "")),
                "publisher": str(s.get("publisher", "")),
                "snippet": str(s.get("snippet", ""))[:500],
            }
            metadata.append(meta)
        ws["source_metadata"] = metadata

    # Outline
    if ctx.outline is not None:
        ws["outline"] = ctx.outline.get("outline", ctx.outline)

    # Claim ledger → claim_ledger compatible format
    if ctx.ledger:
        ws["claim_ledger"] = [
            {
                "claim": c.text,
                "source": c.sources[0] if c.sources else None,
                "status": c.verdict.value,
            }
            for c in ctx.ledger
        ]

    # Verification artifacts
    if ctx.verification is not None:
        ws["verification"] = ctx.verification
    if ctx.editorial_audit is not None:
        ws["editorial_audit"] = ctx.editorial_audit

    # Metrics
    if ctx.metrics is not None:
        ws["metrics"] = ctx.metrics

    # Structural critique
    if ctx.structural_critique is not None:
        ws["structural_critique"] = ctx.structural_critique

    # Audit
    if ctx.audit is not None:
        ws["audit"] = ctx.audit

    # Pre-research
    if ctx.pre_research_summary:
        ws["pre_research_summary"] = ctx.pre_research_summary
    if ctx.pre_research_insights:
        ws["pre_research_insights"] = list(ctx.pre_research_insights)

    # Style brief
    if ctx.style_brief is not None:
        ws["style_brief"] = ctx.style_brief

    # Argument map (derived from outline)
    if ctx.outline and isinstance(ctx.outline, dict):
        ws["argument_map"] = ctx.outline.get("argument_map", {})

    return ws


def writing_state_to_context(ctx: Context, ws: dict[str, Any], deps: AdapterDeps,
                              state: PipelineState | None = None) -> Context:
    """Build a new Context from the old Context + updated writing_state dict.

    This is the reverse of context_to_writing_state — it reads the freeform
    dict and maps typed fields back into the immutable Context.

    Args:
        ctx: Previous Context (source of immutable defaults).
        ws: Updated writing_state dict from the phase.
        deps: Adapter dependencies.
        state: Optional PipelineState that the phase executed against.
               If provided, errors from the state are incorporated.
    """
    # Current doc version
    doc_version = ctx.doc.version if ctx.doc is not None else 0

    # Document
    doc = ctx.doc
    final_article = ws.get("final_article", "")
    if final_article and (doc is None or doc.markdown != final_article):
        doc = Document(
            version=doc_version + 1,
            markdown=final_article,
            title=ws.get("suggested_title", doc.title if doc else ""),
            produced_by=ws.get("_current_phase", "unknown"),
            locked_spans=doc.locked_spans if doc is not None else (),
        )

    # Sources
    sources = ctx.sources
    if ws.get("retrieved_sources"):
        sources = tuple(ws["retrieved_sources"])

    # Outline
    outline = ctx.outline
    if ws.get("outline"):
        outline_ws = ws.get("outline", [])
        arg_map = ws.get("argument_map", {})
        outline = {
            "outline": outline_ws,
            "argument_map": arg_map,
            "suggested_title": ws.get("suggested_title", ""),
        }

    # Verification
    verification = ws.get("verification", ctx.verification)

    # Editorial audit
    editorial_audit = ws.get("editorial_audit", ctx.editorial_audit)

    # Metrics
    metrics = ws.get("metrics", ctx.metrics)

    # Structural critique
    structural_critique = ws.get("structural_critique", ctx.structural_critique)

    # Audit
    audit = ws.get("audit", ctx.audit)

    # Errors
    errors = list(ctx.errors)
    # Check the live PipelineState for new errors (if available)
    if state is not None:
        state_errors = getattr(state, "errors", [])
        if state_errors:
            errors.extend(state_errors)

    return replace(
        ctx,
        doc=doc,
        sources=sources,
        outline=outline,
        verification=verification,
        editorial_audit=editorial_audit,
        metrics=metrics,
        structural_critique=structural_critique,
        audit=audit,
        errors=tuple(errors),
    )


# ═════════════════════════════════════════════════════════════════════
# Adapter: phase runner
# ═════════════════════════════════════════════════════════════════════

async def _run_phase_adapter(
    ctx: Context,
    deps: AdapterDeps,
    phase_fn: Callable,
    phase_name: str,
    domain: str | None = None,
) -> Result[Context, PhaseError]:
    """Generic adapter: run an existing phase function under the new signature.

    Handles conversion, execution, error wrapping, and result extraction.
    """
    state = _build_minimal_state(ctx)
    ws = context_to_writing_state(ctx)
    state.writing_state.update(ws)
    state.writing_state["_current_phase"] = phase_name

    try:
        if domain is not None:
            await phase_fn(state, deps.services, domain=domain)
        else:
            await phase_fn(state, deps.services)
    except Exception as exc:
        logger.warning("Phase '%s' failed with exception: %s", phase_name, exc)
        return Err(PhaseError.INTERNAL, fallback=ctx)

    try:
        new_ctx = writing_state_to_context(ctx, state.writing_state, deps, state=state)
    except Exception as exc:
        logger.warning("Phase '%s' context conversion failed: %s", phase_name, exc)
        return Err(PhaseError.INTERNAL, fallback=ctx)

    return Ok(new_ctx)


# ═════════════════════════════════════════════════════════════════════
# Individual phase adapters
# ═════════════════════════════════════════════════════════════════════

async def adapter_retrieve_sources(
    ctx: Context, deps: AdapterDeps
) -> Result[Context, PhaseError]:
    return await _run_phase_adapter(
        ctx, deps, run_article_retrieve_sources_phase, "retrieve_sources"
    )


async def adapter_build_outline(
    ctx: Context, deps: AdapterDeps
) -> Result[Context, PhaseError]:
    return await _run_phase_adapter(
        ctx, deps, run_article_outline_phase, "build_outline"
    )


async def adapter_draft(
    ctx: Context, deps: AdapterDeps
) -> Result[Context, PhaseError]:
    return await _run_phase_adapter(
        ctx, deps, run_article_draft_phase, "draft"
    )


async def adapter_fact_check(
    ctx: Context, deps: AdapterDeps
) -> Result[Context, PhaseError]:
    return await _run_phase_adapter(
        ctx, deps, run_article_adversarial_verify_phase, "fact_check"
    )


async def adapter_structural_review(
    ctx: Context, deps: AdapterDeps
) -> Result[Context, PhaseError]:
    return await _run_phase_adapter(
        ctx, deps, run_article_structural_review_phase, "structural_review"
    )


async def adapter_developmental_edit(
    ctx: Context, deps: AdapterDeps
) -> Result[Context, PhaseError]:
    return await _run_phase_adapter(
        ctx, deps, run_article_developmental_edit_phase, "developmental_edit"
    )


async def adapter_style_copy_edit(
    ctx: Context, deps: AdapterDeps
) -> Result[Context, PhaseError]:
    return await _run_phase_adapter(
        ctx, deps, run_article_style_copy_edit_phase, "style_copy_edit"
    )


async def adapter_final_audit(
    ctx: Context, deps: AdapterDeps
) -> Result[Context, PhaseError]:
    return await _run_phase_adapter(
        ctx, deps, run_article_final_audit_phase, "final_audit"
    )


async def adapter_synthesis(
    ctx: Context, deps: AdapterDeps
) -> Result[Context, PhaseError]:
    return await _run_phase_adapter(
        ctx, deps, run_synthesis_phase, "synthesis"
    )


# ═════════════════════════════════════════════════════════════════════
# Convenience: list of all adapters in order
# ═════════════════════════════════════════════════════════════════════

ADAPTER_PHASES: list[tuple[str, Callable]] = [
    ("Evidence Collection",     adapter_retrieve_sources),
    ("Argument Map / Outline",   adapter_build_outline),
    ("First Draft",              adapter_draft),
    ("Fact Check + Ledger",      adapter_fact_check),
    ("Structural Review",         adapter_structural_review),
    ("Developmental Edit",        adapter_developmental_edit),
    ("Style + Copy Edit",        adapter_style_copy_edit),
    ("Final Audit",              adapter_final_audit),
    ("Synthesis",                adapter_synthesis),
]
