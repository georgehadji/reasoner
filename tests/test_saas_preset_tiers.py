# tests/test_saas_preset_tiers.py
from reasoner.domain.saas import SubscriptionTier
from reasoner.presets import PRESETS, get_preset_tier

# NOTE: PipelinePreset.required_tier is never populated by any entry in
# preset_registry.py — it stays at the dataclass default (FREE) for every
# preset, including all 24 "-premium" ones. The actual source of truth is
# get_preset_tier(), which derives PRO from the "-premium" suffix against
# the raw registry dict (domain/preset_core.py). That derivation isn't wired
# into any route yet (api/dependencies.py's require_tier() imports it but
# never calls it — tracked as TODO(#501), out of scope here), but it's the
# function that's actually correct, so these tests check it instead of the
# vestigial .required_tier attribute.


def test_all_budget_presets_are_free():
    for name in PRESETS:
        if name.endswith("-budget"):
            assert get_preset_tier(name) == SubscriptionTier.FREE, f"{name} should be FREE"


def test_all_premium_presets_require_pro():
    for name in PRESETS:
        if name.endswith("-premium") or name == "image-gen-premium":
            assert get_preset_tier(name) == SubscriptionTier.PRO, f"{name} should be PRO"


def test_get_preset_tier_unknown_preset_defaults_free():
    assert get_preset_tier("nonexistent-preset") == SubscriptionTier.FREE
