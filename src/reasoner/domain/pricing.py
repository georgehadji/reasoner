"""
LLM Pricing Database
Tracks per-token pricing for all supported models.

Pricing is per-token (not per 1M tokens) for accurate cost calculation.
Source: auto-loaded from openrouter_models.json; static fallbacks for models
not present in the JSON.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelPricing:
    """Immutable pricing data for a model."""
    input_per_token: float   # Cost per input token
    output_per_token: float  # Cost per output token

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate total cost for given token usage."""
        return (input_tokens * self.input_per_token) + (output_tokens * self.output_per_token)


def _load_openrouter_catalogue(what: str = "model catalogue") -> dict[str, dict]:
    """Load the OpenRouter model catalogue snapshot, keyed by model ID.

    Each entry carries ``context_length``, ``pricing``, ``supported_parameters``
    and ``architecture`` — the raw facts both the pricing DB and the ACR
    capability registry derive from. Refresh with
    ``scripts/update_openrouter_catalogue.py``.

    Args:
        what: Named in the warning when the file is corrupt or unreadable, so
            the log says which consumer went without data.
    """
    json_path = Path(__file__).with_name("openrouter_models.json")
    if not json_path.exists():
        return {}
    try:
        with json_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:
        logger.warning("Failed to load %s from %s: %s", what, json_path, exc)
        return {}
    return {
        entry["id"]: entry
        for entry in payload.get("data", [])
        if isinstance(entry, dict) and entry.get("id")
    }


def _load_openrouter_pricing(
    catalogue: dict[str, dict] | None = None,
) -> dict[str, ModelPricing]:
    """Extract per-token pricing from the catalogue snapshot.

    Args:
        catalogue: Pre-loaded catalogue. Omit to read the file directly —
            corrupt or unreadable files warn and yield an empty dict rather
            than failing the import (BUG-002).
    """
    if catalogue is None:
        catalogue = _load_openrouter_catalogue("pricing")

    db: dict[str, ModelPricing] = {}
    for model_id, entry in catalogue.items():
        pricing = entry.get("pricing") or {}
        prompt = pricing.get("prompt")
        completion = pricing.get("completion")
        if prompt is None or completion is None:
            continue
        try:
            db[model_id] = ModelPricing(float(prompt), float(completion))
        except (TypeError, ValueError):
            continue
    return db


MODEL_CATALOGUE: dict[str, dict] = _load_openrouter_catalogue()
"""Raw OpenRouter catalogue snapshot, keyed by served model ID."""


# ─────────────────────────────────────────────────────────────────────
# PRICING DATABASE
# Auto-loaded from openrouter_models.json with manual overrides/fallbacks.
# ─────────────────────────────────────────────────────────────────────

PRICING_DB: dict[str, ModelPricing] = _load_openrouter_pricing(MODEL_CATALOGUE)

# Manual overrides / fallbacks for models that may not be in the JSON
# or whose JSON prices are unreliable.
_STATIC_OVERRIDES: dict[str, ModelPricing] = {
    "_default": ModelPricing(1.0e-6, 5.0e-6),
}

for _mid, _pricing in _STATIC_OVERRIDES.items():
    PRICING_DB[_mid] = _pricing


def get_pricing(model_id: str) -> ModelPricing:
    """
    Get pricing for a model. Falls back to default if not found.
    
    Args:
        model_id: OpenRouter model path (e.g., "anthropic/claude-opus-4.6")
                 or registry ID (e.g., "claude-opus")
    
    Returns:
        ModelPricing instance for cost calculation
    """
    # Direct match in pricing DB
    if model_id in PRICING_DB:
        return PRICING_DB[model_id]

    # Fallback to default pricing. Returned by identity, so callers can detect
    # "unpriced" with `is PRICING_DB["_default"]` rather than comparing values.
    # Callers holding registry shorthand IDs (e.g. "claude-opus") must resolve
    # them first via infrastructure.llm.pricing_resolver.get_pricing(); domain
    # cannot reach the alias table, and silently defaulting here is what made
    # the spend gate price every preset identically.
    return PRICING_DB["_default"]


def calculate_model_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """
    Calculate cost for a single API call.
    
    Args:
        model_id: Model identifier
        input_tokens: Number of input tokens used
        output_tokens: Number of output tokens generated
    
    Returns:
        Cost in USD
    """
    pricing = get_pricing(model_id)
    return pricing.calculate_cost(input_tokens, output_tokens)


def format_cost(cost_usd: float) -> str:
    """Format cost in human-readable way."""
    if cost_usd < 0.001:
        return f"${cost_usd*100:.4f}¢"  # Show in cents with 4 decimals
    elif cost_usd < 0.01:
        return f"${cost_usd:.4f}"
    elif cost_usd < 1.0:
        return f"${cost_usd:.3f}"
    else:
        return f"${cost_usd:.2f}"


def print_cost_summary(phase_costs: dict[str, float], total_cost: float) -> str:
    """
    Print formatted cost summary.
    
    Args:
        phase_costs: {phase_name: cost_in_usd}
        total_cost: Total cost in USD
    
    Returns:
        Formatted string for display
    """
    lines = [
        "💰 Cost Summary",
        "─" * 60,
    ]

    for phase, cost in phase_costs.items():
        lines.append(f"  {phase:30s} {format_cost(cost):>10s}")

    lines.append("─" * 60)
    lines.append(f"  {'TOTAL':30s} {format_cost(total_cost):>10s}")

    return "\n".join(lines)
