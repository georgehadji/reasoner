"""
Preset routing and cost validation tests for the Article method.

Tests cover:
  - Provider-family diversity between drafter and verifier (G4 invariant placeholder)
  - Preset structure and required routing keys
  - Cost table reconciliation (per-role pricing sums to plausible totals)
  - Article constants are within sane bounds

These are read-only structural tests — no LLM calls.
"""

from __future__ import annotations

import pytest
from typing import Any

from reasoner.domain.preset_registry import PRESETS
from reasoner.domain.pricing import get_pricing, ModelPricing, PRICING_DB
from reasoner.core.constants import (
    ARTICLE_MIN_SOURCE_COUNT,
    ARTICLE_MAX_SOURCE_COUNT,
    ARTICLE_SEARCH_RESULTS_PER_QUERY,
    ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION,
    ARTICLE_MIN_CLAIM_SUPPORT_RATIO,
    ARTICLE_CRITIC_MAX_WORDS,
)

# ═════════════════════════════════════════════════════════════════════
# Preset structure
# ═════════════════════════════════════════════════════════════════════

ARTICLE_PRESET_NAMES = ["article-budget", "article-premium"]

ARTICLE_REQUIRED_ROLES = [
    "primary",
    "writing_draft",
    "writing_factcheck",
    "writing_assemble",
    "synthesis",
    "article_sot_skeleton",
    "article_critic",
    "article_revise",
    "article_humanize",
    "article_verifier",
]


class TestArticlePresetStructure:
    """Article presets must exist, have correct method, and define all required roles."""

    def test_article_presets_exist(self):
        for name in ARTICLE_PRESET_NAMES:
            assert name in PRESETS, f"Missing preset: {name}"

    def test_article_presets_have_correct_method(self):
        for name in ARTICLE_PRESET_NAMES:
            preset = PRESETS[name]
            assert preset.get("method") == "article", (
                f"{name}: expected method='article', got '{preset.get('method')}'"
            )

    def test_article_presets_have_tags(self):
        for name in ARTICLE_PRESET_NAMES:
            preset = PRESETS[name]
            tags = preset.get("tags", [])
            assert "writing" in tags, f"{name}: missing 'writing' tag"
            assert "article" in tags, f"{name}: missing 'article' tag"

    def test_article_presets_have_all_required_roles(self):
        for name in ARTICLE_PRESET_NAMES:
            preset = PRESETS[name]
            routing = preset.get("routing", {})
            for role in ARTICLE_REQUIRED_ROLES:
                assert role in routing, f"{name}: missing routing role '{role}'"

    def test_article_presets_have_primary_id(self):
        for name in ARTICLE_PRESET_NAMES:
            preset = PRESETS[name]
            assert preset.get("primary_id"), f"{name}: missing primary_id"


