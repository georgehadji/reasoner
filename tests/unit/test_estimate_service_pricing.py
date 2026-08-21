"""/api/estimate must price the preset's real model, not one fabricated constant.

``estimate_service.estimate_cost`` used to do this:

    registry_entry = get_model_registry_port().entry(gate_preset_name) or {}
    primary_id = registry_entry.get("primary", "openrouter/openai/gpt-4o-mini")
    estimated_cost = calculate_model_cost(primary_id, ...)

Three compounding faults, all of which fired together:

  1. ``entry()`` holds MODEL ids; ``gate_preset_name`` is a PRESET id, so it
     returned None for every preset.
  2. It then read key ``"primary"``; registry entries use ``"model"``, so even a
     hit would have yielded None.
  3. The literal fallback ``"openrouter/openai/gpt-4o-mini"`` is not a
     PRICING_DB key -- the real key is ``"openai/gpt-4o-mini"`` -- so
     ``calculate_model_cost`` fell through to the ``_default`` $1/M / $5/M.

Net effect: every preset, budget or premium, returned the same invented figure.
Unlike the pricing_service DI bug, this one fired WITH the registry port
injected, i.e. in production, and reached POST /api/estimate, the MCP
reasoner_estimate tool, and reserve_run_budget -> credit reservation.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from reasoner.application.services.estimate_service import estimate_cost  # noqa: E402
from reasoner.domain.preset_registry import _REGISTRY as PRESETS  # noqa: E402
from reasoner.domain.pricing import PRICING_DB  # noqa: E402

PROBLEM = "How should we sequence a migration off the legacy billing system?"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_tiers_do_not_return_identical_estimates():
    """The headline symptom: every preset costing the same."""
    budget = await estimate_cost(PROBLEM, "debate-budget")
    premium = await estimate_cost(PROBLEM, "iterative-critique-premium")

    assert budget["estimated_cost_usd"] > 0
    assert premium["estimated_cost_usd"] > 0
    assert budget["estimated_cost_usd"] != premium["estimated_cost_usd"], (
        "a budget and a premium preset estimate identically — pricing has "
        "collapsed back to one flat rate"
    )


@pytest.mark.unit
def test_no_preset_resolves_to_the_default_pricing_entry():
    """No preset's primary model may fall through to _default.

    Asserted by IDENTITY, not by comparing the resulting dollar figure. Four
    presets route to claude-haiku, which is genuinely priced at $1/M in and
    $5/M out -- numerically identical to the _default entry. A value comparison
    flags those as broken when they are correctly priced, and would equally miss
    a real fallthrough on any model that happens to cost something else.
    `domain.pricing.get_pricing` returns the default by identity precisely so
    callers can make this distinction.
    """
    from reasoner.application.services.estimate_service import _preset_primary_model
    from reasoner.infrastructure.llm.pricing_resolver import get_pricing

    default = PRICING_DB["_default"]
    offenders = []
    for preset_id in sorted(PRESETS):
        primary = _preset_primary_model(preset_id)
        assert primary, f"{preset_id}: no primary model resolved"
        if get_pricing(primary) is default:
            offenders.append((preset_id, primary))

    assert not offenders, (
        f"{len(offenders)} preset(s) whose primary model has no pricing entry "
        f"and fell through to _default: {offenders[:10]}"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_estimate_tracks_the_presets_own_primary_model():
    """The figure must move with the routed model, not a hardcoded id."""
    from reasoner.application.services.estimate_service import _preset_primary_model
    from reasoner.infrastructure.llm.pricing_resolver import get_pricing

    preset_id = "debate-budget"
    result = await estimate_cost(PROBLEM, preset_id)
    primary = _preset_primary_model(preset_id)

    assert primary == PRESETS[preset_id]["primary_id"]
    expected = get_pricing(primary).calculate_cost(
        result["estimated_tokens_input"], result["estimated_tokens_output"]
    )
    assert result["estimated_cost_usd"] == pytest.approx(round(expected, 4))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unknown_preset_yields_no_estimate_rather_than_a_guess():
    """A typo must surface as $0.00, not a confident wrong number."""
    result = await estimate_cost(PROBLEM, "definitely-not-a-preset")
    assert result["estimated_cost_usd"] == 0.0
