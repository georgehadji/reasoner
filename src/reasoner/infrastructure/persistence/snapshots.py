"""
Snapshot Strategy for Aggregate Performance

Periodic snapshots allow faster aggregate reconstruction
by avoiding replay of all historical events.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from reasoner.core.aggregates.pipeline import PipelineAggregate, PipelineStateData
from reasoner.core.constants import DEFAULT_SNAPSHOT_INTERVAL, SNAPSHOT_LIST_LIMIT
from reasoner.core.events.domain_events import DomainEvent, EventType

logger = logging.getLogger(__name__)


class SnapshotStrategy:
    """
    Manages aggregate snapshots for performance optimization.
    
    Strategies:
    - Version-based: Snapshot every N events
    - Time-based: Snapshot every N seconds
    - Phase-based: Snapshot after each phase
    - Size-based: Snapshot when events exceed threshold
    """

    def __init__(
        self,
        version_interval: int = 10,
        time_interval_seconds: float = DEFAULT_SNAPSHOT_INTERVAL,
        phase_based: bool = True,
        event_threshold: int = 100,
    ):
        self.version_interval = version_interval
        self.time_interval_seconds = time_interval_seconds
        self.phase_based = phase_based
        self.event_threshold = event_threshold

        # Last snapshot tracking
        self._last_snapshot_version: dict[str, int] = {}
        self._last_snapshot_time: dict[str, float] = {}

        # Background task
        self._time_task: asyncio.Task | None = None

    def should_snapshot(
        self,
        aggregate: PipelineAggregate,
        event: DomainEvent,
    ) -> bool:
        """Determine if snapshot should be created."""
        aggregate_id = aggregate.aggregate_id

        # Version-based
        if self.version_interval > 0:
            last_version = self._last_snapshot_version.get(aggregate_id, 0)
            if aggregate.version - last_version >= self.version_interval:
                return True

        # Time-based
        if self.time_interval_seconds > 0:
            import time
            last_time = self._last_snapshot_time.get(aggregate_id, 0)
            if time.monotonic() - last_time >= self.time_interval_seconds:
                return True

        # Phase-based
        if self.phase_based:
            from reasoner.core.events.domain_events import PhaseCompleted, PipelineCompleted
            if isinstance(event, (PhaseCompleted, PipelineCompleted)):
                return True

        return False

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

        # Update tracking
        self._last_snapshot_version[aggregate_id] = aggregate.version
        self._last_snapshot_time[aggregate_id] = time.monotonic()

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

    async def start_time_based_snapshots(
        self,
        aggregates: dict[str, PipelineAggregate],
        event_store: Any,
    ) -> None:
        """Start background task for time-based snapshots."""
        async def snapshot_loop():
            while True:
                await asyncio.sleep(self.time_interval_seconds)

                for _aggregate_id, aggregate in list(aggregates.items()):
                    if aggregate.is_running:
                        await self.create_snapshot(aggregate, event_store)

        self._time_task = asyncio.create_task(snapshot_loop())

    async def stop_time_based_snapshots(self) -> None:
        """Stop background snapshot task."""
        if self._time_task:
            self._time_task.cancel()
            try:
                await self._time_task
            except asyncio.CancelledError:
                pass


class SnapshotManager:
    """
    High-level snapshot management.
    
    Coordinates between aggregates, event store, and snapshot strategy.
    """

    def __init__(self, event_store: Any):
        self.event_store = event_store
        self.strategy = SnapshotStrategy()
        self._active_aggregates: dict[str, PipelineAggregate] = {}

    def register_aggregate(self, aggregate: PipelineAggregate) -> None:
        """Register aggregate for snapshot management."""
        self._active_aggregates[aggregate.aggregate_id] = aggregate

    def unregister_aggregate(self, aggregate_id: str) -> None:
        """Unregister aggregate."""
        if aggregate_id in self._active_aggregates:
            del self._active_aggregates[aggregate_id]

    async def on_event(
        self,
        aggregate: PipelineAggregate,
        event: DomainEvent,
    ) -> None:
        """Handle event - check if snapshot needed."""
        if self.strategy.should_snapshot(aggregate, event):
            await self.strategy.create_snapshot(aggregate, self.event_store)

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

class ReadModelProjection:
    """
    CQRS Read Model Projections.
    
    Creates denormalized views optimized for specific queries.
    """

    def __init__(self, event_store: Any):
        self.event_store = event_store

    async def project_pipeline_list(self) -> None:
        """Project pipeline list read model."""
        from reasoner.infrastructure.persistence.postgres_store import PostgreSQLEventStore

        if not isinstance(self.event_store, PostgreSQLEventStore):
            return  # Only for PostgreSQL

        # Get all pipelines
        pipelines = await self.event_store.list_pipelines(limit=SNAPSHOT_LIST_LIMIT)

        # Create denormalized view
        read_model_data = {
            'pipelines': [
                {
                    'id': p['aggregate_id'],
                    'problem': p['problem'][:100] if p['problem'] else '',
                    'status': p['status'],
                    'method': p['method'],
                    'preset': p['preset'],
                    'created_at': p['created_at'],
                }
                for p in pipelines
            ],
            'total': len(pipelines),
        }

        await self.event_store.save_read_model(
            model_name='pipeline_list',
            model_key='all',
            data=read_model_data,
        )

    async def project_pipeline_stats(self) -> None:
        """Project pipeline statistics read model."""
        stats = await self.event_store.get_stats()

        await self.event_store.save_read_model(
            model_name='pipeline_stats',
            model_key='summary',
            data=stats,
        )

    async def get_pipeline_list(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get cached pipeline list."""
        if hasattr(self.event_store, 'get_read_model'):
            data = await self.event_store.get_read_model(
                model_name='pipeline_list',
                model_key='all',
            )
            if data:
                # Apply pagination
                pipelines = data.get('pipelines', [])
                return {
                    'pipelines': pipelines[offset:offset + limit],
                    'total': data.get('total', len(pipelines)),
                }

        # Fallback to direct query
        return await self.event_store.list_pipelines(limit, offset)

    async def get_pipeline_stats(self) -> dict[str, Any]:
        """Get cached statistics."""
        if hasattr(self.event_store, 'get_read_model'):
            data = await self.event_store.get_read_model(
                model_name='pipeline_stats',
                model_key='summary',
            )
            if data:
                return data

        # Fallback
        return await self.event_store.get_stats()


# ─────────────────────────────────────────────────────────────────────
# EVENT HANDLERS FOR PROJECTIONS
# ─────────────────────────────────────────────────────────────────────

async def setup_read_model_projections(event_store: Any) -> ReadModelProjection:
    """Setup read model projections with event bus integration."""
    from reasoner.application.event_bus import handle_event

    projection = ReadModelProjection(event_store)

    @handle_event(EventType.PIPELINE_COMPLETED)
    async def update_on_completion(event):
        """Update read models on pipeline completion."""
        await projection.project_pipeline_list()
        await projection.project_pipeline_stats()

    @handle_event(EventType.PIPELINE_FAILED)
    async def update_on_failure(event):
        """Update read models on pipeline failure."""
        await projection.project_pipeline_list()
        await projection.project_pipeline_stats()

    return projection
