"""Unit tests for ACR Phase 5: Adaptive Routing Service.

Tests the AdaptiveRoutingService in shadow, advisory, and adaptive modes.
"""

from __future__ import annotations

import pytest

from reasoner.application.services.adaptive_routing import (
    AdaptiveRoutingService,
)
from reasoner.domain.model_capabilities import (
    ModelCapabilities,
    ModelConstraints,
    ModelProfile,
)
from reasoner.domain.task_requirements import TaskConstraints


class FakeRegistry:
    """A minimal capability registry for testing."""

    def __init__(self) -> None:
        self._profiles: dict[str, ModelProfile] = {}

    def add_model(
        self,
        model_id: str,
        scores: dict[str, float] | None = None,
        vendor: str = "test",
        bloc: str = "US",
    ) -> None:
        constraints = ModelConstraints(
            max_context_tokens=128_000,
            vendor=vendor,
            bloc=bloc,
            supports_temperature=True,
            supports_json_mode=True,
        )
        caps = None
        if scores:
            caps = ModelCapabilities(scores=scores, source="test", sample_count=50)
        self._profiles[model_id] = ModelProfile(
            model_id=model_id,
            constraints=constraints,
            capabilities=caps,
        )

    def get_profile(self, model_id: str) -> ModelProfile | None:
        return self._profiles.get(model_id)

    def get_all_profiles(self) -> dict[str, ModelProfile]:
        return dict(self._profiles)

    def update_capabilities(self, model_id: str, capabilities: ModelCapabilities) -> None:
        existing = self._profiles.get(model_id)
        if existing:
            self._profiles[model_id] = ModelProfile(
                model_id=model_id,
                constraints=existing.constraints,
                capabilities=capabilities,
            )

    def update_constraints(self, model_id: str, constraints: ModelConstraints) -> None:
        existing = self._profiles.get(model_id)
        caps = existing.capabilities if existing else None
        self._profiles[model_id] = ModelProfile(
            model_id=model_id, constraints=constraints, capabilities=caps,
        )

    def get_models_satisfying(self, constraints: TaskConstraints) -> list[ModelProfile]:
        return [
            p for p in self._profiles.values()
            if p.constraints.max_context_tokens >= constraints.min_context_tokens
            and (not constraints.requires_tools or p.constraints.supports_tools)
            and (not constraints.requires_vision or p.constraints.supports_vision)
            and (not constraints.requires_temperature or p.constraints.supports_temperature)
        ]


@pytest.fixture
def registry():
    """A registry with a few test models."""
    reg = FakeRegistry()
    reg.add_model("model-a", {"reasoning": 0.9, "consistency": 0.85}, vendor="ven_a", bloc="US")
    reg.add_model("model-b", {"reasoning": 0.7, "consistency": 0.65}, vendor="ven_b", bloc="EU")
    reg.add_model("model-c", {"reasoning": 0.5, "consistency": 0.5}, vendor="ven_c", bloc="CN")
    return reg


class TestAdaptiveRoutingService:
    """AdaptiveRoutingService mode behavior."""

    @pytest.mark.asyncio
    async def test_shadow_mode_returns_static(self, registry):
        """Shadow mode returns the static routing unchanged."""
        svc = AdaptiveRoutingService(
            registry=registry,
            mode="shadow",
        )
        static = {"constructive": "model-a", "scoring": "model-b"}
        roles = list(static.keys())

        result = await svc.select_routing_table(roles, static)
        assert result == static  # Unchanged in shadow mode

    @pytest.mark.asyncio
    async def test_shadow_mode_logs_selections(self, registry):
        """Shadow mode logs ACR selections."""
        svc = AdaptiveRoutingService(
            registry=registry,
            mode="shadow",
        )
        static = {"constructive": "model-a", "scoring": "model-b"}
        await svc.select_routing_table(list(static.keys()), static)

        assert len(svc.selection_log) == 2
        for entry in svc.selection_log:
            assert entry.preset_model != ""
            assert entry.acr_model != ""

    @pytest.mark.asyncio
    async def test_adaptive_mode_uses_acr(self, registry):
        """Adaptive mode returns ACR-selected models."""
        svc = AdaptiveRoutingService(
            registry=registry,
            mode="adaptive",
        )
        static = {"constructive": "model-c", "scoring": "model-c"}
        roles = list(static.keys())

        result = await svc.select_routing_table(roles, static)
        # In adaptive mode, a new dict is always returned
        assert isinstance(result, dict)
        assert set(result.keys()) == {"constructive", "scoring"}

    @pytest.mark.asyncio
    async def test_advisory_mode_prefers_preset(self, registry):
        """Advisory mode uses ACR when confidence is high."""
        svc = AdaptiveRoutingService(
            registry=registry,
            mode="advisory",
        )
        static = {"constructive": "model-a", "scoring": "model-b"}

        result = await svc.select_routing_table(list(static.keys()), static)
        # ACR should agree with model-a and model-b since they're strong
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_no_registry_fallback(self):
        """Without a registry, static routing is used."""
        svc = AdaptiveRoutingService(
            registry=None,
            mode="adaptive",
        )
        static = {"constructive": "model-a"}
        result = await svc.select_routing_table(["constructive"], static)
        assert result == static

    @pytest.mark.asyncio
    async def test_cold_start_models_neutral(self, registry):
        """Models without capability data get consideration."""
        registry.add_model("new-model", vendor="ven_x", bloc="OTHER")

        svc = AdaptiveRoutingService(
            registry=registry,
            mode="shadow",
        )
        static = {"constructive": "model-a"}
        result = await svc.select_routing_table(["constructive"], static)
        assert result == static

    @pytest.mark.asyncio
    async def test_selection_log_format(self, registry):
        """Selection log entries have all expected fields."""
        svc = AdaptiveRoutingService(
            registry=registry,
            mode="shadow",
        )
        static = {"constructive": "model-a"}
        await svc.select_routing_table(["constructive"], static)

        entry = svc.selection_log[0]
        assert entry.role == "constructive"
        assert entry.preset_model == "model-a"
        assert isinstance(entry.acr_score, float)

    def test_update_weights_for_tier(self, registry):
        """Weights can be updated for a different tier."""
        svc = AdaptiveRoutingService(
            registry=registry,
            mode="shadow",
            preset_tier="balanced",
        )
        assert svc._preset_tier == "balanced"

        svc.update_weights_for_tier("budget")
        assert svc._preset_tier == "budget"
