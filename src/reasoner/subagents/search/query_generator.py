"""
QueryGeneratorSubAgent — ONE JOB: generate diverse search queries for web research.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json
from reasoner.subagents.base import PhaseSubAgent

QUERY_SYSTEM = """You are a Query Generator. Your ONE JOB is to generate 3-5 diverse search queries that will help gather evidence for the problem.

Output ONLY a JSON object with this exact shape:
{
  "queries": [
    {
      "query": "<search query text>",
      "intent": "<what this query is trying to find>",
      "priority": 1-5
    }
  ],
  "confidence": 0.0-1.0,
  "rationale": "<brief summary>"
}

Rules:
- Queries should be diverse (different angles, not variations of the same query)
- priority 1 = most important, 5 = nice-to-have
- Queries should be specific enough to return relevant results
"""


class QueryGeneratorSubAgent(PhaseSubAgent):
    AGENT_NAME = "query_generator"
    TASK_DESCRIPTION = "Generating diverse search queries"
    ROLE = "subagent_search_query"
    MAX_TOKENS = 256
    TEMPERATURE = 0.4

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        return (QUERY_SYSTEM, f"Problem: {state.problem}")

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "queries": data.get("queries", []),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
