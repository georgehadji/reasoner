"""Article writing pipeline phase logic."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json
import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices
from reasoner.core.constants import ARTICLE_MIN_SOURCE_COUNT, ARTICLE_MIN_CLAIM_SUPPORT_RATIO, TRUNCATION
from reasoner.infrastructure.search.discovery import get_search_client_for_method

logger = logging.getLogger(__name__)


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
    metrics = data.get("metrics", {})
    state.writing_state["metrics"] = metrics
    
    if metrics.get("claim_support_ratio", 1.0) < ARTICLE_MIN_CLAIM_SUPPORT_RATIO:
        services.log("WRITING", "Low claim support ratio. Identifying gaps.", state)
        state.writing_state["gaps_noted"] = data.get("gaps", [])

async def run_article_refine_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("WRITING", "Refining article based on verification feedback...", state)
    raw, _ = await services.call_llm(
        role="writing_assemble",
        system_prompt=phases.ARTICLE_REFINE_SYSTEM,
        user_prompt=phases.article_refine_prompt(state),
        state=state
    )
    state.writing_state["final_article"] = raw


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
    rigor = data.get("overall_rigor_score", 0.5)
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
    """Two sequential passes: style edit (article_humanize) then copy edit (writing_assemble)."""
    services.log("WRITING", "Running style edit...", state)
    styled, _ = await services.call_llm(
        role="article_humanize",
        system_prompt=phases.ARTICLE_STYLE_EDIT_SYSTEM,
        user_prompt=phases.article_style_edit_prompt(state),
        state=state,
    )
    state.writing_state["final_article"] = styled

    services.log("WRITING", "Running copy edit and final assembly...", state)
    raw, _ = await services.call_llm(
        role="writing_assemble",
        system_prompt=phases.ARTICLE_COPY_EDIT_SYSTEM,
        user_prompt=phases.article_copy_edit_prompt(state),
        state=state,
    )
    state.writing_state["final_article"] = raw
    services.log("WRITING", "Style + copy edit complete.", state)


# ── Final Editorial Audit ──────────────────────────────────────────────────────

async def run_article_final_audit_phase(state: PipelineState, services: WorkflowServices) -> None:
    """Pre-publication structured checklist audit."""
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
