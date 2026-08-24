"""
CounterfactualSubAgent — ONE JOB: explore "what if the opposite were true?" for each candidate.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json
from reasoner.subagents.base import PhaseSubAgent

COUNTERFACTUAL_SYSTEM = """You are a Counterfactual Sub-Agent. Your ONE JOB is to explore what would happen if the KEY ASSUMPTIONS of each candidate solution were false.

Output ONLY a JSON object with this exact shape:
{
  "counterfactuals": [
    {
      "perspective": "<which candidate>",
      "key_assumption": "<the most important assumption this candidate relies on>",
      "if_false_scenario": "<what happens if this assumption is wrong>",
      "robustness": 0-10,
      "alternative_path": "<what approach would work better under the opposite assumption>"
    }
  ],
  "confidence": 0.0-1.0,
  "rationale": "<brief summary>"
}

Rules:
- robustness: 10 = solution holds even if assumption is false, 0 = completely collapses
- Focus on the SINGLE most important assumption per candidate
- alternative_path should be a constructive alternative, not just "do nothing"
"""


class CounterfactualSubAgent(PhaseSubAgent):
    AGENT_NAME = "counterfactual"
    TASK_DESCRIPTION = "Testing 'what if' alternative scenarios"
    ROLE = "subagent_critique_counter"
    MAX_TOKENS = 512
    TEMPERATURE = 0.3

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        candidate_texts = []
        for c in state.candidates:
            candidate_texts.append(f"--- {c.perspective.value} ---\n{c.content}")
        # Include decomposition assumptions if available
        assumptions = []
        if state.decomposition and hasattr(state.decomposition, 'assumptions'):
            for a in state.decomposition.assumptions:
                assumptions.append(f"- {a.text} [{a.label.value}]")
        user_parts = [f"Problem: {state.problem}", "\nKnown Assumptions:\n" + "\n".join(assumptions) if assumptions else ""]
        user_parts.append("\nCandidates:\n" + "\n\n".join(candidate_texts))
        return (COUNTERFACTUAL_SYSTEM, "\n".join(user_parts))

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "counterfactuals": data.get("counterfactuals", []),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