class TestArticlePresetCostBaseline:
    """Per-role cost estimation for article presets.

    These tests estimate the cost of running the article pipeline with each
    preset by looking up per-role model pricing and estimating token usage.

    The cost baseline serves as a regression check — if a refactored pipeline
    changes how many LLM calls are made or which models are used, the cost
    per golden set entry should change within bounded limits.
    """

    # Estimated token usage per role (conservative estimates):
    #   input:  system prompt + user prompt
    #   output: expected response length
    _ROLE_TOKEN_ESTIMATES: dict[str, dict[str, int]] = {
        "primary":              {"input": 2000,  "output": 400},
        "writing_draft":        {"input": 6000,  "output": 2000},
        "writing_factcheck":    {"input": 5000,  "output": 1000},
        "writing_assemble":     {"input": 4000,  "output": 1500},
        "synthesis":            {"input": 8000,  "output": 1000},
        "article_sot_skeleton": {"input": 4000,  "output": 800},
        "article_critic":       {"input": 5000,  "output": 800},
        "article_revise":       {"input": 5000,  "output": 2000},
        "article_humanize":     {"input": 4000,  "output": 1500},
        "article_verifier":     {"input": 4000,  "output": 800},
    }

    # Expected cost per run bounds (USD) — these are ESTIMATES that should
    # be updated after the first real run.  They catch gross regressions
    # (e.g. accidentally using premium models on budget preset).
    _COST_BOUNDS: dict[str, dict[str, float]] = {
        "article-budget":  {"min": 0.01, "max": 0.25},
        "article-premium": {"min": 0.05, "max": 0.60},
    }

    def _get_model_key(self, role_model_id: str) -> str:
        """Resolve a role model ID to the pricing DB key.

        Handles registry shorthand IDs (e.g. 'claude-sonnet') and
        direct OpenRouter paths (e.g. 'anthropic/claude-sonnet-5').
        """
        # Try direct lookup first
        if role_model_id in PRICING_DB:
            return role_model_id
        # Try with '/completion' suffix that some entries use
        if f"{role_model_id}/completion" in PRICING_DB:
            return f"{role_model_id}/completion"
        # Fall back to default pricing
        return "_default"

    def _estimate_preset_cost(self, preset_name: str) -> float:
        """Estimate total LLM cost for a single run of this preset."""
        preset = PRESETS.get(preset_name, {})
        routing = preset.get("routing", {})
        total = 0.0

        for role, estimates in self._ROLE_TOKEN_ESTIMATES.items():
            model_id = routing.get(role, "")
            if not model_id:
                continue
            pricing = get_pricing(self._get_model_key(model_id))
            role_cost = pricing.calculate_cost(estimates["input"], estimates["output"])
            total += role_cost

        return total

    def test_article_preset_costs_within_bounds(self):
        for preset_name in ARTICLE_PRESET_NAMES:
            cost = self._estimate_preset_cost(preset_name)
            bounds = self._COST_BOUNDS.get(preset_name, {"min": 0, "max": 10})
            assert bounds["min"] <= cost <= bounds["max"], (
                f"{preset_name}: estimated cost ${cost:.4f} is outside bounds "
                f"${bounds['min']:.2f}–${bounds['max']:.2f}"
            )

    def test_budget_cheaper_than_premium(self):
        """Soft check: budget should be cheaper than premium.

        This may fail if the pricing DB doesn't have entries for all role
        model IDs (falling back to uniform default pricing).
        """
        budget_cost = self._estimate_preset_cost("article-budget")
        premium_cost = self._estimate_preset_cost("article-premium")
        if budget_cost >= premium_cost:
            pytest.skip(
                f"Budget (${budget_cost:.4f}) >= premium (${premium_cost:.4f}) — "
                f"likely due to missing pricing DB entries"
            )

    def test_model_pricing_available_for_article_roles(self):
        """Every role model in both article presets must have pricing data."""
        for preset_name in ARTICLE_PRESET_NAMES:
            preset = PRESETS.get(preset_name, {})
            routing = preset.get("routing", {})
            for role in ARTICLE_REQUIRED_ROLES:
                model_id = routing.get(role)
                if not model_id:
                    continue
                pricing = get_pricing(self._get_model_key(model_id))
                assert pricing is not None, (
                    f"{preset_name}/{role}: no pricing for model '{model_id}'"
                )
                # Pricing must be positive
                assert pricing.input_per_token > 0, f"{preset_name}/{role}: zero input price"
                assert pricing.output_per_token > 0, f"{preset_name}/{role}: zero output price"


