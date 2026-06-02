"""
ScopeNarrowerSubAgent — ONE JOB: determine if the problem is too broad and suggest narrowing.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.subagents.base import PhaseSubAgent
from reasoner.parsing import extract_json


SCOPE_SYSTEM = """You are a Scope Narrower. Your ONE JOB is to determine if the problem is too broad or too narrow for a useful answer, and suggest how to refine it.

Output ONLY a JSON object with this exact shape:
{
  "scope_assessment": {
    "is_too_broad": true/false,
    "is_too_narrow": true/false,
    "recommended_scope": "<a better-phrased version of the problem>",
    "specificity_score": 0-10
  },
  "confidence": 0.0-1.0,
  "rationale": "<brief summary>"
}

Rules:
- specificity_score: 10 = perfectly scoped, 0 = impossibly vague
- recommended_scope should be a concrete rephrasing, not just "be more specific"
- If the scope is good, set both flags to false and explain why
"""


class ScopeNarrowerSubAgent(PhaseSubAgent):
    AGENT_NAME = "scope_narrower"
    TASK_DESCRIPTION = "Focusing overly broad problem statements"
    ROLE = "subagent_enhancement"
    MAX_TOKENS = 256
    TEMPERATURE = 0.2

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        return (SCOPE_SYSTEM, f"Problem: {state.problem}")

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "scope_assessment": data.get("scope_assessment", {}),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
