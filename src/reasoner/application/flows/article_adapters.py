"""
Phase adapters — wrap existing article phase bodies inside the new
``ArticleContext`` → ``Result[ArticleContext, str]`` signature.

This is the "Strangler Fig adapter" layer: every phase function is wrapped so
its **internal implementation is unchanged** — it still constructs a temporary
``PipelineState``, calls the same prompt builders, and produces the same output.
Only the boundary signature changes.

The adapter wraps the old in-place mutation into a pure-ish ``ArticleContext`` → new
``ArticleContext`` pipeline.  The old ``ArticleFlow.execute()`` delegates to
``run_article_pipeline()``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine, Protocol

from reasoner.domain.core_types import ArticleContext, Ok, Err, WritingDocument, Claim, Verdict
from reasoner.domain.core_types import map_verdict, compute_locked_spans, verify_locked_spans
from reasoner.domain.core_types import reconcile_ledger, claim_support_ratio
from reasoner.domain.core_types import make_article_event
from reasoner.parsing import extract_json, ParseError

logger = logging.getLogger(__name__)


# ── Protocol ──────────────────────────────────────────────────────────────────

class Deps(Protocol):
    """Service dependencies injected by the pipeline runner.

    Mirrors the current ``WorkflowServices`` protocol.  The ``state``
    parameter for ``log`` and ``call_llm`` must accept ``PipelineState``
    at runtime — the Protocol is typed as ``object`` to allow structural
    subtyping.
    """
    async def call_llm(
        self, role: str, system_prompt: str, user_prompt: str,
        state: object, **kwargs: Any,
    ) -> tuple[str, dict]:
        ...

    def log(self, phase: str, message: str, state: object) -> None:
        ...


# Result type alias for readability
PhaseResult = Ok | Err


# ── Combinators ──────────────────────────────────────────────────────────────

def pipeline(*phases: Callable[[ArticleContext, Deps], Coroutine]) -> Callable[[ArticleContext, Deps], Coroutine]:
    """Compose phases into a linear pipeline with degradation handling.

    Each phase receives the current ``ArticleContext`` and must return an
    ``Ok(new_ctx)`` or an ``Err(error, fallback=degraded_ctx)``.  Errors with
    a fallback are logged and the degraded context is carried forward.
    Fatal errors (no fallback) terminate the pipeline.
    """
    async def run(ctx: ArticleContext, deps: Deps) -> PhaseResult:
        cur = ctx
        for phase_fn in phases:
            name = getattr(phase_fn, "__name__", "unknown")
            try:
                result = await phase_fn(cur, deps)
            except Exception as exc:
                logger.exception("Phase %s raised unhandled exception", name)
                return Err(f"Unhandled exception in {name}: {exc}", phase=name, fallback=cur)

            if isinstance(result, Ok):
                cur = result.value
            elif isinstance(result, Err):
                if result.fallback is not None:
                    logger.info("Phase %s degraded: %s", name, result.error)
                    cur = result.fallback
                else:
                    return result
            else:
                return Err(f"Phase {name} returned unexpected type: {type(result).__name__}", phase=name)
        return Ok(cur)
    return run


def with_retry(
    phase_fn: Callable[[ArticleContext, Deps], Coroutine],
    *,
    max_retries: int = 1,
    on_retry: Callable[[ArticleContext, int], Coroutine] | None = None,
) -> Callable[[ArticleContext, Deps], Coroutine]:
    """Wrap a phase with retry logic.

    Retries up to ``max_retries`` times when the phase returns ``Err`` with
    a fallback context.  The``on_retry`` callback (if provided) is called
    before each retry to prepare the context (e.g. refresh critiques).
    """
    async def wrapped(ctx: ArticleContext, deps: Deps) -> PhaseResult:
        cur = ctx
        for attempt in range(max_retries + 1):
            result = await phase_fn(cur, deps)
            if isinstance(result, Ok):
                return result
            if attempt < max_retries and isinstance(result, Err) and result.fallback is not None:
                cur = result.fallback
                if on_retry is not None:
                    cur = await on_retry(cur, attempt)
                continue
            return result
    return wrapped


def branch(
    predicate: Callable[[ArticleContext], bool],
    then_phase: Callable[[ArticleContext, Deps], Coroutine],
    otherwise: Callable[[ArticleContext, Deps], Coroutine] | None = None,
) -> Callable[[ArticleContext, Deps], Coroutine]:
    """Conditionally run a phase.

    If ``predicate(ctx)`` is True, run ``then_phase``.  Otherwise run
    ``otherwise`` if provided, or return ``Ok(ctx)`` unchanged.
    """
    async def wrapped(ctx: ArticleContext, deps: Deps) -> PhaseResult:
        if predicate(ctx):
            return await then_phase(ctx, deps)
        if otherwise is not None:
            return await otherwise(ctx, deps)
        return Ok(ctx)
    return wrapped


# ── Adapter helpers ──────────────────────────────────────────────────────────

def _extract_field(data: dict, *keys: str) -> str:
    """Extract first non-empty string value from a list of keys."""
    for key in keys:
        val = data.get(key, "")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _safe_json(response_text: str) -> dict:
    """Thin wrapper around extract_json that never raises."""
    try:
        return extract_json(response_text)
    except ParseError:
        return {}


def _build_article_from_draft(data: dict, old_doc: WritingDocument, phase: str) -> WritingDocument:
    """Build a new WritingDocument from a draft response.

    Explicitly clears ``locked_spans`` — they must be recomputed after fact-check
    or reconciliation, not silently carried forward through edit phases.
    """
    from dataclasses import replace as _dc_replace
    text = _extract_field(data, "article", "humanized_article", "markdown", "final_article", "content")
    title = _extract_field(data, "title", "article_title", "suggested_title")
    return _dc_replace(old_doc,
        version=old_doc.version + 1,
        markdown=text or old_doc.markdown,
        title=title or old_doc.title,
        produced_by=phase,
        locked_spans=(),  # always cleared — recomputed by fact_check or final_audit
    )


# ── Phase adapters ──────────────────────────────────────────────────────────

# Each adapter is a top-level async function matching:
#   async def adapter_fn(ctx: ArticleContext, deps: Deps) -> PhaseResult:
#
# The body follows the same pattern:
#   1. Build a temporary PipelineState from ctx.to_pipeline_state()
#   2. Call the existing phase runner (from article_phases)
#   3. Extract the new fields from the mutated state
#   4. Return Ok(updated_context) or Err(...)


async def retrieve_sources(ctx: ArticleContext, deps: Deps) -> PhaseResult:
    """Adapts run_article_retrieve_sources_phase."""
    from reasoner.application.flows.article_phases import run_article_retrieve_sources_phase

    state = ctx.to_pipeline_state()
    # Phase runs as before — mutates state.writing_state
    await run_article_retrieve_sources_phase(state, deps)
    ws = state.writing_state

    new_ctx = ctx.replace(
        sources=tuple(ws.get("retrieved_sources") or ctx.sources),
        source_metadata=tuple(ws.get("source_metadata") or ctx.source_metadata),
        gaps_noted=list(ws.get("insufficient_evidence", [])),
    )
    ev = make_article_event("retrieve_sources", "sources_retrieved",
        f"Retrieved {len(new_ctx.sources)} sources",
        {"count": len(new_ctx.sources), "gaps": len(new_ctx.gaps_noted)})
    new_ctx = new_ctx.replace(events=new_ctx.events + (ev,))
    return Ok(new_ctx)


async def build_outline(ctx: ArticleContext, deps: Deps) -> PhaseResult:
    """Adapts run_article_outline_phase."""
    from reasoner.application.flows.article_phases import run_article_outline_phase

    state = ctx.to_pipeline_state()
    await run_article_outline_phase(state, deps)
    ws = state.writing_state

    arg_map = ws.get("argument_map") or {}
    outline = ws.get("outline") or []
    title = ws.get("suggested_title", ctx.doc.title)
    from dataclasses import replace as _dcr
    doc = _dcr(ctx.doc, title=title, produced_by="outline")

    new_ctx = ctx.replace(
        argument_map=arg_map,
        outline=tuple(outline),
        doc=doc,
    )
    ev = make_article_event("build_outline", "outline_built",
        f"Built outline with {len(new_ctx.outline)} sections",
        {"sections": len(new_ctx.outline), "title": new_ctx.doc.title[:80] if new_ctx.doc.title else ""})
    new_ctx = new_ctx.replace(events=new_ctx.events + (ev,))
    return Ok(new_ctx)


async def first_draft(ctx: ArticleContext, deps: Deps) -> PhaseResult:
    """Adapts run_article_draft_phase."""
    from reasoner.application.flows.article_phases import run_article_draft_phase

    state = ctx.to_pipeline_state()
    await run_article_draft_phase(state, deps)
    ws = state.writing_state

    doc = _build_article_from_draft(ws, ctx.doc, "draft")
    new_ctx = ctx.replace(doc=doc)
    ev = make_article_event("first_draft", "draft_completed",
        f"Completed first draft ({len(new_ctx.doc.markdown)} chars)",
        {"char_count": len(new_ctx.doc.markdown), "title": new_ctx.doc.title[:80] if new_ctx.doc.title else ""})
    new_ctx = new_ctx.replace(events=new_ctx.events + (ev,))
    return Ok(new_ctx)


async def fact_check(ctx: ArticleContext, deps: Deps) -> PhaseResult:
    """Adapts run_article_adversarial_verify_phase.

    Phase 2 enhancement: uses ``map_verdict()`` to normalise raw LLM verdict
    strings into the canonical ``Verdict`` taxonomy, then computes locked
    spans for VERIFIED/SUPPORTED claims.
    """
    from reasoner.application.flows.article_phases import run_article_adversarial_verify_phase

    state = ctx.to_pipeline_state()
    await run_article_adversarial_verify_phase(state, deps)
    ws = state.writing_state

    ledger = ws.get("claim_ledger") or []
    metrics = ws.get("metrics") or {}
    verification = ws.get("verification") or {}
    gaps = ws.get("gaps_noted") or []

    # Phase 2: map raw LLM verdict strings through canonical Verdict taxonomy
    claims = tuple(
        Claim(
            id=str(i),
            text=(c.get("claim", "") if isinstance(c, dict) else getattr(c, "text", "")),
            verdict=map_verdict(
                c.get("status", c.get("verdict", "unverified")) if isinstance(c, dict)
                else getattr(c, "status", getattr(c, "verdict", "unverified")),
            ),
            source_url=(c.get("source", "") if isinstance(c, dict) else getattr(c, "source_url", "")),
            note=(c.get("note", "") if isinstance(c, dict) else getattr(c, "note", "")),
            verified_against_version=ctx.doc.version,
        )
        for i, c in enumerate(ledger)
    )

    # Phase 2: compute locked spans for VERIFIED/SUPPORTED claims
    locked_spans = compute_locked_spans(ctx.doc.markdown, claims)
    from dataclasses import replace as _dcr2
    doc = _dcr2(ctx.doc, locked_spans=locked_spans)

    new_ctx = ctx.replace(
        claims=claims,
        doc=doc,
        metrics=metrics,
        verification_results=verification,
        gaps_noted=list(gaps),
    )
    ev = make_article_event("fact_check", "claim_verification",
        f"Verified {len(new_ctx.claims)} claims, ratio={claim_support_ratio(new_ctx.claims):.2f}",
        {"total": len(new_ctx.claims), "ratio": round(claim_support_ratio(new_ctx.claims), 4)})
    new_ctx = new_ctx.replace(events=new_ctx.events + (ev,))

    return Ok(new_ctx)


async def structural_review(ctx: ArticleContext, deps: Deps) -> PhaseResult:
    """Adapts run_article_structural_review_phase."""
    from reasoner.application.flows.article_phases import run_article_structural_review_phase

    state = ctx.to_pipeline_state()
    await run_article_structural_review_phase(state, deps)
    ws = state.writing_state

    critique = ws.get("structural_critique") or {}
    new_ctx = ctx.replace(structural_critique=critique)

    ev = make_article_event("structural_review", "structural_reviewed",
        f"Structural review: rigor={critique.get('overall_rigor_score', 0):.1f}",
        {"rigor_score": critique.get('overall_rigor_score', 0),
         "gaps": len(critique.get('logical_gaps', []))})
    new_ctx = new_ctx.replace(events=new_ctx.events + (ev,))
    return Ok(new_ctx)


async def developmental_edit(ctx: ArticleContext, deps: Deps) -> PhaseResult:
    """Adapts run_article_developmental_edit_phase."""
    from reasoner.application.flows.article_phases import run_article_developmental_edit_phase

    state = ctx.to_pipeline_state()
    await run_article_developmental_edit_phase(state, deps)
    ws = state.writing_state

    doc = _build_article_from_draft(ws, ctx.doc, "dev_edit")
    new_ctx = ctx.replace(doc=doc)

    ev = make_article_event("developmental_edit", "dev_edit_completed",
        f"Developmental edit: {len(new_ctx.doc.markdown)} chars",
        {"char_count": len(new_ctx.doc.markdown)})
    new_ctx = new_ctx.replace(events=new_ctx.events + (ev,))
    return Ok(new_ctx)


async def style_copy_edit(ctx: ArticleContext, deps: Deps) -> PhaseResult:
    """Adapts run_article_style_copy_edit_phase.

    Phase 2 enhancement: after the edit, verifies that text under
    ``locked_spans`` has not been altered.  If verification fails, the
    original document is preserved (degradation).
    """
    from reasoner.application.flows.article_phases import run_article_style_copy_edit_phase

    state = ctx.to_pipeline_state()
    old_markdown = ctx.doc.markdown
    await run_article_style_copy_edit_phase(state, deps)
    ws = state.writing_state

    doc = _build_article_from_draft(ws, ctx.doc, "style_copy")

    # Phase 2: verify locked spans survived editing
    spans_preserved = True  # default when no locked spans exist
    if ctx.doc.locked_spans:
        spans_preserved = verify_locked_spans(old_markdown, doc.markdown, ctx.doc.locked_spans)
        if not spans_preserved:
            logger.info("style_copy_edit: locked span altered by edit — reverting to original")
            doc = ctx.doc  # degraded fallback: keep old doc
        else:
            from dataclasses import replace as _dcr3
            doc = _dcr3(doc, locked_spans=compute_locked_spans(doc.markdown, ctx.claims))

    new_ctx = ctx.replace(doc=doc)

    ev = make_article_event("style_copy_edit", "style_edit_completed",
        f"Style + copy edit: {len(new_ctx.doc.markdown)} chars, spans_preserved={spans_preserved}",
        {"char_count": len(new_ctx.doc.markdown),
         "locked_spans": len(ctx.doc.locked_spans),
         "spans_preserved": spans_preserved})
    new_ctx = new_ctx.replace(events=new_ctx.events + (ev,))
    return Ok(new_ctx)


async def final_audit(ctx: ArticleContext, deps: Deps) -> PhaseResult:
    """Adapts run_article_final_audit_phase.

    Phase 2/3 enhancement: before delegating, reconciles the claim ledger
    and computes the honest ``claim_support_ratio``.  After delegating,
    evaluates the audit results against a per-content-class ``GatePolicy``
    and returns ``Err`` with degradation if the article fails.

    The ``claim_support`` dimension is replaced with the programmatic
    ``claim_support_ratio()`` from Phase 2 (closing the impressionistic
    self-assessment gap).  Verifier independence (G4) is validated
    by ``route_verifier()`` in preset-registry tests — runtime
    enforcement will land in Phase 4.
    """
    from reasoner.application.flows.article_phases import run_article_final_audit_phase
    from reasoner.domain.core_types import GATE_POLICIES, GatePolicy, DEFAULT_GATE_POLICY

    # Phase 2: reconcile ledger against current doc before audit
    reconciled, to_verify = reconcile_ledger(ctx.claims, ctx.doc)
    honest_ratio = claim_support_ratio(reconciled)

    # Update metrics with the honest ratio
    updated_metrics = dict(ctx.metrics)
    updated_metrics["claim_support_ratio"] = round(honest_ratio, 4)

    from dataclasses import replace as _dcr4
    ctx = ctx.replace(
        claims=reconciled,
        metrics=updated_metrics,
        gaps_noted=list(ctx.gaps_noted) + to_verify,
        doc=_dcr4(ctx.doc, locked_spans=compute_locked_spans(ctx.doc.markdown, reconciled)),
    )

    # Delegate to the LLM audit phase
    state = ctx.to_pipeline_state()
    await run_article_final_audit_phase(state, deps)
    ws = state.writing_state

    audit = ws.get("editorial_audit") or {}
    new_ctx = ctx.replace(editorial_audit=audit)

    # Phase 3: evaluate gate policy against audit data
    # Replace the LLM's impressionistic "claim_support" with the programmatic one
    audit_data = dict(audit.get("audit") or {})
    audit_data["claim_support"] = honest_ratio

    policy = GATE_POLICIES.get(ctx.content_class, DEFAULT_GATE_POLICY)
    passes, details = policy.evaluate(audit_data)

    # Write gate results into editorial_audit for surface_signals (Phase 4)
    enriched_audit = dict(audit)
    enriched_audit["gate_score"] = details["score"]
    enriched_audit["gate_failures"] = details["failures"]
    enriched_audit["passes_audit"] = passes
    new_ctx = new_ctx.replace(editorial_audit=enriched_audit)

    ev = make_article_event("final_audit", "audit_completed",
        f"Audit: passes={passes}, score={details['score']:.2f}, failures={details['failures']}",
        {"gate_score": details['score'], "passes": passes, "failures": details['failures'],
         "honest_ratio": round(honest_ratio, 4)})
    new_ctx = new_ctx.replace(events=new_ctx.events + (ev,))

    if not passes:
        logger.info(
            "final_audit: gate policy rejected (score=%.2f, failures=%s)",
            details['score'], details['failures'])
        return Err(
            f"Gate policy failed: score={details['score']:.2f}, "
            f"failures={details['failures']}",
            phase="final_audit",
            fallback=new_ctx,  # degraded but reportable
        )

    return Ok(new_ctx)



async def synthesis_phase(ctx: ArticleContext, deps: Deps) -> PhaseResult:
    """Adapts run_synthesis_phase."""
    from reasoner.application.flows.synthesis_phase import run_synthesis_phase

    state = ctx.to_pipeline_state()
    await run_synthesis_phase(state, deps)
    # Extract the FinalSolution that synthesis writes to state.final_solution
    final_solution = getattr(state, "final_solution", None)
    if final_solution is not None:
        ctx = ctx.replace(final_solution=final_solution)

    ev = make_article_event("synthesis", "synthesis_completed",
        f"Synthesis completed: solution={'present' if ctx.final_solution else 'absent'}",
        {"has_solution": ctx.final_solution is not None})
    ctx = ctx.replace(events=ctx.events + (ev,))
    return Ok(ctx)


# ── Phase 4: surface_signals, gap detection, gap retrieval ─────────────

def has_evidence_gaps(ctx: ArticleContext) -> bool:
    """Predicate for ``branch`` — true if unverified claims or known gaps exist."""
    if ctx.gaps_noted:
        return True
    factual = [c for c in ctx.claims if c.verdict in (Verdict.VERIFIED, Verdict.SUPPORTED)]
    if ctx.claims and not factual:
        return True
    return False


async def gap_retrieval(ctx: ArticleContext, deps: Deps) -> PhaseResult:
    """Re-run source retrieval for evidence gaps."""
    from reasoner.application.flows.article_phases import run_article_retrieve_sources_phase

    state = ctx.to_pipeline_state()
    await run_article_retrieve_sources_phase(state, deps)
    ws = state.writing_state

    new_ctx = ctx.replace(
        sources=tuple(ws.get("retrieved_sources") or ctx.sources),
        source_metadata=tuple(ws.get("source_metadata") or ctx.source_metadata),
        gaps_noted=list(ws.get("insufficient_evidence", [])),
    )

    ev = make_article_event("gap_retrieval", "gap_sources_retrieved",
        f"Gap retrieval: {len(new_ctx.sources)} sources",
        {"count": len(new_ctx.sources)})
    new_ctx = new_ctx.replace(events=new_ctx.events + (ev,))
    return Ok(new_ctx)


def _compute_surface_signals(ctx: ArticleContext) -> dict:
    """Build structured quality/status signals from the final context."""
    signals: dict = {}
    audit = ctx.editorial_audit or {}
    gate_failures = audit.get("gate_failures", [])

    if not audit.get("passes_audit", True):
        signals["quality_warning"] = {
            "severity": "high" if ctx.content_class in (
                "greek_briefing", "policy_brief", "news_analysis") else "medium",
            "message": f"Article did not pass editorial audit (gate score: {audit.get("gate_score", 0):.2f})",
            "failures": gate_failures,
        }

    if ctx.gaps_noted:
        signals["evidence_gaps"] = {
            "count": len(ctx.gaps_noted),
            "gaps": ctx.gaps_noted[:5],
        }

    ratio = claim_support_ratio(ctx.claims)
    if ratio < 0.5 and ctx.claims:
        signals["low_support_ratio"] = {"ratio": round(ratio, 4)}

    claim_signals = {}
    for c in ctx.claims:
        if c.verdict in (Verdict.SPECULATIVE, Verdict.UNSUPPORTED, Verdict.PARTIAL):
            key = f"claim_{c.id}"
            claim_signals[key] = {
                "text": c.text[:100],
                "verdict": c.verdict.value,
                "note": c.note,
            }
    if claim_signals:
        signals["claims_needing_review"] = claim_signals

    return signals


# ── Assembled pipeline ──────────────────────────────────────────────────────

article_pipeline = pipeline(
    retrieve_sources,
    build_outline,
    first_draft,
    fact_check,
    branch(has_evidence_gaps, gap_retrieval),
    structural_review,
    with_retry(
        pipeline(
            developmental_edit,
            style_copy_edit,
            final_audit,
        ),
        max_retries=1,
    ),
    synthesis_phase,
)
