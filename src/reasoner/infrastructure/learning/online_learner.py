"""Online learning loop — updates capability profiles from telemetry (ACR Phase 6).

Runs as a background task that processes new telemetry in batches,
updating the capability registry with fresh scores derived from
Thompson Sampling posteriors.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from reasoner.domain.telemetry import LLMCallTelemetry
from reasoner.domain.model_capabilities import ModelCapabilities
from reasoner.infrastructure.learning.thompson_sampler import ThompsonSampler
from reasoner.infrastructure.learning.quality_signals import (
    QualitySignalAggregator,
)
from reasoner.infrastructure.learning.exploration import ExplorationPolicy

logger = logging.getLogger(__name__)


class OnlineLearner:
    """Updates capability profiles from telemetry using Thompson Sampling.

    Processes telemetry events in batches and periodically exports
    updated capability scores to the registry.

    Designed to run as a background task:
    ::

        learner = OnlineLearner()
        asyncio.create_task(learner.run_loop(telemetry_store))
    """

    def __init__(
        self,
        sampler: ThompsonSampler | None = None,
        signal_aggregator: QualitySignalAggregator | None = None,
        exploration_policy: ExplorationPolicy | None = None,
        registry: Any = None,  # CapabilityRegistryPort
        batch_size: int = 50,
        export_interval_events: int = 200,
        export_interval_seconds: float = 60.0,
        min_samples_for_export: int = 5,
    ) -> None:
        """Initialise the online learner.

        Args:
            sampler: Thompson Sampler instance. Defaults to fresh instance.
            signal_aggregator: Quality signal aggregator. Defaults to fresh.
            exploration_policy: Exploration policy. Defaults to balanced tier.
            registry: Capability registry to export updated profiles to.
            batch_size: Number of events to process in one batch.
            export_interval_events: Export to registry every N events.
            export_interval_seconds: Also export after this many seconds.
            min_samples_for_export: Minimum observations before a model's
                capabilities are exported to the registry.
        """
        self.sampler = sampler or ThompsonSampler()
        self.signal_aggregator = signal_aggregator or QualitySignalAggregator()
        self.exploration_policy = exploration_policy or ExplorationPolicy()
        self.registry = registry
        self.batch_size = batch_size
        self.export_interval_events = export_interval_events
        self.export_interval_seconds = export_interval_seconds
        self.min_samples_for_export = min_samples_for_export

        self._event_count_since_export = 0
        self._last_export_time = 0.0
        self._running = False

    async def process_batch(self, events: list[LLMCallTelemetry]) -> int:
        """Process a batch of telemetry events and update posteriors.

        Args:
            events: List of telemetry events to process.

        Returns:
            Number of events successfully processed.
        """
        processed = 0
        for event in events:
            try:
                reward = self.signal_aggregator.compute_reward(event)
                self.sampler.update(event.model_id, event.role, reward)
                self._event_count_since_export += 1
                processed += 1
            except Exception as exc:
                logger.debug("Failed to process telemetry event: %s", exc)

        # Check if we should export updated profiles
        if self._should_export():
            await self.export_to_registry()

        return processed

    async def export_to_registry(self) -> int:
        """Export current sampling posteriors to the capability registry.

        Returns:
            Number of model profiles updated.
        """
        if not self.registry:
            logger.debug("No registry configured — skipping export")
            return 0

        try:
            exported = self.sampler.export_capabilities(
                min_samples=self.min_samples_for_export,
            )
            updates = 0
            for model_id, role_scores in exported.items():
                # Convert role-level means to capability dimensions
                # Use role names as dimension names for now
                caps = ModelCapabilities(
                    scores=role_scores,
                    source="online_learning",
                    measured_at=__import__("time").strftime(
                        "%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()
                    ),
                    sample_count=sum(
                        self.sampler.get_posterior(model_id, role).call_count
                        for role in role_scores
                    ),
                )
                self.registry.update_capabilities(model_id, caps)
                updates += 1

            self._event_count_since_export = 0
            self._last_export_time = __import__("time").time()
            logger.info("Online learner exported %d model profiles", updates)
            return updates
        except Exception as exc:
            logger.warning("Failed to export capabilities: %s", exc)
            return 0

    def _should_export(self) -> bool:
        """Check whether we should export to the registry."""
        if self._event_count_since_export >= self.export_interval_events:
            return True
        if self._last_export_time == 0.0:
            return False
        elapsed = __import__("time").time() - self._last_export_time
        return elapsed >= self.export_interval_seconds

    async def run_loop(
        self,
        event_source: Any = None,  # async iterator of LLMCallTelemetry
    ) -> None:
        """Run the continuous learning loop as a background task.

        Args:
            event_source: Async iterator yielding telemetry events.
                If None, polls ``get_pending_events()`` from the source.
        """
        self._running = True
        logger.info("Online learner loop started")

        try:
            while self._running:
                if event_source is not None:
                    batch: list[LLMCallTelemetry] = []
                    try:
                        async for event in event_source:
                            batch.append(event)
                            if len(batch) >= self.batch_size:
                                break
                    except StopAsyncIteration:
                        pass

                    if batch:
                        await self.process_batch(batch)
                else:
                    # No event source — sleep and re-check
                    await asyncio.sleep(5.0)

        except asyncio.CancelledError:
            logger.info("Online learner loop cancelled")
        finally:
            self._running = False

    def stop(self) -> None:
        """Signal the learning loop to stop."""
        self._running = False

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics for observability."""
        sampler_stats = self.sampler.get_stats()
        return {
            **sampler_stats,
            "event_count_since_export": self._event_count_since_export,
            "export_interval_events": self.export_interval_events,
            "min_samples_for_export": self.min_samples_for_export,
            "running": self._running,
        }


__all__ = ["OnlineLearner"]
