"""
TieBreakerSubAgent — ONE JOB: resolve routing ambiguity when Phase-1 sub-agents
conflict or all return low confidence.

Receives the full HyperContext (as JSON in SubAgentInput.context) and produces
a definitive routing decision.

Output schema: {action: str, method: str|null, confidence: float, rationale: str}
"""

from __future__ import annotations

from typing import Any

from reasoner.core.constants import HYPERGATE_MAX_TOKENS_TIEBREAK
from reasoner.hypergate.base_sub_agent import BaseSubAgent

_SYSTEM = (
    "You are a routing arbitrator. Four specialized analyzers have already examined the user's "
    "problem and produced signals. Their results are provided in the context block below.\n\n"
    "Your job is to make ONE final routing decision based on all available signals:\n"
    "- 'direct': answer the user immediately without a reasoning pipeline\n"
    "- 'web_search': perform a live web search and return results\n"
    "- 'pipeline': run a structured multi-phase reasoning pipeline\n\n"
    "If action is 'pipeline', also specify the best method from this list:\n"
    "debate, scientific, socratic, multi_perspective, jury, research, "
    "pre_mortem, bayesian, dialectical, analogical, delphi, "
    "cove, sot, tot, pot, self_discover, writing, coding\n\n"
    "Output ONLY valid JSON with exactly four keys: "
    "'action' (direct|web_search|pipeline), "
    "'method' (method name or null), "
    "'confidence' (float 0.0–1.0), "
    "'rationale' (one sentence explaining the tie-break). "
    "No markdown, no extra text."
)

_VALID_ACTIONS = {"direct", "web_search", "pipeline"}
_VALID_METHODS = {
    "debate", "scientific", "socratic", "multi_perspective", "jury",
    "research", "pre_mortem", "bayesian", "dialectical", "analogical", "delphi",
    "cove", "sot", "tot", "pot", "self_discover", "writing", "coding",
}


class TieBreakerSubAgent(BaseSubAgent):
    AGENT_NAME = "tie_breaker"
    ROLE = "hypergate_tiebreak"
    MAX_TOKENS = HYPERGATE_MAX_TOKENS_TIEBREAK

    def _system_prompt(self) -> str:
        return _SYSTEM

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = self._extract_json(raw)
            action = str(data.get("action", "pipeline")).lower()
            if action not in _VALID_ACTIONS:
                action = "pipeline"
            method_raw = data.get("method")
            method: str | None = str(method_raw).lower() if method_raw else None
            if method and method not in _VALID_METHODS:
                method = "multi_perspective"
            if action == "pipeline" and not method:
                method = "multi_perspective"
            if action != "pipeline":
                method = None
            return {
                "action": action,
                "method": method,
                "confidence": min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
                "rationale": str(data.get("rationale", "")),
            }
        except Exception:
            return {
                "action": "pipeline",
                "method": "multi_perspective",
                "confidence": 0.0,
                "rationale": "parse error",
            }
