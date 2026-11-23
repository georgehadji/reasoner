"""
Snapshot Strategy for Aggregate Performance

Periodic snapshots allow faster aggregate reconstruction
by avoiding replay of all historical events.
"""

from __future__ import annotations

import logging
from typing import Any

from reasoner.core.aggregates.pipeline import PipelineAggregate, PipelineStateData

logger = logging.getLogger(__name__)


class SnapshotStrategy:
    """Writes and reads aggregate snapshots, so a load can skip replaying the full history."""

    async def create_snapshot(
        self,
        aggregate: PipelineAggregate,
        event_store: Any,
    ) -> None:
        """Create and persist snapshot."""
        import time

        aggregate_id = aggregate.aggregate_id

        # Create snapshot data
        snapshot_data = {
            'state': self._serialize_state(aggregate.state_data),
            'version': aggregate.version,
            'timestamp': time.monotonic(),
        }

        # Persist snapshot
        if hasattr(event_store, 'save_snapshot'):
            await event_store.save_snapshot(
                aggregate_id=aggregate_id,
                version=aggregate.version,
                state=snapshot_data,
            )

        logger.debug(f"Snapshot created for {aggregate_id} at version {aggregate.version}")

    def _serialize_state(self, state: PipelineStateData) -> dict[str, Any]:
        """Serialize aggregate state for storage."""
        from dataclasses import asdict
        return asdict(state)

    async def load_snapshot(
        self,
        aggregate_id: str,
        event_store: Any,
    ) -> tuple[int, PipelineStateData] | None:
        """Load snapshot from storage."""
        if not hasattr(event_store, 'get_snapshot'):
            return None

        result = await event_store.get_snapshot(aggregate_id)

        if result is None:
            return None

        version, snapshot_data = result

        # create_snapshot() persists a WRAPPER: {'state': ..., 'version': ...,
        # 'timestamp': ...}. _deserialize_state splats its argument straight
        # into PipelineStateData, which has none of those three field names --
        # so passing the wrapper raised TypeError on every snapshot that this
        # class itself wrote. Unwrap here; the fallback keeps a flat state
        # written directly through EventStore.save_snapshot working too.
        state = self._deserialize_state(snapshot_data.get("state", snapshot_data))

        return version, state

    def _deserialize_state(self, data: dict[str, Any]) -> PipelineStateData:
        """Deserialize state from snapshot."""
        return PipelineStateData(**data)


class SnapshotManager:
    """
    High-level snapshot management.
    
    Coordinates between aggregates, event store, and snapshot strategy.
    """

    def __init__(self, event_store: Any):
        self.event_store = event_store
        self.strategy = SnapshotStrategy()


    async def load_aggregate_with_snapshot(
        self,
        aggregate_id: str,
    ) -> PipelineAggregate | None:
        """Load aggregate using snapshot + events."""
        # Try to load snapshot
        snapshot_result = await self.strategy.load_snapshot(
            aggregate_id, self.event_store
        )

        if snapshot_result:
            version, state = snapshot_result

            # Load events since snapshot. get_events' from_version is
            # EXCLUSIVE (`WHERE version > ?`), so `version` already excludes
            # the snapshotted version; passing `version + 1` skipped the first
            # event after the snapshot, which the gap guard below then reported
            # as store corruption on every otherwise-healthy load.
            events = await self.event_store.get_events(
                aggregate_id, from_version=version
            )

            # Guard against event gaps left by incorrect compaction.
            # Versions must be a contiguous sequence from snapshot_version+1.
            actual_versions = [e.version for e in events]
            expected_versions = list(range(version + 1, version + 1 + len(events)))
            if actual_versions != expected_versions:
                from reasoner.core.exceptions import EventStoreCorruptionError
                raise EventStoreCorruptionError(
                    f"Event gap detected for aggregate {aggregate_id}: "
                    f"expected versions {expected_versions}, got {actual_versions}"
                )

            # Rebuild aggregate. An empty `events` is the normal terminal case
            # (snapshot taken on PipelineCompleted, nothing after it) -- it
            # means "the snapshot IS the state", not "no such aggregate".
            # Returning None here reported completed runs as missing.
            aggregate = PipelineAggregate(aggregate_id=aggregate_id)

            # Apply snapshot state
            aggregate._state_data = state
            aggregate.version = version

            # Apply events since snapshot
            for event in events:
                aggregate.apply(event)

            return aggregate

        # No snapshot - load from full history
        events = await self.event_store.get_events(aggregate_id)

        if not events:
            return None

        aggregate = PipelineAggregate(aggregate_id=aggregate_id)
        aggregate.load_from_history(events)

        return aggregate


# ─────────────────────────────────────────────────────────────────────
# CQRS READ MODELS
# ─────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────
# EVENT HANDLERS FOR PROJECTIONS
# ─────────────────────────────────────────────────────────────────────

