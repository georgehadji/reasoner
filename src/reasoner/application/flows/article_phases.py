"""Article writing pipeline phase logic."""

from __future__ import annotations

import asyncio
import logging

import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices
from reasoner.application.flows.writing_phases import _extract_markdown_source_links
from reasoner.core.constants import (
    ARTICLE_MIN_CLAIM_SUPPORT_RATIO,
)
from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.search.discovery import get_search_client_for_method
from reasoner.parsing import extract_json

logger = logging.getLogger(__name__)


def _extract_source_metadata(sources: list[dict[str, str]]) -> list[dict[str, str]]:
    """Extract structured metadata (author, date, publisher) from source dicts.

    Search results vary by provider — this extracts whatever structured fields
    are available and fills missing fields with empty strings.
    """
    metadata = []
    for src in sources:
        meta = {
            "title": str(src.get("title", "")).strip(),
            "url": str(src.get("url", "")).strip(),
            "author": str(src.get("author", "")).strip(),
            "date": str(src.get("date", "")).strip(),
            "publisher": str(src.get("publisher", "")).strip(),
            "snippet": str(src.get("snippet", "")).strip()[:500],
        }
        metadata.append(meta)
    return metadata


def _parse_sonar_citations(raw_text: str) -> list[dict[str, str]]:
    """Parse inline [Title](URL) citations from a response (sonar or any model).

    Looks for Markdown link patterns and extracts title + URL pairs.
    Falls back to bare URL extraction if no Markdown links found.
    """
    import re

    sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    # Pattern 1: Markdown links — [Source Title](https://url...)
    md_links = re.findall(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', raw_text)
    for title, url in md_links:
        url = url.rstrip(".,;:!?)")
        if url not in seen_urls and len(url) > 10:
            seen_urls.add(url)
            sources.append({"title": title.strip(), "url": url, "snippet": ""})

    # Pattern 2: Bare URLs as fallback (only if no markdown links found)
    if not sources:
        bare_urls = re.findall(r'(https?://[^\s<>"\')\]]+)', raw_text)
        for url in bare_urls:
            url = url.rstrip(".,;:!?")
            if url not in seen_urls and len(url) > 10:
                seen_urls.add(url)
                # Extract domain as title
                from urllib.parse import urlparse
                try:
                    domain = urlparse(url).netloc.replace("www.", "")
                except Exception:
                    domain = url[:60]
                sources.append({"title": domain, "url": url, "snippet": ""})

    return sources


async def run_article_retrieve_sources_phase(state: PipelineState, services: WorkflowServices, domain: str | None = None) -> None:
    # Pre-draft augmentation runs here rather than in ArticleFlow.execute() for
    # the same reason as the audit retry: execute() is CLI-only, so on the web
    # this pass simply never happened. Guarded on the key it produces, because a
    # quality retry of this phase, and adapter_gap_retrieval which reuses this
    # function, would otherwise pay for it a second time.
    if "pre_research_insights" not in state.writing_state:
        from reasoner.application.flows.augmentation import run_augmentation
        await run_augmentation(state, services.call_llm, services.log)

    services.log("WRITING", "Retrieving targeted sources for article...", state)
    try:
        raw_plan, meta = await services.call_llm(
            role="primary",
            system_prompt=phases.ARTICLE_RETRIEVAL_PLAN_SYSTEM,
            user_prompt=phases.article_retrieval_plan_prompt(state),
            state=state
        )

        # ── Path A: Sonar / Perplexity native search → parse inline citations ──
        model_used = (meta or {}).get("model", "")
        is_sonar = "sonar" in model_used.lower() or "perplexity" in model_used.lower()

        if is_sonar:
            sources = _parse_sonar_citations(raw_plan)
            if sources:
                state.writing_state["retrieved_sources"] = sources
                state.writing_state["source_metadata"] = _extract_source_metadata(sources)
                services.log("WRITING", f"Sonar retrieved {len(sources)} sources via native search.", state)
                return

        # ── Path B: Standard JSON query plan → external search ──
        plan = extract_json(raw_plan)
        queries = plan.get("queries", [])[:5]

        if not queries:
            # Fallback: try parsing inline citations from any model's response
            sources = _parse_sonar_citations(raw_plan)
            if sources:
                state.writing_state["retrieved_sources"] = sources
                state.writing_state["source_metadata"] = _extract_source_metadata(sources)
                services.log("WRITING", f"Parsed {len(sources)} inline citations from response.", state)
                return

        method = "article"
        from reasoner.presets import get_preset_price_tier
        tier = get_preset_price_tier(state.preset_name) or "budget"
        client, _ = await get_search_client_for_method(method, tier, source_type="general")

        async def _search(q):
            try: return await client.search(q, num_results=5, domain=domain)
            except Exception: return []

        results = await asyncio.gather(*[_search(q) for q in queries], return_exceptions=True)
        flattened = []
        seen = set()
        for r_list in results:
            if isinstance(r_list, list):
                for r in r_list:
                    if r.get("url") not in seen:
                        seen.add(r.get("url"))
                        flattened.append(r)

        state.writing_state["retrieved_sources"] = flattened
        state.writing_state["source_metadata"] = _extract_source_metadata(flattened)
        if not flattened:
            state.writing_state["insufficient_evidence"] = True
            services.log("WRITING", "No sources found. Triggering insufficient evidence gate.", state)
    except Exception as e:
        services.log("WRITING", f"Source retrieval failed: {e}", state)

async def run_article_draft_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("WRITING", "Drafting long-form article...", state)
    raw, _ = await services.call_llm(
        role="writing_draft",
        system_prompt=phases.ARTICLE_DRAFT_SYSTEM,
        user_prompt=phases.article_draft_prompt(state),
        state=state
    )
    state.writing_state["final_article"] = raw

async def run_article_adversarial_verify_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("WRITING", "Running adversarial verification of article claims...", state)

    # Select system prompt: sonar models get live-web-aware instructions
    verify_system = phases.ARTICLE_VERIFY_SYSTEM
    use_sonar = False
    if hasattr(phases, "ARTICLE_VERIFY_SYSTEM_SONAR"):
        # Check if the writing_factcheck role routes to a sonar model
        from reasoner.presets import get_preset
        try:
            preset = get_preset(state.preset_name) if state.preset_name else None
            factcheck_model = preset.routing.get("writing_factcheck", "") if preset else ""
            if "sonar" in str(factcheck_model).lower():
                verify_system = phases.ARTICLE_VERIFY_SYSTEM_SONAR
                use_sonar = True
        except Exception:
            pass  # fall through to default prompt

    raw, _ = await services.call_llm(
        role="writing_factcheck",
        system_prompt=verify_system,
        user_prompt=phases.article_verify_prompt(state, use_sonar=use_sonar),
        state=state
    )
    data = extract_json(raw)
    state.writing_state["verification"] = data
    state.writing_state["claim_ledger"] = data.get("claim_ledger", [])
    metrics = data.get("metrics", {})
    state.writing_state["metrics"] = metrics

    if metrics.get("claim_support_ratio", 1.0) < ARTICLE_MIN_CLAIM_SUPPORT_RATIO:
        services.log("WRITING", "Low claim support ratio. Identifying gaps.", state)
        state.writing_state["gaps_noted"] = data.get("gaps", [])

# ── Argument Map / Outline ────────────────────────────────────────────────────

async def run_article_outline_phase(state: PipelineState, services: WorkflowServices) -> None:
    """Build argument map + outline (structural blueprint) before drafting."""
    services.log("WRITING", "Building argument map and outline...", state)
    raw, _ = await services.call_llm(
        role="article_sot_skeleton",
        system_prompt=phases.ARTICLE_OUTLINE_SYSTEM,
        user_prompt=phases.article_outline_prompt(state),
        state=state,
    )
    try:
        data = extract_json(raw)
    except Exception as exc:
        services.log("WRITING", f"Outline parse error: {exc}", state)
        state.errors.append(f"Article outline: parse error: {exc}")
        data = {}

    state.writing_state["argument_map"] = data.get("argument_map", {})
    state.writing_state["outline"] = data.get("outline", [])
    state.writing_state["suggested_title"] = data.get("suggested_title", "")
    state.writing_state["total_word_count"] = data.get("total_word_count", 0)
    services.log(
        "WRITING",
        f"Argument map complete: {len(state.writing_state['outline'])} sections, "
        f"title='{state.writing_state['suggested_title']}'",
        state,
    )


# ── Structural Adversarial Review ─────────────────────────────────────────────

async def run_article_structural_review_phase(state: PipelineState, services: WorkflowServices) -> None:
    """Devil's advocate review: logic, assumptions, counterarguments — not facts or grammar."""
    services.log("WRITING", "Running structural adversarial review...", state)
    raw, _ = await services.call_llm(
        role="article_critic",
        system_prompt=phases.ARTICLE_CRITIC_SYSTEM,
        user_prompt=phases.article_critic_prompt(state),
        state=state,
    )
    try:
        data = extract_json(raw)
    except Exception as exc:
        services.log("WRITING", f"Structural critique parse error: {exc}", state)
        state.errors.append(f"Article structural critique: parse error: {exc}")
        data = {}

    state.writing_state["structural_critique"] = data
    rigor = data.get("overall_rigor_score", 0.0)
    services.log(
        "WRITING",
        f"Structural review complete: rigor score={rigor}, "
        f"{len(data.get('logical_gaps', []))} gaps, "
        f"{len(data.get('ignored_counterarguments', []))} ignored counterarguments",
        state,
    )


# ── Developmental Editing ─────────────────────────────────────────────────────

async def run_article_developmental_edit_phase(state: PipelineState, services: WorkflowServices) -> None:
    """Fix argument, evidence, narrative flow based on structural critique."""
    services.log("WRITING", "Running developmental edit...", state)
    raw, _ = await services.call_llm(
        role="article_revise",
        system_prompt=phases.ARTICLE_DEVELOPMENTAL_EDIT_SYSTEM,
        user_prompt=phases.article_developmental_edit_prompt(state),
        state=state,
    )
    state.writing_state["final_article"] = raw
    services.log("WRITING", "Developmental edit complete.", state)


# ── Style + Copy Edit (sequential, one PhaseStep) ─────────────────────────────

async def run_article_style_copy_edit_phase(state: PipelineState, services: WorkflowServices) -> None:
    """Humanize (tell audit + rewrite), then copy edit, then assemble Sources.

    The humanize pass is two-step by construction: the model must first quote the
    AI-writing tells it can find in the draft, then emit the article rewritten
    without them. Enumerating before rewriting is the point — a model asked only
    to "make this sound human" reaches for synonyms, while one made to name the
    pattern first has to act on the specific sentence it just quoted.

    Falls back to the older single-step prose style edit when the JSON contract
    fails, so a parse error costs the audit rather than the whole phase.
    """
    services.log("WRITING", "Running humanize pass (AI-tell audit and rewrite)...", state)
    draft = state.writing_state.get("final_article", "")
    tells: list = []
    try:
        raw, _ = await services.call_llm(
            role="article_humanize",
            system_prompt=phases.WRITING_HUMANIZE_SYSTEM,
            user_prompt=phases.writing_humanize_prompt(state, draft),
            state=state,
        )
        data = extract_json(raw)
        humanized = str(data.get("humanized_article", "") or "").strip()
        if not humanized:
            raise ValueError("humanized_article empty")
        tells = data.get("ai_tells", []) or []
        state.writing_state["final_article"] = humanized
        # The serializer reads ai_tells_found, the prompt emits ai_tells. Re-key
        # here or the audit never reaches the client.
        state.writing_state["ai_tells_found"] = tells
        services.log("WRITING", f"Humanize complete: {len(tells)} AI tells found and rewritten.", state)
    except Exception as exc:
        services.log("WRITING", f"Humanize failed ({exc}) — falling back to prose style edit.", state)
        state.errors.append(f"Article humanize: {exc}")
        try:
            styled, _ = await services.call_llm(
                role="article_humanize",
                system_prompt=phases.ARTICLE_STYLE_EDIT_SYSTEM,
                user_prompt=phases.article_style_edit_prompt(state),
                state=state,
            )
            if styled and styled.strip():
                state.writing_state["final_article"] = styled
        except Exception as exc2:
            services.log("WRITING", f"Style edit failed: {exc2} — proceeding to copy edit on pre-style draft.", state)
            state.errors.append(f"Article style edit: {exc2}")

    services.log("WRITING", "Running copy edit and final assembly...", state)
    raw, _ = await services.call_llm(
        role="writing_assemble",
        system_prompt=phases.ARTICLE_COPY_EDIT_SYSTEM,
        user_prompt=phases.article_copy_edit_prompt(state),
        state=state,
    )

    # ── Sources, from the links actually in the finished text ──
    # Prompt instruction alone left the bibliography describing the intention
    # rather than the article. The writing flow has always done this
    # deterministically; the article flow was the one that did not.
    final_article = raw
    extracted_links = _extract_markdown_source_links(final_article)
    if extracted_links and "## Sources" not in final_article:
        final_article = final_article.rstrip() + "\n\n## Sources\n" + "\n".join(
            f"- [{link['title'] or link['url']}]({link['url']})" for link in extracted_links
        )
    state.writing_state["final_article"] = final_article
    state.writing_state["sources_cited"] = extracted_links
    # Written last and equal to final_article on purpose: _ser_synthesis maps
    # humanized_article onto the published article, so setting it mid-phase
    # would ship the pre-copy-edit text.
    if tells:
        state.writing_state["humanized_article"] = final_article
    services.log(
        "WRITING",
        f"Style + copy edit complete: {len(extracted_links)} sources cited.",
        state,
    )


# ── Final Editorial Audit ──────────────────────────────────────────────────────

async def _run_final_audit(state: PipelineState, services: WorkflowServices) -> None:
    """One pass of the pre-publication structured checklist audit."""
    services.log("WRITING", "Running final editorial audit...", state)
    raw, _ = await services.call_llm(
        role="article_verifier",
        system_prompt=phases.ARTICLE_FINAL_AUDIT_SYSTEM,
        user_prompt=phases.article_final_audit_prompt(state),
        state=state,
    )
    try:
        data = extract_json(raw)
    except Exception as exc:
        services.log("WRITING", f"Final audit parse error: {exc}", state)
        state.errors.append(f"Article final audit: parse error: {exc}")
        data = {}

    state.writing_state["editorial_audit"] = data
    passes = data.get("passes_audit", False)
    score = data.get("audit_score", 0.0)
    services.log(
        "WRITING",
        f"Editorial audit complete: score={score}, passes={passes}",
        state,
    )


async def run_article_final_audit_phase(state: PipelineState, services: WorkflowServices) -> None:
    """Audit the article; on failure redo the edit passes and audit once more.

    The retry lives in the phase rather than in ArticleFlow.execute() because
    execute() is only reached by the CLI. The SSE driver
    (api/execution/pipeline.py) builds a flat list from get_phases() and calls
    the phase functions directly, so anything held in execute() never runs for a
    web user. Here it runs on every driver, including the adapter path, which
    delegates back to this function.
    """
    await _run_final_audit(state, services)

    # An empty audit dict means the parse failed, and a failed parse is a failed
    # audit rather than a pass by default.
    if (state.writing_state.get("editorial_audit") or {}).get("passes_audit", False):
        return

    # A prior timeout on the edit pass means the draft is already degraded.
    # Retrying spends another full budget on the same broken input. Reads
    # state.errors, where both drivers actually write timeouts; the previous
    # version of this guard read state.pending_events, which no article phase
    # writes, so it never once fired.
    if any("Style + Copy Edit" in str(e) for e in state.errors):
        services.log(
            "WRITING",
            "Skipping retry: Style + Copy Edit already timed out on the primary pass",
            state,
        )
        return

    services.log("WRITING", "Audit failed. Retrying developmental edit and re-auditing...", state)
    await run_article_developmental_edit_phase(state, services)
    await run_article_style_copy_edit_phase(state, services)
    await _run_final_audit(state, services)

    # The re-audit used to be run and then ignored, so an article that failed
    # twice shipped exactly like one that passed. Record it: state.errors is
    # surfaced to the client on the next phase_complete.
    retried = state.writing_state.get("editorial_audit") or {}
    if not retried.get("passes_audit", False):
        msg = f"Article final audit failed after retry (score={retried.get('audit_score', 0.0)})"
        services.log("WRITING", msg, state)
        state.errors.append(msg)
