"""
CoverageValidatorSubAgent — ONE JOB: verify that sub-problems cover the full original problem.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.subagents.base import PhaseSubAgent
from reasoner.parsing import extract_json


COVERAGE_SYSTEM = """You are a Coverage Validator. Your ONE JOB is to check whether a given set of sub-problems fully covers the original problem, or if anything is missing.

Output ONLY a JSON object with this exact shape:
{
  "coverage_assessment": {
    "is_complete": true/false,
    "missing_aspects": ["<what is not covered>"],
    "overlap": ["<where sub-problems overlap redundantly>"],
    "coverage_score": 0-10
  },
  "confidence": 0.0-1.0,
  "rationale": "<brief summary>"
}

Rules:
- coverage_score: 10 = every aspect covered exactly once, 0 = huge gaps
- missing_aspects should list specific parts of the original problem not addressed
- overlap should flag redundant sub-problems that could be merged
"""


class CoverageValidatorSubAgent(PhaseSubAgent):
    AGENT_NAME = "coverage_validator"
    TASK_DESCRIPTION = "Checking for gaps and overlaps in analysis"
    ROLE = "subagent_decomposition"
    MAX_TOKENS = 512
    TEMPERATURE = 0.2

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        parts = [f"Original Problem: {state.problem}"]
        if state.decomposition and hasattr(state.decomposition, 'sub_problems'):
            parts.append("\nSub-problems:")
            for sp in state.decomposition.sub_problems:
                parts.append(f"- {sp.id}: {sp.description}")
        return (COVERAGE_SYSTEM, "\n".join(parts))

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "coverage_assessment": data.get("coverage_assessment", {}),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
