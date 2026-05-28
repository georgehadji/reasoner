"""Writing phase logic."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from reasoner.models import PipelineState, PerspectiveType, SolutionCandidate
from reasoner.parsing import extract_json
import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices

logger = logging.getLogger(__name__)

def _extract_markdown_source_links(text: str) -> list[dict[str, str]]:
    seen: set[str] = set()
    links: list[dict[str, str]] = []
    for title, url in re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", text or ""):
        clean_url = url.strip()
        if clean_url in seen:
            continue
        seen.add(clean_url)
        links.append({"title": title.strip(), "url": clean_url})
    return links

def _normalize_sources_cited(
    raw_sources: list[object],
    extracted_links: list[dict[str, str]],
) -> list[dict[str, str]]:
    extracted_by_url = {link["url"]: link for link in extracted_links if link.get("url")}
    normalized: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for item in raw_sources:
        if isinstance(item, dict):
            url = str(item.get("url", "")).strip()
            title = str(item.get("title", "")).strip() or extracted_by_url.get(url, {}).get("title", url)
        elif isinstance(item, str):
            url = item.strip()
            title = extracted_by_url.get(url, {}).get("title", url)
        else:
            continue

        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        normalized.append({"title": title or url, "url": url})

    return normalized

async def run_writing_outline_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("WRITING", "Generating article outline from sources...", state)
    raw, _ = await services.call_llm(
        role="writing_outline",
        system_prompt=phases.WRITING_OUTLINE_SYSTEM,
        user_prompt=phases.writing_outline_prompt(state),
        state=state,
    )
    try:
        data = extract_json(raw)
    except Exception as exc:
        services.log("WRITING", f"Outline parse error: {exc}", state)
        state.errors.append(f"Writing outline: parse error: {exc}")
        data = {}

    state.writing_state["outline"] = data.get("outline", [])
    state.writing_state["suggested_title"] = data.get("suggested_title", "")
    state.writing_state["total_word_count"] = data.get("total_word_count", 0)
    services.log(
        "WRITING",
        f"Outline complete: {len(state.writing_state['outline'])} sections, "
        f"title='{state.writing_state['suggested_title']}'",
        state,
    )

async def run_writing_draft_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("WRITING", "Drafting article from outline and sources...", state)
    raw, _ = await services.call_llm(
        role="writing_draft",
        system_prompt=phases.WRITING_DRAFT_SYSTEM,
        user_prompt=phases.writing_draft_prompt(state),
        state=state,
    )
    try:
        data = extract_json(raw)
    except Exception as exc:
        services.log("WRITING", f"Draft parse error: {exc}", state)
        state.errors.append(f"Writing draft: parse error: {exc}")
        data = {}

    state.writing_state["article"] = data.get("article", "")
    state.writing_state["abstract"] = data.get("abstract", "")
    state.writing_state["draft_word_count"] = data.get("word_count", 0)
    state.writing_state["sections_written"] = data.get("sections_written", [])
    services.log(
        "WRITING",
        f"Draft complete: {state.writing_state.get('draft_word_count', 0)} words, "
        f"{len(state.writing_state.get('sections_written', []))} sections",
        state,
    )

async def run_writing_factcheck_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("WRITING", "Fact-checking article against sources...", state)
    raw, _ = await services.call_llm(
        role="writing_factcheck",
        system_prompt=phases.WRITING_FACTCHECK_SYSTEM,
        user_prompt=phases.writing_factcheck_prompt(state),
        state=state,
    )
    try:
        data = extract_json(raw)
    except Exception as exc:
        services.log("WRITING", f"Fact-check parse error: {exc}", state)
        state.errors.append(f"Writing fact-check: parse error: {exc}")
        data = {}

    state.writing_state["factcheck_reviews"] = data.get("paragraph_reviews", [])
    state.writing_state["overall_confidence"] = data.get("overall_confidence", 0.0)
    state.writing_state["hallucination_risk"] = data.get("hallucination_risk", "unknown")
    state.writing_state["fc_recommendations"] = data.get("recommendations", [])
    state.writing_state["needs_rewrite"] = data.get("needs_rewrite", False)
    services.log(
        "WRITING",
        f"Fact-check complete: confidence={state.writing_state.get('overall_confidence', 0.0)}, "
        f"risk={state.writing_state.get('hallucination_risk', 'unknown')}, "
        f"needs_rewrite={state.writing_state.get('needs_rewrite', False)}",
        state,
    )

async def run_writing_assemble_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("WRITING", "Assembling final article with fact-check feedback...", state)
    raw, _ = await services.call_llm(
        role="writing_assemble",
        system_prompt=phases.WRITING_ASSEMBLE_SYSTEM,
        user_prompt=phases.writing_assemble_prompt(state),
        state=state,
    )
    try:
        data = extract_json(raw)
    except Exception as exc:
        services.log("WRITING", f"Assembly parse error: {exc}", state)
        state.errors.append(f"Writing assemble: parse error: {exc}")
        data = {}

    final_article = data.get("final_article", "")
    extracted_links = _extract_markdown_source_links(final_article)
    if extracted_links and "## Sources" not in final_article:
        final_article = final_article.rstrip() + "\n\n## Sources\n" + "\n".join(
            f"- [{link['title'] or link['url']}]({link['url']})" for link in extracted_links
        )
    normalized_sources = _normalize_sources_cited(data.get("sources_cited", []), extracted_links)
    state.writing_state["final_article"] = final_article
    state.writing_state["final_abstract"] = data.get("abstract", "")
    state.writing_state["final_changes"] = data.get("changes_made", [])
    state.writing_state["sources_cited"] = normalized_sources or extracted_links
    state.writing_state["confidence_notice"] = data.get("confidence_notice", "")
    state.writing_state["final_word_count"] = data.get("word_count", 0)

    # Feed final article into candidates for synthesis
    state.candidates.append(SolutionCandidate(
        perspective=PerspectiveType.CONSTRUCTIVE,
        content=final_article,
        key_insights=state.writing_state.get("final_changes", []),
        model_used="",
    ))
    services.log(
        "WRITING",
        f"Assembly complete: {state.writing_state.get('final_word_count', 0)} words, "
        f"{len(state.writing_state.get('sources_cited', []))} sources cited",
        state,
    )
