"""Delphi's four round-1 experts must be four different models.

`run_delphi_round1_phase` fans out four calls with `role=f"expert_{i+1}"` on an
identical prompt that tells each one it is "Expert N of 4 independent
forecasters ... do NOT anchor to any consensus", and the aggregation phase then
computes a median, an IQR and an "outlier_expert" over the four answers.

Every one of those outputs is meaningless unless the four forecasters really are
independent. Before D0 they were not: `expert_1..4` were declared in
`_KNOWN_ROUTING_ROLES` and mapped to the `generate` task class for ACR, but no
preset routed them, so `ProviderRouter.resolve()` fell through to `primary_id`
(router.py: "Falls back to primary for any unspecified role") and the whole
panel was four temperature samples of ONE model. The reported spread was
sampling noise and the "outlier" was an artefact.

`BlocDiversityConstraint` could not catch it either: its `_GENERATOR_ROLES` set
omitted `expert_*`, so rule 4 -- "no two generator roles resolve to the
identical underlying model", written for exactly this failure -- never fired.

Scope note: this file deliberately does NOT assert the general rule "every role
in _KNOWN_ROUTING_ROLES must be routed by some preset". 37 of the 86 known roles
are legitimately unrouted and intended to fall through to primary_id
(`hypergate_*`, `subagent_*`, `classification`, `decomposition`, ...). What
makes the Delphi panel different is not that the roles were unrouted, but that
the *prompt asserts independence between siblings* -- so falling through to one
model contradicts the phase's own semantics. That is the invariant under test.

See docs/ENSEMBLE_DIVERSITY.md §4 and docs/plans/ensemble-diversity-measurement.md D0.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from reasoner.domain.preset_registry import _REGISTRY as PRESETS  # noqa: E402
from reasoner.infrastructure.llm.constraints.bloc_diversity import (  # noqa: E402
    _GENERATOR_ROLES,
    BlocDiversityConstraint,
)
from reasoner.infrastructure.llm.registry import bloc_of, resolved_model_of  # noqa: E402

EXPERT_ROLES = ("expert_1", "expert_2", "expert_3", "expert_4")

_DELPHI = sorted(p for p, cfg in PRESETS.items() if cfg.get("method") == "delphi")


@pytest.mark.unit
def test_there_is_at_least_one_delphi_preset():
    """Guard the guard: an empty parametrize list would vacuously pass."""
    assert _DELPHI, "no preset declares method == 'delphi'"


@pytest.mark.unit
@pytest.mark.parametrize("preset_id", _DELPHI)
def test_delphi_routes_every_expert_slot(preset_id):
    """An unrouted expert slot silently collapses onto primary_id."""
    routing = PRESETS[preset_id].get("routing", {})
    missing = [r for r in EXPERT_ROLES if not routing.get(r)]
    assert not missing, (
        f"{preset_id}: expert slots {missing} are unrouted, so ProviderRouter "
        f"resolves them to primary_id ({PRESETS[preset_id].get('primary_id')}) "
        f"and the 'independent' panel becomes N samples of one model"
    )


@pytest.mark.unit
@pytest.mark.parametrize("preset_id", _DELPHI)
def test_delphi_experts_are_four_distinct_models(preset_id):
    """Distinctness is judged on the RESOLVED model, never the alias.

    The registry contains cross-vendor aliases, so two slots can look different
    and be the same served model -- which is what rule 4 exists to catch.
    """
    routing = PRESETS[preset_id].get("routing", {})
    served: dict[str, list[str]] = {}
    for role in EXPERT_ROLES:
        alias = routing.get(role)
        if alias:
            served.setdefault(resolved_model_of(alias), []).append(role)

    repeated = {s: rs for s, rs in served.items() if len(rs) > 1}
    assert not repeated, (
        f"{preset_id}: expert roles share served models {repeated}; the panel "
        f"is not independent"
    )
    assert len(served) == len(EXPERT_ROLES), (
        f"{preset_id}: expected {len(EXPERT_ROLES)} distinct served models, "
        f"got {len(served)}"
    )


@pytest.mark.unit
@pytest.mark.parametrize("preset_id", _DELPHI)
def test_delphi_experts_span_blocs(preset_id):
    """Same invariant BlocDiversityConstraint rules 2-3 apply to generators.

    Four models from one bloc would satisfy distinctness while still sharing
    the ideological prior the cross-bloc rules exist to break up.
    """
    routing = PRESETS[preset_id].get("routing", {})
    blocs: dict[str, list[str]] = {}
    for role in EXPERT_ROLES:
        alias = routing.get(role)
        if alias:
            blocs.setdefault(bloc_of(alias), []).append(role)

    known = {b: rs for b, rs in blocs.items() if b != "OTHER"}
    assert len(known) >= 2, f"{preset_id}: expert panel spans <2 known blocs ({blocs})"
    dominant = {b: rs for b, rs in known.items() if len(rs) > 2}
    assert not dominant, (
        f"{preset_id}: bloc(s) dominate the expert panel {dominant}; max 2 per bloc"
    )


@pytest.mark.unit
def test_expert_roles_count_as_generators():
    """The omission that made rule 4 blind to Delphi must not come back."""
    missing = [r for r in EXPERT_ROLES if r not in _GENERATOR_ROLES]
    assert not missing, (
        f"{missing} dropped out of BlocDiversityConstraint._GENERATOR_ROLES; "
        f"rule 4 goes blind to the Delphi panel again"
    )


@pytest.mark.unit
def test_constraint_rejects_a_duplicated_expert():
    """Rule 4 must produce a hard violation when two experts share a model.

    This is the regression the production defect would have tripped: it asserts
    the constraint *can* see expert roles, independently of what the presets
    currently happen to declare.
    """
    violations = BlocDiversityConstraint().validate(
        {
            "expert_1": "claude-sonnet",
            "expert_2": "claude-sonnet",  # same model, different slot
            "expert_3": "deepseek-v4-pro",
            "expert_4": "mistral-large-3",
        },
        "delphi-premium",
    )
    hard = [v for v in violations if v.severity == "hard"]
    assert hard, "duplicated expert model produced no hard violation"
    assert any("same underlying model" in v.reason for v in hard), (
        f"expected rule 4 to fire; got {[v.reason for v in hard]}"
    )


@pytest.mark.unit
def test_constraint_accepts_a_cross_bloc_panel():
    """The positive case: a genuine four-model panel must pass cleanly."""
    violations = BlocDiversityConstraint().validate(
        {
            "expert_1": "gpt-5.6-terra",       # US
            "expert_2": "gemini-pro-real",     # US
            "expert_3": "qwen3-max-thinking",  # CN
            "expert_4": "mistral-large-3",     # EU
        },
        "delphi-premium",
    )
    assert not [v for v in violations if v.severity == "hard"], (
        f"valid cross-bloc panel rejected: {[v.reason for v in violations]}"
    )


@pytest.mark.unit
@pytest.mark.parametrize("preset_id", _DELPHI)
def test_delphi_experts_honour_temperature(preset_id):
    """expert_* is the `generate` family, whose _SAMPLED constraint requires it.

    role_requirements maps expert_1..4 to "generate", whose constraints are
    _SAMPLED = TaskConstraints(requires_temperature=True) -- "a fixed-temperature
    model cannot do the job, so exclude it". A fixed-temperature model in one of
    these slots is therefore dropped by capability_registry.find_candidates when
    ACR_ENABLED=true, and ACR substitutes something else: the panel documented in
    the preset silently stops being the panel that runs.

    delphi-premium shipped with gpt-5.6-terra in expert_1 until this was caught.
    ACR_ENABLED defaults to false, so it was latent, not live.
    """
    from reasoner.infrastructure.llm.registry import honours_tuned_temperature

    routing = PRESETS[preset_id].get("routing", {})
    fixed = [
        (role, routing[role])
        for role in EXPERT_ROLES
        if routing.get(role) and not honours_tuned_temperature(routing[role])
    ]
    assert not fixed, (
        f"{preset_id}: expert slots on fixed-temperature models {fixed}; "
        f"the generate family requires temperature control, so ACR would drop "
        f"and silently replace them"
    )
