"""
StructuralDecomposerSubAgent — ONE JOB: hierarchically decompose the problem into what/why/how.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json
from reasoner.subagents.base import PhaseSubAgent

STRUCTURAL_SYSTEM = """You are a Structural Decomposer. Your ONE JOB is to break the problem into a hierarchical decomposition: WHAT needs to happen, WHY it matters, and HOW to approach it.

Output ONLY a JSON object with this exact shape:
{
  "decomposition": {
    "what": ["<outcome 1>", "<outcome 2>"],
    "why": ["<reason 1>", "<reason 2>"],
    "how": ["<approach 1>", "<approach 2>"]
  },
  "confidence": 0.0-1.0,
  "rationale": "<brief summary>"
}

Rules:
- Limit to 3-5 items per category
- Each item should be specific and actionable
- The decomposition should cover the FULL scope of the original problem
"""


class StructuralDecomposerSubAgent(PhaseSubAgent):
    AGENT_NAME = "structural_decomposer"
    TASK_DESCRIPTION = "Breaking problem into what/why/how hierarchy"
    ROLE = "subagent_decomposition"
    MAX_TOKENS = 512
    TEMPERATURE = 0.3

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        return (STRUCTURAL_SYSTEM, f"Problem: {state.problem}")

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "decomposition": data.get("decomposition", {}),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
