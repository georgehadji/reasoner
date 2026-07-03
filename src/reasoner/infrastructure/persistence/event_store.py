"""
Event Persistence Layer

Stores domain events in SQLite for durability and replay.
Supports aggregate reconstruction and temporal queries.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional, Callable
from datetime import datetime
from dataclasses import asdict

from reasoner.core.events.domain_events import DomainEvent, PipelineEventType, WidgetEventType, MemoryEventType, SaaSEventType, ALL_EVENT_TYPES
from reasoner.infrastructure.persistence.event_store_connection import EventStoreConnection

logger = logging.getLogger(__name__)


class EventStore:
    """
    SQLite-based event store for persistence.

    Features:
    - Append-only event log
    - Aggregate reconstruction from events
    - Temporal queries (get events by time range)
    - Pipeline listing and filtering
    - Connection lifecycle and compaction delegated to sub-modules
    """

    def __init__(self, db_path: str | Path | None = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent / "events.db"

        self.db_path = Path(db_path)
        # Delegate connection lifecycle to dedicated module
        self.conn = EventStoreConnection(self.db_path)

        # Initialize database
        self.conn.init_db()

    # ── Connection method delegation (backward-compat) ──

    def _get_connection(self) -> sqlite3.Connection:
        return self.conn._get_connection()

    async def _run_in_executor(self, func: Callable, *args: Any) -> Any:
        return await self.conn.run_in_executor(func, *args)
    
    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()
        
        conn.executescript("""
            -- Events table (append-only log)
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                event_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                aggregate_type TEXT NOT NULL DEFAULT 'pipeline',
                version INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
                -- UNIQUE(aggregate_id, version) removed: version always 1, see GH-###
            );
            
            -- Indexes for common queries
            CREATE INDEX IF NOT EXISTS idx_events_aggregate 
                ON events(aggregate_id, version);
            CREATE INDEX IF NOT EXISTS idx_events_type 
                ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_timestamp 
                ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_created 
                ON events(created_at);
            
            -- Aggregates table (current state snapshot)
            CREATE TABLE IF NOT EXISTS aggregates (
                aggregate_id TEXT PRIMARY KEY,
                aggregate_type TEXT NOT NULL,
                current_version INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                problem TEXT,
                preset TEXT,
                method TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            
            -- Index for listing aggregates
            CREATE INDEX IF NOT EXISTS idx_aggregates_status 
                ON aggregates(status);
            CREATE INDEX IF NOT EXISTS idx_aggregates_created 
                ON aggregates(created_at);
            
            -- Snapshots table (for faster aggregate reconstruction)
            CREATE TABLE IF NOT EXISTS snapshots (
                aggregate_id TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            -- Dead-letter queue for un-persistable events (DM8)
            CREATE TABLE IF NOT EXISTS dead_letter_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                event_type TEXT NOT NULL,
                raw_payload TEXT NOT NULL,
                error TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        
        conn.commit()
    
    async def save_events(self, events: list[DomainEvent]) -> None:
        """
        Save events to the event store.

        Events are persisted atomically within a transaction.

        Raises:
            sqlite3.Error: If database operation fails
            json.JSONDecodeError: If event payload cannot be serialized
            OSError: If database file is inaccessible
        """
        def _save_events_sync():
            try:
                conn = self._get_connection()

                for event in events:
                    # Serialize event payload
                    payload = json.dumps({
                        k: v for k, v in asdict(event).items()
                        if k not in ('event_id', 'event_type', 'aggregate_id',
                                     'version', 'timestamp')
                    }, default=str)

                    # Determine aggregate type
                    aggregate_type = self._get_aggregate_type(event.event_type)

                    # Insert event
                    conn.execute("""
                        INSERT INTO events
                        (event_id, event_type, aggregate_id, aggregate_type,
                         version, timestamp, payload, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                        ON CONFLICT(event_id) DO NOTHING
                    """, (
                        event.event_id,
                        event.event_type.value,
                        event.aggregate_id,
                        aggregate_type,
                        event.version,
                        event.timestamp,
                        payload,
                    ))

                    # Update aggregate snapshot
                    self._update_aggregate(conn, event, aggregate_type)

                conn.commit()
            except sqlite3.Error as e:
                conn.rollback()
                logger.error(f"Database error saving events: {e}")
                raise
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                conn.rollback()
                logger.error(f"Failed to serialize event payload — writing to DLQ: {e}")
                # Write raw event data to dead-letter queue (DM8)
                for event in events:
                    try:
                        conn.execute("""
                            INSERT INTO dead_letter_queue
                            (event_id, event_type, raw_payload, error)
                            VALUES (?, ?, ?, ?)
                        """, (
                            event.event_id,
                            str(event.event_type.value) if hasattr(event.event_type, 'value') else str(event.event_type),
                            str({k: v for k, v in vars(event).items()}),
                            str(e),
                        ))
                    except Exception:
                        pass  # DLQ write failure is non-fatal
                conn.commit()
                raise
            except Exception as e:
                conn.rollback()
                logger.error(f"Unexpected error saving events — writing to DLQ: {e}")
                try:
                    for event in events:
                        conn.execute("""
                            INSERT INTO dead_letter_queue
                            (event_id, event_type, raw_payload, error)
                            VALUES (?, ?, ?, ?)
                        """, (
                            event.event_id,
                            str(event.event_type.value) if hasattr(event.event_type, 'value') else str(event.event_type),
                            str(event)[:2000],
                            str(e)[:500],
                        ))
                except Exception:
                    pass
                conn.commit()
                raise

        await self._run_in_executor(_save_events_sync)
    
    def _get_aggregate_type(self, event_type: PipelineEventType | WidgetEventType | MemoryEventType | SaaSEventType) -> str:
        """Determine aggregate type from event type."""
        if event_type in (
            PipelineEventType.PIPELINE_STARTED,
            PipelineEventType.PHASE_STARTED,
            PipelineEventType.PHASE_COMPLETED,
            PipelineEventType.PHASE_FAILED,
            PipelineEventType.PIPELINE_COMPLETED,
            PipelineEventType.PIPELINE_FAILED,
        ):
            return "pipeline"
        elif event_type in (
            WidgetEventType.WIDGET_DETECTED,
            WidgetEventType.WIDGET_EXECUTED,
            WidgetEventType.WIDGET_FAILED,
        ):
            return "widget"
        elif event_type in (
            MemoryEventType.MEMORY_STORED,
            MemoryEventType.MEMORY_RECALLED,
        ):
            return "memory"
        elif event_type in (
            SaaSEventType.USER_REGISTERED,
            SaaSEventType.USER_LOGGED_IN,
        ):
            return "saas"
        else:
            return "generic"
    
    def _update_aggregate(
        self,
        conn: sqlite3.Connection,
        event: DomainEvent,
        aggregate_type: str,
    ) -> None:
        """Update aggregate state snapshot."""
        from reasoner.core.events.domain_events import (
            PipelineStarted,
            PipelineCompleted,
            PipelineFailed,
        )
        
        # Extract relevant fields based on event type
        problem = None
        preset = None
        method = None
        status = None
        
        if isinstance(event, PipelineStarted):
            problem = event.problem
            preset = event.preset
            method = event.method
            status = "running"
        elif isinstance(event, PipelineCompleted):
            status = "completed"
        elif isinstance(event, PipelineFailed):
            status = "failed"
        
        # Build update query
        updates = []
        values = []
        
        updates.append("current_version = ?")
        values.append(event.version)
        
        updates.append("updated_at = datetime('now')")
        
        if aggregate_type == "pipeline":
            if problem:
                updates.append("problem = ?")
                values.append(problem)
            if preset:
                updates.append("preset = ?")
                values.append(preset)
            if method:
                updates.append("method = ?")
                values.append(method)
            if status:
                updates.append("status = ?")
                values.append(status)
        
        conn.execute(f"""
            INSERT INTO aggregates 
            (aggregate_id, aggregate_type, current_version, status, 
             problem, preset, method, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(aggregate_id) DO UPDATE SET
            {', '.join(updates)}
        """, (
            event.aggregate_id,
            aggregate_type,
            event.version,
            status or "running",
            problem,
            preset,
            method,
            *values,
        ))
    
    async def get_events(
        self,
        aggregate_id: str,
        from_version: int = 0,
    ) -> list[DomainEvent]:
        """
        Get events for an aggregate.

        Optionally filter by minimum version for incremental loading.
        
        Args:
            aggregate_id: ID of the aggregate
            from_version: Minimum version to retrieve
            
        Returns:
            List of DomainEvent objects
            
        Raises:
            sqlite3.Error: If database operation fails
            ValueError: If aggregate_id is invalid
        """
        def _get_events_sync() -> list[DomainEvent]:
            try:
                conn = self._get_connection()
                cursor = conn.execute("""
                    SELECT * FROM events
                    WHERE aggregate_id = ? AND version > ?
                    ORDER BY version ASC
                """, (aggregate_id, from_version))
                events = []
                for row in cursor.fetchall():
                    event = self._deserialize_event(row)
                    if event:
                        events.append(event)
                return events
            except sqlite3.Error as e:
                logger.error(f"Database error retrieving events for {aggregate_id}: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error retrieving events for {aggregate_id}: {e}")
                raise

        return await self._run_in_executor(_get_events_sync)
    
    def _deserialize_event(self, row: sqlite3.Row) -> DomainEvent | None:
        """Deserialize database row to domain event."""
        from reasoner.core.events.domain_events import make_event
        
        try:
            payload = json.loads(row["payload"])
            
            event_type_str = row["event_type"]
            event_type = ALL_EVENT_TYPES.get(event_type_str)
            if event_type is None:
                logger.warning(
                    "Unknown event type '%s' (aggregate %s v%s) — skipping",
                    event_type_str, row["aggregate_id"], row["version"],
                )
                return None
            event = make_event(
                event_type,
                aggregate_id=row["aggregate_id"],
                version=row["version"],
                **payload,
            )
            
            # Override fields from row
            object.__setattr__(event, 'event_id', row["event_id"])
            object.__setattr__(event, 'timestamp', row["timestamp"])
            
            return event
            
        except Exception as e:
            logger.warning(
                "Failed to deserialize event (aggregate %s v%s): %s",
                row["aggregate_id"] if row else "?",
                row["version"] if row else "?",
                e,
            )
            return None

    async def list_pipelines(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List pipelines with optional filtering.
        
        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            status: Filter by status
            
        Returns:
            List of pipeline dictionaries
            
        Raises:
            sqlite3.Error: If database operation fails
        """
        def _list_pipelines_sync() -> list[dict[str, Any]]:
            try:
                conn = self._get_connection()
                query = "SELECT * FROM aggregates WHERE aggregate_type = 'pipeline'"
                params: list = []
                if status:
                    query += " AND status = ?"
                    params.append(status)
                query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])
                cursor = conn.execute(query, params)
                return [
                    {
                        "aggregate_id": row["aggregate_id"],
                        "status": row["status"],
                        "problem": row["problem"],
                        "preset": row["preset"],
                        "method": row["method"],
                        "version": row["current_version"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                    }
                    for row in cursor.fetchall()
                ]
            except sqlite3.Error as e:
                logger.error(f"Database error listing pipelines: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error listing pipelines: {e}")
                raise

        return await self._run_in_executor(_list_pipelines_sync)
    
    async def get_aggregate_state(
        self,
        aggregate_id: str,
    ) -> dict[str, Any] | None:
        """
        Get current aggregate state from snapshot.
        
        Args:
            aggregate_id: ID of the aggregate
            
        Returns:
            Dictionary with aggregate state or None if not found
            
        Raises:
            sqlite3.Error: If database operation fails
        """
        def _get_aggregate_state_sync() -> dict[str, Any] | None:
            try:
                conn = self._get_connection()
                cursor = conn.execute(
                    "SELECT * FROM aggregates WHERE aggregate_id = ?",
                    (aggregate_id,),
                )
                row = cursor.fetchone()
                if row:
                    return {
                        "aggregate_id": row["aggregate_id"],
                        "type": row["aggregate_type"],
                        "version": row["current_version"],
                        "status": row["status"],
                        "problem": row["problem"],
                        "preset": row["preset"],
                        "method": row["method"],
                    }
                return None
            except sqlite3.Error as e:
                logger.error(f"Database error retrieving aggregate state for {aggregate_id}: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error retrieving aggregate state for {aggregate_id}: {e}")
                raise

        return await self._run_in_executor(_get_aggregate_state_sync)
    
    async def save_snapshot(
        self,
        aggregate_id: str,
        version: int,
        state: dict[str, Any],
    ) -> None:
        """
        Save aggregate state snapshot for faster reconstruction.

        Args:
            aggregate_id: ID of the aggregate
            version: Version number
            state: State dictionary to save

        Raises:
            sqlite3.Error: If database operation fails
            json.JSONDecodeError: If state cannot be serialized
        """
        def _save_snapshot_sync():
            try:
                conn = self._get_connection()

                conn.execute("""
                    INSERT OR REPLACE INTO snapshots
                    (aggregate_id, version, state, created_at)
                    VALUES (?, ?, ?, datetime('now'))
                """, (
                    aggregate_id,
                    version,
                    json.dumps(state),
                ))

                conn.commit()
            except sqlite3.Error as e:
                conn.rollback()
                logger.error(f"Database error saving snapshot for {aggregate_id}: {e}")
                raise
            except (TypeError, ValueError) as e:
                conn.rollback()
                logger.error(f"Failed to serialize state for {aggregate_id}: {e}")
                raise
            except Exception as e:
                conn.rollback()
                logger.error(f"Unexpected error saving snapshot for {aggregate_id}: {e}")
                raise

        await self._run_in_executor(_save_snapshot_sync)
    
    async def get_snapshot(
        self,
        aggregate_id: str,
    ) -> tuple[int, dict[str, Any]] | None:
        """
        Get latest snapshot for aggregate.
        
        Args:
            aggregate_id: ID of the aggregate
            
        Returns:
            Tuple of (version, state) or None if not found
            
        Raises:
            sqlite3.Error: If database operation fails
            json.JSONDecodeError: If snapshot data is corrupted
        """
        def _get_snapshot_sync() -> tuple[int, dict[str, Any]] | None:
            try:
                conn = self._get_connection()
                cursor = conn.execute(
                    "SELECT version, state FROM snapshots WHERE aggregate_id = ?",
                    (aggregate_id,),
                )
                row = cursor.fetchone()
                if row:
                    try:
                        return row["version"], json.loads(row["state"])
                    except json.JSONDecodeError as e:
                        logger.error(f"Corrupted snapshot data for {aggregate_id}: {e}")
                        raise
                return None
            except sqlite3.Error as e:
                logger.error(f"Database error retrieving snapshot for {aggregate_id}: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error retrieving snapshot for {aggregate_id}: {e}")
                raise

        return await self._run_in_executor(_get_snapshot_sync)
    
    async def get_events_since(
        self,
        aggregate_id: str,
        since_version: int,
    ) -> list[DomainEvent]:
        """Get events since a specific version (for sync/resume)."""
        return await self.get_events(aggregate_id, since_version)
    
    async def count_events(self, aggregate_id: str) -> int:
        """
        Count total events for an aggregate.
        
        Args:
            aggregate_id: ID of the aggregate
            
        Returns:
            Total event count
            
        Raises:
            sqlite3.Error: If database operation fails
        """
        def _count_events_sync() -> int:
            try:
                conn = self._get_connection()
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE aggregate_id = ?",
                    (aggregate_id,),
                )
                return cursor.fetchone()[0]
            except sqlite3.Error as e:
                logger.error(f"Database error counting events for {aggregate_id}: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error counting events for {aggregate_id}: {e}")
                raise

        return await self._run_in_executor(_count_events_sync)

    async def list_aggregate_ids_for_user(self, user_id: str) -> list[str]:
        """Return all aggregate IDs for a given user (GDPR erasure support).

        Scans pipeline_owners.json for user -> pipeline_id mapping.
        Returns an empty list on any error.
        """
        try:
            from reasoner.domain.pipeline_owner import _PIPELINE_OWNERS_PATH
            if not _PIPELINE_OWNERS_PATH.exists():
                return []
            import json
            mapping = json.loads(_PIPELINE_OWNERS_PATH.read_text(encoding="utf-8"))
            return [pid for pid, uid in mapping.items() if uid == user_id]
        except Exception as exc:
            logger.warning("Failed to list aggregates for user %s: %s", user_id, exc)
            return []

    async def delete_aggregate(self, aggregate_id: str) -> None:
        """
        Delete aggregate and all its events (for GDPR compliance).

        Args:
            aggregate_id: ID of the aggregate to delete

        Raises:
            sqlite3.Error: If database operation fails
        """
        def _delete_aggregate_sync():
            try:
                conn = self._get_connection()

                conn.execute("""
                    DELETE FROM events WHERE aggregate_id = ?
                """, (aggregate_id,))

                conn.execute("""
                    DELETE FROM aggregates WHERE aggregate_id = ?
                """, (aggregate_id,))

                conn.execute("""
                    DELETE FROM snapshots WHERE aggregate_id = ?
                """, (aggregate_id,))

                conn.commit()
                logger.info(f"Aggregate {aggregate_id} and all related data deleted")
            except sqlite3.Error as e:
                conn.rollback()
                logger.error(f"Database error deleting aggregate {aggregate_id}: {e}")
                raise
            except Exception as e:
                conn.rollback()
                logger.error(f"Unexpected error deleting aggregate {aggregate_id}: {e}")
                raise

        await self._run_in_executor(_delete_aggregate_sync)
    
    async def get_stats(self) -> dict[str, Any]:
        """
        Get event store statistics.
        
        Returns:
            Dictionary with statistics
            
        Raises:
            sqlite3.Error: If database operation fails
        """
        def _get_stats_sync() -> dict[str, Any]:
            try:
                conn = self._get_connection()
                stats: dict[str, Any] = {}
                cursor = conn.execute("SELECT COUNT(*) FROM events")
                stats["total_events"] = cursor.fetchone()[0]
                cursor = conn.execute("SELECT COUNT(*) FROM aggregates")
                stats["total_aggregates"] = cursor.fetchone()[0]
                cursor = conn.execute(
                    "SELECT status, COUNT(*) FROM aggregates GROUP BY status"
                )
                stats["by_status"] = {row["status"]: row[1] for row in cursor.fetchall()}
                cursor = conn.execute(
                    "SELECT aggregate_type, COUNT(*) FROM aggregates GROUP BY aggregate_type"
                )
                stats["by_type"] = {
                    row["aggregate_type"]: row[1] for row in cursor.fetchall()
                }
                return stats
            except sqlite3.Error as e:
                logger.error(f"Database error retrieving stats: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error retrieving stats: {e}")
                raise

        return await self._run_in_executor(_get_stats_sync)
    
    async def prune_events_before(
        self,
        cutoff: datetime,
        batch_size: int = 500,
    ) -> int:
        """Delete events older than cutoff that are covered by a snapshot.

        Only deletes events where a snapshot at version >= the event's version
        exists for the same aggregate. Never creates version gaps that would
        trigger EventStoreCorruptionError on replay.

        Returns:
            Number of event rows deleted.
        """
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

        def _prune_sync() -> int:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    """
                    DELETE FROM events
                    WHERE id IN (
                        SELECT e.id
                        FROM events e
                        INNER JOIN snapshots s ON s.aggregate_id = e.aggregate_id
                        WHERE e.version <= s.version
                          AND e.created_at < ?
                        ORDER BY e.created_at ASC
                        LIMIT ?
                    )
                    """,
                    (cutoff_str, batch_size),
                )
                deleted = cursor.rowcount

                # Clean up terminal aggregates with no remaining events
                conn.execute(
                    """
                    DELETE FROM aggregates
                    WHERE status IN ('completed', 'failed')
                      AND updated_at < ?
                      AND NOT EXISTS (
                          SELECT 1 FROM events
                          WHERE events.aggregate_id = aggregates.aggregate_id
                      )
                    """,
                    (cutoff_str,),
                )

                conn.commit()
                return deleted
            except sqlite3.Error as e:
                conn.rollback()
                logger.error("prune_events_before failed: %s", e)
                raise

        return await self._run_in_executor(_prune_sync)

    async def count_eligible_events(self, cutoff: datetime) -> int:
        """Count events eligible for pruning (dry-run support)."""
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

        def _count_sync() -> int:
            conn = self._get_connection()
            cursor = conn.execute(
                """
                SELECT COUNT(*)
                FROM events e
                INNER JOIN snapshots s ON s.aggregate_id = e.aggregate_id
                WHERE e.version <= s.version
                  AND e.created_at < ?
                """,
                (cutoff_str,),
            )
            return cursor.fetchone()[0]

        return await self._run_in_executor(_count_sync)

    def close(self) -> None:
        """Close database connection and thread pool."""
        if self._connection:
            self._connection.close()
            self._connection = None
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None


# ─────────────────────────────────────────────────────────────────────
# GLOBAL EVENT STORE
# ─────────────────────────────────────────────────────────────────────

_event_store: EventStore | None = None


def get_event_store(db_path: str | Path | None = None) -> Any:
    """Get or create global event store."""
    global _event_store
    if _event_store is None:
        from reasoner.core.settings import settings
        if settings.EVENT_STORE_BACKEND == "postgres" and settings.DATABASE_URL:
            from reasoner.infrastructure.persistence.postgres_store import PostgreSQLEventStore
            _event_store = PostgreSQLEventStore(settings.DATABASE_URL)
        else:
            _event_store = EventStore(db_path)
    return _event_store


def reset_event_store() -> None:
    """Reset global event store (for testing)."""
    global _event_store
    if _event_store:
        _event_store.close()
    _event_store = None
