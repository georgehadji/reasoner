"""
DirectDetectorSubAgent — ONE JOB: decide whether the problem can be answered
directly (no reasoning pipeline needed).

Output schema: {is_direct: bool, confidence: float, rationale: str}
"""

from __future__ import annotations

from typing import Any

from reasoner.core.constants import HYPERGATE_MAX_TOKENS_DIRECT
from reasoner.hypergate.base_sub_agent import BaseSubAgent

_CREATIVE_PATTERNS = [
    r"\b(write|compose|draft|create)\s+(an?\s+)?(poem|story|narrative|letter|speech|script)",
    r"\b(γράψε|συνέθεσε|δημιούργησε|σχεδίασε)\s+(μου\s+)?(ένα\s+)?(ποίημα|ιστορία|λόγο|σενάριο)",
    r"\b(tell\s+me\s+a\s+story|make\s+up\s+a\s+story|write\s+me\s+a\s+poem)",
    r"\b(πες\s+μου\s+μια\s+ιστορία|φτιάξε\s+μου\s+ένα\s+ποίημα)",
]

_SYSTEM = (
    "Decide whether the user's request can be answered directly without any multi-step "
    "reasoning pipeline.\n"
    "Answer 'true' for: greetings, simple arithmetic, definitions, casual conversation, "
    "basic factual questions with a known answer, creative writing requests "
    "(poems, stories, letters, speeches, scripts).\n"
    "Answer 'false' for: anything requiring analysis, strategy, research, structured reasoning, "
    "trade-off evaluation, professional judgment, or research-backed writing such as articles, essays, and blog posts.\n"
    "Output ONLY valid JSON with exactly three keys: "
    "'is_direct' (boolean), "
    "'confidence' (float 0.0–1.0), "
    "'rationale' (one short sentence). "
    "No markdown, no extra text."
)


class DirectDetectorSubAgent(BaseSubAgent):
    AGENT_NAME = "direct_detector"
    ROLE = "hypergate_direct"
    MAX_TOKENS = HYPERGATE_MAX_TOKENS_DIRECT

    def _system_prompt(self) -> str:
        return _SYSTEM

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = self._extract_json(raw)
            is_direct = bool(data.get("is_direct", False))
            return {
                "is_direct": is_direct,
                "confidence": min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
                "rationale": str(data.get("rationale", "")),
            }
        except Exception:
            return {"is_direct": False, "confidence": 0.0, "rationale": "parse error"}
