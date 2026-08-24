"""Tests for vertical domain configurations."""
from __future__ import annotations

from reasoner.reasoner_vs_constants import (
    VS_K_RADIOLOGY_GENERATION,
    VS_TAIL_THRESHOLD_AEROSPACE,
    VS_TAIL_THRESHOLD_LEGAL,
    VS_TAIL_THRESHOLD_RADIOLOGY,
)
from reasoner.vs_config import VSVerticalConfig, VSVerticalRegistry


class TestVerticalRegistry:
    def setup_method(self) -> None:
        VSVerticalRegistry.clear()

    def teardown_method(self) -> None:
        VSVerticalRegistry.clear()

    def test_register_and_get(self) -> None:
        config = VSVerticalConfig(domain="test_domain", k=5, tail_threshold=0.1)
        VSVerticalRegistry.register(config)
        retrieved = VSVerticalRegistry.get("test_domain")
        assert retrieved.domain == "test_domain"
        assert retrieved.k == 5

    def test_missing_domain_returns_default(self) -> None:
        default = VSVerticalRegistry.get("unknown")
        assert default.domain == "default"

    def test_radiology_config_values(self) -> None:
        from reasoner.vs_vertical_configs.radiology_config import RADIOLOGY_CONFIG
        assert RADIOLOGY_CONFIG.domain == "radiology"
        assert RADIOLOGY_CONFIG.k == VS_K_RADIOLOGY_GENERATION
        assert RADIOLOGY_CONFIG.tail_threshold == VS_TAIL_THRESHOLD_RADIOLOGY
        assert "fda_510k" in RADIOLOGY_CONFIG.compliance_flags

    def test_legal_config_values(self) -> None:
        from reasoner.vs_vertical_configs.legal_config import LEGAL_CONFIG
        assert LEGAL_CONFIG.domain == "legal"
        assert LEGAL_CONFIG.tail_threshold == VS_TAIL_THRESHOLD_LEGAL
        assert "human_review_on_low_prob" in LEGAL_CONFIG.compliance_flags

    def test_aerospace_config_values(self) -> None:
        from reasoner.vs_vertical_configs.aerospace_config import AEROSPACE_CONFIG
        assert AEROSPACE_CONFIG.domain == "aerospace"
        assert AEROSPACE_CONFIG.tail_threshold == VS_TAIL_THRESHOLD_AEROSPACE
        assert "cmmc_lvl2" in AEROSPACE_CONFIG.compliance_flags

    def test_auto_register_on_import(self) -> None:
        # Re-import modules to trigger registration after clear
        import importlib

        from reasoner.vs_vertical_configs import aerospace_config, legal_config, radiology_config
        importlib.reload(radiology_config)
        importlib.reload(legal_config)
        importlib.reload(aerospace_config)
        assert VSVerticalRegistry.get("radiology").domain == "radiology"
        assert VSVerticalRegistry.get("legal").domain == "legal"
        assert VSVerticalRegistry.get("aerospace").domain == "aerospace"
