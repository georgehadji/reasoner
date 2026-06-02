"""
SourceEvaluatorSubAgent — ONE JOB: evaluate credibility and relevance of search results.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.subagents.base import PhaseSubAgent
from reasoner.parsing import extract_json


SOURCE_SYSTEM = """You are a Source Evaluator. Your ONE JOB is to evaluate the credibility and relevance of search results for the problem.

Output ONLY a JSON object with this exact shape:
{
  "source_evaluations": [
    {
      "title": "<source title>",
      "credibility": 0-10,
      "relevance": 0-10,
      "recency": "<current|dated|unknown>",
      "bias_risk": "<low|medium|high>"
    }
  ],
  "confidence": 0.0-1.0,
  "rationale": "<brief summary>"
}

Rules:
- credibility: 10 = peer-reviewed / primary source, 0 = unverified blog
- relevance: 10 = directly answers the problem, 0 = tangential
- Evaluate up to 5 sources max
"""


class SourceEvaluatorSubAgent(PhaseSubAgent):
    AGENT_NAME = "source_evaluator"
    TASK_DESCRIPTION = "Evaluating source credibility and relevance"
    ROLE = "subagent_search_eval"
    MAX_TOKENS = 512
    TEMPERATURE = 0.2

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        sources = []
        for r in state.web_discovery_results[:5]:
            sources.append(f"- {r.get('title', 'Untitled')}: {r.get('url', '')}")
        return (SOURCE_SYSTEM, f"Problem: {state.problem}\n\nSources:\n" + "\n".join(sources))

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "source_evaluations": data.get("source_evaluations", []),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
