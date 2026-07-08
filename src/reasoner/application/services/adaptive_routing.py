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
from reasoner.application.services.role_requirements import get_requirement
from reasoner.application.services.utility_scorer import UtilityScorer
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
    ) -> dict[str, str]:
        """Select the optimal model for each role.

        Args:
            roles: List of role names to assign (e.g. ``["constructive", "scoring"]``).
            static_routing: The static preset's role → model_id mapping.
                Used as the fallback in all modes.

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

        for role in roles:
            req = get_requirement(role)
            candidates = self._get_candidates(req)

            if not candidates:
                # No candidates — fall back to static routing
                ranked_per_role[role] = [(static_routing.get(role, ""), 0.0)]
                continue

            scored = self._scorer.rank_models(candidates, req)
            ranked_per_role[role] = [(m.model_id, s) for m, s in scored]

        # 2. Resolve constraints (in adaptive mode)
        if self._mode == "adaptive":
            assignment = self._resolver.resolve(
                ranked_per_role,
                preset_id=self._mode,
                fallback=static_routing,
            )
        else:
            # For shadow/advisory, start with the static routing as baseline
            assignment = dict(static_routing)

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

        # 4. Apply mode logic
        if self._mode == "shadow":
            return static_routing
        elif self._mode == "advisory":
            return self._merge_advisory(assignment, static_routing)
        else:
            return assignment

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

        Static routing wins when the ACR choice has low confidence
        (score < 0.5) or no candidates were found.
        """
        result = dict(static_routing)
        for role, acr_model in acr_assignment.items():
            if role in static_routing:
                # Find the ACR score for this role
                score = 0.0
                for log in self._selection_log:
                    if log.role == role:
                        score = log.acr_score
                        break
                if score >= 0.5:
                    result[role] = acr_model
            else:
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


__all__ = ["AdaptiveRoutingService", "ACRSelectionLog"]
