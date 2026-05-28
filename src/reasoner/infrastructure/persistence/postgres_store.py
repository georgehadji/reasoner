"""
PostgreSQL Event Store

Production-grade event persistence using PostgreSQL.
Supports:
- High availability
- Read replicas
- Connection pooling
- Advanced querying
"""

from __future__ import annotations

import json
import asyncio
import logging
from pathlib import Path
from typing import Any, Optional
from dataclasses import asdict

try:
    import asyncpg
    _AsyncpgError: type[Exception] = asyncpg.PostgresError
except ImportError:
    asyncpg = None  # type: ignore[assignment]
    _AsyncpgError = Exception  # fallback so except clauses compile

from reasoner.core.events.domain_events import DomainEvent, EventType
from reasoner.core.constants import DEFAULT_DB_COMMAND_TIMEOUT
from reasoner.security.encryption import get_encryption_service

logger = logging.getLogger(__name__)


class PostgreSQLEventStore:
    """
    PostgreSQL-based event store for production.
    
    Features:
    - Connection pooling (asyncpg)
    - Read replica support
    - Advanced indexing (Limited for encrypted fields)
    - Full-text search (Limited for encrypted fields)
    - Partitioning for large datasets
    """
    
    def __init__(
        self,
        connection_string: str | None = None,
        pool_size: int = 10,
        use_read_replica: bool = False,
        read_replica_url: str | None = None,
    ):
        self.connection_string = connection_string
        self.pool_size = pool_size
        self.use_read_replica = use_read_replica
        self.read_replica_url = read_replica_url
        
        self._pool = None
        self._read_pool = None
        self._encryption = get_encryption_service()
    
    async def initialize(self) -> None:
        """Initialize connection pools."""
        import asyncpg
        
        # Primary pool (read-write)
        self._pool = await asyncpg.create_pool(
            dsn=self.connection_string,
            min_size=2,
            max_size=self.pool_size,
            command_timeout=DEFAULT_DB_COMMAND_TIMEOUT,
        )
        
        # Read replica pool (optional)
        if self.use_read_replica and self.read_replica_url:
            try:
                self._read_pool = await asyncpg.create_pool(
                    dsn=self.read_replica_url,
                    min_size=2,
                    max_size=self.pool_size,
                    command_timeout=DEFAULT_DB_COMMAND_TIMEOUT,
                )
            except Exception as exc:
                # If read-replica setup fails, close the primary pool to avoid
                # leaking connections, then re-raise so callers can retry.
                try:
                    await self._pool.close()
                except Exception:
                    pass  # Best-effort cleanup; preserve original exception
                self._pool = None
                raise exc
        
        # Initialize schema
        await self._init_schema()
    
    async def _init_schema(self) -> None:
        """Initialize database schema."""
        async with self._pool.acquire() as conn:
            await conn.execute("""
                -- Enable UUID extension
                CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
                
                -- Events table (partitioned by aggregate_type)
                CREATE TABLE IF NOT EXISTS events (
                    id BIGSERIAL,
                    event_id UUID UNIQUE NOT NULL,
                    event_type VARCHAR(100) NOT NULL,
                    aggregate_id VARCHAR(255) NOT NULL,
                    aggregate_type VARCHAR(50) NOT NULL DEFAULT 'pipeline',
                    version INTEGER NOT NULL,
                    timestamp DOUBLE PRECISION NOT NULL,
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (id, aggregate_type)
                ) PARTITION BY LIST (aggregate_type);
                
                -- Partitions by aggregate type
                CREATE TABLE IF NOT EXISTS events_pipeline 
                    PARTITION OF events FOR VALUES IN ('pipeline');
                CREATE TABLE IF NOT EXISTS events_widget 
                    PARTITION OF events FOR VALUES IN ('widget');
                CREATE TABLE IF NOT EXISTS events_memory 
                    PARTITION OF events FOR VALUES IN ('memory');
                CREATE TABLE IF NOT EXISTS events_generic 
                    PARTITION OF events FOR VALUES IN ('generic');
                
                -- Indexes
                CREATE INDEX IF NOT EXISTS idx_events_aggregate 
                    ON events(aggregate_id, version);
                CREATE INDEX IF NOT EXISTS idx_events_type 
                    ON events USING GIN (payload jsonb_path_ops);
                CREATE INDEX IF NOT EXISTS idx_events_timestamp 
                    ON events(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_events_created 
                    ON events(created_at DESC);
                
                -- Full-text search index on blind_index
                CREATE INDEX IF NOT EXISTS idx_events_search 
                    ON events USING GIN ((payload->'_blind_index')) WHERE payload->'_blind_index' IS NOT NULL;
                
                -- Aggregates table
                CREATE TABLE IF NOT EXISTS aggregates (
                    aggregate_id VARCHAR(255) PRIMARY KEY,
                    aggregate_type VARCHAR(50) NOT NULL,
                    current_version INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(50) NOT NULL DEFAULT 'pending',
                    problem TEXT,
                    preset VARCHAR(100),
                    method VARCHAR(100),
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                
                -- Indexes for aggregates
                CREATE INDEX IF NOT EXISTS idx_aggregates_status 
                    ON aggregates(status);
                CREATE INDEX IF NOT EXISTS idx_aggregates_type 
                    ON aggregates(aggregate_type);
                CREATE INDEX IF NOT EXISTS idx_aggregates_created 
                    ON aggregates(created_at DESC);
                
                -- Snapshots table
                CREATE TABLE IF NOT EXISTS snapshots (
                    aggregate_id VARCHAR(255) PRIMARY KEY,
                    version INTEGER NOT NULL,
                    state JSONB NOT NULL,
                    snapshot_type VARCHAR(50) DEFAULT 'full',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                
                -- Read models (CQRS projections)
                CREATE TABLE IF NOT EXISTS read_models (
                    model_name VARCHAR(100) NOT NULL,
                    model_key VARCHAR(255) NOT NULL,
                    data JSONB NOT NULL,
                    version INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (model_name, model_key)
                );
                
                -- Function to update updated_at timestamp
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = NOW();
                    RETURN NEW;
                END;
                $$ language 'plpgsql';
                
                -- Trigger for aggregates
                DROP TRIGGER IF EXISTS update_aggregates_updated_at ON aggregates;
                CREATE TRIGGER update_aggregates_updated_at
                    BEFORE UPDATE ON aggregates
                    FOR EACH ROW
                    EXECUTE FUNCTION update_updated_at_column();
            """)
    
    async def save_events(self, events: list[DomainEvent]) -> None:
        """
        Save events atomically.
        
        Raises:
            asyncpg.Error: If database operation fails
            json.JSONDecodeError: If event payload cannot be serialized
            ConnectionError: If database connection is unavailable
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    for event in events:
                        # Serialize and ENCRYPT payload (Phase 3: E2EE)
                        raw_payload = {
                            k: v for k, v in asdict(event).items()
                            if k not in ('event_id', 'event_type', 'aggregate_id',
                                         'version', 'timestamp')
                        }
                        payload_json = json.dumps(raw_payload)
                        encrypted_payload = self._encryption.encrypt(payload_json)
                        
                        # Generate blind indexes from the textual content of the raw_payload
                        blind_indexes: List[str] = []
                        if isinstance(raw_payload, dict):
                            # Focus on common textual fields for blind indexing
                            text_to_index = []
                            for key in ['problem', 'content', 'rationale', 'summary', 'message']:
                                if key in raw_payload and isinstance(raw_payload[key], str):
                                    text_to_index.append(raw_payload[key])
                            if text_to_index:
                                blind_indexes = self._encryption.generate_blind_index(" ".join(text_to_index))

                        final_payload = {
                            "_e": encrypted_payload,
                            "_blind_index": blind_indexes # Store blind indexes
                        }

                        # Determine aggregate type
                        aggregate_type = self._get_aggregate_type(event.event_type)

                        # Insert event
                        await conn.execute("""
                            INSERT INTO events
                            (event_id, event_type, aggregate_id, aggregate_type,
                             version, timestamp, payload, created_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
                            ON CONFLICT (event_id) DO NOTHING
                        """,
                            event.event_id,
                            event.event_type.value,
                            event.aggregate_id,
                            aggregate_type,
                            event.version,
                            event.timestamp,
                            json.dumps(final_payload),
                        )

                        # Update aggregate
                        await self._update_aggregate(conn, event, aggregate_type)
        except _AsyncpgError as e:
            logger.error(f"PostgreSQL error saving events: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to serialize event payload: {e}")
            raise
        except ConnectionError as e:
            logger.error(f"Database connection error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error saving events: {e}")
            raise
    
    def _get_aggregate_type(self, event_type: EventType) -> str:
        """Determine aggregate type from event."""
        if event_type in (
            EventType.PIPELINE_STARTED, EventType.PHASE_STARTED,
            EventType.PHASE_COMPLETED, EventType.PHASE_FAILED,
            EventType.PIPELINE_COMPLETED, EventType.PIPELINE_FAILED,
        ):
            return "pipeline"
        elif event_type in (
            EventType.WIDGET_DETECTED, EventType.WIDGET_EXECUTED,
            EventType.WIDGET_FAILED,
        ):
            return "widget"
        elif event_type in (
            EventType.MEMORY_STORED, EventType.MEMORY_RECALLED,
        ):
            return "memory"
        else:
            return "generic"
    
    async def _update_aggregate(
        self,
        conn: Any,
        event: DomainEvent,
        aggregate_type: str,
    ) -> None:
        """Update aggregate state."""
        from reasoner.core.events.domain_events import (
            PipelineStarted, PipelineCompleted, PipelineFailed,
        )
        
        problem = preset = method = status = None
        
        if isinstance(event, PipelineStarted):
            # Encrypt sensitive problem field (Phase 3: E2EE)
            problem = self._encryption.encrypt(event.problem)
            preset = event.preset
            method = event.method
            status = "running"
        elif isinstance(event, PipelineCompleted):
            status = "completed"
        elif isinstance(event, PipelineFailed):
            status = "failed"
        
        # Upsert aggregate
        await conn.execute("""
            INSERT INTO aggregates 
            (aggregate_id, aggregate_type, current_version, status, 
             problem, preset, method, metadata, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, '{}', NOW(), NOW())
            ON CONFLICT (aggregate_id) DO UPDATE SET
                current_version = EXCLUDED.current_version,
                status = COALESCE(EXCLUDED.status, aggregates.status),
                problem = COALESCE(EXCLUDED.problem, aggregates.problem),
                preset = COALESCE(EXCLUDED.preset, aggregates.preset),
                method = COALESCE(EXCLUDED.method, aggregates.method),
                updated_at = NOW()
        """,
            event.aggregate_id,
            aggregate_type,
            event.version,
            status or "running",
            problem,
            preset,
            method,
        )
    
    async def get_events(
        self,
        aggregate_id: str,
        from_version: int = 0,
    ) -> list[DomainEvent]:
        """Get events for an aggregate."""
        pool = self._read_pool if (self.use_read_replica and self._read_pool is not None) else self._pool

        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM events
                WHERE aggregate_id = $1 AND version > $2
                ORDER BY version ASC
            """, aggregate_id, from_version)
            
            return [e for e in (self._deserialize_event(row) for row in rows) if e is not None]
    
    def _deserialize_event(self, row: Any) -> DomainEvent | None:
        """Deserialize database row to event. Decrypts payload if necessary (Phase 3)."""
        from reasoner.core.events.domain_events import make_event

        try:
            payload = json.loads(row["payload"])
            
            # Check for encrypted payload (Phase 3: E2EE)
            if "_e" in payload:
                decrypted_json = self._encryption.decrypt(payload["_e"])
                payload = json.loads(decrypted_json)

            event = make_event(
                EventType(row["event_type"]),
                aggregate_id=row["aggregate_id"],
                version=row["version"],
                **payload,
            )

            # Override fields
            object.__setattr__(event, 'event_id', row["event_id"])
            object.__setattr__(event, 'timestamp', row["timestamp"])

            return event
        except Exception as exc:
            logger.error(
                "Data integrity failure: event %s (aggregate %s v%s): %s",
                row.get("event_id"),
                row.get("aggregate_id"),
                row.get("version"),
                exc,
            )
            raise RuntimeError(f"Corrupted event data: {exc}") from exc
    
    async def list_pipelines(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List pipelines with filtering."""
        pool = self._read_pool if self.use_read_replica else self._pool
        
        async with pool.acquire() as conn:
            query = """
                SELECT * FROM aggregates
                WHERE aggregate_type = 'pipeline'
            """
            params = []

            if status:
                params.append(status)
                query += f" AND status = ${len(params)}"

            params.append(limit)
            query += f" ORDER BY created_at DESC LIMIT ${len(params)}"
            params.append(offset)
            query += f" OFFSET ${len(params)}"
            
            rows = await conn.fetch(query, *params)
            
            results = []
            for row in rows:
                problem = row["problem"]
                if problem:
                    try:
                        # Attempt decryption (Phase 3: E2EE)
                        problem = self._encryption.decrypt(problem)
                    except Exception:
                        # Fallback for old plaintext data
                        pass
                
                results.append({
                    "aggregate_id": row["aggregate_id"],
                    "status": row["status"],
                    "problem": problem,
                    "preset": row["preset"],
                    "method": row["method"],
                    "version": row["current_version"],
                    "created_at": row["created_at"].isoformat(),
                    "updated_at": row["updated_at"].isoformat(),
                })
            return results
    
    async def search_events(
        self,
        query: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Full-text search events."""
        pool = self._read_pool if self.use_read_replica else self._pool
        
        async with pool.acquire() as conn:
            # Generate blind indexes for the search query
            search_hashes = self._encryption.generate_blind_index(query)
            if not search_hashes:
                return [] # No search terms to index
            
            # PostgreSQL array contains operator (jsonb @> array)
            # We need to construct a JSONB array for the @> operator
            search_hashes_jsonb = json.dumps(search_hashes)

            rows = await conn.fetch("""
                SELECT e.*, a.problem, a.status
                FROM events e
                JOIN aggregates a ON e.aggregate_id = a.aggregate_id
                WHERE e.payload->'_blind_index' @> $1::jsonb
                ORDER BY e.timestamp DESC
                LIMIT $2
            """, search_hashes_jsonb, limit)
            
            return [
                {
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "aggregate_id": row["aggregate_id"],
                    "problem": row["problem"],
                    "status": row["status"],
                    "timestamp": row["timestamp"],
                }
                for row in rows
            ]
    
    async def save_snapshot(
        self,
        aggregate_id: str,
        version: int,
        state: dict[str, Any],
        snapshot_type: str = "full",
    ) -> None:
        """
        Save aggregate snapshot.
        
        Args:
            aggregate_id: ID of the aggregate
            version: Version number
            state: State dictionary
            snapshot_type: Type of snapshot
            
        Raises:
            asyncpg.Error: If database operation fails
            json.JSONDecodeError: If state cannot be serialized
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Encrypt snapshot state (Phase 3: E2EE)
            state_json = json.dumps(state)
            encrypted_state = self._encryption.encrypt(state_json)
            final_state = {"_e": encrypted_state}

            async with self._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO snapshots
                    (aggregate_id, version, state, snapshot_type, created_at)
                    VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT (aggregate_id) DO UPDATE SET
                        version = EXCLUDED.version,
                        state = EXCLUDED.state
                """, aggregate_id, version, json.dumps(final_state), snapshot_type)
        except _AsyncpgError as e:
            logger.error(f"PostgreSQL error saving snapshot for {aggregate_id}: {e}")
            raise
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize state for {aggregate_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error saving snapshot for {aggregate_id}: {e}")
            raise
    
    async def get_snapshot(
        self,
        aggregate_id: str,
    ) -> tuple[int, dict[str, Any]] | None:
        """Get latest snapshot."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT version, state FROM snapshots 
                WHERE aggregate_id = $1
            """, aggregate_id)
            
            if row:
                state = json.loads(row["state"])
                # Check for encryption (Phase 3: E2EE)
                if isinstance(state, dict) and "_e" in state:
                    decrypted_json = self._encryption.decrypt(state["_e"])
                    state = json.loads(decrypted_json)
                return row["version"], state
            return None
    
    # ─────────────────────────────────────────────────────────────────────
    # CQRS READ MODEL OPERATIONS
    # ─────────────────────────────────────────────────────────────────────
    
    async def save_read_model(
        self,
        model_name: str,
        model_key: str,
        data: dict[str, Any],
        version: int = 0,
    ) -> None:
        """
        Save denormalized read model. Encrypts data (Phase 3: E2EE).
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Encrypt read model data (Phase 3: E2EE)
            data_json = json.dumps(data)
            encrypted_data = self._encryption.encrypt(data_json)
            final_data = {"_e": encrypted_data}

            async with self._pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO read_models
                    (model_name, model_key, data, version, updated_at)
                    VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT (model_name, model_key) DO UPDATE SET
                        data = EXCLUDED.data,
                        version = EXCLUDED.version,
                        updated_at = NOW()
                """, model_name, model_key, json.dumps(final_data), version)
        except _AsyncpgError as e:
            logger.error(f"PostgreSQL error saving read model {model_name}/{model_key}: {e}")
            raise
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize read model data: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error saving read model {model_name}/{model_key}: {e}")
            raise
    
    async def get_read_model(
        self,
        model_name: str,
        model_key: str,
    ) -> dict[str, Any] | None:
        """Get denormalized read model. Decrypts data (Phase 3: E2EE)."""
        pool = self._read_pool if self.use_read_replica else self._pool
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT data, version FROM read_models 
                WHERE model_name = $1 AND model_key = $2
            """, model_name, model_key)
            
            if row:
                try:
                    data = json.loads(row["data"])
                    # Check for encryption (Phase 3: E2EE)
                    if isinstance(data, dict) and "_e" in data:
                        decrypted_json = self._encryption.decrypt(data["_e"])
                        data = json.loads(decrypted_json)
                    return data
                except (json.JSONDecodeError, ValueError) as exc:
                    logger.error(
                        "Corrupted read model data for %s/%s: %s",
                        model_name, model_key, exc,
                    )
                    return None
            return None
    
    async def get_stats(self) -> dict[str, Any]:
        """Get event store statistics."""
        pool = self._read_pool if self.use_read_replica else self._pool
        
        async with pool.acquire() as conn:
            # Total events
            total_events = await conn.fetchval("SELECT COUNT(*) FROM events")
            
            # Total aggregates
            total_aggregates = await conn.fetchval("SELECT COUNT(*) FROM aggregates")
            
            # By status
            by_status_rows = await conn.fetch("""
                SELECT status, COUNT(*) as count 
                FROM aggregates 
                GROUP BY status
            """)
            by_status = {row["status"]: row["count"] for row in by_status_rows}
            
            # By type
            by_type_rows = await conn.fetch("""
                SELECT aggregate_type, COUNT(*) as count 
                FROM aggregates 
                GROUP BY aggregate_type
            """)
            by_type = {row["aggregate_type"]: row["count"] for row in by_type_rows}
            
            return {
                "total_events": total_events,
                "total_aggregates": total_aggregates,
                "by_status": by_status,
                "by_type": by_type,
                "storage": "postgresql",
            }
    
    async def delete_aggregate(self, aggregate_id: str) -> None:
        """
        Delete aggregate and all events (GDPR).
        
        Args:
            aggregate_id: ID of the aggregate to delete
            
        Raises:
            asyncpg.Error: If database operation fails
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute("""
                        DELETE FROM events WHERE aggregate_id = $1
                    """, aggregate_id)
                    await conn.execute("""
                        DELETE FROM aggregates WHERE aggregate_id = $1
                    """, aggregate_id)
                    await conn.execute("""
                        DELETE FROM snapshots WHERE aggregate_id = $1
                    """, aggregate_id)
                    await conn.execute("""
                        DELETE FROM read_models WHERE model_key = $1
                    """, aggregate_id)
            logger.info(f"Aggregate {aggregate_id} and all related data deleted")
        except _AsyncpgError as e:
            logger.error(f"PostgreSQL error deleting aggregate {aggregate_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error deleting aggregate {aggregate_id}: {e}")
            raise
    
    async def close(self) -> None:
        """Close connection pools."""
        if self._pool:
            await self._pool.close()
        if self._read_pool:
            await self._read_pool.close()


# ─────────────────────────────────────────────────────────────────────
# GLOBAL INSTANCE
# ─────────────────────────────────────────────────────────────────────

_postgres_store: PostgreSQLEventStore | None = None


def get_postgres_store(
    connection_string: str | None = None,
    pool_size: int = 10,
) -> PostgreSQLEventStore:
    """Get or create PostgreSQL event store."""
    global _postgres_store
    if _postgres_store is None:
        _postgres_store = PostgreSQLEventStore(
            connection_string=connection_string,
            pool_size=pool_size,
        )
    return _postgres_store


async def initialize_postgres_store(
    connection_string: str | None = None,
    pool_size: int = 10,
) -> PostgreSQLEventStore:
    """Initialize PostgreSQL event store."""
    store = get_postgres_store(connection_string, pool_size)
    try:
        await store.initialize()
    except Exception:
        # Reset singleton so the next call creates a fresh instance
        global _postgres_store
        _postgres_store = None
        raise
    return store
