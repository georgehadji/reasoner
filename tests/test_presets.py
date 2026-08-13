"""
Tests for preset utilities: tier detection, method extraction, and agent mappings.
"""

import pytest
from reasoner.presets import (
    PRESETS,
    get_method_from_preset,
    get_preset_tier,
    get_preset_price_tier,
    FOLLOWUP_AGENT_MODELS,
)
from reasoner.domain.saas import SubscriptionTier

class TestGetPresetPriceTier:
    def test_all_budget_presets_return_budget(self):
        budget_presets = [pid for pid in PRESETS if pid.endswith("-budget")]
        assert len(budget_presets) >= 8
        for pid in budget_presets:
            assert get_preset_price_tier(pid) == "budget", f"Expected budget for {pid}"

    def test_all_premium_presets_return_premium(self):
        premium_presets = [pid for pid in PRESETS if pid.endswith("-premium")]
        assert len(premium_presets) >= 8
        for pid in premium_presets:
            assert get_preset_price_tier(pid) == "premium", f"Expected premium for {pid}"

    def test_unknown_preset_returns_unknown(self):
        assert get_preset_price_tier("random-preset") == "unknown"
        assert get_preset_price_tier("") == "unknown"

class TestGetPresetTierSaaS:
    def test_all_budget_presets_return_free(self):
        budget_presets = [pid for pid in PRESETS if pid.endswith("-budget")]
        for pid in budget_presets:
            assert get_preset_tier(pid) == SubscriptionTier.FREE, f"Expected FREE for {pid}"

    def test_all_premium_presets_return_pro(self):
        premium_presets = [pid for pid in PRESETS if pid.endswith("-premium")]
        for pid in premium_presets:
            assert get_preset_tier(pid) == SubscriptionTier.PRO, f"Expected PRO for {pid}"



class TestFollowupAgentModels:
    def test_budget_maps_to_kimi(self):
        assert FOLLOWUP_AGENT_MODELS["budget"] == "kimi-k2-6"

    def test_premium_maps_to_grok(self):
        assert FOLLOWUP_AGENT_MODELS["premium"] == "grok-4.3"


class TestGetMethodFromPreset:
    @pytest.mark.parametrize(
        "preset, expected_method",
        [
            ("multi-perspective-budget", "multi-perspective"),
            ("multi-perspective-premium", "multi-perspective"),
            ("debate-budget", "debate"),
            ("debate-premium", "debate"),
            ("scientific-budget", "scientific"),
            ("jury-premium", "jury"),
            ("research-budget", "research"),
            ("socratic-premium", "socratic"),
            ("pre-mortem-budget", "pre_mortem"),
            ("pre-mortem-premium", "pre_mortem"),
            ("bayesian-budget", "bayesian"),
            ("bayesian-premium", "bayesian"),
            ("dialectical-budget", "dialectical"),
            ("dialectical-premium", "dialectical"),
            ("analogical-budget", "analogical"),
            ("analogical-premium", "analogical"),
            ("delphi-budget", "delphi"),
            ("delphi-premium", "delphi"),
            ("cove-budget", "cove"),
            ("cove-premium", "cove"),
            ("sot-budget", "sot"),
            ("sot-premium", "sot"),
            ("tot-budget", "tot"),
            ("tot-premium", "tot"),
            ("pot-budget", "pot"),
            ("pot-premium", "pot"),
            ("self-discover-budget", "self_discover"),
            ("self-discover-premium", "self_discover"),
        ],
    )
    def test_method_extraction(self, preset, expected_method):
        assert get_method_from_preset(preset) == expected_method
