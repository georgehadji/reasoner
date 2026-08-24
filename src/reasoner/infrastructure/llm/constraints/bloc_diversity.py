"""Constraint: enforce cross-bloc diversity in model assignments.

Rules (derived from Buyl et al., npj AI 2026):
1. synthesis bloc ≠ scoring bloc
2. Perspective/debate generator roles span ≥2 blocs
3. No single bloc holds >2 generator roles
4. No two generator roles resolve to the identical underlying model
   (catches alias collisions, e.g. "gemini-pro" and "claude-sonnet" both
   secretly routing to anthropic/claude-sonnet-5 — same model arguing
   and judging itself)
"""

from __future__ import annotations

from collections import Counter, defaultdict

from reasoner.core.ports.routing_constraint_port import (
    ConstraintViolation,
)
from reasoner.infrastructure.llm.registry import bloc_of, resolved_model_of

_GENERATOR_ROLES = frozenset({
    "constructive", "destructive", "systemic", "minimalist",
    "empirical", "financial", "environmental", "ethical",
    "technical", "practical",
    "opening", "generator",
})


class BlocDiversityConstraint:
    """Enforce cross-bloc diversity in model assignments."""

    def validate(
        self,
        proposed: dict[str, str],  # role → model_id
        preset_id: str,            # unused, kept for protocol compatibility
    ) -> list[ConstraintViolation]:
        violations: list[ConstraintViolation] = []

        if not proposed:
            return violations

        # Build role → bloc mapping
        role_bloc: dict[str, str] = {}
        for role, model_id in proposed.items():
            role_bloc[role] = bloc_of(model_id)

        # Rule 1: synthesis bloc ≠ scoring bloc
        synth_bloc = role_bloc.get("synthesis")
        scoring_bloc = role_bloc.get("scoring")
        if synth_bloc and scoring_bloc and synth_bloc == scoring_bloc:
            violations.append(ConstraintViolation(
                constraint_name="bloc_diversity",
                role="synthesis",
                model_id=proposed.get("synthesis", ""),
                reason=(
                    f"Synthesis bloc ({synth_bloc}) must differ from "
                    f"scoring bloc ({scoring_bloc})"
                ),
                severity="hard",
            ))

        # Rule 2: Generator roles span ≥2 blocs
        gen_blocs = set()
        for role in _GENERATOR_ROLES:
            bloc = role_bloc.get(role)
            if bloc:
                gen_blocs.add(bloc)
        if len(gen_blocs) < 2 and len(gen_blocs) > 0:
            role_list = [r for r in _GENERATOR_ROLES if r in proposed]
            violations.append(ConstraintViolation(
                constraint_name="bloc_diversity",
                role=role_list[0] if role_list else "unknown",
                model_id=proposed.get(role_list[0], "") if role_list else "",
                reason=(
                    f"Generator roles span only {len(gen_blocs)} bloc(s) "
                    f"({', '.join(sorted(gen_blocs))}); need ≥2 blocs"
                ),
                severity="hard",
            ))

        # Rule 3: No single bloc holds >2 generator roles
        gen_role_counts: Counter[str] = Counter()
        for role in _GENERATOR_ROLES:
            bloc = role_bloc.get(role)
            if bloc:
                gen_role_counts[bloc] += 1
        for bloc, count in gen_role_counts.items():
            if count > 2:
                # Find the roles assigned to this bloc
                bloc_roles = [r for r in _GENERATOR_ROLES
                              if role_bloc.get(r) == bloc]
                violations.append(ConstraintViolation(
                    constraint_name="bloc_diversity",
                    role=bloc_roles[0] if bloc_roles else "unknown",
                    model_id=proposed.get(bloc_roles[0], "") if bloc_roles else "",
                    reason=(
                        f"Bloc '{bloc}' holds {count} generator roles "
                        f"(max 2): {', '.join(bloc_roles)}"
                    ),
                    severity="hard",
                ))

        # Rule 4: No two generator roles resolve to the identical model
        model_roles: dict[str, list[str]] = defaultdict(list)
        for role in _GENERATOR_ROLES:
            if role in proposed:
                model_roles[resolved_model_of(proposed[role])].append(role)
        for model, roles in model_roles.items():
            if len(roles) > 1:
                violations.append(ConstraintViolation(
                    constraint_name="bloc_diversity",
                    role=roles[0],
                    model_id=proposed.get(roles[0], ""),
                    reason=(
                        f"Roles {', '.join(sorted(roles))} all resolve to the "
                        f"same underlying model ({model}) despite distinct "
                        f"aliases — defeats adversarial/perspective diversity"
                    ),
                    severity="hard",
                ))

        return violations


__all__ = ["BlocDiversityConstraint"]
