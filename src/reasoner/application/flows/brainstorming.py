"""Brainstorming reasoning workflow strategy."""

from __future__ import annotations

import asyncio
from typing import Any

import reasoner.phases as phases
from reasoner.application.flows.base import PhaseStep, WorkflowServices, WorkflowStrategy
from reasoner.application.flows.brainstorming_phases import (
    run_brainstorm_cluster_phase,
    run_brainstorm_develop_phase,
    run_brainstorm_generate_phase,
    run_brainstorm_synthesis_phase,
)
from reasoner.application.services.serializers import _ser_2, _ser_3, _ser_4, _ser_synthesis
from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.search.discovery import get_search_client_for_method
from reasoner.parsing import extract_json
from reasoner.presets import get_preset_price_tier


async def run_brainstorm_prior_art_search_phase(state: PipelineState, services: WorkflowServices) -> None:
    """Search for existing solutions and prior art before ideation."""
    services.log("BRAINSTORM", "Searching for existing solutions and prior art...", state)
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
            services.log("BRAINSTORM", f"Found {len(flattened)} existing solutions/prior art.", state)
    except Exception as e:
        services.log("BRAINSTORM", f"Prior art search failed: {e}", state)

class BrainstormingFlow(WorkflowStrategy):
    """
    Brainstorming workflow:
    1. VS Idea Generation
    2. Cluster & Score
    3. Deep Development
    4. Synthesis
    """

    def get_phases(self, state: PipelineState) -> list[PhaseStep]:
        return [
            PhaseStep(1.5, "Prior Art Search", run_brainstorm_prior_art_search_phase, _ser_2),
            PhaseStep(2, "VS Idea Generation", run_brainstorm_generate_phase, _ser_2),
            PhaseStep(3, "Cluster & Score", run_brainstorm_cluster_phase, _ser_3, critical=True),
            PhaseStep(4, "Deep Development", run_brainstorm_develop_phase, _ser_4),
            PhaseStep(5, "Synthesis", run_brainstorm_synthesis_phase, _ser_synthesis),
        ]

    async def execute(
        self,
        state: PipelineState,
        services: WorkflowServices,
        config: Any = None
    ) -> PipelineState:
        for step in self.get_phases(state):
            success = await services.run_phase(step, state)
            if not success and step.critical:
                break

        return state
