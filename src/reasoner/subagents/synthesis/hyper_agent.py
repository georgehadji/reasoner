"""
SynthesisHyperAgent — orchestrates 3 parallel analysis subagents + 1 writer.

Phase 1 (parallel):
  - ConsensusMapperSubAgent     → what do all perspectives agree on?
  - ContradictionResolverSubAgent → where do they disagree?
  - EvidenceWeighterSubAgent    → which arguments have strongest evidence?

Phase 2 (sequential):
  - SynthesisWriterSubAgent     → writes final answer using all analyses

All subagent outputs are stored in state.synthesis_subagent_outputs for transparency.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.domain.core_types import FinalSolution, MetaCognitiveAudit
from reasoner.domain.pipeline_state import PipelineState
from reasoner.models import ClaimLabel
from reasoner.sanitization import clean_llm_artifacts_with_report
from reasoner.subagents.models import PhaseSubAgentOutput
from reasoner.subagents.synthesis.consensus_mapper import ConsensusMapperSubAgent
from reasoner.subagents.synthesis.contradiction_resolver import ContradictionResolverSubAgent
from reasoner.subagents.synthesis.evidence_weighter import EvidenceWeighterSubAgent
from reasoner.subagents.synthesis.synthesis_writer import SynthesisWriterSubAgent

logger = logging.getLogger(__name__)


class SynthesisHyperAgent:
    """Orchestrates parallel synthesis subagents and produces FinalSolution."""

    def __init__(self) -> None:
        self._consensus = ConsensusMapperSubAgent()
        self._contradiction = ContradictionResolverSubAgent()
        self._evidence = EvidenceWeighterSubAgent()

    async def execute(self, state: PipelineState, router: ProviderRouter) -> FinalSolution:
        logger.info("[SynthesisHyperAgent] starting Phase 1: 3 parallel analysis subagents")

        # ── Phase 1: parallel analysis ────────────────────────────────
        results = await asyncio.gather(
            self._consensus.execute(state, router),
            self._contradiction.execute(state, router),
            self._evidence.execute(state, router),
            return_exceptions=True,
        )

        def _unwrap(res, name: str) -> PhaseSubAgentOutput:
            if isinstance(res, BaseException):
                logger.warning("[SynthesisHyperAgent] %s failed: %s", name, res)
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

        consensus_out = _unwrap(results[0], "consensus_mapper")
        contradiction_out = _unwrap(results[1], "contradiction_resolver")
        evidence_out = _unwrap(results[2], "evidence_weighter")

        # Store for transparency / resume
        state.synthesis_subagent_outputs = [
            consensus_out.to_dict(),
            contradiction_out.to_dict(),
            evidence_out.to_dict(),
        ]

        logger.info(
            "[SynthesisHyperAgent] Phase 1 complete: consensus_conf=%.2f contradiction_conf=%.2f evidence_conf=%.2f",
            consensus_out.confidence,
            contradiction_out.confidence,
            evidence_out.confidence,
        )

        # ── Phase 2: synthesis writer ─────────────────────────────────
        writer = SynthesisWriterSubAgent(context={
            "consensus": consensus_out,
            "contradictions": contradiction_out,
            "evidence": evidence_out,
        })
        writer_out = await writer.execute(state, router)
        state.synthesis_subagent_outputs.append(writer_out.to_dict())

        logger.info(
            "[SynthesisHyperAgent] writer complete: confidence=%.2f model=%s",
            writer_out.confidence,
            writer_out.model,
        )

        # ── Build FinalSolution ───────────────────────────────────────
        result = writer_out.result

        meta_audit_raw = result.get("meta_audit", {})
        meta_audit = MetaCognitiveAudit(
            most_dangerous_assumption=meta_audit_raw.get("most_dangerous_assumption", ""),
            dominant_bias=meta_audit_raw.get("dominant_bias", ""),
            remaining_uncertainty=meta_audit_raw.get("remaining_uncertainty", ""),
            assumption_failure_impact=meta_audit_raw.get("assumption_failure_impact", ""),
            non_obvious_insight=meta_audit_raw.get("non_obvious_insight", ""),
        )

        raw_labels = result.get("claim_labels", {})
        clean_labels = {}
        for k, v in raw_labels.items():
            try:
                clean_labels[k] = ClaimLabel(v)
            except ValueError:
                clean_labels[k] = ClaimLabel.UNKNOWN

        # Egress Layer A scrub -- mirrors application/flows/synthesis_phase.py's
        # legacy path so both routes to FinalSolution get the same hygiene.
        core_solution, core_solution_report = clean_llm_artifacts_with_report(
            result.get("core_solution", "")
        )

        def _scrub_strings(items: list) -> tuple[list[str], int]:
            cleaned: list[str] = []
            changed = 0
            for item in items:
                text, report = clean_llm_artifacts_with_report(str(item))
                cleaned.append(text)
                if report is not None:
                    changed += report.suspicious_total
            return cleaned, changed

        def _scrub_blueprint_steps(items: list) -> tuple[list, int]:
            changed = 0
            cleaned: list = []
            for step in items:
                if not isinstance(step, dict):
                    cleaned.append(step)
                    continue
                new_step = dict(step)
                for key in ("step", "action", "time_horizon", "go_criteria", "fallback"):
                    if key in new_step and new_step[key]:
                        text, report = clean_llm_artifacts_with_report(str(new_step[key]))
                        new_step[key] = text
                        if report is not None:
                            changed += report.suspicious_total
                cleaned.append(new_step)
            return cleaned, changed

        critical_insights, insights_changed = _scrub_strings(result.get("critical_insights", []))
        open_questions, questions_changed = _scrub_strings(result.get("open_questions", []))
        action_blueprint, blueprint_changed = _scrub_blueprint_steps(result.get("action_blueprint", []))

        state.meta.provenance_report = {
            "core_solution": core_solution_report.to_dict() if core_solution_report else None,
            "critical_insights_removed": insights_changed,
            "action_blueprint_removed": blueprint_changed,
            "open_questions_removed": questions_changed,
        }

        return FinalSolution(
            core_solution=core_solution,
            critical_insights=critical_insights,
            action_blueprint=action_blueprint,
            open_questions=open_questions,
            claim_labels=clean_labels,
            meta_audit=meta_audit,
            sources=result.get("sources", []),
            layout_hints=result.get("layout_hints", {}),
            generator_attribution={},
            critic_weighting={},
        )
