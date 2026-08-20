"""Alias-aware pricing lookup.

``domain/pricing.py`` is keyed by SERVED model id (``deepseek/deepseek-v4-flash``);
callers hold registry aliases (``deepseek-v4-flash``). Resolving between them
needs the registry's alias table, so this lives in infrastructure.

Why not the application layer behind ``ModelRegistryPort``: it was there, and it
returned the ``_default`` price for every alias in any process that had not run a
composition root. ``get_model_registry_port()`` raises when nothing injected it,
and the call site swallowed that into a bare ``except Exception: pass``, so an
uninjected port and a genuinely unknown model were indistinguishable — both
silently priced at $1/$5 per M. That backs ``spend_limit_service.estimate_run_cost``,
the per-run spend gate, which could therefore not tell a budget preset from a
premium one. A spend gate must not treat "wiring not ready" as "model unknown".

Pricing is a dict read, not provider construction, so it does not need the port's
allowlist enforcement and must not depend on request-time DI: it has to be
correct in the API, the CLI, MCP stdio, and tests alike.

Importers stay inside the dependency rule. ``scripts/check_no_registry_bypass.py``
forbids application/domain/core from importing ``infrastructure.llm.registry``
*directly*; its own docstring notes the registry "is legitimately reachable via
infrastructure.llm.router, which application already depends on", i.e. reaching
registry data through another infrastructure module is the sanctioned path, not a
loophole. This module is that path for pricing; the registry import below is
infrastructure -> infrastructure.
"""

from __future__ import annotations

import logging

from reasoner.domain.pricing import PRICING_DB, ModelPricing
from reasoner.domain.pricing import get_pricing as _domain_get_pricing
from reasoner.infrastructure.llm.registry import _REGISTRY

logger = logging.getLogger(__name__)


def get_pricing(model_id: str) -> ModelPricing:
    """Pricing for *model_id*, resolving registry aliases.

    Accepts either a served model path (``anthropic/claude-sonnet-5``) or a
    registry alias (``claude-sonnet``). Falls back to the ``_default`` entry
    only when the id is genuinely unpriceable — and says so in the log, because
    a silent default here becomes a wrong spend estimate downstream.
    """
    pricing = _domain_get_pricing(model_id)
    if pricing is not PRICING_DB["_default"]:
        return pricing

    entry = _REGISTRY.get(model_id)
    served = entry.get("model") if entry else None
    # Looked up unstripped: the catalogue carries the auto-updating "~vendor/
    # model-latest" ids verbatim, so stripping the "~" (as resolved_model_of
    # does) turns a hit into a miss for exactly those entries.
    if served in PRICING_DB:
        return PRICING_DB[served]

    logger.warning(
        "No pricing for model %r (registry served id: %r) — falling back to the "
        "default $%g/$%g per token. Spend estimates involving it are not meaningful.",
        model_id,
        served,
        pricing.input_per_token,
        pricing.output_per_token,
    )
    return pricing


__all__ = ["get_pricing"]
