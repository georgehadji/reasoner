"""
EnhancementHyperAgent — orchestrates 3 parallel enhancement subagents.

Phase 1 (parallel):
  - AmbiguityDetectorSubAgent    → what is unclear?
  - ContextEnricherSubAgent      → what context is missing?
  - ScopeNarrowerSubAgent        → is the problem too broad?

Phase 2 (rule-based synthesis):
  - Rewrites the prompt using subagent findings
"""
from __future__ import annotations

import asyncio
import logging

from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.domain.pipeline_state import PipelineState
from reasoner.subagents.models import PhaseSubAgentOutput
from reasoner.subagents.enhancement.ambiguity_detector import AmbiguityDetectorSubAgent
from reasoner.subagents.enhancement.context_enricher import ContextEnricherSubAgent
from reasoner.subagents.enhancement.scope_narrower import ScopeNarrowerSubAgent

logger = logging.getLogger(__name__)


class EnhancementHyperAgent:
    """Orchestrates parallel prompt enhancement subagents."""

    def __init__(self) -> None:
        self._ambiguity = AmbiguityDetectorSubAgent()
        self._context = ContextEnricherSubAgent()
        self._scope = ScopeNarrowerSubAgent()

    async def execute(self, state: PipelineState, router: ProviderRouter) -> str:
        logger.info("[EnhancementHyperAgent] starting 3 parallel enhancement subagents")

        results = await asyncio.gather(
            self._ambiguity.execute(state, router),
            self._context.execute(state, router),
            self._scope.execute(state, router),
            return_exceptions=True,
        )

        def _unwrap(res, name: str) -> PhaseSubAgentOutput:
            if isinstance(res, BaseException):
                logger.warning("[EnhancementHyperAgent] %s failed: %s", name, res)
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

        ambiguity_out = _unwrap(results[0], "ambiguity_detector")
        context_out = _unwrap(results[1], "context_enricher")
        scope_out = _unwrap(results[2], "scope_narrower")

        state.enhancement_subagent_outputs = [
            ambiguity_out.to_dict(),
            context_out.to_dict(),
            scope_out.to_dict(),
        ]

        # If scope narrower has a strong recommendation, use it
        scope_assessment = scope_out.result.get("scope_assessment", {})
        if scope_assessment.get("recommended_scope") and scope_out.confidence >= 0.7:
            enhanced = scope_assessment["recommended_scope"]
            logger.info("[EnhancementHyperAgent] using scope-narrower rewrite")
            return enhanced

        # Otherwise, build an enriched version by appending context
        enhancements = []
        ambiguities = ambiguity_out.result.get("ambiguities", [])
        if ambiguities and ambiguity_out.confidence >= 0.6:
            questions = [a.get("clarification_question", "") for a in ambiguities]
            enhancements.append("Clarifications needed: " + "; ".join(q for q in questions if q))

        missing = context_out.result.get("missing_context", [])
        if missing and context_out.confidence >= 0.6:
            contexts = [m.get("description", "") for m in missing]
            enhancements.append("Assumed context: " + "; ".join(c for c in contexts if c))

        if enhancements:
            enhanced = f"{state.problem}\n\n[Enhancements]\n" + "\n".join(f"- {e}" for e in enhancements)
            logger.info("[EnhancementHyperAgent] produced enriched prompt")
            return enhanced

        logger.info("[EnhancementHyperAgent] no meaningful enhancements found, returning original")
        return state.problem
