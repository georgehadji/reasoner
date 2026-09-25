"""
TieBreakerSubAgent — ONE JOB: resolve routing ambiguity when Phase-1 sub-agents
conflict or all return low confidence.

Receives the full HyperContext (as JSON in SubAgentInput.context) and produces
a definitive routing decision.

The LLM sees and answers with the MethodClassifier's opaque letters, never real
method names (CLAUDE.md §5); resolve() maps the letter back. The result's
"method" is the real name, for code downstream.

Output schema: {action: str, method: str|null, confidence: float, rationale: str}
"""

from __future__ import annotations

from typing import Any

from reasoner.core.constants import HYPERGATE_MAX_TOKENS_TIEBREAK
from reasoner.core.degrade import degraded
from reasoner.hypergate.base_sub_agent import BaseSubAgent
from reasoner.hypergate.sub_agents.method_classifier import CATEGORY_LIST, MethodClassifierSubAgent

_SYSTEM = (
    "You are a routing arbitrator. Four specialized analyzers have already examined the user's "
    "problem and produced signals. Their results are provided in the context block below.\n\n"
    "Your job is to make ONE final routing decision based on all available signals:\n"
    "- 'direct': answer the user immediately without a reasoning pipeline\n"
    "- 'web_search': perform a live web search and return results\n"
    "- 'pipeline': run a structured multi-phase reasoning pipeline\n\n"
    "If action is 'pipeline', also choose the best reasoning category from this list:\n"
    f"{CATEGORY_LIST}\n\n"
    "Output ONLY valid JSON with exactly four keys: "
    "'action' (direct|web_search|pipeline), "
    "'category' (one letter from the list above, or null unless action is 'pipeline'), "
    "'confidence' (float 0.0–1.0), "
    "'rationale' (one sentence explaining the tie-break). "
    "No markdown, no extra text."
)

_VALID_ACTIONS = {"direct", "web_search", "pipeline"}


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
            # resolve() falls back to E (multi_perspective) on a missing or
            # unknown letter -- including a method *name*, which is what a user
            # naming a method in the problem text would get echoed back.
            category = str(data.get("category") or "").strip()
            method: str | None = (
                MethodClassifierSubAgent.resolve(category)[1] if action == "pipeline" else None
            )
            return {
                "action": action,
                "method": method,
                "confidence": min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
                "rationale": str(data.get("rationale", "")),
            }
        except Exception as exc:
            return degraded(
                "hypergate.tie_breaker.parse",
                {
                    "action": "pipeline",
                    "method": "multi_perspective",
                    "confidence": 0.0,
                    "rationale": "parse error",
                },
                exc=exc,
            )
