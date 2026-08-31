"""
LanguageDetectorSubAgent — ONE JOB: detect the language of the input text.

Output schema: {language: str, confidence: float}
"""

from __future__ import annotations

from typing import Any

from reasoner.core.constants import HYPERGATE_MAX_TOKENS_LANGUAGE
from reasoner.hypergate.base_sub_agent import BaseSubAgent

_SYSTEM = (
    "Detect the language of the user's text. "
    "Output ONLY valid JSON with exactly two keys: "
    "'language' (full English name, e.g. 'English', 'Greek', 'Arabic') "
    "and 'confidence' (float 0.0–1.0). "
    "No markdown, no explanation."
)


class LanguageDetectorSubAgent(BaseSubAgent):
    AGENT_NAME = "language_detector"
    ROLE = "hypergate_language"
    MAX_TOKENS = HYPERGATE_MAX_TOKENS_LANGUAGE

    def _system_prompt(self) -> str:
        return _SYSTEM

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = self._extract_json(raw)
            return {
                "language": str(data.get("language", "English")),
                "confidence": min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
            }
        except Exception:
            return {"language": "English", "confidence": 0.0}
