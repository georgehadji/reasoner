"""Tests for vs_config models and registry."""
from __future__ import annotations

import pytest

from reasoner.vs_config import (
    VSDeploymentProfile,
    VSFeatureFlags,
    VSVerticalConfig,
    VSVerticalRegistry,
)
from reasoner.reasoner_vs_constants import VS_K_GENERATION, VS_TAIL_THRESHOLD_RADIOLOGY


class TestVSDeploymentProfile:
    def test_enum_values(self) -> None:
        assert VSDeploymentProfile.LATENCY_SENSITIVE == "latency_sensitive"
        assert VSDeploymentProfile.BALANCED == "balanced"
        assert VSDeploymentProfile.MAX_ACCURACY == "max_accuracy"


class TestVSFeatureFlags:
    def test_all_flags_default_true(self) -> None:
        flags = VSFeatureFlags()
        for name, value in flags.model_dump().items():
            assert value is True, f"{name} should default to True"

    def test_all_disabled_sets_all_false(self) -> None:
        flags = VSFeatureFlags.all_disabled()
        for name, value in flags.model_dump().items():
            assert value is False, f"{name} should be False after all_disabled()"

    def test_all_disabled_returns_vs_feature_flags_instance(self) -> None:
        flags = VSFeatureFlags.all_disabled()
        assert isinstance(flags, VSFeatureFlags)

    def test_partial_override(self) -> None:
        flags = VSFeatureFlags(probe_generation=False)
        assert flags.probe_generation is False
        assert flags.decomposition is True

    def test_flag_count_matches_fields(self) -> None:
        assert len(VSFeatureFlags.model_fields) == 9


class TestVSVerticalConfig:
    def test_valid_config(self) -> None:
        config = VSVerticalConfig(domain="legal", k=5, tail_threshold=0.08)
        assert config.domain == "legal"
        assert config.k == 5
        assert config.tail_threshold == pytest.approx(0.08)

    def test_default_generation_strategy(self) -> None:
        config = VSVerticalConfig(domain="x", k=2, tail_threshold=0.1)
        assert config.generation_strategy == "best_verifiable"

    def test_default_probe_template_empty(self) -> None:
        config = VSVerticalConfig(domain="x", k=2, tail_threshold=0.1)
        assert config.probe_template == ""

    def test_default_compliance_flags_empty_list(self) -> None:
        config = VSVerticalConfig(domain="x", k=2, tail_threshold=0.1)
        assert config.compliance_flags == []

    def test_k_too_large_raises(self) -> None:
        with pytest.raises(ValueError, match="k > 20 is excessive"):
            VSVerticalConfig(domain="x", k=21, tail_threshold=0.1)

    def test_k_boundary_accepted(self) -> None:
        config = VSVerticalConfig(domain="x", k=20, tail_threshold=0.1)
        assert config.k == 20

    def test_k_below_two_raises(self) -> None:
        with pytest.raises(Exception):  # pydantic ge=2
            VSVerticalConfig(domain="x", k=1, tail_threshold=0.1)

    def test_empty_domain_raises(self) -> None:
        with pytest.raises(Exception):  # pydantic min_length=1
            VSVerticalConfig(domain="", k=2, tail_threshold=0.1)

    def test_tail_threshold_zero_raises(self) -> None:
        with pytest.raises(Exception):  # pydantic gt=0
            VSVerticalConfig(domain="x", k=2, tail_threshold=0.0)

    def test_tail_threshold_one_raises(self) -> None:
        with pytest.raises(Exception):  # pydantic lt=1
            VSVerticalConfig(domain="x", k=2, tail_threshold=1.0)


class TestVSVerticalRegistry:
    def setup_method(self) -> None:
        VSVerticalRegistry.clear()

    def teardown_method(self) -> None:
        VSVerticalRegistry.clear()

    def test_register_and_get(self) -> None:
        config = VSVerticalConfig(domain="aerospace", k=4, tail_threshold=0.06)
        VSVerticalRegistry.register(config)
        retrieved = VSVerticalRegistry.get("aerospace")
        assert retrieved.domain == "aerospace"
        assert retrieved.k == 4

    def test_missing_domain_returns_default(self) -> None:
        default = VSVerticalRegistry.get("unknown")
        assert default.domain == "default"
        assert default.k == VS_K_GENERATION
        assert default.tail_threshold == VS_TAIL_THRESHOLD_RADIOLOGY

    def test_overwrite_existing(self) -> None:
        c1 = VSVerticalConfig(domain="same", k=3, tail_threshold=0.1)
        c2 = VSVerticalConfig(domain="same", k=8, tail_threshold=0.2)
        VSVerticalRegistry.register(c1)
        VSVerticalRegistry.register(c2)
        assert VSVerticalRegistry.get("same").k == 8

    def test_clear_removes_all(self) -> None:
        VSVerticalRegistry.register(VSVerticalConfig(domain="x", k=2, tail_threshold=0.1))
        VSVerticalRegistry.clear()
        default = VSVerticalRegistry.get("x")
        assert default.domain == "default"
