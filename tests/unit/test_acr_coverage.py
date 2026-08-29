"""ACR coverage guarantees.

Two properties this suite exists to protect:

1. Every model a preset routes to is a real ACR candidate — with catalogue-derived
   limits and prices, not guessed ones — and every routing role has a real
   requirement vector. A model or role that silently falls through is invisible:
   ACR keeps working, it just never considers it.
2. Rerouting preserves fallbacks. A fallback that resolves to the same served
   model as the role's primary choice is not a fallback, and a reroute that drops
   the fallback table leaves the role with nothing.
"""

from __future__ import annotations

import pytest

from reasoner.application.services.adaptive_routing import AdaptiveRoutingService
from reasoner.application.services.role_requirements import (
    ACR_EXCLUDED_ROLES,
    get_requirement,
    has_requirement,
)
from reasoner.application.services.utility_scorer import COLD_START_SCORE
from reasoner.domain.model_capabilities import ModelCapabilities
from reasoner.domain.preset_core import _KNOWN_ROUTING_ROLES
from reasoner.domain.preset_registry import _REGISTRY as PRESETS
from reasoner.infrastructure.llm.capability_registry import CapabilityRegistry
from reasoner.infrastructure.llm.registry import _MODEL_WHITELIST, resolved_model_of
from reasoner.infrastructure.llm.router import ProviderRouter


def _routed_model_ids() -> set[str]:
    """Every model ID any preset can dispatch to, fallbacks and cascades included."""
    routed: set[str] = set()
    for cfg in PRESETS.values():
        routed.add(cfg["primary_id"])
        routed |= set(cfg.get("routing", {}).values())
        routed |= set(cfg.get("fallback_routing", {}).values())
        for chain in cfg.get("cascading_routing", {}).values():
            routed |= set(chain)
    return routed


@pytest.fixture(scope="module")
def registry(tmp_path_factory) -> CapabilityRegistry:
    """Registry with an isolated profile file — never touch ~/.reasoner."""
    path = tmp_path_factory.mktemp("acr") / "capability_profiles.json"
    return CapabilityRegistry(profiles_path=str(path))


# ── Model coverage ────────────────────────────────────────────────────────────


def test_every_routed_model_is_profiled(registry: CapabilityRegistry) -> None:
    profiles = registry.get_all_profiles()
    missing = sorted(m for m in _routed_model_ids() if m not in profiles)
    assert missing == [], f"routed models with no ACR profile: {missing}"


def test_every_routed_model_has_catalogue_constraints(
    registry: CapabilityRegistry,
) -> None:
    """Routed models must have real limits, not the unknown-model default.

    An "unknown" profile is excluded from candidate lists, so a routed model
    landing there would be permanently invisible to ACR.
    """
    profiles = registry.get_all_profiles()
    guessed = sorted(
        m for m in _routed_model_ids()
        if profiles[m].constraints.data_source == "unknown"
    )
    assert guessed == [], (
        "routed models with no catalogue or hint entry — refresh "
        f"domain/openrouter_models.json: {guessed}"
    )


@pytest.mark.parametrize("field", ["max_context_tokens", "cost_per_1k_output_usd"])
def test_routed_model_constraints_are_populated(
    registry: CapabilityRegistry, field: str
) -> None:
    profiles = registry.get_all_profiles()
    zeroed = sorted(
        m for m in _routed_model_ids()
        if not getattr(profiles[m].constraints, field)
    )
    assert zeroed == [], f"routed models with {field} == 0: {zeroed}"


def test_served_model_is_recorded(registry: CapabilityRegistry) -> None:
    """Aliases must carry their served model so collisions are detectable."""
    profiles = registry.get_all_profiles()
    for model_id in _routed_model_ids():
        assert profiles[model_id].constraints.served_model == resolved_model_of(model_id)


def test_unresolved_models_are_local_or_floating_only(
    registry: CapabilityRegistry,
) -> None:
    """Only Ollama builds and floating '-latest' aliases may lack catalogue data."""
    for model_id in registry.unresolved_models():
        assert model_id.startswith("ollama-") or model_id.endswith("-latest"), (
            f"'{model_id}' has no catalogue entry and is not a local or floating alias"
        )


def test_new_alias_becomes_a_candidate_without_restart(
    registry: CapabilityRegistry,
) -> None:
    """A model added to the registry is profiled on the next selection.

    This is the property that keeps ACR current: adding a model to the whitelist
    is enough to make it a candidate — there is no second table to update.
    """
    alias = "__acr_probe_model__"
    assert alias not in registry.get_all_profiles()

    _MODEL_WHITELIST[alias] = {"model": "google/gemini-2.5-flash-lite"}
    try:
        added = registry.refresh()
        assert alias in added

        profile = registry.get_profile(alias)
        assert profile is not None
        assert profile.constraints.data_source == "catalogue"
        assert profile.constraints.max_context_tokens > 0

        eligible = registry.get_models_satisfying(get_requirement("scoring").constraints)
        assert alias in {p.model_id for p in eligible}
    finally:
        _MODEL_WHITELIST.pop(alias, None)
        registry.get_all_profiles().pop(alias, None)
        registry._profiles.pop(alias, None)


