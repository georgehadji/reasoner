"""
StakeholderMapperSubAgent — ONE JOB: identify relevant perspectives and stakeholders.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.subagents.base import PhaseSubAgent
from reasoner.parsing import extract_json


STAKEHOLDER_SYSTEM = """You are a Stakeholder Mapper. Your ONE JOB is to identify which perspectives, roles, or stakeholders are relevant to this problem.

Output ONLY a JSON object with this exact shape:
{
  "stakeholders": [
    {
      "role": "<e.g. user, developer, manager, customer, regulator>",
      "concerns": ["<what they care about>"],
      "perspective_label": "<constructive|destructive|systemic|minimalist>"
    }
  ],
  "confidence": 0.0-1.0,
  "rationale": "<brief summary>"
}

Rules:
- Map each stakeholder to one of the four Reasoner perspective labels
- concerns should be specific to the problem domain
- Include at least 2 and at most 5 stakeholders
"""


class StakeholderMapperSubAgent(PhaseSubAgent):
    AGENT_NAME = "stakeholder_mapper"
    TASK_DESCRIPTION = "Identifying relevant stakeholders and concerns"
    ROLE = "subagent_decomposition"
    MAX_TOKENS = 512
    TEMPERATURE = 0.3

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        return (STAKEHOLDER_SYSTEM, f"Problem: {state.problem}")

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "stakeholders": data.get("stakeholders", []),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
