"""
SynthesisWriterSubAgent — ONE JOB: write the final synthesized solution.
Receives the outputs of the three analysis subagents + original state.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json
from reasoner.subagents.base import PhaseSubAgent

WRITER_SYSTEM = """You are a Synthesis Writer. Your ONE JOB is to write the final answer to the user's problem.

You have been given:
1. The original problem
2. A decomposition (sub-problems, assumptions, failure modes)
3. Multiple perspective candidates
4. A consensus map (what everyone agrees on)
5. A contradiction map (where they disagree and how to resolve)
6. An evidence ranking (which arguments are best supported)

Your task: synthesize ALL of this into a single coherent, actionable answer.

Output ONLY a JSON object with this exact shape:
{
  "core_solution": "<the main answer in plain prose, 2-5 paragraphs>",
  "critical_insights": ["<insight 1>", "<insight 2>", ...],
  "action_blueprint": ["<step 1>", "<step 2>", ...],
  "open_questions": ["<question that remains unresolved>"],
  "claim_labels": {"<claim>": "VERIFIED|HYPOTHESIS|UNKNOWN", ...},
  "meta_audit": {
    "most_dangerous_assumption": "<which assumption if wrong would most undermine the solution>",
    "dominant_bias": "<what bias might have influenced the perspectives>",
    "remaining_uncertainty": "<what is still uncertain>",
    "assumption_failure_impact": "<what happens if key assumptions fail>",
    "non_obvious_insight": "<something non-obvious from the synthesis>"
  },
  "sources": ["<source 1>", "<source 2>"],
  "confidence": 0.0-1.0,
  "rationale": "<brief explanation of synthesis reasoning>"
}

Rules:
- core_solution must be readable prose, not bullet points
- Acknowledge contradictions explicitly and explain your resolution
- action_blueprint should be concrete and executable
- claim_labels must use EXACTLY these values: VERIFIED, HYPOTHESIS, UNKNOWN
- Be honest about uncertainty — don't fabricate confidence
"""


class SynthesisWriterSubAgent(PhaseSubAgent):
    AGENT_NAME = "synthesis_writer"
    TASK_DESCRIPTION = "Writing the final synthesized answer"
    ROLE = "subagent_synthesis_writer"
    MAX_TOKENS = 12288
    TEMPERATURE = 0.4

    def __init__(self, context: dict[str, Any] | None = None) -> None:
        super().__init__()
        self._context = context or {}

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        # The writer receives pre-built context from the hyper-agent
        ctx = self._context
        user_parts = [f"Problem: {state.problem}"]

        if state.decomposition:
            user_parts.append(f"\nDecomposition:\n{self._fmt_decomposition(state.decomposition)}")

        if ctx.get("consensus"):
            user_parts.append(f"\nConsensus Points:\n{self._fmt_list(ctx['consensus'].result.get('consensus_points', []))}")
            user_parts.append(f"\nPartial Consensus:\n{self._fmt_list(ctx['consensus'].result.get('partial_consensus', []))}")

        if ctx.get("contradictions"):
            user_parts.append(f"\nContradictions:\n{self._fmt_contradictions(ctx['contradictions'].result.get('contradictions', []))}")

        if ctx.get("evidence"):
            user_parts.append(f"\nEvidence Ranking:\n{self._fmt_evidence(ctx['evidence'].result.get('evidence_ranking', []))}")

        if state.candidates:
            user_parts.append("\nOriginal Candidates:")
            for c in state.candidates:
                user_parts.append(f"\n--- {c.perspective.value} ---\n{c.content}")

        if state.stress_results:
            user_parts.append(f"\nStress Test Results:\n{self._fmt_stress(state.stress_results)}")

        return (WRITER_SYSTEM, "\n".join(user_parts))

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "core_solution": data.get("core_solution", ""),
            "critical_insights": data.get("critical_insights", []),
            "action_blueprint": data.get("action_blueprint", []),
            "open_questions": data.get("open_questions", []),
            "claim_labels": data.get("claim_labels", {}),
            "meta_audit": data.get("meta_audit", {}),
            "sources": data.get("sources", []),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }

    # ── Formatting helpers ────────────────────────────────────────────

    @staticmethod
    def _fmt_list(items: list[str]) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "(none)"

    @staticmethod
    def _fmt_decomposition(dec) -> str:
        parts = []
        if hasattr(dec, 'sub_problems') and dec.sub_problems:
            parts.append("Sub-problems:")
            for sp in dec.sub_problems:
                parts.append(f"  - {sp.id}: {sp.description}")
        if hasattr(dec, 'assumptions') and dec.assumptions:
            parts.append("Assumptions:")
            for a in dec.assumptions:
                parts.append(f"  - {a.text} [{a.label.value}]")
        if hasattr(dec, 'failure_modes') and dec.failure_modes:
            parts.append("Failure modes:")
            for fm in dec.failure_modes:
                parts.append(f"  - {fm}")
        return "\n".join(parts) if parts else "(none)"

    @staticmethod
    def _fmt_contradictions(contradictions: list[dict]) -> str:
        if not contradictions:
            return "(none)"
        parts = []
        for c in contradictions:
            parts.append(f"- Topic: {c.get('topic', '')}")
            parts.append(f"  A: {c.get('position_a', '')}")
            parts.append(f"  B: {c.get('position_b', '')}")
            parts.append(f"  Resolution hint: {c.get('resolution_hint', '')}")
        return "\n".join(parts)

    @staticmethod
    def _fmt_evidence(ranking: list[dict]) -> str:
        if not ranking:
            return "(none)"
        parts = []
        for r in ranking:
            parts.append(f"- {r.get('perspective', '')}: {r.get('strongest_claim', '')} (strength: {r.get('evidence_strength', 0)})")
        return "\n".join(parts)

    @staticmethod
    def _fmt_stress(results) -> str:
        if not results:
            return "(none)"
        parts = []
        for r in results:
            scenario = r.scenario.value if hasattr(r.scenario, 'value') else str(r.scenario)
            parts.append(f"- {scenario}: survival={r.survival_rate}, failure={r.failure_mode}")
        return "\n".join(parts)
