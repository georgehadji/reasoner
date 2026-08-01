"""In-memory capability registry backed by JSON file for persistence (ACR Phase 2).

Bootstraps from _MODEL_WHITELIST static facts and benchmark results file.
Dynamic capabilities updated by telemetry and online learning engine.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from reasoner.domain.model_capabilities import (
    ModelCapabilities,
    ModelConstraints,
    ModelProfile,
)
from reasoner.domain.task_requirements import TaskConstraints
from reasoner.infrastructure.llm.registry import _MODEL_WHITELIST, _REGISTRY, bloc_of


# ── Default bootstrap: hard-coded constraint metadata ──
# Populated from the inline comments in _MODEL_WHITELIST.
# This maps model_id -> partial ModelConstraints (fields not set are inferred).
_MODEL_CONSTRAINT_HINTS: dict[str, dict[str, Any]] = {
    # Anthropic
    "claude-fable-5":  {"max_context": 1_000_000, "cost_in": 10.0, "cost_out": 50.0, "tools": True, "vision": True, "json": True, "temp": True},
    "claude-opus":     {"max_context": 1_000_000, "cost_in": 5.0, "cost_out": 25.0, "tools": True, "vision": True, "json": True, "temp": True},
    "claude-sonnet":   {"max_context": 1_000_000, "cost_in": 2.0, "cost_out": 10.0, "tools": True, "vision": True, "json": True, "temp": True},
    "claude-haiku":    {"max_context": 200_000, "cost_in": 1.0, "cost_out": 5.0, "tools": True, "vision": True, "json": True, "temp": True},
    # OpenAI
    "gpt-5.5":         {"max_context": 1_000_000, "cost_in": 5.0, "cost_out": 30.0, "tools": True, "vision": True, "json": True, "temp": True},
    "gpt-5.5-pro":     {"max_context": 1_000_000, "cost_in": 30.0, "cost_out": 180.0, "tools": True, "vision": True, "json": True, "temp": True},
    "gpt-5":           {"max_context": 400_000, "cost_in": 1.25, "cost_out": 10.0, "tools": True, "vision": True, "json": True, "temp": True},
    "gpt-5-pro":       {"max_context": 400_000, "cost_in": 15.0, "cost_out": 120.0, "tools": True, "vision": True, "json": True, "temp": True},
    "gpt-5-mini":      {"max_context": 400_000, "cost_in": 0.25, "cost_out": 2.0, "tools": True, "vision": True, "json": True, "temp": True},
    "gpt-5-nano":      {"max_context": 400_000, "cost_in": 0.05, "cost_out": 0.40, "tools": True, "vision": False, "json": True, "temp": True},
    "gpt-5.4":         {"max_context": 400_000, "cost_in": 2.50, "cost_out": 15.0, "tools": True, "vision": True, "json": True, "temp": True},
    "o3":              {"max_context": 200_000, "cost_in": 2.0, "cost_out": 8.0, "tools": True, "vision": True, "json": True, "temp": False},
    "o3-mini":         {"max_context": 200_000, "cost_in": 1.0, "cost_out": 4.0, "tools": True, "vision": False, "json": True, "temp": False},
    "o4-mini":         {"max_context": 200_000, "cost_in": 1.10, "cost_out": 4.40, "tools": True, "vision": True, "json": True, "temp": False},
    # Google
    "gemini-flash":    {"max_context": 1_000_000, "cost_in": 1.50, "cost_out": 9.0, "tools": True, "vision": True, "json": True, "temp": True},
    "gemini-pro-real": {"max_context": 1_000_000, "cost_in": 2.0, "cost_out": 12.0, "tools": True, "vision": True, "json": True, "temp": True},
    # DeepSeek
    "deepseek-v4-pro":  {"max_context": 1_000_000, "cost_in": 0.435, "cost_out": 0.87, "tools": True, "vision": False, "json": True, "temp": True},
    "deepseek-v4-flash": {"max_context": 1_000_000, "cost_in": 0.09, "cost_out": 0.18, "tools": True, "vision": False, "json": True, "temp": True},
    "deepseek-v3":      {"max_context": 1_000_000, "cost_in": 0.12, "cost_out": 0.50, "tools": True, "vision": False, "json": True, "temp": True},
    # Qwen
    "qwen3.7-max":      {"max_context": 1_000_000, "cost_in": 1.25, "cost_out": 3.75, "tools": True, "vision": True, "json": True, "temp": True},
    "qwen3.7-plus":     {"max_context": 1_000_000, "cost_in": 0.32, "cost_out": 1.28, "tools": True, "vision": True, "json": True, "temp": True},
    "qwen3.7-flash":    {"max_context": 1_000_000, "cost_in": 0.03, "cost_out": 0.13, "tools": True, "vision": True, "json": True, "temp": True},
    "qwen3.5-flash":    {"max_context": 1_000_000, "cost_in": 0.065, "cost_out": 0.26, "tools": True, "vision": False, "json": True, "temp": True},
    # Mistral
    "mistral-large-3":    {"max_context": 262_000, "cost_in": 2.0, "cost_out": 8.0, "tools": True, "vision": True, "json": True, "temp": True},
    "mistral-small":      {"max_context": 262_000, "cost_in": 0.15, "cost_out": 0.60, "tools": True, "vision": False, "json": True, "temp": True},
    # xAI
    "grok-4.5":           {"max_context": 500_000, "cost_in": 2.0, "cost_out": 6.0, "tools": True, "vision": True, "json": True, "temp": True},
    "grok-4.3":           {"max_context": 1_000_000, "cost_in": 1.25, "cost_out": 2.50, "tools": True, "vision": True, "json": True, "temp": True},
    "grok-build-0.1":     {"max_context": 256_000, "cost_in": 1.0, "cost_out": 2.0, "tools": True, "vision": True, "json": True, "temp": True},
    # Meta
    "llama-4-scout":      {"max_context": 10_000_000, "cost_in": 0.10, "cost_out": 0.30, "tools": True, "vision": True, "json": True, "temp": True},
    "llama-4-maverick":   {"max_context": 1_000_000, "cost_in": 0.15, "cost_out": 0.60, "tools": True, "vision": True, "json": True, "temp": True},
}


def _infer_vendor(model_id: str) -> str:
    """Extract vendor name from a model ID."""
    if model_id in _MODEL_WHITELIST:
        cfg = _MODEL_WHITELIST[model_id]
        actual = str(cfg.get("model", model_id)).lstrip("~")
        vendor = actual.split("/", 1)[0] if "/" in actual else model_id
        return vendor
    # Check _REGISTRY
    cfg = _REGISTRY.get(model_id) or {}
    actual = str(cfg.get("model", model_id)).lstrip("~")
    vendor = actual.split("/", 1)[0] if "/" in actual else model_id
    return vendor


def _build_constraints(model_id: str) -> ModelConstraints:
    """Build ModelConstraints from the hint table or whitelist fallback."""
    hint = _MODEL_CONSTRAINT_HINTS.get(model_id, {})
    vendor = _infer_vendor(model_id)
    bloc = bloc_of(model_id)

    # Try to find cost info from whitelist comment via basic heuristics
    return ModelConstraints(
        max_context_tokens=hint.get("max_context", 4096),
        cost_per_1k_input_usd=hint.get("cost_in", 0.0) / 1000.0,  # Per 1K from per-M
        cost_per_1k_output_usd=hint.get("cost_out", 0.0) / 1000.0,  # Per 1K from per-M
        supports_tools=hint.get("tools", False),
        supports_vision=hint.get("vision", False),
        supports_streaming=True,
        supports_json_mode=hint.get("json", False),
        supports_temperature=hint.get("temp", True),
        vendor=vendor,
        bloc=bloc,
    )


class CapabilityRegistry:
    """In-memory capability registry backed by JSON file for persistence.

    Bootstraps from _MODEL_WHITELIST static facts. Capability scores are
    None until the benchmark engine or online learning engine provides them.
    """

    def __init__(self, profiles_path: str | None = None) -> None:
        """Initialise the registry.

        Args:
            profiles_path: Path to the JSON file for persistence.
                Defaults to ``~/.reasoner/acr/capability_profiles.json``.
        """
        if profiles_path is None:
            profiles_path = str(
                Path.home() / ".reasoner" / "acr" / "capability_profiles.json"
            )
        self._profiles_path = profiles_path
        self._profiles: dict[str, ModelProfile] = {}
        self._bootstrap()

    def _bootstrap(self) -> None:
        """Bootstrap profiles from the model whitelist and persisted data."""
        # 1. Build from whitelist
        for model_id in _MODEL_WHITELIST:
            if model_id not in self._profiles:
                constraints = _build_constraints(model_id)
                self._profiles[model_id] = ModelProfile(
                    model_id=model_id,
                    constraints=constraints,
                )

        # 2. Load persisted capabilities (overwrites if present)
        persisted = self._load_persisted()
        for model_id, caps in persisted.items():
            if model_id in self._profiles:
                existing = self._profiles[model_id]
                caps_obj = ModelCapabilities(
                    scores=caps.get("scores", {}),
                    source=caps.get("source", "persisted"),
                    measured_at=caps.get("measured_at", ""),
                    sample_count=caps.get("sample_count", 0),
                )
                self._profiles[model_id] = ModelProfile(
                    model_id=model_id,
                    constraints=existing.constraints,
                    capabilities=caps_obj,
                )

    def get_profile(self, model_id: str) -> ModelProfile | None:
        return self._profiles.get(model_id)

    def get_all_profiles(self) -> dict[str, ModelProfile]:
        return dict(self._profiles)

    def update_capabilities(
        self,
        model_id: str,
        capabilities: ModelCapabilities,
    ) -> None:
        existing = self._profiles.get(model_id)
        if existing is None:
            # Unknown model — create a minimal profile
            constraints = _build_constraints(model_id)
            existing = ModelProfile(model_id=model_id, constraints=constraints)
        self._profiles[model_id] = ModelProfile(
            model_id=model_id,
            constraints=existing.constraints,
            capabilities=capabilities,
        )
        self._save_persisted()

    def update_constraints(
        self,
        model_id: str,
        constraints: ModelConstraints,
    ) -> None:
        existing = self._profiles.get(model_id)
        caps = existing.capabilities if existing else None
        self._profiles[model_id] = ModelProfile(
            model_id=model_id,
            constraints=constraints,
            capabilities=caps,
        )
        self._save_persisted()

    def get_models_satisfying(
        self,
        constraints: TaskConstraints,
    ) -> list[ModelProfile]:
        """Filter models by hard constraints."""
        results: list[ModelProfile] = []
        for profile in self._profiles.values():
            c = profile.constraints
            # Context window
            if c.max_context_tokens < constraints.min_context_tokens:
                continue
            # Cost ceiling (per 1K output)
            if c.cost_per_1k_output_usd > constraints.max_cost_per_1k_output_usd:
                continue
            # Tool support
            if constraints.requires_tools and not c.supports_tools:
                continue
            # Vision support
            if constraints.requires_vision and not c.supports_vision:
                continue
            # Temperature support
            if constraints.requires_temperature and not c.supports_temperature:
                continue
            # Bloc exclusion
            if c.bloc in constraints.excluded_blocs:
                continue
            # Model exclusion
            if profile.model_id in constraints.excluded_models:
                continue
            results.append(profile)
        return results

    def _load_persisted(self) -> dict[str, dict[str, Any]]:
        """Load capability profiles from the JSON file."""
        path = self._profiles_path
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return data.get("capabilities", {})
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_persisted(self) -> None:
        """Save capability profiles to the JSON file."""
        parent = os.path.dirname(self._profiles_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        data: dict[str, Any] = {
            "version": 1,
            "capabilities": {},
        }
        for model_id, profile in self._profiles.items():
            if profile.capabilities:
                data["capabilities"][model_id] = {
                    "scores": profile.capabilities.scores,
                    "source": profile.capabilities.source,
                    "measured_at": profile.capabilities.measured_at,
                    "sample_count": profile.capabilities.sample_count,
                }

        with open(self._profiles_path, "w") as f:
            json.dump(data, f, indent=2)


__all__ = ["CapabilityRegistry"]
