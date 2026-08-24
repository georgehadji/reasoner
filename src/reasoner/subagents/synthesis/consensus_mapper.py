"""
ConsensusMapperSubAgent — ONE JOB: identify which points all perspectives agree on.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.subagents.base import PhaseSubAgent

CONSENSUS_SYSTEM = """You are a Consensus Mapper. Your ONE JOB is to read all perspective candidates and identify which claims, conclusions, or recommendations appear in ALL of them (or in a strong majority).

Output ONLY a JSON object with this exact shape:
{
  "consensus_points": ["<point 1>", "<point 2>", ...],
  "partial_consensus": ["<point that 2/3 agree on>"],
  "confidence": 0.0-1.0,
  "rationale": "<brief explanation of your reasoning>"
}

Rules:
- consensus_points must contain claims that appear in every candidate
- partial_consensus contains claims that appear in a majority but not all
- Be specific. Avoid vague summaries.
- If there is NO consensus, return empty arrays and explain why.
"""


class ConsensusMapperSubAgent(PhaseSubAgent):
    AGENT_NAME = "consensus_mapper"
    TASK_DESCRIPTION = "Mapping agreements across all perspectives"
    ROLE = "subagent_synthesis_analysis"
    MAX_TOKENS = 512
    TEMPERATURE = 0.2

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        candidates = state.candidates
        candidate_texts = []
        for c in candidates:
            candidate_texts.append(f"--- {c.perspective.value} ---\n{c.content}")

        user = f"Problem: {state.problem}\n\nCandidates:\n" + "\n\n".join(candidate_texts)
        return (CONSENSUS_SYSTEM, user)

    def _parse_result(self, raw: str) -> dict[str, Any]:
        from reasoner.parsing import extract_json
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "consensus_points": data.get("consensus_points", []),
            "partial_consensus": data.get("partial_consensus", []),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
