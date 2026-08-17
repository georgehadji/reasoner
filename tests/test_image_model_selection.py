"""
Unit tests for automatic image-model selection.

Two halves:
  * ImageModelSelector — the on-demand HyperGate sub-agent (offline FakeRouter)
  * image_model_catalogue.select_models — pure price/family/lab-diversity logic
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from reasoner.core.constants import IMAGE_GEN_IMAGE_COUNT
from reasoner.hypergate.models import SubAgentInput
from reasoner.hypergate.sub_agents import ImageModelSelector
from reasoner.infrastructure.llm.image_model_catalogue import (
    FAMILIES,
    FAMILY_VECTOR,
    _candidates,
    image_catalogue,
    select_models,
)
from reasoner.infrastructure.llm.registry import _REGISTRY

# The vector family is deliberately exempt from the `count` and lab-diversity
# invariants (only Recraft ships SVG), so shared invariant tests skip it.
NON_VECTOR_FAMILIES = [f for f in FAMILIES if f != FAMILY_VECTOR]


# ── Helpers (house pattern from tests/test_hypergate.py) ──────────────


class FakeProvider:
    def __init__(self, model: str = "fake-model"):
        self.model = model
        self.last_input_tokens = 10
        self.last_output_tokens = 5
        self.last_cost_usd = 0.0


def make_router(*responses: str) -> Any:
    """Fake ProviderRouter whose call() returns each response in sequence."""
    provider = FakeProvider()
    router = MagicMock()
    router.get.return_value = provider

    call_results = list(responses)
    call_count = {"n": 0}

    async def fake_call(role, system_prompt, user_prompt, **kwargs):
        idx = min(call_count["n"], len(call_results) - 1)
        call_count["n"] += 1
        return call_results[idx], {"input_tokens": 10, "output_tokens": 5, "model": "fake-model"}

    router.call = fake_call
    return router


def _j(**kwargs) -> str:
    return json.dumps(kwargs)


def _labs(aliases: list[str]) -> set[str]:
    cat = image_catalogue()
    return {cat[a].lab for a in aliases}


def _is_svg(alias: str) -> bool:
    return image_catalogue()[alias].model_id.endswith("-vector")


def _mean_price(aliases: list[str]) -> float:
    cat = image_catalogue()
    return sum(cat[a].price_per_image for a in aliases) / len(aliases)


# ── ImageModelSelector sub-agent ──────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("family", list(FAMILIES))
async def test_selector_happy_path_per_family(family):
    agent = ImageModelSelector()
    agent._cache.clear()

    router = make_router(_j(family=family, tier_hint="premium", confidence=0.9, rationale="why"))
    out = await agent.execute(SubAgentInput(problem="a logo for a bakery", agent_name="test"), router)

    assert out.error is None
    assert out.result["family"] == family
    assert out.result["tier_hint"] == "premium"
    assert out.result["confidence"] == 0.9
    assert out.result["rationale"] == "why"


@pytest.mark.asyncio
async def test_selector_family_list_matches_catalogue():
    """The sub-agent duplicates FAMILIES (layering); keep the copies in sync."""
    from reasoner.hypergate.sub_agents.image_model_selector import _VALID_FAMILIES

    assert _VALID_FAMILIES == set(FAMILIES)


@pytest.mark.asyncio
async def test_selector_invalid_family_coerces_to_general():
    agent = ImageModelSelector()
    agent._cache.clear()

    router = make_router(_j(family="interpretive_dance", tier_hint="luxury", confidence=0.8))
    out = await agent.execute(SubAgentInput(problem="draw a cat", agent_name="test"), router)

    assert out.result["family"] == "general"
    assert out.result["tier_hint"] == "budget"


@pytest.mark.asyncio
async def test_selector_garbage_input_still_returns_dict():
    agent = ImageModelSelector()
    result = agent._parse_result("not json at all <<<>>>")

    assert isinstance(result, dict)
    assert result["family"] == "general"
    assert result["confidence"] == 0.0


@pytest.mark.asyncio
async def test_selector_broken_router_yields_error_and_zero_confidence():
    agent = ImageModelSelector()
    agent._cache.clear()

    router = MagicMock()
    router.get.return_value = FakeProvider()
    router.call = MagicMock(side_effect=RuntimeError("provider exploded"))

    out = await agent.execute(SubAgentInput(problem="draw a cat", agent_name="test"), router)

    assert out.error is not None
    assert out.confidence == 0.0


# ── select_models ─────────────────────────────────────────────────────


@pytest.mark.parametrize("family", list(FAMILIES))
@pytest.mark.parametrize("tier", ["budget", "premium"])
def test_every_returned_alias_is_registered(family, tier):
    primaries, fallbacks = select_models(family, tier, IMAGE_GEN_IMAGE_COUNT, False)
    for alias in primaries + fallbacks:
        assert alias in _REGISTRY, f"{alias} is not in _REGISTRY"


@pytest.mark.parametrize("family", NON_VECTOR_FAMILIES)
@pytest.mark.parametrize("tier", ["budget", "premium"])
def test_primaries_count_and_lab_diversity(family, tier):
    primaries, fallbacks = select_models(family, tier, IMAGE_GEN_IMAGE_COUNT, False)
    assert len(primaries) == IMAGE_GEN_IMAGE_COUNT
    assert len(set(primaries)) == IMAGE_GEN_IMAGE_COUNT
    assert len(_labs(primaries)) >= 4, f"{family}/{tier} primaries share labs: {primaries}"
    assert len(fallbacks) >= 4
    assert not set(fallbacks) & set(primaries)


@pytest.mark.parametrize("family", NON_VECTOR_FAMILIES)
def test_budget_is_cheaper_than_premium(family):
    budget, _ = select_models(family, "budget", IMAGE_GEN_IMAGE_COUNT, False)
    premium, _ = select_models(family, "premium", IMAGE_GEN_IMAGE_COUNT, False)
    assert _mean_price(budget) < _mean_price(premium)


def test_price_ordering_puts_grok_above_the_cheap_tier():
    """Flat-per-image models must not be mistaken for token-priced bargains."""
    cat = image_catalogue()
    assert cat["grok-imagine"].price_per_image > cat["flux.2-klein-4b"].price_per_image
    assert cat["grok-imagine"].price_per_image > cat["krea-2-medium-turbo"].price_per_image
    assert cat["grok-imagine"].price_per_image > cat["riverflow-v2.5-fast"].price_per_image


def test_needs_reference_input_returns_only_image_input_models():
    cat = image_catalogue()
    for tier in ("budget", "premium"):
        primaries, fallbacks = select_models("general", tier, IMAGE_GEN_IMAGE_COUNT, True)
        for alias in primaries + fallbacks:
            assert cat[alias].accepts_image_input, f"{alias} cannot take a reference image"


def test_vector_family_routes_to_a_recraft_vector_model():
    for tier in ("budget", "premium"):
        primaries, _ = select_models("vector", tier, IMAGE_GEN_IMAGE_COUNT, False)
        assert any("vector" in a for a in primaries), primaries
        assert any(image_catalogue()[a].lab == "recraft" for a in primaries)


# ── SVG hard filter (both directions) ─────────────────────────────────


@pytest.mark.parametrize("family", NON_VECTOR_FAMILIES)
@pytest.mark.parametrize("tier", ["budget", "premium"])
@pytest.mark.parametrize("needs_reference_input", [False, True])
def test_no_non_vector_family_ever_returns_an_svg_model(family, tier, needs_reference_input):
    """An SVG for a photo prompt is a broken response, not a pricier one."""
    primaries, fallbacks = select_models(
        family, tier, IMAGE_GEN_IMAGE_COUNT, needs_reference_input
    )
    for alias in primaries + fallbacks:
        assert not _is_svg(alias), f"{family}/{tier} leaked SVG model {alias}"


@pytest.mark.parametrize("tier", ["budget", "premium"])
def test_vector_family_returns_only_svg_models(tier):
    """The inverse: a caller asking for SVG must never receive a raster model."""
    primaries, fallbacks = select_models("vector", tier, IMAGE_GEN_IMAGE_COUNT, False)
    assert primaries
    for alias in primaries + fallbacks:
        assert _is_svg(alias), f"vector/{tier} leaked raster model {alias}"


def test_vector_family_is_exempt_from_count_and_lab_diversity():
    """Only Recraft ships SVG, so fewer-than-`count` single-lab results are correct."""
    primaries, fallbacks = select_models("vector", "premium", 99, False)
    assert 0 < len(primaries) < 99
    assert _labs(primaries) == {"recraft"}
    assert fallbacks == []  # everything vector fits in the primaries


async def _attempted_aliases_for_vector_run(num_images: int, failing: set[str] | None = None):
    """Run generate_images() with a real vector selection; return (result, attempted).

    Nothing touches the network: generate_image_with_model is mocked, so the only
    thing under test is which aliases generate_images() decides to call.
    """
    from unittest.mock import AsyncMock, patch

    from reasoner.infrastructure.llm.image_generation import ImageGenerationError, generate_images

    primaries, fallbacks = select_models(FAMILY_VECTOR, "budget", num_images, False)
    attempted: list[str] = []

    def _side_effect(prompt, alias, *args, **kwargs):
        attempted.append(alias)
        if failing and alias in failing:
            raise ImageGenerationError(f"{alias} refused")
        return {
            "success": True,
            "image_data": "data:image/svg+xml;base64,ok",
            "model_used": alias,
        }

    with patch(
        "reasoner.infrastructure.llm.image_generation.generate_image_with_model",
        new_callable=AsyncMock,
    ) as mock_gen:
        mock_gen.side_effect = _side_effect
        result = await generate_images(
            "a flat vector logo of a fox",
            preset="budget",
            enhance=False,
            num_images=num_images,
            model_aliases=primaries,
            fallback_aliases=fallbacks,
        )
    return result, attempted


@pytest.mark.asyncio
async def test_vector_request_larger_than_the_vector_family_never_returns_raster():
    """Regression: a shallow-but-valid vector selection must not become raster.

    Exactly four SVG models exist, so any num_images > 4 leaves select_models()
    short of `count` — which is CORRECT for this family (see the EXEMPTION in
    select_models). The old guard read "fewer than requested" as "selection
    failed" and substituted the raster static preset, handing PNGs to a caller
    who asked for SVG and silently defeating the vector filter one layer up.
    """
    num_images = len(select_models(FAMILY_VECTOR, "budget", 99, False)[0]) + 1
    result, attempted = await _attempted_aliases_for_vector_run(num_images)

    assert attempted, "no model was attempted at all"
    for alias in attempted:
        assert _is_svg(alias), f"raster model {alias} used for a vector request"
    # Fewer images than asked for is the correct outcome; failing the run is not.
    assert result["success"] is True
    assert 0 < len(result["images"]) < num_images


@pytest.mark.asyncio
async def test_vector_fallbacks_never_widen_to_raster_models():
    """The break-even case: count == 4 leaves no vector fallbacks to hand back.

    An empty fallback list must stay empty rather than degrading to the raster
    static fallbacks, which is the same leak reached through the retry path.
    """
    vector_aliases = select_models(FAMILY_VECTOR, "budget", 99, False)[0]
    _, attempted = await _attempted_aliases_for_vector_run(
        len(vector_aliases), failing={vector_aliases[0]}
    )

    for alias in attempted:
        assert _is_svg(alias), f"raster fallback {alias} used for a vector request"


def test_vector_budget_is_cheaper_than_premium():
    """At count=4 both tiers return all four vector models, so compare at count=2."""
    budget, _ = select_models("vector", "budget", 2, False)
    premium, _ = select_models("vector", "premium", 2, False)
    assert _mean_price(budget) < _mean_price(premium)


# ── Premium means capability, not price ───────────────────────────────


def _premium_order(family: str) -> list[str]:
    return [m.alias for m in _candidates(family, "premium", False)]


def test_premium_prefers_gpt_image_2_over_the_pricier_gpt_image_1():
    """gpt-image-1 costs MORE, so a price ranking would invert this."""
    cat = image_catalogue()
    assert cat["gpt-image-1"].price_per_image > cat["gpt-image-2"].price_per_image

    order = _premium_order("text_in_image")
    assert order.index("gpt-image-2") < order.index("gpt-image-1")


@pytest.mark.parametrize(
    "better, worse",
    [
        ("flux.2-max", "flux.2-pro"),
        ("flux.2-pro", "flux.2-flex"),
        ("flux.2-flex", "flux.2-klein-4b"),
        ("recraft-v4.1-pro", "recraft-v4-pro"),
        ("recraft-v4", "recraft-v3"),
        ("seedream-5-pro", "seedream-4.5"),
        ("riverflow-v2.5-pro", "riverflow-v2-pro"),  # cheaper but newer
        ("gemini-pro-image", "gemini-3-pro-image-preview"),  # stable over preview
    ],
)
def test_premium_ranks_newer_generations_first(better, worse):
    order = _premium_order("general")
    assert order.index(better) < order.index(worse)


def test_premium_no_longer_picks_the_pure_price_leaders():
    """Regression: the old ranking returned the four priciest aliases."""
    primaries, _ = select_models("general", "premium", IMAGE_GEN_IMAGE_COUNT, False)
    assert "gpt-image-1" not in primaries
    assert "recraft-v4.1-pro-vector" not in primaries


def test_unknown_family_falls_back_to_general():
    assert select_models("nonsense", "budget", IMAGE_GEN_IMAGE_COUNT, False) == select_models(
        "general", "budget", IMAGE_GEN_IMAGE_COUNT, False
    )


def test_injected_unknown_aliases_are_dropped_not_raised():
    """Bad injected aliases must degrade to the static preset, never raise."""
    from reasoner.core.constants import IMAGE_GEN_PRESETS
    from reasoner.infrastructure.llm.image_generation import _registered_aliases

    assert _registered_aliases(["made-up-model", "flux.2-klein-4b"]) == ["flux.2-klein-4b"]
    assert _registered_aliases(None) == []
    # A wholly bogus list survives nothing, so generate_images() uses the preset.
    assert len(_registered_aliases(["nope-1", "nope-2"])) < IMAGE_GEN_IMAGE_COUNT
    assert IMAGE_GEN_PRESETS["budget"]


def test_selection_is_deterministic():
    assert select_models("photoreal", "budget", IMAGE_GEN_IMAGE_COUNT, False) == select_models(
        "photoreal", "budget", IMAGE_GEN_IMAGE_COUNT, False
    )
