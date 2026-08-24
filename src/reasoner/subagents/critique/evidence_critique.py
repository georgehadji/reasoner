"""
EvidenceCritiqueSubAgent — ONE JOB: evaluate quality and reliability of sources/evidence.
"""
from __future__ import annotations

from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json
from reasoner.subagents.base import PhaseSubAgent

EVIDENCE_SYSTEM = """You are an Evidence Critique Sub-Agent. Your ONE JOB is to evaluate the quality, reliability, and sufficiency of evidence supporting each candidate solution.

Output ONLY a JSON object with this exact shape:
{
  "evidence_assessment": [
    {
      "perspective": "<which candidate>",
      "strongest_evidence": "<best piece of evidence cited>",
      "weakest_evidence": "<most questionable or unsupported claim>",
      "source_quality": 0-10,
      "sufficiency": 0-10,
      "gaps": ["<what evidence is missing>"]
    }
  ],
  "confidence": 0.0-1.0,
  "rationale": "<brief summary>"
}

Rules:
- source_quality: 10 = peer-reviewed / primary sources, 0 = pure assertion
- sufficiency: 10 = fully supported, 0 = no evidence at all
- gaps should list specific missing evidence that would strengthen the argument
"""


class EvidenceCritiqueSubAgent(PhaseSubAgent):
    AGENT_NAME = "evidence_critique"
    TASK_DESCRIPTION = "Evaluating source quality and evidence reliability"
    ROLE = "subagent_critique_evidence"
    MAX_TOKENS = 512
    TEMPERATURE = 0.2

    def _build_prompt(self, state: PipelineState) -> tuple[str, str]:
        candidate_texts = []
        for c in state.candidates:
            candidate_texts.append(f"--- {c.perspective.value} ---\n{c.content}")
        user = f"Problem: {state.problem}\n\nCandidates:\n" + "\n\n".join(candidate_texts)
        return (EVIDENCE_SYSTEM, user)

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = extract_json(raw)
        except Exception:
            data = {}
        return {
            "evidence_assessment": data.get("evidence_assessment", []),
            "confidence": float(data.get("confidence", 0.0)),
            "rationale": data.get("rationale", ""),
        }
