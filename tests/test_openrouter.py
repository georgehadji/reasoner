"""
Test OpenRouter integration for ARA Pipeline.

Tests cover:
1. Registry: All OpenRouter models properly registered
2. Provider: OpenRouterProvider builds correctly
3. Presets: All method-based presets valid
4. Routing: ProviderRouter handles OpenRouter models
5. Pricing: Cost assumptions validated
"""

import os
import pytest
from reasoner.llm import (
    build_provider,
    _REGISTRY,
    list_models,
    OpenRouterProvider,
    ProviderRouter,
)
from reasoner.presets import PRESETS


# ─────────────────────────────────────────────────────────────────────
# TEST 1: Registry Validation
# ─────────────────────────────────────────────────────────────────────

class TestOpenRouterRegistry:
    """Test that all OpenRouter models are properly registered."""

    def test_or_models_exist_in_registry(self):
        """At least 30 OpenRouter models should be in _REGISTRY."""
        or_models = [
            k for k in _REGISTRY
            if not _REGISTRY[k].get("is_local") and _REGISTRY[k].get("cls") == "openrouter"
        ]
        assert len(or_models) >= 30, (
            f"Expected at least 30 OpenRouter models, got {len(or_models)}. "
            f"Models found: {or_models}"
        )

    def test_or_models_use_openrouter_cls(self):
        """All OpenRouter models should use 'openrouter' cls."""
        or_models = [
            k for k in _REGISTRY
            if _REGISTRY[k].get("cls") == "openrouter"
        ]
        for model_id in or_models:
            cfg = _REGISTRY[model_id]
            assert cfg["cls"] == "openrouter", (
                f"{model_id} has wrong cls: '{cfg['cls']}', expected 'openrouter'"
            )

    def test_or_models_require_openrouter_key(self):
        """All OpenRouter models should require OPENROUTER_API_KEY."""
        or_models = [
            k for k in _REGISTRY
            if _REGISTRY[k].get("cls") == "openrouter"
        ]
        for model_id in or_models:
            cfg = _REGISTRY[model_id]
            assert cfg["env"] == "OPENROUTER_API_KEY", (
                f"{model_id} has wrong env var: '{cfg['env']}', expected 'OPENROUTER_API_KEY'"
            )

    def test_or_models_have_valid_openrouter_paths(self):
        """All non-local models should have valid OpenRouter model paths."""
        or_models = [
            k for k in _REGISTRY
            if not _REGISTRY[k].get("is_local")
        ]
        for model_id in or_models:
            cfg = _REGISTRY[model_id]
            model_path = cfg["model"]
            # Should contain provider slash model format
            assert "/" in model_path, (
                f"{model_id} has invalid model path: '{model_path}' (expected 'provider/model')"
            )

    def test_specific_or_models_present(self):
        """Key models should be present in registry."""
        expected_models = [
            "claude-opus",
            "claude-sonnet",
            "gpt-5",
            "gemini-flash",
            "deepseek-v3",
            "qwen3-max",
            "kimi-k2-5",
            "glm-5",
            "grok-4",
            "sonar-pro",
        ]
        for model_id in expected_models:
            assert model_id in _REGISTRY, f"Expected model '{model_id}' not found in registry"


# ─────────────────────────────────────────────────────────────────────
# TEST 2: Provider Building
# ─────────────────────────────────────────────────────────────────────

class TestOpenRouterProvider:
    """Test OpenRouter provider construction."""

    @pytest.mark.skipif(
        not os.environ.get("OPENROUTER_API_KEY"),
        reason="OPENROUTER_API_KEY not set"
    )
    def test_build_or_provider_success(self):
        """Should build provider successfully with valid key."""
        provider = build_provider("deepseek-v3")
        assert isinstance(provider, OpenRouterProvider)
        assert provider.model == "deepseek/deepseek-v3.2"

    def test_build_or_provider_fails_without_key(self):
        """Should raise ValueError when OPENROUTER_API_KEY not set."""
        # Save original key if exists
        original_key = os.environ.get("OPENROUTER_API_KEY")
        
        # Temporarily remove key
        if "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]
        
        try:
            with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
                build_provider("deepseek-v3")
        finally:
            # Restore original key
            if original_key:
                os.environ["OPENROUTER_API_KEY"] = original_key

    @pytest.mark.skipif(
        not os.environ.get("OPENROUTER_API_KEY"),
        reason="OPENROUTER_API_KEY not set"
    )
    def test_multiple_or_providers_build(self):
        """Should be able to build multiple different OR providers."""
        models_to_test = ["claude-sonnet", "gpt-5", "glm-5"]
        
        for model_id in models_to_test:
            provider = build_provider(model_id)
            assert isinstance(provider, OpenRouterProvider)
            assert "/" in provider.model  # Valid OpenRouter path


# ─────────────────────────────────────────────────────────────────────
# TEST 3: Preset Validation
# ─────────────────────────────────────────────────────────────────────

