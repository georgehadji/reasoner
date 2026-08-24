"""
DecompositionHyperAgent — orchestrates 3 parallel decomposition subagents.

Phase 1 (parallel):
  - StructuralDecomposerSubAgent → what/why/how hierarchy
  - StakeholderMapperSubAgent    → relevant perspectives
  - CoverageValidatorSubAgent    → completeness check

Phase 2 (synthesis):
  - Merges findings into the standard Decomposition format
"""
from __future__ import annotations

import asyncio
import logging

from reasoner.domain.core_types import (
    Assumption,
    Decomposition,
    SubProblem,
)
from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.models import ClaimLabel
from reasoner.subagents.decomposition.coverage_validator import CoverageValidatorSubAgent
from reasoner.subagents.decomposition.stakeholder_mapper import StakeholderMapperSubAgent
from reasoner.subagents.decomposition.structural_decomposer import StructuralDecomposerSubAgent
from reasoner.subagents.models import PhaseSubAgentOutput

logger = logging.getLogger(__name__)


class DecompositionHyperAgent:
    """Orchestrates parallel decomposition subagents."""

    def __init__(self) -> None:
        self._structural = StructuralDecomposerSubAgent()
        self._stakeholder = StakeholderMapperSubAgent()
        self._coverage = CoverageValidatorSubAgent()

    async def execute(self, state: PipelineState, router: ProviderRouter) -> Decomposition:
        logger.info("[DecompositionHyperAgent] starting 3 parallel decomposition subagents")

        results = await asyncio.gather(
            self._structural.execute(state, router),
            self._stakeholder.execute(state, router),
            self._coverage.execute(state, router),
            return_exceptions=True,
        )

        def _unwrap(res, name: str) -> PhaseSubAgentOutput:
            if isinstance(res, BaseException):
                logger.warning("[DecompositionHyperAgent] %s failed: %s", name, res)
                return PhaseSubAgentOutput(
                    agent_name=name,
                    result={},
                    confidence=0.0,
                    reasoning="",
                    tokens_in=0,
                    tokens_out=0,
                    model="unknown",
                    duration_ms=0.0,
                    error=str(res),
                )
            return res

        structural_out = _unwrap(results[0], "structural_decomposer")
        stakeholder_out = _unwrap(results[1], "stakeholder_mapper")
        coverage_out = _unwrap(results[2], "coverage_validator")

        state.decomposition_subagent_outputs = [
            structural_out.to_dict(),
            stakeholder_out.to_dict(),
            coverage_out.to_dict(),
        ]

        # ── Synthesize Decomposition ──────────────────────────────────
        decomposition = structural_out.result.get("decomposition", {})
        stakeholders = stakeholder_out.result.get("stakeholders", [])
        coverage = coverage_out.result.get("coverage_assessment", {})

        # Build sub-problems from what/why/how
        sub_problems: list[SubProblem] = []
        what_items = decomposition.get("what", [])
        how_items = decomposition.get("how", [])
        for i, (what, how) in enumerate(zip(what_items, how_items, strict=False)):
            sub_problems.append(SubProblem(
                id=f"SP{i+1}",
                description=f"{what}. Approach: {how}",
                inputs=[],
                outputs=[],
                constraints=[],
            ))

        # Build assumptions from stakeholders and coverage gaps
        assumptions: list[Assumption] = []
        for s in stakeholders:
            for concern in s.get("concerns", []):
                assumptions.append(Assumption(
                    text=f"{s['role']} cares about: {concern}",
                    label=ClaimLabel.HYPOTHESIS,
                    rationale=f"From stakeholder mapping ({stakeholder_out.confidence:.2f} confidence)",
                ))

        for gap in coverage.get("missing_aspects", []):
            assumptions.append(Assumption(
                text=f"Coverage gap: {gap}",
                label=ClaimLabel.UNKNOWN,
                rationale=f"From coverage validation ({coverage_out.confidence:.2f} confidence)",
            ))

        failure_modes = []
        if not coverage.get("is_complete", True):
            failure_modes.append(f"Incomplete coverage (score: {coverage.get('coverage_score', 0)})")
        for overlap in coverage.get("overlap", []):
            failure_modes.append(f"Redundant overlap: {overlap}")

        return Decomposition(
            sub_problems=sub_problems,
            assumptions=assumptions,
            failure_modes=failure_modes,
            raw_response="",
            critical_sources=[],
        )