def test_unknown_models_are_never_candidates(registry: CapabilityRegistry) -> None:
    unknown = set(registry.unresolved_models())
    assert unknown, "expected at least the Ollama aliases to be unresolved"

    eligible = registry.get_models_satisfying(get_requirement("scoring").constraints)
    assert unknown.isdisjoint({p.model_id for p in eligible})


# ── Role coverage ─────────────────────────────────────────────────────────────


def test_every_known_role_has_a_requirement() -> None:
    unmapped = sorted(
        role for role in _KNOWN_ROUTING_ROLES
        if role not in ACR_EXCLUDED_ROLES and not has_requirement(role)
    )
    assert unmapped == [], (
        "routing roles with no requirement — add them to _ROLE_FAMILY or "
        f"_FAMILY_PREFIXES in role_requirements.py: {unmapped}"
    )


def test_only_sampling_roles_demand_temperature_control() -> None:
    """Requiring temperature control excludes fixed-temperature models entirely.

    claude-sonnet and gpt-5.6-luna are the two most-routed models in the registry
    and the catalogue reports neither as accepting a temperature parameter. Only
    roles whose value genuinely comes from sampling may demand it.
    """
    demanding = {
        role for role in _KNOWN_ROUTING_ROLES
        if role not in ACR_EXCLUDED_ROLES
        and get_requirement(role).constraints.requires_temperature
    }
    expected = {
        # Phase 2 perspectives — multi-sample then prune, run at T=1.0
        "constructive", "destructive", "systemic", "minimalist",
        "perspective", "perspective_cot", "perspective_analysis",
        # Divergent idea generation
        "brainstorm_generate", "brainstorm_develop",
        "expert_1", "expert_2", "expert_3", "expert_4",
        # Tree-of-Thoughts branches before evaluation and backtracking
        "tot_generate",
    }
    assert demanding == expected


def test_every_role_used_by_a_preset_finds_candidates(
    registry: CapabilityRegistry,
) -> None:
    """No role may filter the entire fleet down to nothing."""
    used = {role for cfg in PRESETS.values() for role in cfg.get("routing", {})}
    for role in sorted(used - ACR_EXCLUDED_ROLES):
        eligible = registry.get_models_satisfying(get_requirement(role).constraints)
        assert eligible, f"role '{role}' has zero eligible models"


# ── Fallback selection ────────────────────────────────────────────────────────


@pytest.fixture()
def service(registry: CapabilityRegistry) -> AdaptiveRoutingService:
    return AdaptiveRoutingService(registry=registry, mode="adaptive")


def test_fallback_is_never_the_same_served_model(
    service: AdaptiveRoutingService,
) -> None:
    """'claude-sonnet' and 'claude-sonnet' are one endpoint under two names.

    Pairing them would produce a fallback that fails whenever the primary does.
    """
    assert resolved_model_of("claude-sonnet") == resolved_model_of("claude-sonnet")

    service._ranked_per_role = {
        "scoring": [("claude-sonnet", 0.9), ("glm-5.2", 0.8)],
    }
    service._evidence_roles = {"scoring": True}
    fallbacks = service._select_fallbacks(
        ["scoring"],
        {"scoring": "claude-sonnet"},
        static_fallbacks={"scoring": "claude-sonnet"},
    )
    assert fallbacks["scoring"] == "glm-5.2"


def test_fallback_prefers_a_different_bloc(service: AdaptiveRoutingService) -> None:
    service._ranked_per_role = {
        "scoring": [("grok-4.6", 0.9), ("glm-5.2", 0.7)],
    }
    service._evidence_roles = {"scoring": True}
    fallbacks = service._select_fallbacks(
        ["scoring"], {"scoring": "gpt-5.6-luna"}, static_fallbacks={}
    )
    # grok-4.6 outranks glm-5.2 but shares the US bloc with the assigned model.
    assert fallbacks["scoring"] == "glm-5.2"


def test_cold_start_fallback_stays_inside_the_preset(
    service: AdaptiveRoutingService,
) -> None:
    """With no benchmark data the ranking is a tie broken alphabetically.

    Picking the tie-winner would back synthesis with whatever model sorts first;
    the pool narrows to models this preset already routes to instead.
    """
    service._ranked_per_role = {
        "synthesis": [("codestral", 0.5), ("glm-5.2", 0.5), ("grok-4.6", 0.5)],
    }
    service._evidence_roles = {"synthesis": False}

    fallbacks = service._select_fallbacks(
        ["synthesis", "scoring"],
        {"synthesis": "gpt-5.6-luna", "scoring": "glm-5.2"},
        static_fallbacks={},
    )
    # codestral outranks nothing — it merely sorts first — and the preset never
    # routes to it, so glm-5.2 (used by the scoring role) backs synthesis.
    assert fallbacks["synthesis"] == "glm-5.2"


