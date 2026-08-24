"""Tests for ara_vs_constants — frozen numeric invariants."""
from __future__ import annotations

import pytest

from reasoner.reasoner_vs_constants import (
    PROFILE_NLI_BUDGET,
    VS_BEHAVIORAL_AUDIT_ENABLED,
    VS_CALIBRATION_ENABLED,
    VS_CLAIM_EXTRACTION_ENABLED,
    VS_CONFLICT_SURFACING_ENABLED,
    VS_COVERAGE_AUDIT_ENABLED,
    VS_DECOMPOSITION_ENABLED,
    VS_GENERATION_ENABLED,
    VS_K_CLAIMS,
    VS_K_COVERAGE,
    VS_K_DECOMPOSITION,
    VS_K_GENERATION,
    VS_K_PROBES,
    VS_K_RADIOLOGY_GENERATION,
    VS_PROBE_GENERATION_ENABLED,
    VS_TAIL_THRESHOLD_AEROSPACE,
    VS_TAIL_THRESHOLD_LEGAL,
    VS_TAIL_THRESHOLD_RADIOLOGY,
    VS_VERIFICATION_ROUTING_ENABLED,
    W_ENTROPY,
    W_NLI,
    W_RANK,
    W_SUPPORT,
    VSDeploymentProfile,
)


class TestCalibrationWeights:
    def test_weights_sum_to_one(self) -> None:
        assert W_ENTROPY + W_SUPPORT + W_NLI + W_RANK == pytest.approx(1.0)

    def test_each_weight_in_unit_interval(self) -> None:
        for name, weight in [
            ("W_ENTROPY", W_ENTROPY),
            ("W_SUPPORT", W_SUPPORT),
            ("W_NLI", W_NLI),
            ("W_RANK", W_RANK),
        ]:
            assert 0.0 < weight < 1.0, f"{name}={weight} outside (0,1)"


class TestTailThresholds:
    def test_all_thresholds_in_unit_interval(self) -> None:
        for name, threshold in [
            ("VS_TAIL_THRESHOLD_RADIOLOGY", VS_TAIL_THRESHOLD_RADIOLOGY),
            ("VS_TAIL_THRESHOLD_LEGAL", VS_TAIL_THRESHOLD_LEGAL),
            ("VS_TAIL_THRESHOLD_AEROSPACE", VS_TAIL_THRESHOLD_AEROSPACE),
        ]:
            assert 0.0 < threshold < 1.0, f"{name}={threshold} outside (0,1)"

    def test_threshold_ordering_by_risk(self) -> None:
        # Aerospace (most critical) < Legal < Radiology (most lenient)
        assert VS_TAIL_THRESHOLD_AEROSPACE < VS_TAIL_THRESHOLD_LEGAL
        assert VS_TAIL_THRESHOLD_LEGAL < VS_TAIL_THRESHOLD_RADIOLOGY


class TestKDefaults:
    def test_all_k_at_least_two(self) -> None:
        for name, k in [
            ("VS_K_DECOMPOSITION", VS_K_DECOMPOSITION),
            ("VS_K_GENERATION", VS_K_GENERATION),
            ("VS_K_PROBES", VS_K_PROBES),
            ("VS_K_COVERAGE", VS_K_COVERAGE),
            ("VS_K_CLAIMS", VS_K_CLAIMS),
            ("VS_K_RADIOLOGY_GENERATION", VS_K_RADIOLOGY_GENERATION),
        ]:
            assert k >= 2, f"{name}={k} must be >= 2"

    def test_radiology_k_higher_than_default(self) -> None:
        assert VS_K_RADIOLOGY_GENERATION > VS_K_GENERATION


class TestFeatureFlags:
    def test_all_feature_flags_default_true(self) -> None:
        flags = [
            VS_PROBE_GENERATION_ENABLED,
            VS_DECOMPOSITION_ENABLED,
            VS_COVERAGE_AUDIT_ENABLED,
            VS_GENERATION_ENABLED,
            VS_CALIBRATION_ENABLED,
            VS_CLAIM_EXTRACTION_ENABLED,
            VS_VERIFICATION_ROUTING_ENABLED,
            VS_CONFLICT_SURFACING_ENABLED,
            VS_BEHAVIORAL_AUDIT_ENABLED,
        ]
        for name, value in [
            ("VS_PROBE_GENERATION_ENABLED", VS_PROBE_GENERATION_ENABLED),
            ("VS_DECOMPOSITION_ENABLED", VS_DECOMPOSITION_ENABLED),
            ("VS_COVERAGE_AUDIT_ENABLED", VS_COVERAGE_AUDIT_ENABLED),
            ("VS_GENERATION_ENABLED", VS_GENERATION_ENABLED),
            ("VS_CALIBRATION_ENABLED", VS_CALIBRATION_ENABLED),
            ("VS_CLAIM_EXTRACTION_ENABLED", VS_CLAIM_EXTRACTION_ENABLED),
            ("VS_VERIFICATION_ROUTING_ENABLED", VS_VERIFICATION_ROUTING_ENABLED),
            ("VS_CONFLICT_SURFACING_ENABLED", VS_CONFLICT_SURFACING_ENABLED),
            ("VS_BEHAVIORAL_AUDIT_ENABLED", VS_BEHAVIORAL_AUDIT_ENABLED),
        ]:
            assert value is True, f"{name} should default to True"


class TestDeploymentProfiles:
    def test_profile_nli_budget_monotonic(self) -> None:
        ls = PROFILE_NLI_BUDGET[VSDeploymentProfile.LATENCY_SENSITIVE]
        bal = PROFILE_NLI_BUDGET[VSDeploymentProfile.BALANCED]
        maxa = PROFILE_NLI_BUDGET[VSDeploymentProfile.MAX_ACCURACY]
        assert ls < bal < maxa

    def test_all_profiles_have_budget(self) -> None:
        for profile in [
            VSDeploymentProfile.LATENCY_SENSITIVE,
            VSDeploymentProfile.BALANCED,
            VSDeploymentProfile.MAX_ACCURACY,
        ]:
            assert profile in PROFILE_NLI_BUDGET
            assert isinstance(PROFILE_NLI_BUDGET[profile], int)
            assert PROFILE_NLI_BUDGET[profile] >= 1
