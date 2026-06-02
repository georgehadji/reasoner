"""Research phase logic."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from reasoner.core.constants import TRUNCATION
from reasoner.infrastructure.search.discovery import get_discovery_client
from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import ParseError, extract_json
import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices

logger = logging.getLogger(__name__)

async def run_research_web_search_phase(
    state: PipelineState, 
    services: WorkflowServices,
    domain: str | None = None
) -> None:
    services.log("RESEARCH", "Starting deep iterative research...", state)
    max_iterations = 3
    current_knowledge = []
    
    try:
        client, _ = await get_discovery_client()
    except Exception as e:
        services.log("RESEARCH", f"Failed to initialize discovery client: {e}", state)
        state.errors.append(f"Research: Client init failed: {e}")
        return

    for i in range(1, max_iterations + 1):
        services.log("RESEARCH", f"Iteration {i}/{max_iterations}: Planning searches...", state)
        raw, _ = await services.call_llm(
            role="primary",
            phase_key="research",
            system_prompt=phases.DEEP_RESEARCH_SYSTEM,
            user_prompt=phases.deep_research_prompt(state, current_knowledge, i, max_iterations),
            state=state
        )
        try:
            data = extract_json(raw)
        except ParseError as e:
            services.log("RESEARCH", f"Failed to parse research plan: {e}", state)
            break
            
        action = data.get("action")
        reasoning = data.get("reasoning", "")
        services.log("RESEARCH", f"Action: {action}. Reason: {reasoning}", state)
        
        if action == "done" or i == max_iterations:
            break
            
        _raw_q = data.get("queries", [])
        if isinstance(_raw_q, list):
            queries = _raw_q[:TRUNCATION.KEY_INSIGHTS]
        elif isinstance(_raw_q, str) and _raw_q.strip():
            queries = [_raw_q.strip()]
        else:
            queries = []
        if not queries:
            break
            
        services.log("RESEARCH", f"Executing queries: {queries}", state)
        
        # Enforce domain if provided
        async def _search(q):
            try:
                return await client.search(q, num_results=3, domain=domain)
            except Exception as exc:
                services.log("RESEARCH", f"Query failed '{q}': {exc}", state)
                return []
                
        results_nested = await asyncio.gather(*[_search(q) for q in queries], return_exceptions=True)
        results_nested = [r for r in results_nested if not isinstance(r, Exception)]
        
        # Flatten and deduplicate
        new_results = []
        seen_urls = {res.get("url") for res in current_knowledge}
        
        for res_list in results_nested:
            for res in (res_list or []):
                url = res.get("url")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    new_results.append(res)
        
        services.log("RESEARCH", f"Found {len(new_results)} new unique sources.", state)
        current_knowledge.extend(new_results)
        
    state.web_discovery_results = current_knowledge
    services.log("RESEARCH", f"Deep research complete. Total sources: {len(state.web_discovery_results)}", state)