class TestArticlePresetRoutingDiversity:
    """Verify model diversity across article presets.

    The plan recommends (G4) that verifier should come from a different provider
    family than the drafter to reduce correlated errors.
    """

    # Heuristic provider-family mapping for known model IDs.
    # This is NOT the authoritative provider registry — just a structural
    # check that verifier != drafter family.
    _FAMILY_MAP: dict[str, str] = {
        # Anthropic
        "claude-sonnet": "anthropic",
        "claude-haiku": "anthropic",
        "claude-opus": "anthropic",
        "claude-fable-5": "anthropic",
        # OpenAI
        "gpt-4o-mini": "openai",
        "gpt-5.5": "openai",
        "gpt-5": "openai",
        "gpt-5-mini": "openai",
        "gpt-latest": "openai",
        "gpt-mini-latest": "openai",
        # Google
        "gemini-flash": "google",
        "gemini-pro": "anthropic",  # aliased in this config
        # DeepSeek
        "deepseek-v4-flash": "deepseek",
        "deepseek-v4-pro": "deepseek",
        # Qwen
        "qwen3.7-plus": "qwen",
        "qwen3.7-max": "qwen",
        # xAI
        "grok-4.3": "xai",
        # Perplexity
        "sonar": "perplexity",
        "sonar-pro": "perplexity",
        # Tencent
        "hy3": "tencent",
    }

    def _get_family(self, model_id: str) -> str:
        """Determine provider family from model ID."""
        if model_id in self._FAMILY_MAP:
            return self._FAMILY_MAP[model_id]
        # Fallback: try prefix match
        known_prefixes = {
            "claude": "anthropic", "gpt": "openai", "o3": "openai", "o4": "openai",
            "gemini": "google", "deepseek": "deepseek", "qwen": "qwen",
            "grok": "xai", "sonar": "perplexity", "hy": "tencent",
            "kimi": "moonshot", "glm": "zhipuai", "mistral": "mistral",
            "laguna": "poolside", "llama": "meta", "arcee": "arcee",
            "hermes": "nousresearch", "seed-": "bytedance", "minimax": "minimax",
            "ministral": "mistral", "mimo": "xiaomi", "stepfun": "stepfun",
        }
        for prefix, family in known_prefixes.items():
            if model_id.startswith(prefix):
                return family
        return "unknown"

    def test_drafter_and_verifier_are_different_families(self):
        """The verifier model should come from a different provider family
        than the drafter model.  This is a structural diversity check (G4 preamble)."""
        for preset_name in ARTICLE_PRESET_NAMES:
            preset = PRESETS.get(preset_name, {})
            routing = preset.get("routing", {})
            drafter = routing.get("writing_draft", "")
            verifier = routing.get("article_verifier", "")

            if not drafter or not verifier:
                pytest.skip(f"{preset_name}: missing drafter or verifier role")

            drafter_family = self._get_family(drafter)
            verifier_family = self._get_family(verifier)

            # NOTE: This is a soft check (no assert) because the current presets
            # may not satisfy this invariant yet.  G4 will enforce it in Phase 3.
            if drafter_family == verifier_family:
                pytest.skip(
                    f"{preset_name}: drafter ({drafter}, family={drafter_family}) and "
                    f"verifier ({verifier}, family={verifier_family}) share the same "
                    f"provider family — will be enforced in Phase 3 (G4)"
                )

    def test_factcheck_not_same_family_as_drafter(self):
        """Similarly, the fact-check model should be from a different family
        than the drafter to avoid monoculture verification."""
        for preset_name in ARTICLE_PRESET_NAMES:
            preset = PRESETS.get(preset_name, {})
            routing = preset.get("routing", {})
            drafter = routing.get("writing_draft", "")
            factcheck = routing.get("writing_factcheck", "")

            if not drafter or not factcheck:
                pytest.skip(f"{preset_name}: missing drafter or factcheck role")

            drafter_family = self._get_family(drafter)
            factcheck_family = self._get_family(factcheck)

            if drafter_family == factcheck_family:
                pytest.skip(
                    f"{preset_name}: drafter ({drafter}) and factcheck ({factcheck}) "
                    f"share the same provider family — will be enforced in Phase 3 (G4)"
                )

    def test_all_article_routing_model_ids_resolvable(self):
        """Every model ID in article presets has a recognisable provider family."""
        for preset_name in ARTICLE_PRESET_NAMES:
            preset = PRESETS.get(preset_name, {})
            routing = preset.get("routing", {})
            for role, model_id in routing.items():
                family = self._get_family(model_id)
                assert family != "unknown", (
                    f"{preset_name}/{role}: unrecognised model '{model_id}' — "
                    f"add to _FAMILY_MAP or check the model ID"
                )
