"""Research reasoning workflow strategy."""

from __future__ import annotations

from reasoner.application.flows.base import PhaseStep, WorkflowStrategy
from reasoner.application.flows.research_phases import run_research_web_search_phase
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.application.services.serializers import _ser_2, _ser_synthesis
from reasoner.domain.pipeline_state import PipelineState


class ResearchFlow(WorkflowStrategy):
    """
    Research workflow:
    1. Deep Iterative Web Search
    2. Synthesis

    There is no critique step: run_critique_phase scores state.candidates, and
    research produces none, so it always skipped and showed an empty phase.
    """

    def get_phases(self, state: PipelineState) -> list[PhaseStep]:
        return [
            PhaseStep(2, "Deep Research", run_research_web_search_phase, _ser_2, critical=True),
            PhaseStep(5, "Synthesis", run_synthesis_phase, _ser_synthesis),
        ]
