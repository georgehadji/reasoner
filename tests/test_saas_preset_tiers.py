# tests/test_saas_preset_tiers.py
import pytest
from reasoner.presets import PRESETS, get_preset_tier
from reasoner.domain.saas import SubscriptionTier


def test_all_budget_presets_are_free():
    for name, preset in PRESETS.items():
        if name.endswith("-budget"):
            assert preset.required_tier == SubscriptionTier.FREE, f"{name} should be FREE"


def test_all_premium_presets_require_pro():
    for name, preset in PRESETS.items():
        if name.endswith("-premium") or name == "image-gen-premium":
            assert preset.required_tier == SubscriptionTier.PRO, f"{name} should be PRO"


def test_get_preset_tier_unknown_preset_defaults_free():
    assert get_preset_tier("nonexistent-preset") == SubscriptionTier.FREE
