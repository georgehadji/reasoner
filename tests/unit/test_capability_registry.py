"""Unit tests for ACR Phase 2: Capability Registry.

Tests domain objects and the CapabilityRegistry implementation.
"""

from __future__ import annotations

import json

import pytest

from reasoner.domain.model_capabilities import (
    ModelCapabilities,
    ModelConstraints,
    ModelProfile,
)
from reasoner.domain.task_requirements import TaskConstraints


class TestModelConstraints:
    """ModelConstraints value object behavior."""

    def test_defaults(self):
        """Default constraints have sensible zero values."""
        c = ModelConstraints()
        assert c.max_context_tokens == 4096
        assert c.cost_per_1k_input_usd == 0.0
        assert c.supports_tools is False

    def test_full_construction(self):
        """All constraint fields can be set."""
        c = ModelConstraints(
            max_context_tokens=1_000_000,
            cost_per_1k_input_usd=0.002,
            cost_per_1k_output_usd=0.010,
            supports_tools=True,
            supports_vision=True,
            supports_json_mode=True,
            supports_temperature=True,
            vendor="anthropic",
            bloc="US",
        )
        assert c.max_context_tokens == 1_000_000
        assert c.vendor == "anthropic"
        assert c.bloc == "US"


class TestModelCapabilities:
    """ModelCapabilities value object behavior."""

    def test_empty_scores(self):
        """Empty capabilities return default score."""
        caps = ModelCapabilities()
        assert caps.get_score("reasoning") == 0.0
        assert caps.get_score("coding", 0.5) == 0.5

    def test_with_scores(self):
        """Capabilities with scores return correct values."""
        caps = ModelCapabilities(
            scores={"reasoning": 0.92, "coding": 0.88},
            source="benchmark_v1",
            measured_at="2026-07-01T00:00:00Z",
            sample_count=100,
        )
        assert caps.get_score("reasoning") == 0.92
        assert caps.get_score("coding") == 0.88
        assert caps.get_score("creativity", 0.5) == 0.5
        assert caps.source == "benchmark_v1"


class TestModelProfile:
    """ModelProfile combining constraints and capabilities."""

    def test_minimal(self):
        """Minimal profile with just constraints."""
        constraints = ModelConstraints(vendor="openai", bloc="US")
        profile = ModelProfile(model_id="gpt-5-nano", constraints=constraints)
        assert profile.model_id == "gpt-5-nano"
        assert profile.has_capabilities is False
        assert profile.capabilities is None

    def test_full(self):
        """Full profile with constraints and capabilities."""
        constraints = ModelConstraints(
            max_context_tokens=1_000_000,
            cost_per_1k_input_usd=0.002,
            cost_per_1k_output_usd=0.010,
            vendor="anthropic",
            bloc="US",
        )
        caps = ModelCapabilities(
            scores={"reasoning": 0.95, "writing": 0.90},
            source="telemetry_7d",
            sample_count=500,
        )
        profile = ModelProfile(
            model_id="claude-sonnet",
            constraints=constraints,
            capabilities=caps,
        )
        assert profile.has_capabilities is True
        assert profile.capabilities.get_score("reasoning") == 0.95
        assert profile.cost_per_1k_total_usd == 0.012  # 0.002 + 0.010


