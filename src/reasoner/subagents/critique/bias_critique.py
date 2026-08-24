"""
BiasCritiqueSubAgent — ONE JOB: detect cognitive biases and framing effects.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json
from reasoner.subagents.base import PhaseSubAgent

BIAS_SYSTEM = """You are a Bias Critique Sub-Agent. Your ONE JOB is to identify cognitive biases, framing effects, and unstated assumptions that may have influenced each candidate solution.

Output ONLY a JSON object with this exact shape:
{
  "bias_findings": [
    {
      "perspective": "<which candidate>",
      "bias_type": "<e.g. confirmation_bias, anchoring, availability_heuristic, status_quo_bias>",
      "description": "<how it manifests in this candidate>",
      "severity": 1-10,
      "mitigation": "<how to correct for this bias>"
    }
  ],
  "confidence": 0.0-1.0,
  "rationale": "<brief summary>"
}

Rules:
- Only flag REAL biases, not minor preferences or legitimate value judgments
- severity 1 = negligible influence, 10 = completely distorted conclusion
- mitigation should be actionable — how would a neutral party address this?
"""


class BiasCritiqueSubAgent(PhaseSubAgent):
    AGENT_NAME = "bias_critique"
    TASK_DESCRIPTION = "Detecting cognitive biases and framing effects"
    ROLE = "subagent_critique_bias"
    MAX_TOKENS = 512
    TEMPERATURE = 0.2

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        candidate_texts = []
        for c in state.candidates:
            candidate_texts.append(f"--- {c.perspective.value} ---\n{c.content}")
        user = f"Problem: {state.problem}\n\nCandidates:\n" + "\n\n".join(candidate_texts)
        return (BIAS_SYSTEM, user)

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "bias_findings": data.get("bias_findings", []),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
