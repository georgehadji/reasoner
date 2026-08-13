"""Application-layer pricing service.

Wraps domain pricing with registry-aware model ID resolution.
The domain layer (pricing.py) does not import from infrastructure; this
service is the correct place for callers that pass shorthand model IDs
(e.g. "claude-opus") and need them resolved to OpenRouter paths.
"""

from __future__ import annotations

from reasoner.domain.pricing import ModelPricing, PRICING_DB, get_pricing as _domain_get_pricing


def get_pricing(model_id: str) -> ModelPricing:
    """Get pricing for a model, resolving registry shorthand IDs when needed.

    Tries direct lookup first, then resolves via the LLM registry
    (e.g. "claude-opus" → "anthropic/claude-opus-4.6").
    Falls back to the default pricing entry if still unresolved.
    """
    pricing = _domain_get_pricing(model_id)
    if pricing is not PRICING_DB.get("_default"):
        return pricing

    # Try registry resolution for shorthand IDs
    try:
        from reasoner.core.ports.model_registry_port import get_model_registry_port
        entry = get_model_registry_port().entry(model_id)
        if entry:
            or_model = entry["model"]
            if or_model in PRICING_DB:
                return PRICING_DB[or_model]
    except Exception:
        pass

    return pricing
