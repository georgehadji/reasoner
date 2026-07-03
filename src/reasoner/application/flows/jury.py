"""Jury reasoning workflow strategy."""

from __future__ import annotations

import asyncio
from typing import List
from reasoner.domain.pipeline_state import PipelineState
from reasoner.application.flows.base import WorkflowStrategy, WorkflowServices, PhaseStep
from reasoner.application.flows.jury_phases import (
    run_jury_generate_phase,
    run_jury_critique_phase,
    run_jury_verify_and_meta_eval_phase,
    run_jury_weighted_ranking_phase
)
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.application.services.serializers import _ser_2, _ser_3, _ser_4, _ser_5
from reasoner.infrastructure.search.discovery import get_search_client_for_method
import reasoner.phases as phases
from reasoner.parsing import extract_json
from reasoner.presets import get_preset_price_tier

async def run_jury_evidence_search_phase(state: PipelineState, services: WorkflowServices) -> None:
    """Search for evidence to ground jury generation."""
    services.log("JURY", "Searching for relevant evidence...", state)
    try:
        tier = get_preset_price_tier(state.preset_name) or "budget"
        client, _ = await get_search_client_for_method("research", tier, source_type="general")
        raw_plan, _ = await services.call_llm(
            role="primary",
            system_prompt=phases.ARTICLE_RETRIEVAL_PLAN_SYSTEM,
            user_prompt=phases.article_retrieval_plan_prompt(state),
            state=state
        )
        plan = extract_json(raw_plan)
        queries = plan.get("queries", [])[:3]
        async def _search(q):
            try: return await client.search(q, num_results=5)
            except Exception: return []
        results = await asyncio.gather(*[_search(q) for q in queries], return_exceptions=True)
        flattened = []
        seen = set()
        for r_list in results:
            if isinstance(r_list, list):
                for r in r_list:
                    url = r.get("url", "")
                    if url not in seen:
                        seen.add(url)
                        flattened.append(r)
        state.web_discovery_results = flattened[:10]
        if flattened:
            services.log("JURY", f"Found {len(flattened)} relevant sources.", state)
    except Exception as e:
        services.log("JURY", f"Evidence search failed: {e}", state)

class JuryFlow(WorkflowStrategy):
    """Jury reasoning workflow."""

    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(1.5, "Evidence Search", run_jury_evidence_search_phase, _ser_2),
            PhaseStep(2, "Generation Pool", run_jury_generate_phase, _ser_2),
            PhaseStep(3, "Critic Pool", run_jury_critique_phase, _ser_3, critical=True),
            PhaseStep(4, "Verification & Meta", run_jury_verify_and_meta_eval_phase, _ser_4),
            PhaseStep(4.5, "Weighted Ranking", run_jury_weighted_ranking_phase, _ser_4),
            PhaseStep(5, "Synthesis", run_synthesis_phase, _ser_5)
        ]

    async def execute(
        self, 
        state: PipelineState, 
        services: WorkflowServices,
    ) -> PipelineState:
        for step in self.get_phases(state):
            await services.run_phase(step, state)
        return state
