"""VS Coverage Audit stage — CoverageAuditStage."""
from __future__ import annotations

from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel

from reasoner.reasoner_verbalized_sampling import (
    VSMode,
    build_vs_prompt,
    parse_vs_response,
)
from reasoner.reasoner_vs_constants import VS_K_CLAIMS
from reasoner.vs_config import VSFeatureFlags


class _LLMClient(Protocol):
    async def generate(self, *, system: str = "", user: str = "") -> str: ...


class GapType(str, Enum):
    GENUINE = "genuine"
    PHRASING_MISMATCH = "phrasing_mismatch"
    COVERED = "covered"


class CoverageAuditResult(BaseModel):
    gaps: list[tuple[str, GapType]]
    coverage_ratio: float
    vs_metadata: dict[str, Any] = {}


async def _generate_paraphrases_vs(claim: str, llm_client: _LLMClient) -> list[str]:
    """Generate paraphrases of a claim using VS."""
    system, user = build_vs_prompt(claim, VSMode.STANDARD, VS_K_CLAIMS)
    raw = await llm_client.generate(system=system, user=user)
    try:
        result = parse_vs_response(raw)
        return [c.text for c in result.candidates]
    except ValueError:
        return [claim]


async def _check_overlap_with_evidence(paraphrases: list[str], evidence: list[str]) -> float:
    """Simplified overlap check: max proportion of words in any evidence sentence."""
    if not evidence or not paraphrases:
        return 0.0
    claim_words = set()
    for p in paraphrases:
        claim_words.update(p.lower().split())
    best = 0.0
    for ev in evidence:
        ev_words = set(ev.lower().split())
        if not ev_words:
            continue
        overlap = len(claim_words & ev_words) / len(claim_words)
        best = max(best, overlap)
    return best


async def audit_claim_coverage_vs(
    claims: list[str],
    evidence: list[str],
    llm_client: _LLMClient,
    flags: VSFeatureFlags,
) -> CoverageAuditResult:
    if not flags.coverage_audit:
        return CoverageAuditResult(gaps=[], coverage_ratio=1.0)

    gaps: list[tuple[str, GapType]] = []
    for claim in claims:
        paraphrases = await _generate_paraphrases_vs(claim, llm_client)
        overlap = await _check_overlap_with_evidence(paraphrases, evidence)
        if overlap < 0.5:
            gaps.append((claim, GapType.GENUINE))
        elif overlap < 0.9:
            gaps.append((claim, GapType.PHRASING_MISMATCH))

    coverage = 1.0 - (len([g for g in gaps if g[1] == GapType.GENUINE]) / max(len(claims), 1))
    return CoverageAuditResult(
        gaps=gaps,
        coverage_ratio=coverage,
        vs_metadata={"claims_checked": len(claims), "gaps_found": len(gaps)},
    )
