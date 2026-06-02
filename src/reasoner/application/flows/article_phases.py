"""Article writing pipeline phase logic."""

from __future__ import annotations

import json
import logging
from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json
import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices
from reasoner.core.constants import ARTICLE_MIN_SOURCE_COUNT, ARTICLE_MIN_CLAIM_SUPPORT_RATIO, TRUNCATION

logger = logging.getLogger(__name__)

async def run_article_retrieve_sources_phase(state: PipelineState, services: WorkflowServices, domain: str | None = None) -> None:
    services.log("WRITING", "Retrieving targeted sources for article...", state)
    try:
        from reasoner.infrastructure.search.discovery import get_discovery_client
        client, _ = await get_discovery_client(source_type="general")
        
        raw_plan, _ = await services.call_llm(
            role="primary",
            system_prompt=phases.ARTICLE_RETRIEVAL_PLAN_SYSTEM,
            user_prompt=phases.article_retrieval_plan_prompt(state),
            state=state
        )
        plan = extract_json(raw_plan)
        queries = plan.get("queries", [])[:5]
        
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
    raw, _ = await services.call_llm(
        role="writing_factcheck",
        system_prompt=phases.ARTICLE_VERIFY_SYSTEM,
        user_prompt=phases.article_verify_prompt(state),
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
