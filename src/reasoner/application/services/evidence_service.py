"""EvidenceService — epistemic label promotion and provenance tracking.

Paper grounding: §5.2.2 — "make every accepted action carry an evidence bundle".

Core rule: A claim may be VERIFIED with source="sensor" ONLY if a deterministic
check backs it. Otherwise it is capped at HYPOTHESIS regardless of what the LLM
asserted. This operationalizes "a label is a claim about evidence, not confidence."
"""

from __future__ import annotations

from typing import Protocol

from reasoner.core.constants_limits import EVIDENCE_SENSOR_SOURCES
from reasoner.domain.authority_sources import AuthorityTier, authority_tier
from reasoner.domain.core_types import EvidenceBundle
from reasoner.domain.models import ClaimLabel
from reasoner.domain.stakes import StakesProfile

_SENSOR_SOURCES = set(EVIDENCE_SENSOR_SOURCES)


_RANK = {ClaimLabel.UNKNOWN: 0, ClaimLabel.HYPOTHESIS: 1, ClaimLabel.VERIFIED: 2}


def _norm(url: str) -> str:
    return url.strip().rstrip(".,;:!?").rstrip("/")


class EpistemicPolicy(Protocol):
    def promote(
        self, bundle: EvidenceBundle, allowed_refs: set[str] | None
    ) -> EvidenceBundle: ...


class StandardPolicy:
    """Every run: model-sourced VERIFIED is capped; search needs a retrieved URL."""

    def promote(self, bundle: EvidenceBundle, allowed_refs: set[str] | None) -> EvidenceBundle:
        return _apply_promotion(bundle, allowed_refs)


class HighStakesPolicy:
    """Standard, plus VERIFIED needs a PRIMARY authority source for the run's domain and country."""

    def __init__(self, profile: StakesProfile) -> None:
        self._profile = profile

    def promote(self, bundle: EvidenceBundle, allowed_refs: set[str] | None) -> EvidenceBundle:
        out = _apply_promotion(bundle, allowed_refs)
        if out.label.upper() != "VERIFIED":
            return out
        p = self._profile
        if any(
            authority_tier(r, p.domain, p.jurisdiction.country) >= AuthorityTier.PRIMARY
            for r in out.evidence_refs
        ):
            return out
        return _downgraded(out)


def apply_promotion_rules(
    bundles: dict[str, EvidenceBundle],
    allowed_refs: set[str] | None = None,
    policy: EpistemicPolicy | None = None,
) -> dict[str, EvidenceBundle]:
    """Apply evidence-tier promotion rules to a set of evidence bundles.

    Rules:
      1. A claim with source="model" and label="VERIFIED" → HYPOTHESIS
         (model self-attestation is not sufficient for VERIFIED).
      2. A claim with source="sensor" and label="VERIFIED" → VERIFIED.
         source="search" keeps VERIFIED only when ``allowed_refs`` is None
         (check skipped) or one of its evidence_refs is in ``allowed_refs``:
         the source is self-declared, so its URLs must be ones the run retrieved.
      3. All other labels pass through unchanged.

    Args:
        bundles: {claim_text: EvidenceBundle}

    Returns:
        Updated bundles with labels corrected according to promotion rules.
    """
    corrected: dict[str, EvidenceBundle] = {}
    for claim, bundle in bundles.items():
        updated = (policy or StandardPolicy()).promote(bundle, allowed_refs)
        corrected[claim] = updated
    return corrected


def _apply_promotion(
    bundle: EvidenceBundle, allowed_refs: set[str] | None = None
) -> EvidenceBundle:
    """Apply promotion rules to a single EvidenceBundle."""
    label = bundle.label.upper()

    ungrounded = (
        bundle.source == "search"
        and allowed_refs is not None
        and not any(_norm(r) in allowed_refs for r in bundle.evidence_refs)
    )
    if label == "VERIFIED" and (bundle.source not in _SENSOR_SOURCES or ungrounded):
        # Model self-attestation is not sufficient — downgrade to HYPOTHESIS
        return _downgraded(bundle)

    # Pass through unchanged
    return bundle


def _downgraded(bundle: EvidenceBundle) -> EvidenceBundle:
    return EvidenceBundle(
        label="HYPOTHESIS",
        checks_run=bundle.checks_run,
        evidence_refs=bundle.evidence_refs,
        untested=bundle.untested,
        residual_risk=bundle.residual_risk,
        source=bundle.source,
    )


def reconcile_labels(
    claim_labels: dict[str, ClaimLabel],
    evidence: dict[str, EvidenceBundle],
) -> dict[str, ClaimLabel]:
    """Cap each claim label at its (already promoted) evidence bundle's label.

    A VERIFIED claim with no bundle becomes HYPOTHESIS. Never raises a label.
    """
    out: dict[str, ClaimLabel] = {}
    for claim, label in claim_labels.items():
        bundle = evidence.get(claim)
        if bundle is None:
            cap = ClaimLabel.HYPOTHESIS
        else:
            try:
                cap = ClaimLabel(bundle.label.upper())
            except ValueError:
                cap = ClaimLabel.UNKNOWN
        out[claim] = label if _RANK[label] <= _RANK[cap] else cap
    return out


def attach_execution_evidence(
    bundles: dict[str, EvidenceBundle],
    execution_evidence_id: str,
    claim_match_fn=None,
) -> dict[str, EvidenceBundle]:
    """Link a PoT execution's evidence id to matching claims.

    Args:
        bundles: Existing evidence bundles (may be empty before synthesis).
        execution_evidence_id: Evidence id from the CodeExecutionCompleted event.
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
