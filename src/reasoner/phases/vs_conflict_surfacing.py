"""VS Conflict Surfacing stage — ConflictSurfacingStage."""
from __future__ import annotations

from collections import Counter
from typing import Any, Protocol

from pydantic import BaseModel, Field

from reasoner.phases.vs_claim_extraction import _extract_claims
from reasoner.phases.vs_generation import GenerationCandidate
from reasoner.vs_config import VSFeatureFlags


class _NLIGate(Protocol):
    async def score_entailment(self, premise: str, hypothesis: str) -> float: ...


class CrossCandidateConflict(BaseModel):
    claim: str
    support_ratio: float
    conflict_priority: int
    recommendation: str  # HUMAN_REVIEW, FLAG, MONITOR
    vs_metadata: dict[str, Any] = Field(default_factory=dict)


async def _check_contradictions(claim: str, candidates: list[GenerationCandidate], nli_gate: _NLIGate | None) -> list[str]:
    """Check which candidates contradict the given claim via NLI."""
    if nli_gate is None:
        return []
    contradictions = []
    for c in candidates:
        if c.text.lower().strip() == claim.lower().strip():
            continue
        try:
            score = await nli_gate.score_entailment(claim, c.text)
            if score < 0.3:
                contradictions.append(c.text)
        except Exception:
            continue
    return contradictions


async def surface_cross_candidate_conflicts(
    candidates: list[GenerationCandidate],
    nli_gate: _NLIGate | None,
    flags: VSFeatureFlags,
) -> list[CrossCandidateConflict]:
    if not flags.conflict_surfacing:
        return []

    if not candidates:
        return []

    # Extract claims from all candidates
    all_claims: list[tuple[str, float]] = []
    for c in candidates:
        claims = await _extract_claims(c.text, None)
        all_claims.extend([(claim, c.probability) for claim in claims])

    # Compute support ratio per claim
    claim_support: Counter = Counter()
    for claim, prob in all_claims:
        claim_support[claim] += prob

    total_prob = sum(c.probability for c in candidates)
    conflicts: list[CrossCandidateConflict] = []

    for claim, total_claim_prob in claim_support.items():
        support_ratio = total_claim_prob / total_prob if total_prob > 0 else 0.0
        contradictions = await _check_contradictions(claim, candidates, nli_gate)
        if contradictions:
            priority = len(contradictions)
            if support_ratio < 0.3:
                rec = "HUMAN_REVIEW"
            elif support_ratio < 0.7:
                rec = "FLAG"
            else:
                rec = "MONITOR"
            conflicts.append(CrossCandidateConflict(
                claim=claim,
                support_ratio=support_ratio,
                conflict_priority=priority,
                recommendation=rec,
            ))

    return sorted(conflicts, key=lambda c: (-c.conflict_priority, -c.support_ratio))
