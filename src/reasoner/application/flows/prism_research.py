"""Iterative tool-calling researcher — Prism logic ported to Python."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from reasoner.application.flows.base import WorkflowServices
from reasoner.core.constants_limits import TRUNCATION
from reasoner.core.ports.file_search_port import FileSearchPort
from reasoner.core.ports.llm_port import LLMPort
from reasoner.core.ports.search_port import SearchServicePort, SourceType
from reasoner.core.search import _normalize_url
from reasoner.core.settings import settings
from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import ParseError, extract_json
from reasoner.phases import prism_research_system

logger = logging.getLogger(__name__)

ResearchMode = Literal["speed", "balanced", "quality"]
_MODE_MAX_ITERS: dict[ResearchMode, int] = {"speed": 2, "balanced": 6, "quality": 25}


@dataclass
class _Citation:
    url: str
    title: str
    snippet: str
    source_type: str  # "web" | "academic" | "discussion" | "file" | "scraped"


async def _rank_citations(
    problem: str,
    citations: list[_Citation],
) -> list[_Citation]:
    """BM25 pre-sort (free) → optional semantic rerank (gated)."""
    if len(citations) <= 1:
        return citations

    from reasoner.core.search import _bm25_score
    scored = [
        (c, _bm25_score(problem, {"title": c.title, "content": c.snippet}))
        for c in citations
    ]
    scored.sort(key=lambda t: t[1], reverse=True)
    ranked = [c for c, _ in scored]

    if not settings.PRISM_RERANK_ENABLED:
        return ranked

    try:
        from reasoner.core.rerank import rerank_documents
        docs = [
            {"title": c.title, "content": c.snippet, "url": c.url, "_cit": c}
            for c in ranked
        ]
        reranked = await rerank_documents(problem, docs, top_n=len(docs))
        if reranked:
            return [d["_cit"] for d in reranked if d.get("_cit")]
    except Exception as exc:
        logger.warning("Prism rerank skipped: %s", exc)
    return ranked


async def run_prism_standalone(
    problem: str,
    router: LLMPort,
    search_client: SearchServicePort,
    mode: ResearchMode = "balanced",
) -> tuple[list[dict[str, str]], str]:
    """Standalone Prism loop for simple web-search path (no PipelineState needed).

    Returns (citations, summary) where citations are dicts with url/title/snippet/source_type.
    """
    max_iterations = _MODE_MAX_ITERS.get(mode, 6)
    citations: list[_Citation] = []
    by_url: dict[str, _Citation] = {}
    data: dict[str, Any] = {}

    actions: dict[str, Callable[[list[str]], asyncio.Coroutine[Any, Any, list[_Citation]]]] = {
        "webSearch": lambda qs: _action_web_search(search_client, qs, None),
        "academicSearch": lambda qs: _action_web_search(search_client, qs, "academic"),
        "discussionSearch": lambda qs: _action_web_search(search_client, qs, "social"),
        "scrape": lambda urls: _action_scrape(urls),
    }

    for i in range(1, max_iterations + 1):
        prompt = _build_iteration_prompt(problem, citations, i, max_iterations, [])
        try:
            raw, _ = await router.call(
                role="primary",
                system_prompt=prism_research_system(mode),
                user_prompt=prompt,
                max_tokens=512,
            )
        except Exception as exc:
            logger.warning("Prism standalone LLM call failed: %s", exc)
            break

        try:
            data = extract_json(raw) or {}
        except ParseError:
            break

        action = data.get("action", "done")
        reasoning = data.get("reasoning", "")
        queries = data.get("queries", [])
        urls = data.get("urls", [])

        if isinstance(queries, str):
            queries = [queries] if queries.strip() else []
        if isinstance(urls, str):
            urls = [urls] if urls.strip() else []

        logger.info("[PRISM] iter=%d action=%s reason=%s", i, action, reasoning[:80])

        if action == "done" or i == max_iterations:
            break

        action_fn = actions.get(action)
        if action_fn is None:
            break

        try:
            new_citations = await action_fn(queries if action != "scrape" else urls)
        except Exception as exc:
            logger.warning("Prism action %s failed: %s", action, exc)
            new_citations = []

        for c in new_citations:
            norm = _normalize_url(c.url)
            if not norm:
                citations.append(c)
                continue
            existing = by_url.get(norm)
            if existing is None:
                by_url[norm] = c
                citations.append(c)
            elif c.snippet and c.snippet not in existing.snippet:
                existing.snippet = f"{existing.snippet}\n\n{c.snippet}"[:TRUNCATION.CONTENT]

    ranked_citations = await _rank_citations(problem, citations)
    citation_dicts = [
        {"url": c.url, "title": c.title, "snippet": c.snippet, "source_type": c.source_type}
        for c in ranked_citations
    ]
    return citation_dicts, data.get("summary", "")


async def run_prism_research_phase(
    state: PipelineState,
    services: WorkflowServices,
    search_client: SearchServicePort,
    mode: ResearchMode = "balanced",
    file_search: FileSearchPort | None = None,
) -> None:
    """Iterative researcher loop: plan → search → refine → done."""
    max_iterations = _MODE_MAX_ITERS.get(mode, 6)
    citations: list[_Citation] = []
    by_url: dict[str, _Citation] = {}
    iteration_log: list[str] = []

    prism_state = state.method_state.get("prism")
    file_ids = prism_state.get("file_ids", []) if prism_state else []
    classification = prism_state.get("classification", {}) if prism_state else {}

    # Determine source_type preference from classification
    source_type: SourceType | None = None
    if classification.get("academic_search"):
        source_type = "academic"
    elif classification.get("discussion_search"):
        source_type = "social"

    problem = state.problem
    # Use standalone_follow_up if available from classifier
    if classification.get("standalone_follow_up"):
        problem = classification["standalone_follow_up"]

    # Action registry
    actions: dict[str, Callable[[list[str]], asyncio.Coroutine[Any, Any, list[_Citation]]]] = {
        "webSearch": lambda qs: _action_web_search(search_client, qs, source_type),
        "academicSearch": lambda qs: _action_web_search(search_client, qs, "academic"),
        "discussionSearch": lambda qs: _action_web_search(search_client, qs, "social"),
        "scrape": lambda urls: _action_scrape(urls),
        "uploadsSearch": lambda qs: _action_uploads_search(file_search, file_ids, qs),
    }

    services.log("RESEARCH", f"Starting Prism research ({mode} mode, max {max_iterations} iterations)", state)

    for i in range(1, max_iterations + 1):
        services.log("RESEARCH", f"Iteration {i}/{max_iterations}: Planning...", state)

        # Build prompt with current citations
        prompt = _build_iteration_prompt(problem, citations, i, max_iterations, file_ids)

        raw, _ = await services.call_llm(
            role="primary",
            phase_key="prism_research",
            system_prompt=prism_research_system(mode),
            user_prompt=prompt,
            state=state,
            max_tokens=512,
        )

        try:
            data = extract_json(raw) or {}
        except ParseError as e:
            services.log("RESEARCH", f"Failed to parse research plan: {e}", state)
            break

        action = data.get("action", "done")
        reasoning = data.get("reasoning", "")
        queries = data.get("queries", [])
        urls = data.get("urls", [])

        if isinstance(queries, str):
            queries = [queries] if queries.strip() else []
        if isinstance(urls, str):
            urls = [urls] if urls.strip() else []

        services.log("RESEARCH", f"Action: {action}. Reason: {reasoning}", state)
        iteration_log.append(f"[{action}] {reasoning}")

        # Emit step event via pending_events for SSE streaming
        state.pending_events.append({
            "type": "research_step_emitted",
            "step_type": _map_step_type(action),
            "queries": queries,
            "plan": reasoning,
            "urls": urls,
        })

        if action == "done" or i == max_iterations:
            services.log("RESEARCH", "Research loop complete.", state)
            break

        action_fn = actions.get(action)
        if action_fn is None:
            services.log("RESEARCH", f"Unknown action '{action}', stopping.", state)
            break

        # Execute action
        try:
            new_citations = await action_fn(queries if action != "scrape" else urls)
        except Exception as exc:
            services.log("RESEARCH", f"Action {action} failed: {exc}", state)
            new_citations = []

        # Deduplicate and merge
        added = 0
        for c in new_citations:
            norm = _normalize_url(c.url)
            if not norm:
                citations.append(c)
                added += 1
                continue
            existing = by_url.get(norm)
            if existing is None:
                by_url[norm] = c
                citations.append(c)
                added += 1

                # Emit SourceAdded event via pending_events
                state.pending_events.append({
                    "type": "source_added",
                    "url": c.url,
                    "title": c.title,
                    "source_type": c.source_type,
                    "relevance_score": 1.0,
                })
            elif c.snippet and c.snippet not in existing.snippet:
                existing.snippet = f"{existing.snippet}\n\n{c.snippet}"[:TRUNCATION.CONTENT]

        services.log("RESEARCH", f"Action {action} added {added} new citations (total: {len(citations)})", state)

    # Store results in method_state
    ranked_citations = await _rank_citations(problem, citations)
    citation_dicts = [
        {"url": c.url, "title": c.title, "snippet": c.snippet, "source_type": c.source_type}
        for c in ranked_citations
    ]
    state.method_state.set("prism", {
        **state.method_state.get("prism"),
        "citations": citation_dicts,
        "iteration_log": iteration_log,
    })

    # Emit citations ready event
    state.pending_events.append({
        "type": "research_citations_ready",
        "citation_count": len(citations),
        "source_types": list({c.source_type for c in citations}),
    })

    services.log("RESEARCH", f"Prism research complete. Total citations: {len(citations)}", state)


def _build_iteration_prompt(
    problem: str,
    citations: list[_Citation],
    iteration: int,
    max_iterations: int,
    file_ids: list[str],
) -> str:
    sources_str = json.dumps(
        [{"title": c.title, "url": c.url, "type": c.source_type} for c in citations],
        indent=2,
    ) if citations else "No sources gathered yet."
    file_hint = "\nUploaded files are available for searching." if file_ids else ""
    return (
        f"Problem: {problem}\n"
        f"Iteration: {iteration} of {max_iterations}\n"
        f"Sources gathered so far: {len(citations)}\n"
        f"Current sources:\n{sources_str}\n"
        f"{file_hint}\n\n"
        f"Decide the next action. If you have enough authoritative sources (≥5), choose 'done'. "
        f"If you need more depth on specific URLs, choose 'scrape' with those URLs. "
        f"If uploaded files might contain relevant information, choose 'uploadsSearch'."
    )


def _map_step_type(action: str) -> str:
    if action in ("webSearch", "academicSearch", "discussionSearch", "uploadsSearch"):
        return "searching"
    if action == "scrape":
        return "reading"
    if action == "done":
        return "reasoning"
    return "reasoning"


async def _action_web_search(
    client: SearchServicePort,
    queries: list[str],
    source_type: SourceType | None,
) -> list[_Citation]:
    results: list[_Citation] = []
    for q in queries:
        try:
            res = await client.search(q, num_results=5, source_type=source_type)
            for r in res:
                results.append(_Citation(
                    url=r.get("url", ""),
                    title=r.get("title", "Unknown"),
                    snippet=r.get("snippet", r.get("content", ""))[:500],
                    source_type=source_type if source_type else "web",
                ))
        except Exception as exc:
            logger.warning("Web search query failed '%s': %s", q, exc)
    return results


async def _action_scrape(urls: list[str]) -> list[_Citation]:
    from reasoner.scraper import scrape_urls
    results: list[_Citation] = []
    try:
        scraped = await scrape_urls(urls)
        for s in scraped:
            results.append(_Citation(
                url=s.get("url", ""),
                title=s.get("title", "Scraped content"),
                snippet=s.get("text", "")[:500],
                source_type="scraped",
            ))
    except Exception as exc:
        logger.warning("Scrape action failed: %s", exc)
    return results


async def _action_uploads_search(
    file_search: FileSearchPort | None,
    file_ids: list[str],
    queries: list[str],
) -> list[_Citation]:
    if not file_search or not file_ids or not queries:
        return []
    results: list[_Citation] = []
    for q in queries:
        try:
            chunks = await file_search.search_chunks(file_ids, q, top_k=5)
            for ch in chunks:
                results.append(_Citation(
                    url=f"file://{ch.file_id}",
                    title=f"Uploaded file: {ch.file_id}",
                    snippet=ch.content[:500],
                    source_type="file",
                ))
        except Exception as exc:
            logger.warning("Uploads search failed '%s': %s", q, exc)
    return results
