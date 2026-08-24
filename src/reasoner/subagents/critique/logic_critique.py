"""
LogicCritiqueSubAgent — ONE JOB: identify formal logical fallacies and structural flaws.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json
from reasoner.subagents.base import PhaseSubAgent

LOGIC_SYSTEM = """You are a Logic Critique Sub-Agent. Your ONE JOB is to examine each candidate solution and identify formal logical fallacies, circular reasoning, false dichotomies, or structural reasoning flaws.

Output ONLY a JSON object with this exact shape:
{
  "logic_issues": [
    {
      "perspective": "<which candidate>",
      "issue": "<name of fallacy or flaw>",
      "location": "<which claim or argument contains it>",
      "severity": 1-10,
      "explanation": "<why this is a problem>"
    }
  ],
  "confidence": 0.0-1.0,
  "rationale": "<brief summary of your analysis>"
}

Rules:
- severity 1 = minor quibble, 10 = completely undermines the argument
- If no issues found, return empty logic_issues and explain why
- Be specific about WHICH claim contains the flaw
"""


class LogicCritiqueSubAgent(PhaseSubAgent):
    AGENT_NAME = "logic_critique"
    TASK_DESCRIPTION = "Checking for logical fallacies and inconsistencies"
    ROLE = "subagent_critique_logic"
    MAX_TOKENS = 512
    TEMPERATURE = 0.2

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        candidate_texts = []
        for c in state.candidates:
            candidate_texts.append(f"--- {c.perspective.value} ---\n{c.content}")
        user = f"Problem: {state.problem}\n\nCandidates:\n" + "\n\n".join(candidate_texts)
        return (LOGIC_SYSTEM, user)

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "logic_issues": data.get("logic_issues", []),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
