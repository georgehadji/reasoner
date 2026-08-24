"""Debate reasoning workflow strategy."""

from __future__ import annotations

import asyncio

import reasoner.phases as phases
from reasoner.application.flows.base import PhaseStep, WorkflowServices, WorkflowStrategy
from reasoner.application.flows.debate_phases import (
    run_debate_cross_examine_phase,
    run_debate_judge_phase,
    run_debate_opening_phase,
    run_debate_rebuttal_phase,
)
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.application.services.serializers import _ser_2, _ser_3, _ser_4, _ser_5
from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.search.discovery import get_search_client_for_method
from reasoner.parsing import extract_json


async def run_debate_evidence_search_phase(state: PipelineState, services: WorkflowServices) -> None:
    """Search for evidence to ground debate opening statements."""
    services.log("DEBATE", "Searching for evidence to support debate positions...", state)
    try:
        from reasoner.presets import get_preset_price_tier
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
            services.log("DEBATE", f"Found {len(flattened)} relevant sources.", state)
    except Exception as e:
        services.log("DEBATE", f"Evidence search failed: {e}", state)


class DebateFlow(WorkflowStrategy):
    """
    Debate workflow:
    1. Opening Statements
    2. Rebuttals
    3. Cross-Examination
    4. Judging
    5. Synthesis
    """

    def get_phases(self, state: PipelineState) -> list[PhaseStep]:
        return [
            PhaseStep(1.5, "Evidence Search", run_debate_evidence_search_phase, _ser_2),
            PhaseStep(2, "Opening Statements", run_debate_opening_phase, _ser_2),
            PhaseStep(3, "Rebuttals", run_debate_rebuttal_phase, _ser_3),
            PhaseStep(4, "Cross-Examination", run_debate_cross_examine_phase, _ser_4),
            PhaseStep(4.5, "Judging", run_debate_judge_phase, _ser_3),
            PhaseStep(5, "Synthesis", run_synthesis_phase, _ser_5),
        ]

    async def execute(
        self,
        state: PipelineState,
        services: WorkflowServices,
    ) -> PipelineState:
        for step in self.get_phases(state):
            success = await services.run_phase(step, state)
            if not success and step.critical:
                break
        return state
