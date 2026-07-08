"""Port: capability registry for model profiles (ACR Phase 2)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from reasoner.domain.model_capabilities import ModelCapabilities, ModelConstraints, ModelProfile
from reasoner.domain.task_requirements import TaskConstraints


@runtime_checkable
class CapabilityRegistryPort(Protocol):
    """Read/write model capability profiles.

    Implementations provide model profile storage backed by
    in-memory caches, JSON files, or databases.
    """

    def get_profile(self, model_id: str) -> ModelProfile | None:
        """Get the full profile for a model, or None if unknown."""
        ...

    def get_all_profiles(self) -> dict[str, ModelProfile]:
        """Get profiles for all known models keyed by model_id."""
        ...

    def update_capabilities(
        self,
        model_id: str,
        capabilities: ModelCapabilities,
    ) -> None:
        """Update the capability scores for a model.

        This is the primary write path — called by the online learning
        engine or benchmark engine when new measurements arrive.
        """
        ...

    def update_constraints(
        self,
        model_id: str,
        constraints: ModelConstraints,
    ) -> None:
        """Update the static constraints for a model."""
        ...

    def get_models_satisfying(
        self,
        constraints: TaskConstraints,
    ) -> list[ModelProfile]:
        """Return all models whose hard constraints satisfy the given task constraints.

        This is a filtering operation — models that fail any hard constraint
        (e.g. context window too small, cost too high) are excluded.
        """
        ...


__all__ = ["CapabilityRegistryPort"]
