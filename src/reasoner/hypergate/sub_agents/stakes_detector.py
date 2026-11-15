"""
StakesDetectorSubAgent — ONE JOB: say whether a question is one where a wrong
answer can hurt the asker in health, law or personal finance.

Output schema: {domain: health|legal|financial|none, confidence: float, rationale: str}

It backs up the regex pre-check (hypergate/stakes_patterns.py), which misses
paraphrases and languages the patterns do not cover. It never names a method.
"""

from __future__ import annotations

from typing import Any

from reasoner.core.constants import HYPERGATE_MAX_TOKENS_STAKES
from reasoner.core.degrade import degraded
from reasoner.domain.stakes import StakesDomain
from reasoner.hypergate.base_sub_agent import BaseSubAgent

_SYSTEM = (
    "Decide whether the user's question is one where a wrong answer could harm "
    "the person asking, and which field it belongs to.\n"
    "'health': medical symptoms, diagnosis, treatment, medication or dosage, "
    "mental health, pregnancy, nutrition for a condition.\n"
    "'legal': a legal right, duty, contract, court, fine, visa or immigration, "
    "tenancy, employment law, or whether something is legal.\n"
    "'financial': taxes, investing, loans or mortgages, pensions, insurance, "
    "or how to handle the asker's own money.\n"
    "'none': everything else, including general knowledge, coding, writing, "
    "history, and business strategy that is not about the asker's own health, "
    "legal position or money.\n"
    "Work in any language. Output ONLY valid JSON with exactly three keys: "
    "'domain' (one of health, legal, financial, none), "
    "'confidence' (float 0.0-1.0), "
    "'rationale' (one short sentence). No markdown, no extra text."
)

_NONE: dict[str, Any] = {"domain": "none", "confidence": 0.0, "rationale": "parse error"}


class StakesDetectorSubAgent(BaseSubAgent):
    AGENT_NAME = "stakes_detector"
    ROLE = "hypergate_stakes"
    MAX_TOKENS = HYPERGATE_MAX_TOKENS_STAKES

    def _system_prompt(self) -> str:
        return _SYSTEM

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = self._extract_json(raw)
            domain = str(data.get("domain", "none")).strip().lower()
            if domain not in {d.value for d in StakesDomain}:
                domain = "none"
            return {
                "domain": domain,
                "confidence": min(1.0, max(0.0, float(data.get("confidence", 0.0)))),
                "rationale": str(data.get("rationale", ""))[:200],
            }
        except Exception as exc:
            return degraded("hypergate.stakes_detector.parse", dict(_NONE), exc=exc)
