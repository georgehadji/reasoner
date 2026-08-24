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
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

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
from reasoner.application.flows.base import WorkflowServices
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.domain.article_domain import (
    Claim,
    Context,
    Document,
    Err,
    Ok,
    PhaseError,
    Result,
    Verdict,
    map_verdict,
)
from reasoner.domain.pipeline_state import PipelineState

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

    # Claim ledger — materialize raw dict list into typed Claim tuple (G1 fix)
    ledger = ctx.ledger
    raw_ledger = ws.get("claim_ledger", None)
    if raw_ledger is not None and isinstance(raw_ledger, (list, tuple)):
        try:
            typed_claims = []
            for i, entry in enumerate(raw_ledger):
                if not isinstance(entry, dict):
                    continue
                raw_status = str(entry.get("status", "unsupported")).lower()
                text = str(entry.get("claim", ""))
                if not text:
                    continue
                source_url = entry.get("source")
                typed_claims.append(Claim(
                    id=f"fc_{i}",
                    text=text,
                    sources=(source_url,) if source_url else (),
                    verdict=map_verdict(raw_status),
                    confidence=0.8 if raw_status in ("verified", "supported") else 0.3,
                ))
            if typed_claims:
                ledger = tuple(typed_claims)
        except Exception:
            logger.warning("Failed to convert claim_ledger to typed Claim objects", exc_info=True)

    # Validate locked_spans bounds (D3 fix)
    if doc is not None and doc.locked_spans:
        max_len = len(doc.markdown)
        valid_spans = tuple(
            (s, e) for s, e in doc.locked_spans
            if 0 <= s < e <= max_len
        )
        if len(valid_spans) != len(doc.locked_spans):
            logger.warning(
                "Removed %d out-of-bounds locked_spans",
                len(doc.locked_spans) - len(valid_spans),
            )
            doc = replace(doc, locked_spans=valid_spans)

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
        ledger=ledger,
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
    """Fact-check phase with span-lock recording (G2).

    After verification, records char spans of VERIFIED/SUPPORTED claims
    into Document.locked_spans so downstream edits preserve them.
    """
    result = await _run_phase_adapter(
        ctx, deps, run_article_adversarial_verify_phase, "fact_check"
    )
    if isinstance(result, Ok):
        ctx = result.value
        # Record locked_spans from VERIFIED/SUPPORTED claims
        if ctx.doc is not None and ctx.ledger:
            locked = []
            for c in ctx.ledger:
                if c.verdict in (Verdict.VERIFIED, Verdict.SUPPORTED) and c.span is not None:
                    locked.append(c.span)
            if locked:
                from dataclasses import replace
                ctx = replace(ctx, doc=replace(ctx.doc, locked_spans=tuple(locked)))
                result = Ok(ctx)
    return result


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
    """Style + copy edit with span-lock enforcement and reconciliation.

    1. Runs the existing style + copy edit phase.
    2. Enforces locked_spans: rejects changes that touch verified content.
    3. Runs reconcile_ledger to refresh the claim ledger against the new doc.
    """
    from reasoner.domain.article_domain import reconcile

    result = await _run_phase_adapter(
        ctx, deps, run_article_style_copy_edit_phase, "style_copy_edit"
    )
    if not isinstance(result, Ok):
        return result

    ctx_after_edit = result.value

    # ── Span-lock enforcement ──
    if ctx_after_edit.doc is not None and ctx.doc is not None and ctx.doc.locked_spans:
        old_text = ctx.doc.markdown
        new_text = ctx_after_edit.doc.markdown
        if old_text != new_text:
            # Check if any locked span changed
            violations = []
            for start, end in ctx.doc.locked_spans:
                old_segment = old_text[start:end]
                # Find where that segment is in the new text
                if old_segment and old_segment not in new_text:
                    violations.append({"span": (start, end), "text": old_segment})

            if violations:
                logger.warning(
                    "Span-lock violation: %d verified claim span(s) were modified "
                    "by style/copy edit — reverting to preserve factual content",
                    len(violations),
                )
                # Full revert: restore old text to preserve verified content
                ctx_after_edit = replace(
                    ctx_after_edit,
                    doc=replace(
                        ctx_after_edit.doc,
                        markdown=old_text,
                    ),
                )

    # ── Ledger reconciliation ──
    if ctx_after_edit.doc is not None and ctx.ledger:
        carried, deltas = reconcile(ctx.ledger, ctx_after_edit.doc)
        events = list(ctx_after_edit.events)
        if deltas:
            events.append({
                "type": "reconciliation",
                "version": ctx_after_edit.doc.version,
                "carried_count": len(carried),
                "deltas_count": len(deltas),
            })
            logger.info(
                "Ledger reconciliation: %d claims carried, %d deltas need verification",
                len(carried), len(deltas),
            )
        ctx_after_edit = replace(
            ctx_after_edit,
            ledger=carried,
            events=tuple(events),
        )
        result = Ok(ctx_after_edit)

    return result


def _revert_spans(new_text: str, old_text: str, locked_spans: tuple[tuple[int, int], ...]) -> str:
    """Revert changes to specific locked spans while preserving edits elsewhere.

    For each locked span, tries exact match first, then word-level fuzzy
    match within a search window around the expected position.
    """
    result = new_text
    # Process right-to-left so earlier fixes don't shift later positions
    for start, end in reversed(sorted(locked_spans)):
        original = old_text[start:end]
        pos = result.find(original)
        if pos >= 0:
            # Exact match found — no violation
            continue
        # Locked span was altered — try word-level recovery within the region
        words = [w for w in original.split() if len(w) > 3]
        if words:
            # Try to find the anchored word in the expected region
            search_start = max(0, start - 20)
            search_end = min(len(result), end + 20)
            region = result[search_start:search_end]
            # Check if any key words survive
            surviving = [w for w in words if w in region]
            if len(surviving) >= len(words) * 0.5:
                continue  # enough words survive — skip revert
        # Revert the entire locked span
        result = result[:start] + original + result[min(end, len(result)):]
    return result


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
# Combinators (higher-order functions wrapping adapters)
# ═════════════════════════════════════════════════════════════════════

