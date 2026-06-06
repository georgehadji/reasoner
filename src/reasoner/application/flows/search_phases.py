"""Search and vetting phase logic."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

import httpx

from reasoner.core.constants import TRUNCATION, YOUTUBE_OEMBED_URL, YOUTUBE_WATCH_BASE_URL
from reasoner.infrastructure.search.discovery import get_discovery_client
from reasoner.core.search import (
    _should_include_result,
    _normalize_url,
    _bm25_score,
)
from reasoner.infrastructure.search.discovery import _extract_search_keywords
from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import ParseError, extract_json, safe_list
from reasoner.sanitization import sanitize_for_prompt
import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices

logger = logging.getLogger(__name__)

_YOUTUBE_URL_RE = re.compile(
    r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
    re.IGNORECASE,
)

def _extract_youtube_id(text: str) -> str | None:
    match = _YOUTUBE_URL_RE.search(text)
    return match.group(1) if match else None

async def _fetch_youtube_metadata(video_id: str) -> dict | None:
    from reasoner.core.constants import TIMEOUTS
    oembed_url = YOUTUBE_OEMBED_URL
    watch_url = f"{YOUTUBE_WATCH_BASE_URL}{video_id}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUTS.WIDGET_SHORT, follow_redirects=True) as client:
            response = await client.get(
                oembed_url,
                params={"url": watch_url, "format": "json"},
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    "title": data.get("title", ""),
                    "author": data.get("author_name", ""),
                    "thumbnail": data.get("thumbnail_url", ""),
                    "video_id": video_id,
                }
    except Exception as exc:
        logger.debug(f"YouTube oEmbed failed for {video_id}: {exc}")
    return None

async def enrich_problem_with_youtube(state: PipelineState, services: WorkflowServices) -> str:
    video_id = _extract_youtube_id(state.problem)
    if not video_id:
        return state.problem
    meta = await _fetch_youtube_metadata(video_id)
    if not meta:
        return state.problem
    services.log(
        "VETTING",
        f"YouTube video detected: '{meta['title']}' by {meta['author']}",
        state,
    )
    enriched = (
        f"{state.problem}\n\n"
        f"[YouTube Video Metadata: Title: {meta['title']}, Author: {meta['author']}, Video ID: {meta['video_id']}]"
    )
    return enriched

def _enrich_query(query: str, problem: str) -> str:
    problem_lower = problem.lower()
    query_lower = query.lower()
    if "agi" in query_lower and (
        "artificial general intelligence" in problem_lower
        or "singularity" in problem_lower
        or "timeline" in problem_lower
    ):
        if "artificial general intelligence" not in query_lower:
            query += " artificial general intelligence"
    if any(k in query_lower for k in ["agi", "γενική τεχνητή νοημοσύνη", "γενική τν"]):
        if "artificial general intelligence" not in query_lower and "γενική τεχνητή νοημοσύνη" not in query_lower:
            query += " artificial general intelligence"
    if "ανάπτυξη" in problem_lower or "ανάπτυξη" in query_lower:
        if any(
            k in problem_lower
            for k in ["ai", "agent", "software", "programming", "python", "τεχνητή νοημοσύνη", "πράκτορας"]
        ):
            if "παιδ" not in problem_lower and "child" not in problem_lower and "παιδαγωγ" not in problem_lower:
                if "λογισμικού" not in query_lower and "software" not in query_lower and "προγραμματισμός" not in query_lower:
                    query += " λογισμικού προγραμματισμός"
    return query.strip()

async def run_context_vetting_phase(
    state: PipelineState, 
    services: WorkflowServices,
    source_type: str = "general",
    domain: str | None = None
) -> None:
    services.log("VETTING", f"Starting iterative context gathering (source: {source_type})...", state)

    if state.web_discovery_results:
        services.log("VETTING", "Reusing existing web discovery results from research phase.", state)
        await vet_results(state, state.web_discovery_results, services)
        return

    _real_original_problem = state.problem
    enriched_problem = await enrich_problem_with_youtube(state, services)
    if enriched_problem != state.problem:
        state.problem = enriched_problem
        services.log("VETTING", "Enriched problem with YouTube metadata for search.", state)

    _AMBIGUOUS_PRONOUNS_RE = re.compile(r"\b(it|this|that|these|those|they|them|their|he|she|his|her|him)\b", re.IGNORECASE)
    disambiguated_problem = state.problem
    if len(state.problem) < 120 and not _AMBIGUOUS_PRONOUNS_RE.search(state.problem):
        services.log("VETTING", "Query is short and unambiguous — skipping disambiguation.", state)
    else:
        try:
            raw_disam, _ = await services.call_llm(
                role="primary",
                phase_key="disambiguation",
                system_prompt=phases.DISAMBIGUATION_SYSTEM,
                user_prompt=phases.disambiguation_prompt(state.problem, state.task_type.value if state.task_type else None),
                max_tokens=256,
                state=state,
            )
            disam_data = extract_json(raw_disam) or {}
            if disam_data.get("was_ambiguous"):
                disambiguated_problem = disam_data.get("rewritten_query", state.problem)
                services.log("VETTING", f"Disambiguated query: '{disambiguated_problem}' (was ambiguous: {disam_data.get('reasoning', '')})", state)
            else:
                services.log("VETTING", "Query is clear — no disambiguation needed.", state)
        except Exception as exc:
            services.log("VETTING", f"Disambiguation failed ({exc}) — using original problem.", state)

    current_results: list[dict] = []
    seen_urls: set[str] = set()

    try:
        client, _ = await get_discovery_client(source_type=source_type)
    except Exception as e:
        services.log("VETTING", f"Failed to initialize discovery client: {e}", state)
        state.errors.append(f"Vetting: Client init failed: {e}")
        return

    pre_search_problem = state.problem
    state.problem = disambiguated_problem

    raw_plan, _ = await services.call_llm(
        role="primary",
        phase_key="research",
        system_prompt=phases.ITERATIVE_PREPLAN_SYSTEM,
        user_prompt=phases.iterative_preplan_prompt(state),
        state=state,
    )
    services.log("VETTING", "Search pre-plan received from LLM.", state)

    try:
        plan_data = extract_json(raw_plan)
    except ParseError as e:
        services.log("VETTING", f"Failed to parse search pre-plan: {e} — falling back to basic search.", state)
        plan_data = {}

    iterations_raw = plan_data.get("iterations", []) if isinstance(plan_data, dict) else []
    all_queries: list[str] = []
    seen_queries: set[str] = set()
    for it in iterations_raw:
        raw_q = it.get("queries", []) if isinstance(it, dict) else []
        if not isinstance(raw_q, list):
            if isinstance(raw_q, str) and raw_q.strip():
                raw_q = [raw_q.strip()[:TRUNCATION.SNIPPET]]
            else:
                continue
        for q in raw_q:
            if isinstance(q, str) and q.strip():
                q_norm = q.strip().lower()
                if q_norm not in seen_queries:
                    seen_queries.add(q_norm)
                    all_queries.append(q.strip())

    if not all_queries:
        services.log("VETTING", "Pre-plan returned no valid queries — falling back to basic keyword search.", state)
        all_queries = [_extract_search_keywords(disambiguated_problem, max_keywords=5)]
        all_queries = [q for q in all_queries if q and q.strip()]

    services.log("VETTING", f"Executing {len(all_queries)} pre-planned queries in parallel: {all_queries}", state)
    enriched_queries = [_enrich_query(q, disambiguated_problem) for q in all_queries]

    async def _search(q: str):
        try:
            return await client.search(q, num_results=5, source_type=source_type, domain=domain)
        except Exception as exc:
            services.log("VETTING", f"Query failed '{q}': {exc}", state)
            return []

    results_nested = await asyncio.gather(*[_search(q) for q in enriched_queries], return_exceptions=True)
    results_nested = [r for r in results_nested if not isinstance(r, Exception)]

    dropped = 0
    for res_list in results_nested:
        for res in (res_list or []):
            url = res.get("url")
            norm = _normalize_url(url) if url else ""
            if not norm or norm in seen_urls:
                continue
            if not _should_include_result(res):
                dropped += 1
                continue
            seen_urls.add(norm)
            current_results.append(res)

    if dropped:
        services.log("VETTING", f"Dropped {dropped} low-quality results.", state)
    services.log("VETTING", f"Found {len(current_results)} unique results from pre-planned search.", state)

    if len(current_results) < 3:
        services.log("VETTING", f"Only {len(current_results)} results — attempting broad keyword fallback.", state)
        try:
            broad_q = _extract_search_keywords(disambiguated_problem, max_keywords=5)
            if broad_q and broad_q not in all_queries:
                broad_res = await client.search(broad_q, num_results=5, source_type=source_type)
                added = 0
                for res in broad_res:
                    norm = _normalize_url(res.get("url", ""))
                    if norm and norm not in seen_urls and _should_include_result(res):
                        seen_urls.add(norm)
                        current_results.append(res)
                        added += 1
                services.log("VETTING", f"Broad fallback added {added} results (total: {len(current_results)}).", state)
        except Exception as broad_exc:
            services.log("VETTING", f"Broad fallback failed: {broad_exc}", state)

    state.problem = _real_original_problem
    state.web_discovery_results = current_results
    services.log("VETTING", f"Iterative search complete. Total results: {len(current_results)}", state)

    if current_results:
        problem_for_rank = disambiguated_problem or state.problem
        current_results.sort(
            key=lambda r: (
                _bm25_score(problem_for_rank, r) * 0.8
                + r.get("freshness_score", 0.5) * 0.2
            ),
            reverse=True,
        )
        state.web_discovery_results = current_results
        services.log("VETTING", "Applied BM25 + freshness re-ranking to search results.", state)

    await vet_results(state, current_results, services)

async def vet_results(state: PipelineState, results: list[dict], services: WorkflowServices) -> None:
    services.log("VETTING", f"Applying batch CoT vetting to {len(results)} results...", state)
    snippets = []
    for i, r in enumerate(results):
        text = r.get("snippet", "")
        if text:
            snippets.append({"index": i, "url": r.get("url", ""), "text": text})

    if not snippets:
        state.context_quality = "good"
        state.vetted_context = results
        return

    try:
        raw_batch, _ = await services.call_llm(
            role="context_vetting",
            system_prompt=phases.COT_DETECTION_SYSTEM,
            user_prompt=phases.cot_detection_batch_prompt(state, snippets),
            max_tokens=1024,
            state=state,
        )
        batch_data = extract_json(raw_batch)
        flagged_items = batch_data.get("flagged", []) if isinstance(batch_data, dict) else []
        flagged_indices = set()
        for item in flagged_items:
            idx = item.get("index")
            if isinstance(idx, int) and 0 <= idx < len(results):
                results[idx]["vetting_flags"] = item.get("flags", [])
                flagged_indices.add(idx)
        if flagged_indices:
            services.log("VETTING", f"Flagged issues in {len(flagged_indices)}/{len(results)} results.", state)
    except Exception as e:
        services.log("VETTING", f"Batch vetting failed ({e}) — all results pass through clean.", state)

    flagged_count = sum(1 for r in results if r.get("vetting_flags"))
    total = len(results)
    if not results:
        state.context_quality = "missing"
    elif flagged_count == total and total > 0:
        state.context_quality = "contaminated"
    elif flagged_count > total // 2:
        state.context_quality = "partial"
    else:
        state.context_quality = "good"
            
    clean_results = [r for r in results if not r.get("vetting_flags")]
    dropped_count = total - len(clean_results)
    services.log("VETTING", f"Context vetting complete. Removed {dropped_count} flagged sources. Quality: {state.context_quality}", state)
    state.vetted_context = clean_results

async def run_deep_read_phase(state: PipelineState, services: WorkflowServices, max_sources: int = 3, domain: str | None = None) -> None:
    services.log("DEEP_READ", "Starting deep read of critical sources...", state)
    from reasoner.scraper import scrape_urls
    sources_to_scrape = []

    if state.decomposition:
        if isinstance(state.decomposition, dict):
            critical_sources = state.decomposition.get("critical_sources", [])
        else:
            critical_sources = getattr(state.decomposition, "critical_sources", [])
        if critical_sources:
            sources_to_scrape = [s.get("url") for s in critical_sources if isinstance(s, dict) and s.get("url")]

    if not sources_to_scrape and state.vetted_context:
        services.log("DEEP_READ", "No critical sources specified, using top 3 vetted sources.", state)
        sources_to_scrape = [r.get("url") for r in state.vetted_context[:max_sources] if r.get("url")]

    if not sources_to_scrape:
        services.log("DEEP_READ", "No sources available for deep reading. Attempting fallback search...", state)
        try:
            client, _ = await get_discovery_client(source_type="general")
            fallback_results = await client.search(state.problem, num_results=5, source_type="general", domain=domain)
            if fallback_results:
                sources_to_scrape = [r.get("url") for r in fallback_results[:max_sources] if r.get("url")]
                state.web_discovery_results.extend(fallback_results)
                services.log("DEEP_READ", f"Fallback search found {len(sources_to_scrape)} sources.", state)
        except Exception as exc:
            services.log("DEEP_READ", f"Fallback search failed: {exc}", state)
    
    if not sources_to_scrape:
        services.log("DEEP_READ", "No sources found. Extracting general knowledge fallback...", state)
        try:
            raw, _ = await services.call_llm(
                role="primary",
                system_prompt=phases.DEEP_READ_SYSTEM,
                user_prompt=phases.deep_read_prompt(state, url="internal-knowledge", title="General knowledge", content=f"Provide a brief, factual overview of topics relevant to: {state.problem}"),
                phase_key="deep_read",
                max_tokens=1024,
                state=state,
            )
            extraction = extract_json(raw)
            state.vetted_context.append({
                "url": "internal-knowledge",
                "title": "General knowledge",
                "summary": extraction.get("summary", "").strip() or "No specific sources available; using general knowledge.",
                "key_facts": safe_list(extraction.get("key_facts")),
                "relevant_quotes": safe_list(extraction.get("relevant_quotes")),
                "extraction_success": True,
            })
            services.log("DEEP_READ", "General knowledge fallback complete.", state)
        except Exception as exc:
            services.log("DEEP_READ", f"General knowledge fallback failed: {exc}", state)
        return

    services.log("DEEP_READ", f"Deep reading {len(sources_to_scrape)} sources...", state)
    from reasoner.core.settings import settings
    use_llm_extraction = settings.REASONER_DEEP_READ_LLM

    async def _process_scraped(scraped: dict, matching_result: dict) -> None:
        url = scraped.get("url")
        title = scraped.get("title", "Unknown")
        if scraped.get("success"):
            matching_result["deep_content"] = scraped.get("content", "")
            matching_result["deep_title"] = title
            services.log("DEEP_READ", f"Successfully scraped: {title}", state)
            if use_llm_extraction:
                try:
                    sanitized_content = sanitize_for_prompt(scraped.get("content", ""))[0]
                    raw_extraction, _ = await services.call_llm(
                        role="primary",
                        system_prompt=phases.DEEP_READ_SYSTEM,
                        user_prompt=phases.deep_read_prompt(state, url, title, sanitized_content),
                        phase_key="deep_read",
                        max_tokens=1024,
                        state=state,
                    )
                    extraction = extract_json(raw_extraction)
                    matching_result["summary"] = extraction.get("summary", "").strip()
                    matching_result["key_facts"] = safe_list(extraction.get("key_facts"))
                    matching_result["relevant_quotes"] = safe_list(extraction.get("relevant_quotes"))
                    matching_result["extraction_success"] = True
                    services.log("DEEP_READ", f"Extracted summary for: {title}", state)
                except Exception:
                    matching_result["summary"] = scraped.get("content", "")[:TRUNCATION.CONTENT]
                    matching_result["extraction_success"] = False
            else:
                matching_result["summary"] = scraped.get("content", "")[:TRUNCATION.CONTENT]
                matching_result["extraction_success"] = False
        else:
            services.log("DEEP_READ", f"Failed to scrape {url}: {scraped.get('error')}", state)
            if use_llm_extraction:
                try:
                    snippet = sanitize_for_prompt(matching_result.get("snippet", ""))[0]
                    raw_fallback, _ = await services.call_llm(
                        role="primary",
                        phase_key="deep_read",
                        system_prompt=phases.SHALLOW_READ_SYSTEM,
                        user_prompt=phases.shallow_read_prompt(state, url, title, snippet),
                        max_tokens=512,
                        state=state,
                    )
                    fallback = extract_json(raw_fallback)
                    matching_result["summary"] = fallback.get("summary", "").strip()
                    matching_result["key_facts"] = safe_list(fallback.get("key_facts"))
                    matching_result["relevant_quotes"] = safe_list(fallback.get("relevant_quotes"))
                except Exception:
                    matching_result["summary"] = f"(Scrape failed: {scraped.get('error')})"
            else:
                matching_result["summary"] = f"(Scrape failed: {scraped.get('error')})"

    try:
        scraped_results = await scrape_urls(sources_to_scrape)
        url_to_result = {r.get("url"): r for r in state.vetted_context if r.get("url")}
        tasks = []
        for scraped in scraped_results:
            matching_result = url_to_result.get(scraped.get("url"))
            if matching_result:
                tasks.append(_process_scraped(scraped, matching_result))
        semaphore = asyncio.Semaphore(4)
        async def _with_limit(task):
            async with semaphore: return await task
        await asyncio.gather(*[_with_limit(t) for t in tasks], return_exceptions=True)
        for vc in state.vetted_context:
            if not vc.get("extraction_success"): continue
            deep_text = " ".join([vc.get("summary", ""), *vc.get("key_facts", [])])
            vc["deep_relevance_score"] = round(_bm25_score(state.problem, {"title": vc.get("deep_title", vc.get("title", "")), "content": deep_text}), 4)
        state.vetted_context.sort(key=lambda r: r.get("deep_relevance_score", 0.0), reverse=True)
        services.log("DEEP_READ", "Deep read complete.", state)
    except Exception as e:
        services.log("DEEP_READ", f"Deep read failed: {e}", state)
        state.errors.append(f"Deep read failed: {e}")

def validate_evidence_coverage(state: PipelineState, services: WorkflowServices) -> None:
    if not state.decomposition: return
    if isinstance(state.decomposition, dict): assumptions = state.decomposition.get("assumptions", [])
    elif hasattr(state.decomposition, "assumptions"):
        assumptions = [{"text": a.text, "label": a.label.value} for a in (state.decomposition.assumptions or [])]
    else: assumptions = []
    uncertain = [a for a in assumptions if a.get("label") in ("HYPOTHESIS", "UNKNOWN")]
    if not uncertain: return
    summaries = [vc for vc in (state.vetted_context or []) if (vc.get("summary") or "").strip() and vc.get("summary") != "INSUFFICIENT"]
    if not summaries:
        services.log("VALIDATION", f"No extracted evidence for {len(uncertain)} uncertain assumption(s). Proceeding with low-evidence synthesis.", state)
