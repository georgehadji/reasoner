"""EvidenceService — epistemic label promotion and provenance tracking.

Paper grounding: §5.2.2 — "make every accepted action carry an evidence bundle".

Core rule: A claim may be VERIFIED with source="sensor" ONLY if a deterministic
check backs it. Otherwise it is capped at HYPOTHESIS regardless of what the LLM
asserted. This operationalizes "a label is a claim about evidence, not confidence."
"""

from __future__ import annotations

from reasoner.domain.core_types import EvidenceBundle, FinalSolution
from reasoner.domain.models import ClaimLabel

# Sources eligible for VERIFIED status.
_SENSOR_SOURCES = {"sensor", "search"}  # "model" alone cannot reach VERIFIED


def apply_promotion_rules(
    bundles: dict[str, EvidenceBundle],
) -> dict[str, EvidenceBundle]:
    """Apply evidence-tier promotion rules to a set of evidence bundles.

    Rules:
      1. A claim with source="model" and label="VERIFIED" → HYPOTHESIS
         (model self-attestation is not sufficient for VERIFIED).
      2. A claim with source="sensor" or "search" and label="VERIFIED" → VERIFIED
         (deterministic or grounded evidence backs it).
      3. All other labels pass through unchanged.

    Args:
        bundles: {claim_text: EvidenceBundle}

    Returns:
        Updated bundles with labels corrected according to promotion rules.
    """
    corrected: dict[str, EvidenceBundle] = {}
    for claim, bundle in bundles.items():
        updated = _apply_promotion(bundle)
        corrected[claim] = updated
    return corrected


def _apply_promotion(bundle: EvidenceBundle) -> EvidenceBundle:
    """Apply promotion rules to a single EvidenceBundle."""
    label = bundle.label.upper()

    if label == "VERIFIED" and bundle.source not in _SENSOR_SOURCES:
        # Model self-attestation is not sufficient — downgrade to HYPOTHESIS
        return EvidenceBundle(
            label="HYPOTHESIS",
            checks_run=bundle.checks_run,
            evidence_refs=bundle.evidence_refs,
            untested=bundle.untested,
            residual_risk=bundle.residual_risk,
            source=bundle.source,
        )

    # Pass through unchanged
    return bundle


def attach_execution_evidence(
    bundles: dict[str, EvidenceBundle],
    execution_evidence_id: str,
    claim_match_fn=None,
) -> dict[str, EvidenceBundle]:
    """Link a PoT execution's evidence id to matching claims.

    Args:
        bundles: Existing evidence bundles (may be empty before synthesis).
        execution_evidence_id: Evidence id from #1's CodeExecuted event.
        claim_match_fn: Optional function (claim_text: str) -> bool to
                        select which claims get the evidence link. If None,
                        links to the first claim or creates a generic entry.

    Returns:
        Bundles with the execution evidence ref added.
    """
    if claim_match_fn is not None:
        for claim, bundle in bundles.items():
            if claim_match_fn(claim):
                bundle.evidence_refs.append(execution_evidence_id)
                bundle.source = "sensor"
    else:
        # No matcher — add a generic execution evidence entry
        bundles["execution_evidence"] = EvidenceBundle(
            label="HYPOTHESIS",
            checks_run=[f"code_executed: {execution_evidence_id}"],
            evidence_refs=[execution_evidence_id],
            source="sensor",
        )
    return bundles