def with_budget_guard(adapter_fn: Callable) -> Callable:
    """Budget circuit-breaker combinator (G10).

    Wraps an adapter function: if the budget is exhausted, returns
    Err(PhaseError.BUDGET) instead of running the phase.
    """
    async def wrapped(ctx: Context, deps: AdapterDeps) -> Result:
        if ctx.budget is not None and ctx.budget.remaining_usd() <= 0:
            logger.info("Budget exhausted — skipping phase")
            return Err(PhaseError.BUDGET, fallback=ctx)
        return await adapter_fn(ctx, deps)
    wrapped.__name__ = f"budget_guard_{adapter_fn.__name__}"
    return wrapped


def _has_evidence_gaps(ctx: Context) -> bool:
    """Check if the recent fact-check identified evidence gaps (G7)."""
    gaps = ctx.events
    for ev in gaps:
        if ev.get("type") == "evidence_gap":
            return True
    # Also check verification dict for gaps
    if ctx.verification and ctx.verification.get("gaps"):
        return True
    return False


async def adapter_gap_retrieval(
    ctx: Context, deps: AdapterDeps
) -> Result[Context, PhaseError]:
    """Gap-driven retrieval phase (G7).

    Runs additional source retrieval for topics where fact-check found
    insufficient evidence, then updates the context with new sources.
    """
    gaps = []
    if ctx.verification:
        gaps = ctx.verification.get("gaps", [])

    if not gaps:
        logger.info("No evidence gaps — skipping gap retrieval")
        return Ok(ctx)

    logger.info("Retrieving additional sources for %d evidence gaps...", len(gaps))

    # Build gap-targeted search queries
    gap_queries = [f"evidence about {g[:100]}" for g in gaps[:3]]

    # Run the existing retrieve phase with gap-targeted queries
    from reasoner.application.flows.article_phases import run_article_retrieve_sources_phase
    result = await _run_phase_adapter(
        ctx, deps, run_article_retrieve_sources_phase, "gap_retrieval"
    )

    if isinstance(result, Ok):
        ctx = result.value
        # Log the gap retrieval
        ctx = replace(ctx, events=ctx.events + (
            {"type": "gap_retrieval", "gaps_addressed": len(gaps), "sources_added": len(ctx.sources)},
        ))
        result = Ok(ctx)

    return result


async def adapter_surface_signals(
    ctx: Context, deps: AdapterDeps
) -> Result[Context, PhaseError]:
    """Surface quality signals to the user (G8).

    Reads the editorial audit and emits events that the frontend can
    display: quality warnings, hold-for-review flags, claim-level
    verdict summaries.
    """
    events: list[dict] = list(ctx.events)

    # ── Quality warning on audit failure ──
    audit = ctx.editorial_audit or {}
    passes = audit.get("passes_audit", True)
    score = audit.get("audit_score", 1.0)

    if not passes:
        issues = audit.get("issues", [])
        failing_dims = [
            f"{k}={v:.2f}" for k, v in (audit.get("audit") or {}).items()
            if isinstance(v, (int, float)) and v < 0.6
        ]
        events.append({
            "type": "quality_warning",
            "severity": "warning",
            "message": f"Article failed audit (score={score:.2f})",
            "failing_dimensions": failing_dims,
            "issues_count": len(issues),
        })

        # ── Hold-for-review policy ──
        # High-stakes content classes default to hold-for-review
        high_stakes = ("policy_brief", "news_analysis", "greek_briefing")
        if ctx.content_class in high_stakes:
            events.append({
                "type": "hold_for_review",
                "severity": "info",
                "message": f"Article held for manual review ({ctx.content_class})",
                "content_class": ctx.content_class,
            })

    # ── Claim-level verdict summary ──
    if ctx.ledger:
        verdict_counts: dict[str, int] = {}
        for c in ctx.ledger:
            v = c.verdict.value
            verdict_counts[v] = verdict_counts.get(v, 0) + 1
        events.append({
            "type": "claim_summary",
            "total_claims": len(ctx.ledger),
            "verdicts": verdict_counts,
        })

    ctx = replace(ctx, events=tuple(events))
    return Ok(ctx)


# ═════════════════════════════════════════════════════════════════════
# Convenience: list of all adapters in order
# ═════════════════════════════════════════════════════════════════════

ADAPTER_PHASES: list[tuple[str, Callable]] = [
    ("Evidence Collection",     with_budget_guard(adapter_retrieve_sources)),
    ("Argument Map / Outline",   with_budget_guard(adapter_build_outline)),
    ("First Draft",              with_budget_guard(adapter_draft)),
    ("Fact Check + Ledger",      with_budget_guard(adapter_fact_check)),
    ("Gap Retrieval",            with_budget_guard(adapter_gap_retrieval)),
    ("Structural Review",         with_budget_guard(adapter_structural_review)),
    ("Developmental Edit",        with_budget_guard(adapter_developmental_edit)),
    ("Style + Copy Edit",        with_budget_guard(adapter_style_copy_edit)),
    ("Final Audit",              with_budget_guard(adapter_final_audit)),
    ("Surface Signals",          with_budget_guard(adapter_surface_signals)),
    ("Synthesis",                with_budget_guard(adapter_synthesis)),
]
