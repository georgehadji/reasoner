"""
ComplexityEstimatorSubAgent — ONE JOB: estimate whether the problem is simple,
medium, or complex in terms of reasoning depth required.

Output schema: {complexity: "simple"|"medium"|"complex", confidence: float}
"""

from __future__ import annotations

from typing import Any

from reasoner.core.constants import HYPERGATE_MAX_TOKENS_COMPLEXITY
from reasoner.hypergate.base_sub_agent import BaseSubAgent

_SYSTEM = (
    "Estimate the reasoning complexity of the user's problem.\n"
    "- 'simple': a greeting, basic factual question, trivial lookup, or creative writing request "
    "(poem, story, letter, speech, script) that can be answered "
    "directly by a capable language model without external research.\n"
    "- 'medium': needs some analysis but not deep multi-step reasoning, including light structured writing.\n"
    "- 'complex': requires structured multi-phase reasoning, trade-off analysis, or expert knowledge\n"
    "Output ONLY valid JSON with exactly two keys: "
    "'complexity' (one of: simple, medium, complex) "
    "and 'confidence' (float 0.0–1.0). "
    "No markdown, no explanation."
)

_VALID = {"simple", "medium", "complex"}


class ComplexityEstimatorSubAgent(BaseSubAgent):
    AGENT_NAME = "complexity_estimator"
    ROLE = "hypergate_complexity"
    MAX_TOKENS = HYPERGATE_MAX_TOKENS_COMPLEXITY

    def _system_prompt(self) -> str:
        return _SYSTEM

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = self._extract_json(raw)
            complexity = str(data.get("complexity", "medium")).lower()
            if complexity not in _VALID:
                complexity = "medium"
            return {
                "complexity": complexity,
                "confidence": min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
            }
        except Exception:
            return {"complexity": "medium", "confidence": 0.0}
