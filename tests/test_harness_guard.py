"""Tests for harness_guard's registry-backed vendor lookup (W6).

Before W6, ``get_model_lab`` checked a hand-maintained ``_MODEL_LABS`` dict
that mirrored ``infrastructure.llm.registry`` and drifted from it. Its
docstring claimed an unknown alias "doesn't count toward diversity", but both
invariants used a Python ``set``, so a missing alias silently *inflated*
diversity (Invariant 1) and let a same-vendor-but-unlisted fallback silently
*pass* the cross-lab check (Invariant 2). See
docs/plans/gate-and-registry-remediation.md W6.
"""

from __future__ import annotations

import pytest

from reasoner.application.services.harness_guard import (
    check_mutation_invariants,
    get_model_lab,
)
from reasoner.core.ports.model_registry_port import ModelRegistryPort, get_model_registry_port
from reasoner.domain.harness_metrics import HarnessMutation
from reasoner.infrastructure.llm.registry import RegistryAdapter, _MODEL_WHITELIST


def _mutation(target: str = "preset:debate-budget.scoring") -> HarnessMutation:
    return HarnessMutation(
        target=target,
        component="routing",
        failure_mode="cost_issue",
        predicted_effect="test",
        invariant_preserved="cross-lab diversity maintained",
        rollback="revert",
        risk_tier="safe",
    )


def test_registry_adapter_satisfies_model_registry_port():
    assert isinstance(RegistryAdapter(), ModelRegistryPort)


def test_every_whitelisted_model_resolves_to_a_nonempty_vendor():
    port = get_model_registry_port()
    for model_id in _MODEL_WHITELIST:
        vendor = port.vendor_of(model_id)
        assert vendor, f"{model_id!r} resolved to an empty vendor"


def test_get_model_lab_raises_for_unregistered_alias():
    """Fail loud (W6 design option (a)): an alias the registry doesn't know
    is a caller bug, not a diversity-neutral "unknown"."""
    with pytest.raises(ValueError):
        get_model_lab("totally-not-a-real-model-alias")


def test_same_vendor_triple_is_rejected():
    """Three same-vendor models must fail the min-diversity invariant.

    Regression guard for the old bug: if two of the three had been missing
    from _MODEL_LABS, they'd each read "unknown" and inflate len(labs) to 2,
    passing a check that should fail.
    """
    accepted, reason = check_mutation_invariants(
        _mutation(),
        current_models=["gpt-5", "gpt-5-mini", "o3"],
        proposed_models=["gpt-5", "gpt-5-mini", "o3"],
    )
    assert not accepted
    assert "diversity" in reason.lower()


def test_same_vendor_fallback_terminal_is_rejected():
    """Primary + fallback from the same real vendor must fail the terminal check.

    Regression guard: previously, a fallback alias missing from _MODEL_LABS
    resolved to "unknown", which never equals the primary's real lab, so a
    same-vendor-but-unlisted fallback silently passed. vendor_of() has no
    "unlisted" state for a registered model, so this can no longer happen.
    """
    accepted, reason = check_mutation_invariants(
        _mutation(),
        current_models=["mistral-large-3", "mistral-small"],
        proposed_models=["mistral-large-3", "mistral-small"],
    )
    assert not accepted
    assert "cross-lab" in reason.lower()


def test_cross_vendor_pair_is_accepted():
    accepted, _ = check_mutation_invariants(
        _mutation(),
        current_models=["gpt-5", "claude-sonnet"],
        proposed_models=["gpt-5", "claude-sonnet"],
    )
    assert accepted


def test_cost_mutation_requires_non_safe_risk_tier():
    accepted, reason = check_mutation_invariants(
        _mutation(target="preset:debate-budget.cost_cap"),
        current_models=["gpt-5", "claude-sonnet"],
        proposed_models=["gpt-5", "claude-sonnet"],
    )
    assert not accepted
    assert "risk_tier" in reason
