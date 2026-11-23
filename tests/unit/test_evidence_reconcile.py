"""Claim labels never exceed their evidence; search VERIFIED needs a retrieved URL."""

from reasoner.application.services.evidence_service import (
    apply_promotion_rules,
    reconcile_labels,
)
from reasoner.domain.core_types import EvidenceBundle
from reasoner.domain.models import ClaimLabel

V, H, U = ClaimLabel.VERIFIED, ClaimLabel.HYPOTHESIS, ClaimLabel.UNKNOWN


def test_verified_claim_capped_to_bundle_label():
    ev = {"a": EvidenceBundle(label="HYPOTHESIS", source="model")}
    assert reconcile_labels({"a": V}, ev) == {"a": H}


def test_verified_without_bundle_becomes_hypothesis():
    assert reconcile_labels({"a": V}, {}) == {"a": H}


def test_never_raises_a_label():
    ev = {"a": EvidenceBundle(label="VERIFIED", source="sensor")}
    assert reconcile_labels({"a": H, "b": U}, ev) == {"a": H, "b": U}


def test_sensor_verified_claim_stays_verified():
    ev = {"a": EvidenceBundle(label="VERIFIED", source="sensor")}
    assert reconcile_labels({"a": V}, ev) == {"a": V}


def test_model_verified_bundle_caps_claim_end_to_end():
    ev = apply_promotion_rules({"a": EvidenceBundle(label="VERIFIED", source="model")})
    assert reconcile_labels({"a": V}, ev) == {"a": H}


def test_bad_bundle_label_caps_to_unknown():
    ev = {"a": EvidenceBundle(label="bogus", source="sensor")}
    assert reconcile_labels({"a": V}, ev) == {"a": U}
