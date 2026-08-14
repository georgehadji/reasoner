"""
SearchHyperAgent — orchestrates 3 parallel search subagents.

Phase 1 (parallel):
  - QueryGeneratorSubAgent     → diverse search queries
  - SourceEvaluatorSubAgent    → credibility/relevance scoring
  - GapIdentifierSubAgent      → missing evidence detection

Phase 2 (synthesis):
  - Returns enriched search context for the pipeline
"""
from __future__ import annotations

from typing import Any

import asyncio
import logging

from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.domain.pipeline_state import PipelineState
from reasoner.subagents.models import PhaseSubAgentOutput
from reasoner.subagents.search.query_generator import QueryGeneratorSubAgent
from reasoner.subagents.search.source_evaluator import SourceEvaluatorSubAgent
from reasoner.subagents.search.gap_identifier import GapIdentifierSubAgent

logger = logging.getLogger(__name__)


class SearchHyperAgent:
    """Orchestrates parallel search subagents."""

    def __init__(self) -> None:
        self._queries = QueryGeneratorSubAgent()
        self._sources = SourceEvaluatorSubAgent()
        self._gaps = GapIdentifierSubAgent()

    async def execute(self, state: PipelineState, router: ProviderRouter) -> dict[str, Any]:
        logger.info("[SearchHyperAgent] starting 3 parallel search subagents")

        results = await asyncio.gather(
            self._queries.execute(state, router),
            self._sources.execute(state, router),
            self._gaps.execute(state, router),
            return_exceptions=True,
        )

        def _unwrap(res, name: str) -> PhaseSubAgentOutput:
            if isinstance(res, BaseException):
                logger.warning("[SearchHyperAgent] %s failed: %s", name, res)
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

        queries_out = _unwrap(results[0], "query_generator")
        sources_out = _unwrap(results[1], "source_evaluator")
        gaps_out = _unwrap(results[2], "gap_identifier")

        state.search_subagent_outputs = [
            queries_out.to_dict(),
            sources_out.to_dict(),
            gaps_out.to_dict(),
        ]

        logger.info(
            "[SearchHyperAgent] complete: queries_conf=%.2f sources_conf=%.2f gaps_conf=%.2f",
            queries_out.confidence,
            sources_out.confidence,
            gaps_out.confidence,
        )

        return {
            "queries": queries_out.result.get("queries", []),
            "source_evaluations": sources_out.result.get("source_evaluations", []),
            "gaps": gaps_out.result.get("gaps", []),
        }