class TestCapabilityRegistry:
    """CapabilityRegistry bootstrap and query behavior."""

    @pytest.fixture
    def registry(self, tmp_path):
        """Create a registry pointing to a temp profiles file."""
        from reasoner.infrastructure.llm.capability_registry import CapabilityRegistry
        profiles_path = str(tmp_path / "profiles.json")
        return CapabilityRegistry(profiles_path=profiles_path)

    def test_bootstrap_has_models(self, registry):
        """Registry bootstraps models from whitelist."""
        profiles = registry.get_all_profiles()
        assert len(profiles) > 10  # We have many models
        # Key models should be present
        for key in ["claude-sonnet", "gpt-5", "deepseek-v4-flash", "qwen3.7-plus"]:
            assert key in profiles, f"Missing model: {key}"

    def test_get_profile_known(self, registry):
        """Known model returns full profile."""
        profile = registry.get_profile("claude-sonnet")
        assert profile is not None
        assert profile.model_id == "claude-sonnet"
        assert profile.constraints.vendor != ""

    def test_get_profile_unknown(self, registry):
        """Unknown model returns None."""
        profile = registry.get_profile("nonexistent-model-v99")
        assert profile is None

    def test_constraints_populated(self, registry):
        """Known models have populated constraints from hints."""
        profile = registry.get_profile("claude-sonnet")
        assert profile is not None
        c = profile.constraints
        assert c.max_context_tokens == 1_000_000
        assert c.cost_per_1k_input_usd == 0.002  # $2/M / 1000
        assert c.cost_per_1k_output_usd == 0.010  # $10/M / 1000
        assert c.supports_tools is True
        assert c.supports_vision is True
        assert c.bloc == "US"
        assert c.vendor == "anthropic"

    def test_update_capabilities(self, registry):
        """Updating capabilities replaces them in the profile."""
        caps = ModelCapabilities(
            scores={"reasoning": 0.85, "coding": 0.75},
            source="benchmark_v1",
            measured_at="2026-07-01T00:00:00Z",
            sample_count=50,
        )
        registry.update_capabilities("claude-sonnet", caps)
        profile = registry.get_profile("claude-sonnet")
        assert profile is not None
        assert profile.has_capabilities is True
        assert profile.capabilities.get_score("reasoning") == 0.85
        assert profile.capabilities.source == "benchmark_v1"

    def test_update_persists_to_disk(self, registry, tmp_path):
        """Updated capabilities are persisted to JSON."""
        caps = ModelCapabilities(
            scores={"reasoning": 0.80},
            source="test",
            measured_at="2026-07-01T00:00:00Z",
            sample_count=10,
        )
        registry.update_capabilities("gpt-5-nano", caps)

        # Read back the file
        profiles_path = str(tmp_path / "profiles.json")
        with open(profiles_path) as f:
            data = json.load(f)
        assert "gpt-5-nano" in data["capabilities"]
        assert data["capabilities"]["gpt-5-nano"]["scores"]["reasoning"] == 0.80

    def test_get_models_satisfying_context(self, registry):
        """Context window filtering works."""
        constraints = TaskConstraints(min_context_tokens=500_000)
        models = registry.get_models_satisfying(constraints)
        # claude-haiku has 200K ctx — should be excluded
        for m in models:
            assert m.constraints.max_context_tokens >= 500_000

    def test_get_models_satisfying_tools(self, registry):
        """Tool support filtering works."""
        constraints = TaskConstraints(requires_tools=True)
        models = registry.get_models_satisfying(constraints)
        for m in models:
            assert m.constraints.supports_tools is True

    def test_get_models_satisfying_bloc_exclusion(self, registry):
        """Bloc exclusion filtering works."""
        constraints = TaskConstraints(excluded_blocs=frozenset(["CN"]))
        models = registry.get_models_satisfying(constraints)
        for m in models:
            assert m.constraints.bloc != "CN"

    def test_bootstrap_loads_persisted(self, tmp_path):
        """Registry bootstraps from persisted file on construction."""
        from reasoner.infrastructure.llm.capability_registry import CapabilityRegistry

        # Pre-write a persisted file
        profiles_path = str(tmp_path / "profiles.json")
        pre_data = {
            "version": 1,
            "capabilities": {
                "claude-sonnet": {
                    "scores": {"reasoning": 0.91},
                    "source": "preloaded",
                    "measured_at": "2026-07-01T00:00:00Z",
                    "sample_count": 30,
                }
            },
        }
        with open(profiles_path, "w") as f:
            json.dump(pre_data, f)

        reg = CapabilityRegistry(profiles_path=profiles_path)
        profile = reg.get_profile("claude-sonnet")
        assert profile is not None
        assert profile.has_capabilities is True
        assert profile.capabilities.get_score("reasoning") == 0.91
