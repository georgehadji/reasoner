"""
EvidenceWeighterSubAgent — ONE JOB: score which candidate arguments have the strongest evidence.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.subagents.base import PhaseSubAgent
from reasoner.parsing import extract_json


EVIDENCE_SYSTEM = """You are an Evidence Weighter. Your ONE JOB is to read all perspective candidates and evaluate which arguments have the STRONGEST supporting evidence.

Output ONLY a JSON object with this exact shape:
{
  "evidence_ranking": [
    {
      "perspective": "<name>",
      "strongest_claim": "<the best-supported claim from this perspective>",
      "evidence_strength": 0-10,
      "why": "<brief justification>"
    }
  ],
  "confidence": 0.0-1.0,
  "rationale": "<brief explanation>"
}

Rules:
- Rank ALL perspectives, not just the top ones
- evidence_strength is 0-10 (10 = rock-solid evidence, 0 = pure speculation)
- Consider: cited sources, logical rigor, specificity, real-world grounding
"""


class EvidenceWeighterSubAgent(PhaseSubAgent):
    AGENT_NAME = "evidence_weighter"
    TASK_DESCRIPTION = "Ranking arguments by evidence strength"
    ROLE = "subagent_synthesis_analysis"
    MAX_TOKENS = 512
    TEMPERATURE = 0.2

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        candidates = state.candidates
        candidate_texts = []
        for c in candidates:
            candidate_texts.append(f"--- {c.perspective.value} ---\n{c.content}")

        user = f"Problem: {state.problem}\n\nCandidates:\n" + "\n\n".join(candidate_texts)
        return (EVIDENCE_SYSTEM, user)

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "evidence_ranking": data.get("evidence_ranking", []),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
