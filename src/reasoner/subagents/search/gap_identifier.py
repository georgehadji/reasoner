"""
GapIdentifierSubAgent — ONE JOB: identify what evidence is still missing after search.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.subagents.base import PhaseSubAgent
from reasoner.parsing import extract_json


GAP_SYSTEM = """You are a Gap Identifier. Your ONE JOB is to identify what evidence or information is still MISSING after reviewing search results.

Output ONLY a JSON object with this exact shape:
{
  "gaps": [
    {
      "topic": "<what is missing>",
      "why_needed": "<how this would change the conclusion>",
      "suggested_query": "<a search query that might find it>"
    }
  ],
  "confidence": 0.0-1.0,
  "rationale": "<brief summary>"
}

Rules:
- Only list gaps that are REASONABLY findable through search
- why_needed should explain the impact on the final answer
- suggested_query should be a concrete, searchable query
"""


class GapIdentifierSubAgent(PhaseSubAgent):
    AGENT_NAME = "gap_identifier"
    TASK_DESCRIPTION = "Finding missing evidence gaps"
    ROLE = "subagent_search_eval"
    MAX_TOKENS = 256
    TEMPERATURE = 0.3

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        sources = []
        for r in state.web_discovery_results[:5]:
            sources.append(f"- {r.get('title', 'Untitled')}: {r.get('snippet', '')}")
        return (GAP_SYSTEM, f"Problem: {state.problem}\n\nFound Sources:\n" + "\n".join(sources))

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "gaps": data.get("gaps", []),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
