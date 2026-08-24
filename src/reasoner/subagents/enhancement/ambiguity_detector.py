"""
AmbiguityDetectorSubAgent — ONE JOB: identify what is unclear or vague in the problem statement.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json
from reasoner.subagents.base import PhaseSubAgent

AMBIGUITY_SYSTEM = """You are an Ambiguity Detector. Your ONE JOB is to read the user's problem and identify what is unclear, vague, or ambiguous.

Output ONLY a JSON object with this exact shape:
{
  "ambiguities": [
    {
      "phrase": "<the ambiguous word or phrase>",
      "issue": "<why it's ambiguous>",
      "clarification_question": "<what question would resolve this>"
    }
  ],
  "confidence": 0.0-1.0,
  "rationale": "<brief summary>"
}

Rules:
- Focus on terms that could have multiple meanings in context
- If the problem is crystal clear, return empty ambiguities
- clarification_question should be specific, not generic
"""


class AmbiguityDetectorSubAgent(PhaseSubAgent):
    AGENT_NAME = "ambiguity_detector"
    TASK_DESCRIPTION = "Finding unclear terms and vague language"
    ROLE = "subagent_enhancement"
    MAX_TOKENS = 256
    TEMPERATURE = 0.2

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        return (AMBIGUITY_SYSTEM, f"Problem: {state.problem}")

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "ambiguities": data.get("ambiguities", []),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
