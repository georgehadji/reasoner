"""
WebSearchDetectorSubAgent — ONE JOB: decide whether the problem requires
real-time or very recent information that only a web search can provide.

Output schema: {needs_search: bool, confidence: float, rationale: str}
"""

from __future__ import annotations

from typing import Any

from reasoner.core.constants import HYPERGATE_MAX_TOKENS_WEB
from reasoner.hypergate.base_sub_agent import BaseSubAgent

_SYSTEM = (
    "Decide whether the user's query requires real-time or very recent information "
    "that only a live web search can satisfy.\n"
    "Answer 'true' for: current weather, live sports scores, today's news headlines, "
    "stock or cryptocurrency prices, recent software/product releases or updates, "
    "breaking news, latest company announcements, live events, current exchange rates, "
    "or anything that changes daily or requires information from the last few days or weeks.\n"
    "Answer 'false' for: questions answerable from general knowledge, historical facts, "
    "analytical problems, strategic decisions, coding help, explanations, or anything timeless.\n"
    "Output ONLY valid JSON with exactly three keys: "
    "'needs_search' (boolean), "
    "'confidence' (float 0.0–1.0), "
    "'rationale' (one short sentence). "
    "No markdown, no extra text."
)


class WebSearchDetectorSubAgent(BaseSubAgent):
    AGENT_NAME = "web_detector"
    MAX_TOKENS = HYPERGATE_MAX_TOKENS_WEB

    def _system_prompt(self) -> str:
        return _SYSTEM

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = self._extract_json(raw)
            needs_search = bool(data.get("needs_search", False))
            return {
                "needs_search": needs_search,
                "confidence": min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
                "rationale": str(data.get("rationale", "")),
            }
        except Exception:
            return {"needs_search": False, "confidence": 0.0, "rationale": "parse error"}