def test_preset_fallback_is_kept_when_still_valid(
    service: AdaptiveRoutingService,
) -> None:
    service._ranked_per_role = {"scoring": [("grok-4.6", 0.9)]}
    fallbacks = service._select_fallbacks(
        ["scoring"], {"scoring": "gpt-5.6-luna"}, static_fallbacks={"scoring": "glm-5.2"}
    )
    assert fallbacks["scoring"] == "glm-5.2"


def test_no_fallback_invented_when_no_alternative_exists(
    service: AdaptiveRoutingService,
) -> None:
    service._ranked_per_role = {"scoring": [("claude-sonnet", 0.9)]}
    service._evidence_roles = {"scoring": True}
    fallbacks = service._select_fallbacks(
        ["scoring"], {"scoring": "claude-sonnet"}, static_fallbacks={}
    )
    assert "scoring" not in fallbacks


@pytest.mark.asyncio
async def test_routing_plan_assigns_fallbacks_for_every_role(
    service: AdaptiveRoutingService,
) -> None:
    static = {"scoring": "glm-5.2", "synthesis": "gpt-5.6-luna"}
    plan = await service.select_routing_plan(list(static), static, static_fallbacks={})

    for role, assigned in plan.routing.items():
        fallback = plan.fallbacks.get(role)
        assert fallback, f"role '{role}' left with no fallback"
        assert resolved_model_of(fallback) != resolved_model_of(assigned)


# ── Evidence guard ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_override_without_measured_capabilities(
    registry: CapabilityRegistry,
) -> None:
    """Cold-start models all score identically, so a win means nothing.

    Without this guard the alphabetically-first candidate takes every role.
    """
    service = AdaptiveRoutingService(registry=registry, mode="advisory")
    static = {"scoring": "glm-5.2"}

    routing = await service.select_routing_table(["scoring"], static)

    assert routing["scoring"] == "glm-5.2"
    assert all(log.acr_score <= COLD_START_SCORE for log in service.selection_log)


@pytest.mark.asyncio
async def test_override_allowed_once_capabilities_are_measured(
    tmp_path,
) -> None:
    registry = CapabilityRegistry(profiles_path=str(tmp_path / "profiles.json"))
    registry.update_capabilities(
        "grok-4.6",
        ModelCapabilities(
            scores={"reasoning": 0.95, "consistency": 0.95, "json_output": 0.95},
            source="benchmark_test",
            sample_count=100,
        ),
    )

    service = AdaptiveRoutingService(registry=registry, mode="advisory")
    routing = await service.select_routing_table(["scoring"], {"scoring": "glm-5.2"})

    assert routing["scoring"] == "grok-4.6"


# ── Router / preset plumbing ──────────────────────────────────────────────────


def test_router_retains_model_ids_for_rebuild() -> None:
    """The reroute in PipelineOrchestrator rebuilds from these IDs.

    The built tables hold providers, so without the ID-level copy a rebuild
    silently drops every fallback and cascade.
    """
    router = ProviderRouter.from_model_ids(
        primary_id="claude-sonnet",
        routing={"scoring": "glm-5.2"},
        fallback_routing={"scoring": "grok-4.6"},
        cascading_routing={"coding_generate": ["glm-5.2", "grok-4.6"]},
    )

    assert router.primary_id == "claude-sonnet"
    assert router.routing_ids == {"scoring": "glm-5.2"}
    assert router.fallback_routing_ids == {"scoring": "grok-4.6"}
    assert router.cascading_routing_ids == {"coding_generate": ["glm-5.2", "grok-4.6"]}


def test_auto_router_carries_preset_fallbacks() -> None:
    """Auto-selected presets must keep the fallbacks a named preset would get."""
    from reasoner.application.services.preset_service import PresetService
    from reasoner.core.ports.model_registry_port import set_model_registry_port
    from reasoner.infrastructure.llm.registry import RegistryAdapter

    set_model_registry_port(RegistryAdapter())

    # Only two presets declare explicit fallbacks; coding-budget is one, and it
    # also carries a cascade — both are dropped without the fix.
    preset = PRESETS["coding-budget"]
    assert preset.get("fallback_routing"), "coding-budget lost its fallback table"

    preset_id, router = PresetService().build_auto_router(method="coding", tier="budget")

    assert preset_id == "coding-budget"
    assert router.fallback_routing_ids == preset["fallback_routing"]
    assert router.cascading_routing_ids == preset.get("cascading_routing", {})
