"""Adaptive routing service — orchestrates ACR model selection (ACR Phase 5).

Wires together the capability registry, utility scorer, constraint resolver,
and telemetry store to select optimal models for each pipeline role.

Supports three modes defined in the ACR implementation plan:
  - SHADOW: Logs what ACR would select alongside static routing (no impact)
  - ADVISORY: ACR selects, but preset overrides win on conflict
  - ADAPTIVE: ACR selects, constraints validate, preset is fallback only
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from reasoner.domain.model_capabilities import (
    ModelCapabilities,
    ModelConstraints,
    ModelProfile,
)
from reasoner.domain.task_requirements import TaskRequirement
from reasoner.domain.scoring_weights import ScoringWeights, get_weights_for_tier
from reasoner.application.services.role_requirements import (
    ACR_EXCLUDED_ROLES,
    get_requirement,
)
from reasoner.application.services.utility_scorer import COLD_START_SCORE, UtilityScorer
from reasoner.application.services.constraint_resolver import ConstraintResolver

logger = logging.getLogger(__name__)


@dataclass
class ACRSelectionLog:
    """Log entry for a single ACR selection decision."""

    role: str
    preset_model: str
    acr_model: str
    acr_score: float = 0.0
    preset_score: float | None = None
    reason: str = ""
    constraints_passed: bool = True


@dataclass(frozen=True)
class RoutingPlan:
    """A complete ACR decision: which model runs each role, and what backs it up."""

    routing: dict[str, str] = field(default_factory=dict)
    fallbacks: dict[str, str] = field(default_factory=dict)
    log: list[ACRSelectionLog] = field(default_factory=list)


class AdaptiveRoutingService:
    """Orchestrates adaptive model selection for pipeline runs.

    Wires together the capability registry, utility scorer, constraint
    resolver, and telemetry store.

    Modes:
    - ``shadow``: Logs ACR selections alongside static preset routing.
      No impact on actual routing. Default — safe for production.
    - ``advisory``: ACR selects, but preset overrides win on conflict.
    - ``adaptive``: ACR selects, constraints validate, preset is fallback.
    """

    def __init__(
        self,
        registry: Any = None,  # CapabilityRegistryPort
        scorer: UtilityScorer | None = None,
        resolver: ConstraintResolver | None = None,
        telemetry: Any = None,  # CallTelemetryPort
        mode: str = "shadow",
        preset_tier: str = "balanced",
    ) -> None:
        """Initialise the adaptive routing service.

        Args:
            registry: Capability registry instance. If None, attempts
                to lazy-load the default implementation.
            scorer: Utility scorer. Defaults to balanced-weight scorer.
            resolver: Constraint resolver. Defaults to default resolver.
            telemetry: Call telemetry store. If None, no telemetry recording.
            mode: ``"shadow"`` (default), ``"advisory"``, or ``"adaptive"``.
            preset_tier: ``"budget"``, ``"balanced"``, or ``"premium"``.
        """
        self._mode = mode
        self._preset_tier = preset_tier
        self._registry = registry
        self._scorer = scorer or UtilityScorer(
            weights=get_weights_for_tier(preset_tier),
        )
        self._resolver = resolver or ConstraintResolver()
        self._telemetry = telemetry
        self._selection_log: list[ACRSelectionLog] = []
        # Per-selection working state, kept so fallback selection can reuse the
        # ranking and profiles instead of re-scoring every candidate.
        self._ranked_per_role: dict[str, list[tuple[str, float]]] = {}
        self._profiles_per_role: dict[str, dict[str, ModelProfile]] = {}
        self._evidence_roles: dict[str, bool] = {}

        # Lazy-load registry if not provided
        if self._registry is None:
            self._lazy_load_registry()

    def _lazy_load_registry(self) -> None:
        """Lazy-load the default capability registry."""
        try:
            from reasoner.infrastructure.llm.capability_registry import (
                CapabilityRegistry,
            )
            self._registry = CapabilityRegistry()
        except Exception as exc:
            logger.warning("Failed to load capability registry: %s", exc)

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def selection_log(self) -> list[ACRSelectionLog]:
        return list(self._selection_log)

    def update_weights_for_tier(self, tier: str) -> None:
        """Update the utility scorer weights for a different preset tier."""
        self._scorer.weights = get_weights_for_tier(tier)
        self._preset_tier = tier

    async def select_routing_table(
        self,
        roles: list[str],
        static_routing: dict[str, str],
        preset_id: str = "",
    ) -> dict[str, str]:
        """Select the optimal model for each role.

        Args:
            roles: List of role names to assign (e.g. ``["constructive", "scoring"]``).
            static_routing: The static preset's role → model_id mapping.
                Used as the fallback in all modes.
            preset_id: Preset being routed, passed to constraint validation.

        Returns:
            role → model_id mapping.

        In SHADOW mode: returns ``static_routing`` unchanged, logs ACR choices.
        In ADVISORY mode: returns ACR choices, but ``static_routing`` wins
            on conflict if the ACR choice has low confidence.
        In ADAPTIVE mode: returns ACR choices validated by constraints.
        """
        if not self._registry:
            return static_routing

        self._selection_log.clear()

        # 1. Get requirements for each role
        ranked_per_role: dict[str, list[tuple[str, float]]] = {}

        self._profiles_per_role.clear()
        self._evidence_roles.clear()

        for role in roles:
            if role in ACR_EXCLUDED_ROLES:
                # Selected by other machinery (e.g. the image model catalogue).
                ranked_per_role[role] = [(static_routing.get(role, ""), 0.0)]
                continue

            req = get_requirement(role)
            candidates = self._get_candidates(req)

            if not candidates:
                # No candidates — fall back to static routing
                ranked_per_role[role] = [(static_routing.get(role, ""), 0.0)]
                continue

            scored = self._scorer.rank_models(candidates, req)
            ranked_per_role[role] = [(m.model_id, s) for m, s in scored]
            self._profiles_per_role[role] = {m.model_id: m for m, _ in scored}
            # Without at least one benchmarked candidate the ranking is a tie at
            # the cold-start score and the winner is decided alphabetically.
            # Record that so no mode overrides the preset on zero evidence.
            self._evidence_roles[role] = any(m.has_capabilities for m, _ in scored)

        self._ranked_per_role = ranked_per_role

        # 2. Resolve constraints.
        # Run in every mode, not just adaptive: resolution is pure in-process
        # computation, and skipping it left `assignment` equal to the static
        # routing — which made shadow logging report "ACR agrees" unconditionally
        # and made advisory mode a no-op, since it merged static onto static.
        assignment = self._resolver.resolve(
            ranked_per_role,
            preset_id=preset_id,
            fallback=static_routing,
        )

        # 3. Log ACR selections vs static routing
        for role in roles:
            static_model = static_routing.get(role, "?")
            acr_model = assignment.get(role, static_model)
            acr_score = 0.0
            if role in ranked_per_role and ranked_per_role[role]:
                for model_id, score in ranked_per_role[role]:
                    if model_id == acr_model:
                        acr_score = score
                        break

            log_entry = ACRSelectionLog(
                role=role,
                preset_model=static_model,
                acr_model=acr_model,
                acr_score=acr_score,
                reason=self._selection_reason(role, static_model, acr_model),
            )
            self._selection_log.append(log_entry)

            # Log significant differences
            if static_model != acr_model:
                logger.info(
                    "ACR %s: role='%s' preset=%s acr=%s (score=%.3f)",
                    self._mode, role, static_model, acr_model, acr_score,
                )

        # 4. Never override a preset for a role with no measured data
        assignment = {
            role: (model if self._evidence_roles.get(role) else static_routing.get(role, model))
            for role, model in assignment.items()
        }

        # 5. Apply mode logic
        if self._mode == "shadow":
            return static_routing
        elif self._mode == "advisory":
            return self._merge_advisory(assignment, static_routing)
        else:
            return assignment

    async def select_routing_plan(
        self,
        roles: list[str],
        static_routing: dict[str, str],
        static_fallbacks: dict[str, str] | None = None,
        preset_id: str = "",
    ) -> RoutingPlan:
        """Select models *and* per-role fallbacks.

        ``select_routing_table`` only answers "which model runs this role" —
        which leaves the fallback table to be carried over from the preset. That
        is wrong whenever ACR moves a role: a fallback chosen for the preset's
        model may now be the same served model as the new primary choice, which
        makes it no fallback at all.

        Args:
            roles: Role names to assign.
            static_routing: The preset's role → model_id mapping.
            static_fallbacks: The preset's role → fallback model_id mapping.

        Returns:
            A ``RoutingPlan`` carrying routing, fallbacks and the selection log.
        """
        static_fallbacks = dict(static_fallbacks or {})
        routing = await self.select_routing_table(roles, static_routing, preset_id)
        fallbacks = self._select_fallbacks(roles, routing, static_fallbacks)
        return RoutingPlan(
            routing=routing,
            fallbacks=fallbacks,
            log=self.selection_log,
        )

    def _select_fallbacks(
        self,
        roles: list[str],
        routing: dict[str, str],
        static_fallbacks: dict[str, str],
    ) -> dict[str, str]:
        """Pick a per-role fallback that is a genuine alternative.

        A fallback only helps if it is a *different served model* — two aliases
        pointing at the same endpoint fail together. Where possible it should
        also come from a different bloc, matching the cross-lab fallback rule
        the presets already follow.

        The preset's own fallback is kept whenever it is still a real
        alternative, so hand-tuned choices survive.

        Candidate pool depends on evidence. With measured capabilities the whole
        ranked list is in play. Without it every candidate scores the same and
        the "winner" is whichever model sorts first alphabetically — so the pool
        narrows to models this preset already routes to. Backing synthesis with
        an arbitrary tie-winner is worse than backing it with a sibling the
        preset author picked.
        """
        fallbacks: dict[str, str] = {}
        trusted = {m for m in routing.values() if m} | {
            m for m in static_fallbacks.values() if m
        }

        for role in roles:
            assigned = routing.get(role, "")
            if not assigned or role in ACR_EXCLUDED_ROLES:
                if role in static_fallbacks:
                    fallbacks[role] = static_fallbacks[role]
                continue

            assigned_served = self._served(assigned)
            assigned_bloc = self._bloc(assigned)

            preset_choice = static_fallbacks.get(role)
            if preset_choice and self._served(preset_choice) != assigned_served:
                fallbacks[role] = preset_choice
                continue

            pool = self._ranked_per_role.get(role, [])
            if not self._evidence_roles.get(role):
                pool = [(mid, s) for mid, s in pool if mid in trusted]

            ranked = [
                mid for mid, _ in pool
                if mid and self._served(mid) != assigned_served
            ]
            if not ranked:
                continue

            cross_bloc = next(
                (mid for mid in ranked if self._bloc(mid) != assigned_bloc),
                None,
            )
            fallbacks[role] = cross_bloc or ranked[0]

        return fallbacks

    def _served(self, model_id: str) -> str:
        """Served model string for an alias, or the alias if unprofiled."""
        profile = self._profile(model_id)
        return profile.constraints.served_model if profile else model_id

    def _bloc(self, model_id: str) -> str:
        """Training bloc for an alias, or ``""`` if unprofiled."""
        profile = self._profile(model_id)
        return profile.constraints.bloc if profile else ""

    def _profile(self, model_id: str) -> ModelProfile | None:
        for by_id in self._profiles_per_role.values():
            if model_id in by_id:
                return by_id[model_id]
        if self._registry and hasattr(self._registry, "get_profile"):
            return self._registry.get_profile(model_id)
        return None

    def _get_candidates(self, req: TaskRequirement) -> list[ModelProfile]:
        """Get candidate models matching a task requirement's constraints."""
        if not hasattr(self._registry, "get_models_satisfying"):
            return []
        try:
            return self._registry.get_models_satisfying(req.constraints)
        except Exception:
            return []

    def _merge_advisory(
        self,
        acr_assignment: dict[str, str],
        static_routing: dict[str, str],
    ) -> dict[str, str]:
        """Merge ACR and static routing in advisory mode.

        Static routing wins unless ACR has measured capability data for the role
        *and* clears the confidence threshold. The evidence check matters: an
        unbenchmarked model scores exactly ``COLD_START_SCORE``, so a bare
        ``score >= threshold`` test would hand every role to whichever cold-start
        model sorts first alphabetically.
        """
        result = dict(static_routing)
        for role, acr_model in acr_assignment.items():
            if role not in static_routing:
                result[role] = acr_model
                continue
            if not self._evidence_roles.get(role):
                continue
            # Find the ACR score for this role
            score = 0.0
            for log in self._selection_log:
                if log.role == role:
                    score = log.acr_score
                    break
            if score > COLD_START_SCORE:
                result[role] = acr_model
        return result

    def _selection_reason(
        self,
        role: str,
        static_model: str,
        acr_model: str,
    ) -> str:
        """Generate a human-readable reason for the selection."""
        if static_model == acr_model:
            return "ACR agrees with preset routing"
        if static_model == "?":
            return f"ACR selected {acr_model} (no preset for this role)"
        return f"ACR prefers {acr_model} over preset {static_model}"


