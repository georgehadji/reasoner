"""PRV-3 contract over `PRESETS`: declared fallbacks respect the price specification.

A role with no `fallback_routing` entry retries on the preset primary, so the
effective fallback is explicit-else-primary, the same rule the router applies.
`fallback_within_budget` is the specification; `ProviderRouter._resolve_fallback`
enforces it at run time, so an over-budget pair here no longer costs money, it
costs a retry that the router now skips. This test keeps the config honest:

* an *explicit* fallback must satisfy the specification outright;
* the *implicit* (primary) ones are ratcheted. The count may only fall. Fixing
  a pair means giving that role a same-class, cross-lab `fallback_routing`
  entry (CLAUDE.md section 5); lower `MAX_IMPLICIT_OVER_BUDGET` when you do.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

# Measured 2026-10-21 at FALLBACK_MAX_PRICE_RATIO = 10 across all presets.
MAX_IMPLICIT_OVER_BUDGET = 45


def _pairs():
    import reasoner.api  # noqa: F401  (wires the model-registry port)
    from reasoner.domain.preset_registry import _REGISTRY as PRESETS
    from reasoner.domain.pricing import blended_usd_per_mtok, fallback_within_budget
    from reasoner.infrastructure.llm.pricing_resolver import get_pricing

    def price(model: str) -> float:
        return blended_usd_per_mtok(get_pricing(model))

    for preset_id, cfg in PRESETS.items():
        primary = cfg["primary_id"]
        explicit = cfg.get("fallback_routing", {})
        for role, model in cfg.get("routing", {}).items():
            if model == primary:
                continue
            candidate = explicit.get(role) or primary
            if candidate == model:
                continue
            yield (
                preset_id, role, model, candidate, role in explicit,
                fallback_within_budget(price(model), price(candidate)),
            )


def test_explicit_fallbacks_are_within_budget():
    over = [
        f"{pid}.{role}: {model} -> {cand}"
        for pid, role, model, cand, is_explicit, within in _pairs()
        if is_explicit and not within
    ]
    assert not over, "explicit fallback costs too much:\n  " + "\n  ".join(over)


def test_implicit_over_budget_pairs_do_not_grow():
    over = [
        f"{pid}.{role}: {model} -> {cand} (primary)"
        for pid, role, model, cand, is_explicit, within in _pairs()
        if not is_explicit and not within
    ]
    assert len(over) <= MAX_IMPLICIT_OVER_BUDGET, (
        f"{len(over)} role/preset pairs fall back to an over-budget primary "
        f"(limit {MAX_IMPLICIT_OVER_BUDGET}); give the new ones an explicit "
        "fallback_routing entry:\n  " + "\n  ".join(over)
    )
