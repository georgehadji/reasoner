"""Preset resolution, routing validation, and router construction."""

from __future__ import annotations

import logging
import os
from typing import Any

from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.infrastructure.llm.registry import _REGISTRY
from reasoner.presets import build_auto_preset, build_custom_router, get_preset

logger = logging.getLogger(__name__)


class PresetService:
    """Encapsulates all preset-related logic: resolution, filtering, router building."""

    def resolve(self, raw_preset: str) -> tuple[str, bool, str]:
        """
        Resolve a raw preset string into gate preset parameters.

        Returns:
            (gate_preset_name, is_auto, auto_tier)
        """
        is_auto = raw_preset.startswith("auto")
        auto_tier = raw_preset.split("-", 1)[1] if is_auto and "-" in raw_preset else "budget"
        gate_preset_name = f"multi-perspective-{auto_tier}" if is_auto else raw_preset
        return gate_preset_name, is_auto, auto_tier

    def filter_routing(self, routing: dict[str, str], primary_id: str) -> dict[str, str]:
        """Fall back routing entries whose API key env var is missing to primary_id."""
        filtered: dict[str, str] = {}
        for role, model_id in routing.items():
            entry = _REGISTRY.get(model_id, {})
            env = entry.get("env")
            if env and not os.environ.get(env):
                filtered[role] = primary_id
            else:
                filtered[role] = model_id
        return filtered

    def build_router(
        self,
        preset_name: str,
        custom_routing: dict[str, str] | None = None,
        agent_model: str | None = None,
    ) -> tuple[str, ProviderRouter]:
        """
        Build a ProviderRouter from a preset or custom routing.
        Validates model IDs against the registry at this layer.
        """
        if custom_routing:
            # Validate custom routing
            for model_id in custom_routing.values():
                if model_id not in _REGISTRY:
                    raise ValueError(f"Unknown model ID: {model_id}")
            
            filtered = self.filter_routing(custom_routing, "claude-sonnet")
            router = build_custom_router(filtered)
            return preset_name, router

        preset = get_preset(preset_name)
        
        # Validate preset configuration
        if preset.primary_id not in _REGISTRY:
             raise ValueError(f"Preset primary model '{preset.primary_id}' not in registry.")
        
        for role, mid in preset.routing.items():
            if mid not in _REGISTRY:
                raise ValueError(f"Preset '{preset_name}' role '{role}' uses unknown model '{mid}'")
        
        for role, mid in preset.fallback_routing.items():
            if mid not in _REGISTRY:
                raise ValueError(f"Preset '{preset_name}' role '{role}' fallback uses unknown model '{mid}'")

        for role, model_ids in preset.cascading_routing.items():
            for mid in model_ids:
                if mid not in _REGISTRY:
                    raise ValueError(
                        f"Preset '{preset_name}' role '{role}' cascade uses unknown model '{mid}'"
                    )

        filtered_routing = self.filter_routing(preset.routing, preset.primary_id)

        if agent_model:
            for role in ("synthesis", "classification", "decomposition"):
                filtered_routing[role] = agent_model
            logger.info(
                "Follow-up agent override: using %s for roles %s",
                agent_model,
                ["synthesis", "classification", "decomposition"],
            )

        router = ProviderRouter.from_model_ids(
            primary_id=preset.primary_id,
            routing=filtered_routing,
            fallback_routing=preset.fallback_routing or None,
            cascading_routing=preset.cascading_routing or None,
        )
        return preset_name, router

    def build_auto_router(
        self,
        method: str,
        tier: str,
        agent_model: str | None = None,
    ) -> tuple[str, ProviderRouter]:
        """
        Build a router for an auto-selected method.

        Returns:
            (effective_preset_name, router)
        """
        effective_preset_name = build_auto_preset(method, tier)
        preset = get_preset(effective_preset_name)
        filtered_routing = self.filter_routing(preset.routing, preset.primary_id)

        if agent_model:
            for role in ("synthesis", "classification", "decomposition"):
                filtered_routing[role] = agent_model

        router = ProviderRouter.from_model_ids(
            primary_id=preset.primary_id,
            routing=filtered_routing,
        )
        logger.info(
            "Auto-method: gate selected '%s' → preset '%s'",
            method,
            effective_preset_name,
        )
        return effective_preset_name, router
