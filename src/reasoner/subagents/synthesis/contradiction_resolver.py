"""
ContradictionResolverSubAgent — ONE JOB: find disagreements between perspectives and explain why.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json
from reasoner.subagents.base import PhaseSubAgent

CONTRADICTION_SYSTEM = """You are a Contradiction Resolver. Your ONE JOB is to read all perspective candidates and identify where they DIRECTLY CONTRADICT each other.

Output ONLY a JSON object with this exact shape:
{
  "contradictions": [
    {
      "topic": "<what they disagree about>",
      "position_a": "<perspective X says this>",
      "position_b": "<perspective Y says the opposite>",
      "resolution_hint": "<which position has stronger evidence or how to reconcile>"
    }
  ],
  "confidence": 0.0-1.0,
  "rationale": "<brief explanation>"
}

Rules:
- Only list REAL contradictions, not minor differences in emphasis
- If there are no contradictions, return empty array and explain why
- resolution_hint should suggest which side is better supported or how they can be reconciled
"""


class ContradictionResolverSubAgent(PhaseSubAgent):
    AGENT_NAME = "contradiction_resolver"
    TASK_DESCRIPTION = "Finding and resolving conflicts between perspectives"
    ROLE = "subagent_synthesis_analysis"
    MAX_TOKENS = 512
    TEMPERATURE = 0.2

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        candidates = state.candidates
        candidate_texts = []
        for c in candidates:
            candidate_texts.append(f"--- {c.perspective.value} ---\n{c.content}")

        user = f"Problem: {state.problem}\n\nCandidates:\n" + "\n\n".join(candidate_texts)
        return (CONTRADICTION_SYSTEM, user)

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "contradictions": data.get("contradictions", []),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
