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


def _load_openrouter_pricing() -> dict[str, ModelPricing]:
    """Load pricing from openrouter_models.json if available."""
    db: dict[str, ModelPricing] = {}
    json_path = Path(__file__).with_name("openrouter_models.json")
    if not json_path.exists():
        return db
    try:
        with json_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        for entry in payload.get("data", []):
            model_id = entry.get("id")
            pricing = entry.get("pricing") or {}
            prompt = pricing.get("prompt")
            completion = pricing.get("completion")
            if model_id and prompt is not None and completion is not None:
                try:
                    db[model_id] = ModelPricing(float(prompt), float(completion))
                except ValueError:
                    continue
    except Exception as exc:
        logger.warning("Failed to load pricing from %s: %s", json_path, exc)
        pass
    return db


# ─────────────────────────────────────────────────────────────────────
# PRICING DATABASE
# Auto-loaded from openrouter_models.json with manual overrides/fallbacks.
# ─────────────────────────────────────────────────────────────────────

PRICING_DB: dict[str, ModelPricing] = _load_openrouter_pricing()

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
    
    # Try to extract from registry model ID
    # (e.g., "claude-opus" -> look up "anthropic/claude-opus-4.6")
    from reasoner.infrastructure.llm.registry import _REGISTRY
    if model_id in _REGISTRY:
        or_model = _REGISTRY[model_id]["model"]
        if or_model in PRICING_DB:
            return PRICING_DB[or_model]
    
    # Fallback to default pricing
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
