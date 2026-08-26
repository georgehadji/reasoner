"""Constraint: terminal roles must meet a propagation-resistance floor.

Rule (derived from Papadopoulos et al., arXiv:2608.10218, 2026):

    The roles that produce *persisted, replayed, or user-facing* output — synthesis
    and the independent-verification family — must resolve to a model with a
    measured resistance to self-propagating content at or above the configured
    floor.

Why terminal roles specifically, and not every role:

A susceptible *generator* is contained by the topology. Phase-2 perspectives are
blind to each other and everything they produce funnels through critique, scoring,
and synthesis, so one compromised generator is one out-voted opinion. A susceptible
*synthesiser* is not contained by anything: its output is what gets streamed to the
user, stored as the run's answer, and — since the Neuro loop closed — replayed into
future runs as recalled memory. That is the point where content stops being a
candidate and becomes the system's position.

This mirrors BlocDiversityConstraint's rule 1 (synthesis bloc ≠ scoring bloc): both
say the terminal position carries requirements the generators do not.

MEASURED STATE AS OF 2026-08-25 — READ BEFORE ENABLING ENFORCEMENT
==================================================================
Run against the live preset registry at floor 0.60, **0 of 49 presets clear it**:

    post_synthesis_verify   49 presets   sonar, sonar-pro, sonar-deep-research
    synthesis               47 presets   deepseek-v4-pro, glm-5.2, grok-4.3,
                                         llama-4-maverick, gemini-3.7-flash
    verifier                45 presets   gemini-flash-lite-real, qwen3-max-thinking

Lowering the floor to 0.25 changes nothing. The reason is not that Reasoner routes
badly — it is that the published evidence base covers roughly 7 model families out
of 224 whitelist entries, so almost everything scores UNMEASURED and fails closed.

The verify-role result is the clearest illustration. Every preset routes
post-synthesis verification to Perplexity Sonar, and that is a *good* decision:
Sonar has live web search, which is precisely what an independent fact-checker
needs. Sonar is unmeasured, not weak. A constraint that blocked it would be
destroying a real control in the name of a theoretical one.

So this constraint ships as **observability, not a gate**, and the default stays
soft. It earns the right to enforce only when one of these is true:

  a. Reasoner has its own per-model propagation-resistance measurements (an
     eval harness replaying known payloads through each candidate terminal
     model), or
  b. the published evidence base widens enough to cover the models actually in
     terminal roles.

Until then, treat a rising violation count against a *previously clearing* preset
as the signal — a routing change that moved a terminal role from measured-resistant
to unmeasured is worth knowing about, even when the absolute number is unusable.
Do not set PROPAGATION_RESISTANCE_ENFORCE=true against the current table; it would
fail every preset in the registry.
"""

from __future__ import annotations

from reasoner.core.ports.routing_constraint_port import ConstraintViolation
from reasoner.infrastructure.llm.propagation_resistance import (
    is_measured,
    propagation_resistance_of,
)

# Roles whose output is persisted, replayed, or shown to the user as the answer.
# "verify" roles are included because a verifier that has adopted the content it
# was meant to check is worse than no verifier — it launders the claim.
_TERMINAL_ROLES = frozenset({
    "synthesis",
    "final_synthesis",
    "post_synthesis_verify",
    "verification",
    "verifier",
})


class PropagationResistanceConstraint:
    """Enforce a resistance floor on roles that produce terminal output."""

    def __init__(self, floor: float | None = None, enforce: bool | None = None) -> None:
        self._floor = floor
        self._enforce = enforce

    def _settings(self) -> tuple[float, bool]:
        from reasoner.core.settings import settings

        floor = (
            self._floor
            if self._floor is not None
            else settings.PROPAGATION_RESISTANCE_FLOOR
        )
        enforce = (
            self._enforce
            if self._enforce is not None
            else settings.PROPAGATION_RESISTANCE_ENFORCE
        )
        return floor, enforce

    def validate(
        self,
        proposed: dict[str, str],  # role → model_id
        preset_id: str,            # unused, kept for protocol compatibility
    ) -> list[ConstraintViolation]:
        violations: list[ConstraintViolation] = []
        if not proposed:
            return violations

        floor, enforce = self._settings()
        if floor <= 0:
            return violations

        severity = "hard" if enforce else "soft"

        for role, model_id in proposed.items():
            if role not in _TERMINAL_ROLES:
                continue
            score = propagation_resistance_of(model_id)
            if score >= floor:
                continue
            if is_measured(model_id):
                reason = (
                    f"terminal role '{role}' routes to '{model_id}', whose measured "
                    f"propagation resistance ({score:.2f}) is below the floor "
                    f"({floor:.2f})"
                )
            else:
                reason = (
                    f"terminal role '{role}' routes to '{model_id}', which has no "
                    f"published propagation-resistance measurement. Unmeasured is "
                    f"treated as failing the floor ({floor:.2f}) rather than passing "
                    f"it — capability does not predict resistance"
                )
            violations.append(
                ConstraintViolation(
                    constraint_name="propagation_resistance",
                    role=role,
                    model_id=model_id,
                    reason=reason,
                    severity=severity,
                )
            )

        return violations


__all__ = ["PropagationResistanceConstraint"]
