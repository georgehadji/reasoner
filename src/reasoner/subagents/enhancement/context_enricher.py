"""
ContextEnricherSubAgent — ONE JOB: identify what context is missing from the problem.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json
from reasoner.subagents.base import PhaseSubAgent

CONTEXT_SYSTEM = """You are a Context Enricher. Your ONE JOB is to identify what background information, constraints, or domain knowledge is missing that would help answer the problem better.

Output ONLY a JSON object with this exact shape:
{
  "missing_context": [
    {
      "type": "<background|constraint|domain_knowledge|stakeholder>",
      "description": "<what is missing>",
      "why_it_matters": "<how this would change the answer>"
    }
  ],
  "confidence": 0.0-1.0,
  "rationale": "<brief summary>"
}

Rules:
- Only list context that is REASONABLY expected to be available
- Don't invent impossible-to-know information
- why_it_matters should explain the impact on the solution
"""


class ContextEnricherSubAgent(PhaseSubAgent):
    AGENT_NAME = "context_enricher"
    TASK_DESCRIPTION = "Identifying missing background context"
    ROLE = "subagent_enhancement"
    MAX_TOKENS = 256
    TEMPERATURE = 0.2

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        return (CONTEXT_SYSTEM, f"Problem: {state.problem}")

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "missing_context": data.get("missing_context", []),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