VALID_ACR_MODES: frozenset[str] = frozenset({"shadow", "advisory", "adaptive"})

_SHARED_REGISTRY: Any = None


def _shared_capability_registry() -> Any:
    """Process-wide capability registry.

    Bootstrapping profiles reads the catalogue snapshot and walks every registry
    alias, so it is shared rather than rebuilt per request. The registry itself
    is append-only during a run (``refresh()`` never mutates an existing
    profile), which keeps sharing safe across concurrent selections.
    """
    global _SHARED_REGISTRY
    if _SHARED_REGISTRY is None:
        from reasoner.infrastructure.llm.capability_registry import CapabilityRegistry

        _SHARED_REGISTRY = CapabilityRegistry()
    return _SHARED_REGISTRY


def build_adaptive_routing_service(
    preset_tier: str = "balanced",
) -> AdaptiveRoutingService:
    """Build a routing service honouring the configured ``ACR_MODE``.

    A fresh service per call: selection keeps per-call working state on the
    instance, so sharing one across concurrent runs would let them interleave.
    Only the expensive capability registry is shared.
    """
    from reasoner.core.settings import settings

    mode = str(getattr(settings, "ACR_MODE", "shadow") or "shadow").lower()
    if mode not in VALID_ACR_MODES:
        logger.warning("Unknown ACR_MODE %r — falling back to shadow", mode)
        mode = "shadow"

    return AdaptiveRoutingService(
        registry=_shared_capability_registry(),
        mode=mode,
        preset_tier=preset_tier,
    )


__all__ = [
    "ACRSelectionLog",
    "AdaptiveRoutingService",
    "RoutingPlan",
    "VALID_ACR_MODES",
    "build_adaptive_routing_service",
]