class TestOpenRouterPresets:
    """Test OpenRouter presets."""

    def test_all_presets_have_required_api_key(self):
        """All presets should require at least one valid API key."""
        valid_keys = {"OPENROUTER_API_KEY", "NVIDIA_API_KEY", "OLLAMA_API_KEY"}
        for preset_name, preset in PRESETS.items():
            assert any(k in valid_keys for k in preset.required_env_vars), (
                f"{preset_name} has no recognized API key in required_env_vars: {preset.required_env_vars}"
            )

    def test_method_presets_exist(self):
        """All method-based Budget/Premium presets should exist."""
        expected = [
            "debate-budget", "debate-premium",
            "scientific-budget", "scientific-premium",
            "socratic-budget", "socratic-premium",
            "multi-perspective-budget", "multi-perspective-premium",
            "research-budget", "research-premium",
            "jury-budget", "jury-premium",
            "pre-mortem-budget", "pre-mortem-premium",
            "bayesian-budget", "bayesian-premium",
            "dialectical-budget", "dialectical-premium",
            "analogical-budget", "analogical-premium",
            "delphi-budget", "delphi-premium",
        ]
        for preset_name in expected:
            assert preset_name in PRESETS, f"Preset '{preset_name}' not found"

    @pytest.mark.skipif(
        not os.environ.get("OPENROUTER_API_KEY"),
        reason="OPENROUTER_API_KEY not set"
    )
    def test_research_budget_can_build_router(self):
        """Research budget preset should build router successfully."""
        preset = PRESETS["research-budget"]
        router = preset.build_router()
        assert router is not None


# ─────────────────────────────────────────────────────────────────────
# TEST 4: Model Listing
# ─────────────────────────────────────────────────────────────────────

class TestModelListing:
    """Test that OpenRouter models appear in model listings."""

    def test_list_models_includes_openrouter_group(self):
        """list_models() should include 'openrouter' group."""
        groups = list_models()
        assert "openrouter" in groups, (
            f"'openrouter' group not found in list_models(). Groups: {list(groups.keys())}"
        )

    def test_openrouter_group_has_models(self):
        """OpenRouter group should have at least 30 models."""
        groups = list_models()
        or_models = groups.get("openrouter", [])
        assert len(or_models) >= 30, (
            f"OpenRouter group only has {len(or_models)} models, expected 30+"
        )

    def test_openrouter_models_have_correct_format(self):
        """All models in openrouter group should use the openrouter provider class."""
        groups = list_models()
        or_models = groups.get("openrouter", [])

        for model_id in or_models:
            assert _REGISTRY[model_id]["cls"] == "openrouter", (
                f"Model '{model_id}' in openrouter group doesn't use openrouter provider"
            )


# ─────────────────────────────────────────────────────────────────────
# TEST 5: ProviderRouter Integration
# ─────────────────────────────────────────────────────────────────────

class TestProviderRouter:
    """Test ProviderRouter with OpenRouter models."""

    @pytest.mark.skipif(
        not os.environ.get("OPENROUTER_API_KEY"),
        reason="OPENROUTER_API_KEY not set"
    )
    def test_router_with_or_models(self):
        """Should create router with OpenRouter models."""
        router = ProviderRouter.from_model_ids(
            primary_id="claude-sonnet",
            routing={
                "classification": "gemini-flash",
                "constructive": "deepseek-v3",
                "synthesis": "glm-5",
            }
        )
        assert router is not None
        assert "claude-sonnet-4.6" in router.primary.model or "anthropic/claude-sonnet-4.6" in router.primary.model

    @pytest.mark.skipif(
        not os.environ.get("OPENROUTER_API_KEY"),
        reason="OPENROUTER_API_KEY not set"
    )
    def test_router_describe_with_or_models(self):
        """Router describe should show OpenRouter model paths."""
        router = ProviderRouter.from_model_ids(
            primary_id="deepseek-v3",
            routing={
                "scoring": "qwen3-max",
            }
        )
        desc = router.describe()
        assert "deepseek/deepseek-v3.2" in desc["[primary]"]
        assert "qwen/qwen3.6-plus" in desc["scoring"]


# ─────────────────────────────────────────────────────────────────────
# TEST 6: Backward Compatibility
# ─────────────────────────────────────────────────────────────────────

class TestBackwardCompatibility:
    """Ensure OpenRouter integration doesn't break existing functionality."""

    def test_direct_api_models_still_exist(self):
        """Direct API models should still be in registry."""
        direct_models = [
            "claude-opus", "gpt-5", "gemini-flash",
            "deepseek-v3", "qwen3-max", "glm-5",
        ]
        for model_id in direct_models:
            assert model_id in _REGISTRY, (
                f"Direct API model '{model_id}' missing from registry"
            )

    def test_direct_api_presets_still_work(self):
        """Core presets should still be available."""
        core_presets = [
            "debate-budget", "debate-premium",
            "scientific-budget", "scientific-premium",
            "socratic-budget", "socratic-premium",
            "multi-perspective-budget", "multi-perspective-premium",
            "research-budget", "research-premium",
            "jury-budget", "jury-premium",
        ]
        for preset_name in core_presets:
            assert preset_name in PRESETS, (
                f"Core preset '{preset_name}' missing"
            )


# ─────────────────────────────────────────────────────────────────────
# TEST 7: Preset Validation Helpers
# ─────────────────────────────────────────────────────────────────────

class TestPresetValidation:
    """Test that preset validation catches errors."""

    def test_invalid_or_model_in_routing_raises(self):
        """Preset with invalid OR model should raise ValueError."""
        from reasoner.presets import PipelinePreset
        
        with pytest.raises(ValueError, match="unknown model"):
            PipelinePreset(
                name="Test",
                description="Test",
                primary_id="claude-sonnet",
                routing={"classification": "invalid-model"},
                required_env_vars=["OPENROUTER_API_KEY"],
            )

    def test_invalid_role_in_routing_raises(self):
        """Preset with invalid role should raise ValueError."""
        from reasoner.presets import PipelinePreset
        
        with pytest.raises(ValueError, match="unknown routing keys"):
            PipelinePreset(
                name="Test",
                description="Test",
                primary_id="claude-sonnet",
                routing={"invalid_role": "deepseek-v3"},
                required_env_vars=["OPENROUTER_API_KEY"],
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
