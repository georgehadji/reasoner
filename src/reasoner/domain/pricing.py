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

# A fallback may cost at most this many times the model it replaces (blended
# input+output USD per million tokens). Ten is the line the audit drew: 45
# role/preset pairs sat above it, the worst at 48x. Open question Q3 in
# docs/plans/audit-remediation-3-2026-10-21.md is whether it should be 3.
# Lives here, not in core/constants_limits: domain may not import core.
FALLBACK_MAX_PRICE_RATIO: float = 10.0
# A free or near-free assigned model is priced at this floor for the ratio, so
# the first paid fallback is judged against something rather than against zero.
FALLBACK_PRICE_FLOOR_USD_PER_MTOK: float = 0.3


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


def blended_usd_per_mtok(pricing: ModelPricing) -> float:
    """Input plus output price per million tokens: one comparable number per model."""
    return (pricing.input_per_token + pricing.output_per_token) * 1_000_000


def fallback_within_budget(
    assigned_usd_per_mtok: float,
    candidate_usd_per_mtok: float,
    ratio: float = FALLBACK_MAX_PRICE_RATIO,
) -> bool:
    """May *candidate* stand in for *assigned* without costing far more?

    Pure specification, enforced twice: the preset contract test checks the
    declared routing, and ``ProviderRouter._resolve_fallback`` checks the
    routers built at run time (``build_auto_preset``), which a static test
    cannot see.
    """
    base = max(assigned_usd_per_mtok, FALLBACK_PRICE_FLOOR_USD_PER_MTOK)
    return candidate_usd_per_mtok <= base * ratio


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
