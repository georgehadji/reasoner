"""
CritiqueHyperAgent — orchestrates 4 parallel critique subagents and synthesizes scores.

Phase 1 (parallel):
  - LogicCritiqueSubAgent      → formal logical fallacies
  - EvidenceCritiqueSubAgent   → quality/reliability of sources
  - BiasCritiqueSubAgent       → cognitive biases, framing effects
  - CounterfactualSubAgent     → "what if the opposite were true?"

Phase 2 (rule-based synthesis):
  - Aggregates findings into CritiqueScore objects per candidate
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.models import CritiqueScore, PipelineState, PerspectiveType
from reasoner.subagents.models import PhaseSubAgentOutput
from reasoner.subagents.critique.logic_critique import LogicCritiqueSubAgent
from reasoner.subagents.critique.evidence_critique import EvidenceCritiqueSubAgent
from reasoner.subagents.critique.bias_critique import BiasCritiqueSubAgent
from reasoner.subagents.critique.counterfactual import CounterfactualSubAgent

logger = logging.getLogger(__name__)


class CritiqueHyperAgent:
    """Orchestrates parallel critique subagents and produces CritiqueScore list."""

    def __init__(self) -> None:
        self._logic = LogicCritiqueSubAgent()
        self._evidence = EvidenceCritiqueSubAgent()
        self._bias = BiasCritiqueSubAgent()
        self._counterfactual = CounterfactualSubAgent()

    async def execute(self, state: PipelineState, router: ProviderRouter) -> list[CritiqueScore]:
        logger.info("[CritiqueHyperAgent] starting Phase 1: 4 parallel critique subagents")

        # ── Phase 1: parallel critique ────────────────────────────────
        results = await asyncio.gather(
            self._logic.execute(state, router),
            self._evidence.execute(state, router),
            self._bias.execute(state, router),
            self._counterfactual.execute(state, router),
            return_exceptions=True,
        )

        def _unwrap(res, name: str) -> PhaseSubAgentOutput:
            if isinstance(res, BaseException):
                logger.warning("[CritiqueHyperAgent] %s failed: %s", name, res)
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

        logic_out = _unwrap(results[0], "logic_critique")
        evidence_out = _unwrap(results[1], "evidence_critique")
        bias_out = _unwrap(results[2], "bias_critique")
        counterfactual_out = _unwrap(results[3], "counterfactual")

        # Store for transparency
        state.critique_subagent_outputs = [
            logic_out.to_dict(),
            evidence_out.to_dict(),
            bias_out.to_dict(),
            counterfactual_out.to_dict(),
        ]

        logger.info(
            "[CritiqueHyperAgent] Phase 1 complete: logic_conf=%.2f evidence_conf=%.2f bias_conf=%.2f counterfactual_conf=%.2f",
            logic_out.confidence,
            evidence_out.confidence,
            bias_out.confidence,
            counterfactual_out.confidence,
        )

        # ── Phase 2: synthesize scores ────────────────────────────────
        scores = self._synthesize_scores(
            state,
            logic_out,
            evidence_out,
            bias_out,
            counterfactual_out,
        )
        return scores

    def _synthesize_scores(
        self,
        state: PipelineState,
        logic_out: PhaseSubAgentOutput,
        evidence_out: PhaseSubAgentOutput,
        bias_out: PhaseSubAgentOutput,
        counterfactual_out: PhaseSubAgentOutput,
    ) -> list[CritiqueScore]:
        """Aggregate subagent findings into per-candidate CritiqueScore objects."""
        scores: list[CritiqueScore] = []

        # Build lookup tables by perspective name
        logic_by_perspective = self._index_by_perspective(logic_out.result.get("logic_issues", []), "perspective")
        evidence_by_perspective = self._index_by_perspective(evidence_out.result.get("evidence_assessment", []), "perspective")
        bias_by_perspective = self._index_by_perspective(bias_out.result.get("bias_findings", []), "perspective")
        counter_by_perspective = self._index_by_perspective(counterfactual_out.result.get("counterfactuals", []), "perspective")

        for candidate in state.candidates:
            pname = candidate.perspective.value

            # Logic scoring: 10 minus average severity of issues (or 10 if none)
            logic_issues = logic_by_perspective.get(pname, [])
            logic_score = 10.0
            if logic_issues:
                avg_severity = sum(i.get("severity", 5) for i in logic_issues) / len(logic_issues)
                logic_score = max(0.0, 10.0 - avg_severity)

            # Evidence scoring: average of source_quality and sufficiency
            ev = evidence_by_perspective.get(pname, {})
            if isinstance(ev, list) and ev:
                ev = ev[0]
            evidence_score = (ev.get("source_quality", 5) + ev.get("sufficiency", 5)) / 2.0 if isinstance(ev, dict) else 5.0

            # Feasibility score from counterfactual robustness
            cf = counter_by_perspective.get(pname, {})
            if isinstance(cf, list) and cf:
                cf = cf[0]
            feasibility_score = cf.get("robustness", 5) if isinstance(cf, dict) else 5.0

            # Bias penalty: subtract severity from a base score
            bias_items = bias_by_perspective.get(pname, [])
            bias_penalty = sum(b.get("severity", 0) for b in bias_items) / max(len(bias_items), 1) if bias_items else 0
            bias_score = max(0.0, 10.0 - bias_penalty)

            # Steel-man: boost score if counterfactual offers a strong alternative
            steel_man_score = 0.0
            if isinstance(cf, dict) and cf.get("alternative_path"):
                steel_man_score = 2.0

            scores.append(CritiqueScore(
                perspective=candidate.perspective,
                logical_consistency=round(logic_score, 1),
                evidence_support=round(evidence_score, 1),
                failure_resilience=round(feasibility_score, 1),
                feasibility=round(feasibility_score, 1),
                bias_flags=[b.get("bias_type", "unknown") for b in bias_items],
                steel_man=round(steel_man_score, 1),
            ))

        return scores

    @staticmethod
    def _index_by_perspective(items: list[dict], key: str) -> dict[str, Any]:
        """Index a list of dicts by perspective name."""
        result: dict[str, Any] = {}
        for item in items:
            pname = item.get(key)
            if pname:
                if pname not in result:
                    result[pname] = []
                result[pname].append(item)
        return result
