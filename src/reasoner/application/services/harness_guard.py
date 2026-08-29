"""HarnessGuard — invariant validation for governed harness mutations (#4).

Paper grounding: §3.5.3 — hard invariant guard: a mutation may not reduce
Phase-2 cross-lab diversity below preset minima or remove a fallback chain's
cross-lab terminal.
"""

from __future__ import annotations

from reasoner.core.evolution_constants import (
    EVOLUTION_MIN_CROSS_LAB_DIVERSITY,
    EVOLUTION_REQUIRE_CROSS_LAB_FALLBACK_TERMINAL,
)
from reasoner.core.ports.model_registry_port import get_model_registry_port
from reasoner.domain.harness_metrics import HarnessMutation


def get_model_lab(model_alias: str) -> str:
    """Return the training ecosystem (vendor) for a model alias, via the registry port.

    Was a hand-maintained ~150-entry dict here (``_MODEL_LABS``) that mirrored
    ``infrastructure.llm.registry`` and drifted from it — a model added to the
    registry needed a second, manual edit here to stay covered, and nothing
    enforced that; see docs/plans/gate-and-registry-remediation.md W6.

    Raises ``ValueError`` for an alias the registry doesn't know (W6, option
    (a)): the aliases this guard receives come from routing tables built off
    the registry, so an unknown one means the caller passed a bad alias, not
    that the model is genuinely lab-less. The previous "unknown" sentinel let
    that same bug pass silently in both directions — see
    ``check_mutation_invariants``.
    """
    port = get_model_registry_port()
    if not port.contains(model_alias):
        raise ValueError(
            f"harness_guard received unregistered model alias {model_alias!r}. "
            "Mutation model aliases must come from the model registry."
        )
    return port.vendor_of(model_alias)


def check_mutation_invariants(
    mutation: HarnessMutation,
    current_models: list[str],
    proposed_models: list[str],
) -> tuple[bool, str]:
    """Check that a proposed mutation preserves hard invariants.

    Args:
        mutation: The proposed harness mutation.
        current_models: Model aliases currently in use for this routing role.
        proposed_models: Model aliases after the mutation would be applied.

    Returns:
        (accepted: bool, reason: str) — False + reason if an invariant would
        be violated.
    """
    # Invariant 1: cross-lab diversity must not fall below minimum
    current_labs = {get_model_lab(m) for m in current_models}
    proposed_labs = {get_model_lab(m) for m in proposed_models}
    current_diversity = len(current_labs)
    proposed_diversity = len(proposed_labs)

    if proposed_diversity < EVOLUTION_MIN_CROSS_LAB_DIVERSITY:
        return False, (
            f"Mutation would reduce cross-lab diversity from {current_diversity} "
            f"to {proposed_diversity} (min {EVOLUTION_MIN_CROSS_LAB_DIVERSITY} required). "
            f"Labs: {proposed_labs}"
        )

    # Invariant 2: fallback chain terminal must be cross-lab (if required)
    if EVOLUTION_REQUIRE_CROSS_LAB_FALLBACK_TERMINAL and len(proposed_models) >= 2:
        primary_lab = get_model_lab(proposed_models[0])
        fallback_labs = {get_model_lab(m) for m in proposed_models[1:]}
        if primary_lab in fallback_labs:
            return False, (
                f"Fallback terminal {proposed_models[-1]} is same lab ({primary_lab}) "
                f"as primary {proposed_models[0]}. Cross-lab fallback required."
            )

    # Invariant 3: cost-tier mutations require risk_tier="cost" or "safety"
    if "cost" in mutation.target.lower() or "spend" in mutation.target.lower():
        if mutation.risk_tier == "safe":
            return False, (
                f"Cost-affecting mutation targeting '{mutation.target}' must be "
                f"risk_tier='cost' or 'safety', not '{mutation.risk_tier}'."
            )

    return True, ""
