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

import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime
from typing import Any

from aiocircuitbreaker import CircuitBreaker  # New import
from tenacity import retry, stop_after_attempt, wait_exponential  # New import

try:
    import asyncpg
    _AsyncpgError: type[Exception] = asyncpg.PostgresError
except ImportError:
    asyncpg = None  # type: ignore[assignment]

    class _AsyncpgError(Exception):
        """Sentinel for when asyncpg is not installed.

        Using a dedicated class instead of bare `Exception` prevents
        `except _AsyncpgError` from inadvertently catching unrelated
        errors like KeyError, TypeError, or ValueError in the try blocks.
        """

from cryptography.fernet import InvalidToken

from reasoner.core.constants import DEFAULT_DB_COMMAND_TIMEOUT
from reasoner.core.events.domain_events import (
    ALL_EVENT_TYPES,
    DomainEvent,
    MemoryEventType,
    PipelineEventType,
    SaaSEventType,
    WidgetEventType,
)
from reasoner.core.ports.crypto_port import EncryptionPort
from reasoner.security.encryption import get_encryption_service

logger = logging.getLogger(__name__)

# Retained references to background publish tasks to prevent premature GC.
_BG_PUBLISH_TASKS: set[asyncio.Task] = set()


def _fire_and_forget(coro, *, label: str = "background task") -> asyncio.Task:
    """Create a tracked asyncio task; log exceptions via done_callback."""
    task = asyncio.create_task(coro)
    _BG_PUBLISH_TASKS.add(task)
    task.add_done_callback(_BG_PUBLISH_TASKS.discard)
    task.add_done_callback(
        lambda t: logger.warning("%s failed: %s", label, t.exception())
        if not t.cancelled() and t.exception()
        else None
    )
    return task


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
        pool_size: int = 20,  # v3.4: C5 — raised from 10 to match UVICORN_WORKERS
        use_read_replica: bool = False,
        read_replica_url: str | None = None,
        circuit_breaker_enabled: bool = True,
    ):
        self.connection_string = connection_string
        self.pool_size = pool_size
        self.use_read_replica = use_read_replica
        self.read_replica_url = read_replica_url

        self._pool = None
        self._read_pool = None
        self._encryption: EncryptionPort = get_encryption_service()

        # Initialize circuit breaker.
        # aiocircuitbreaker.CircuitBreaker's constructor is
        # (failure_threshold, recovery_timeout, ...) -- this previously
        # passed fail_max/reset_timeout (pybreaker's kwarg names, not this
        # library's), which raised TypeError on every construction, making
        # PostgreSQLEventStore entirely unconstructable.
        self._circuit_breaker = (
            CircuitBreaker(failure_threshold=5, recovery_timeout=30)
            if circuit_breaker_enabled
            else None
        )

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
        async with self._pool.acquire(timeout=10.0) as conn:
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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
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

        # If circuit breaker is enabled, wrap the operation with it.
        # aiocircuitbreaker.CircuitBreaker is NOT an async context manager
        # (it has only sync __enter__/__exit__); use .call(coro_fn, *args),
        # which applies the breaker's sync `with self:` around an awaited
        # call. `async with self._circuit_breaker` raised TypeError on every
        # invocation -- previously never reached because the breaker failed
        # to construct at all (fixed in the prior commit), now it would.
        if self._circuit_breaker:
            await self._circuit_breaker.call(self._save_events_internal, events)
        else:
            await self._save_events_internal(events)

    async def _save_events_internal(self, events: list[DomainEvent]) -> None:
        """
        Internal method for saving events, allowing external decorators to wrap it.
        """
        try:
            async with self._pool.acquire(timeout=10.0) as conn:
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
                        blind_indexes: list[str] = []
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

    def _get_aggregate_type(self, event_type: PipelineEventType | WidgetEventType | MemoryEventType | SaaSEventType) -> str:
        """Determine aggregate type from event."""
        if event_type in (
            PipelineEventType.PIPELINE_STARTED, PipelineEventType.PHASE_STARTED,
            PipelineEventType.PHASE_COMPLETED, PipelineEventType.PHASE_FAILED,
            PipelineEventType.PIPELINE_COMPLETED, PipelineEventType.PIPELINE_FAILED,
        ):
            return "pipeline"
        elif event_type in (
            WidgetEventType.WIDGET_DETECTED, WidgetEventType.WIDGET_EXECUTED,
            WidgetEventType.WIDGET_FAILED,
        ):
            return "widget"
        elif event_type in (
            MemoryEventType.MEMORY_STORED, MemoryEventType.MEMORY_RECALLED,
        ):
            return "memory"
        elif event_type in (
            SaaSEventType.USER_REGISTERED, SaaSEventType.USER_LOGGED_IN,
        ):
            return "saas"
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
            PipelineCompleted,
            PipelineFailed,
            PipelineStarted,
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

        async with pool.acquire(timeout=10.0) as conn:
            rows = await conn.fetch("""
                SELECT * FROM events
                WHERE aggregate_id = $1 AND version > $2
                ORDER BY version ASC
            """, aggregate_id, from_version)

            events = []
            for row in rows:
                event = await self._deserialize_event(row)
                if event is not None:
                    events.append(event)
            return events

    async def _publish_error_or_persist(self, error_event: DomainEvent, label: str) -> None:
        """Publish error event to bus; persist directly to event store if bus is unavailable."""
        from reasoner.application.event_bus.bus import get_event_bus
        try:
            bus = get_event_bus()
            await asyncio.wait_for(bus.publish(error_event), timeout=5.0)
        except Exception as exc:
            logger.error(
                "%s: bus publish failed (%s) — persisting error event directly to store",
                label, exc,
            )
            try:
                if self._pool is not None:
                    await self.save_events([error_event])
            except Exception as db_exc:
                logger.error(
                    "%s: error event lost — bus and direct persist both failed: "
                    "bus_err=%s db_err=%s aggregate=%s version=%s event_id=%s",
                    label, exc, db_exc,
                    error_event.aggregate_id, error_event.version, error_event.event_id,
                )

    async def _deserialize_event(self, row: Any) -> DomainEvent | None:
        """Deserialize database row to event. Decrypts payload if necessary (Phase 3)."""
        from reasoner.core.events.domain_events import PipelineEventType, make_event

        try:
            payload = json.loads(row["payload"])

            # Check for encrypted payload (Phase 3: E2EE)
            if "_e" in payload:
                decrypted_json = self._encryption.decrypt(payload["_e"])
                payload = json.loads(decrypted_json)

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

            # Override fields
            object.__setattr__(event, 'event_id', row["event_id"])
            object.__setattr__(event, 'timestamp', row["timestamp"])

            return event
        except InvalidToken as exc:
            # Deliberately NOT downgraded to "skip this event": silently
            # dropping an undecryptable event truncates aggregate history and
            # replay would rebuild a wrong-but-plausible state.
            raise RuntimeError(
                f"Cannot decrypt event {row.get('event_id')} "
                f"(aggregate {row.get('aggregate_id')} v{row.get('version')}): "
                f"ENCRYPTION_KEY does not match the key this event was written with. "
                f"Append the original key to the ENCRYPTION_KEY list to decrypt it."
            ) from exc
        except json.JSONDecodeError as exc:
            logger.error(
                "Data integrity failure (JSONDecodeError): event %s (aggregate %s v%s): %s",
                row.get("event_id"),
                row.get("aggregate_id"),
                row.get("version"),
                exc,
            )
            error_event = make_event(
                PipelineEventType.ERROR_OCCURRED,
                aggregate_id=row.get("aggregate_id", "unknown"),
                version=row.get("version", 0),
                message=f"JSONDecodeError in event deserialization: {exc}",
                details={
                    "event_id": str(row.get("event_id", "unknown")),
                    "event_type": row.get("event_type", "unknown"),
                    "payload_sample": str(row.get("payload", ""))[:200],
                }
            )
            await self._publish_error_or_persist(error_event, "postgres_store _deserialize_event JSONDecodeError")
            return None
        except Exception as exc:
            logger.error(
                "Data integrity failure (Generic Exception): event %s (aggregate %s v%s): %s",
                row.get("event_id"),
                row.get("aggregate_id"),
                row.get("version"),
                exc,
            )
            error_event = make_event(
                PipelineEventType.ERROR_OCCURRED,
                aggregate_id=row.get("aggregate_id", "unknown"),
                version=row.get("version", 0),
                message=f"Generic error in event deserialization: {exc}",
                details={
                    "event_id": str(row.get("event_id", "unknown")),
                    "event_type": row.get("event_type", "unknown"),
                    "payload_sample": str(row.get("payload", ""))[:200],
                }
            )
            await self._publish_error_or_persist(error_event, "postgres_store _deserialize_event Exception")
            return None

    async def list_pipelines(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """List pipelines with filtering."""
        pool = self._read_pool if self.use_read_replica else self._pool

        async with pool.acquire(timeout=10.0) as conn:
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
                # Passes legacy plaintext through, but raises on a key
                # mismatch rather than returning ciphertext to the caller.
                problem = self._encryption.decrypt_optional(row["problem"])

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

        async with pool.acquire(timeout=10.0) as conn:
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
                    # aggregates.problem is encrypted at write time; without
                    # this the raw ciphertext leaks into API responses.
                    "problem": self._encryption.decrypt_optional(row["problem"]),
                    "status": row["status"],
                    "timestamp": row["timestamp"],
                }
                for row in rows
            ]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
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

        # If circuit breaker is enabled, wrap the operation with it.
        # See save_events for why this is .call(...) and not `async with`.
        if self._circuit_breaker:
            await self._circuit_breaker.call(
                self._save_snapshot_internal, aggregate_id, version, state, snapshot_type
            )
        else:
            await self._save_snapshot_internal(aggregate_id, version, state, snapshot_type)

    async def _save_snapshot_internal(
        self,
        aggregate_id: str,
        version: int,
        state: dict[str, Any],
        snapshot_type: str = "full",
    ) -> None:
        """
        Internal method for saving snapshots, allowing external decorators to wrap it.
        """
        try:
            # Encrypt snapshot state (Phase 3: E2EE). Snapshots are large,
            # repetitive JSON, so compress before encrypting.
            state_json = json.dumps(state)
            encrypted_state = self._encryption.encrypt(state_json, compress=True)
            final_state = {"_e": encrypted_state}

            async with self._pool.acquire(timeout=10.0) as conn:
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
        async with self._pool.acquire(timeout=10.0) as conn:
            row = await conn.fetchrow("""
                SELECT version, state FROM snapshots 
                WHERE aggregate_id = $1
            """, aggregate_id)

            if row:
                try:
                    state = json.loads(row["state"])
                    # Check for encryption (Phase 3: E2EE)
                    if isinstance(state, dict) and "_e" in state:
                        decrypted_json = self._encryption.decrypt(state["_e"])
                        state = json.loads(decrypted_json)
                    return row["version"], state
                except json.JSONDecodeError as exc:
                    logger.error(
                        "Corrupted snapshot data for aggregate %s: JSONDecodeError: %s",
                        aggregate_id, exc,
                    )
                    from reasoner.core.events.domain_events import PipelineEventType, make_event
                    error_event = make_event(
                        PipelineEventType.ERROR_OCCURRED,
                        aggregate_id=aggregate_id,
                        version=row.get("version", 0),
                        message=f"JSONDecodeError in snapshot deserialization: {exc}",
                        details={
                            "snapshot_data_sample": str(row.get("state", ""))[:200]
                        }
                    )
                    await self._publish_error_or_persist(error_event, "postgres_store get_snapshot")
                    return None
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
            # Encrypt read model data (Phase 3: E2EE). Compress first — read
            # models are denormalized JSON with the same redundancy profile
            # as snapshots.
            data_json = json.dumps(data)
            encrypted_data = self._encryption.encrypt(data_json, compress=True)
            final_data = {"_e": encrypted_data}

            async with self._pool.acquire(timeout=10.0) as conn:
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

        async with pool.acquire(timeout=10.0) as conn:
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
                except json.JSONDecodeError as exc:
                    logger.error(
                        "Corrupted read model data for %s/%s: JSONDecodeError: %s",
                        model_name, model_key, exc,
                    )
                    from reasoner.core.events.domain_events import PipelineEventType, make_event
                    error_event = make_event(
                        PipelineEventType.ERROR_OCCURRED,
                        aggregate_id=model_key,
                        version=row.get("version", 0),
                        message=f"JSONDecodeError in read model deserialization: {exc}",
                        details={
                            "model_name": model_name,
                            "model_key": model_key,
                            "read_model_data_sample": str(row.get("data", ""))[:200]
                        }
                    )
                    await self._publish_error_or_persist(error_event, "postgres_store get_read_model JSONDecodeError")
                    return None
                except ValueError as exc:
                    logger.error(
                        "Corrupted read model data for %s/%s: ValueError: %s",
                        model_name, model_key, exc,
                    )
                    from reasoner.core.events.domain_events import PipelineEventType, make_event
                    error_event = make_event(
                        PipelineEventType.ERROR_OCCURRED,
                        aggregate_id=model_key,
                        version=row.get("version", 0),
                        message=f"ValueError in read model deserialization: {exc}",
                        details={
                            "model_name": model_name,
                            "model_key": model_key,
                            "read_model_data_sample": str(row.get("data", ""))[:200]
                        }
                    )
                    await self._publish_error_or_persist(error_event, "postgres_store get_read_model ValueError")
                    return None
            return None

    async def get_stats(self) -> dict[str, Any]:
        """Get event store statistics."""
        pool = self._read_pool if self.use_read_replica else self._pool

        async with pool.acquire(timeout=10.0) as conn:
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
            async with self._pool.acquire(timeout=10.0) as conn:
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

    async def list_aggregate_ids_for_user(self, user_id: str) -> list[str]:
        """Return all aggregate IDs for a given user (GDPR erasure support).

        This method was previously entirely absent from PostgreSQLEventStore
        (only EventStore, the SQLite backend, had it), so data_eraser.py's
        call to it raised AttributeError on any deployment running
        EVENT_STORE_BACKEND=postgres -- caught by the caller's broad except,
        but combined with a separate receipt-construction bug meant the
        erasure receipt could still claim "completed" via cache eviction
        alone, while the user's actual pipeline data was never touched.

        The aggregates table here has no user_id column -- ownership was
        never tracked in either event-store backend's own schema, only in
        the separate ownership store (formerly a JSON file, now
        PipelineOwnershipRepository). That store is backend-agnostic by
        design, so this delegates to the same global singleton EventStore's
        own list_aggregate_ids_for_user uses, rather than needing a
        Postgres-native ownership table.
        """
        from reasoner.infrastructure.persistence.pipeline_ownership_repo import (
            ensure_pipeline_ownership_backfilled,
            get_pipeline_ownership_repo,
        )
        await ensure_pipeline_ownership_backfilled()
        repo = get_pipeline_ownership_repo()
        return await repo.list_pipeline_ids_for_user(user_id)

    async def prune_events_before(
        self,
        cutoff: datetime,
        batch_size: int = 500,
    ) -> int:
        """Delete events older than cutoff that are covered by a snapshot.

        Uses a CTE to work around the PostgreSQL restriction that partitioned
        tables do not support LIMIT in a top-level DELETE statement.

        Returns:
            Number of event rows deleted.
        """
        if self._pool is None:
            raise RuntimeError("PostgreSQLEventStore not initialized")

        async with self._pool.acquire(timeout=10.0) as conn:
            result = await conn.execute(
                """
                WITH to_delete AS (
                    SELECT e.id
                    FROM events e
                    INNER JOIN snapshots s ON s.aggregate_id = e.aggregate_id
                    WHERE e.version <= s.version
                      AND e.created_at < $1
                    ORDER BY e.created_at ASC
                    LIMIT $2
                )
                DELETE FROM events
                WHERE id IN (SELECT id FROM to_delete)
                """,
                cutoff,
                batch_size,
            )
            # asyncpg returns "DELETE N" string
            deleted = int(result.split()[-1]) if result else 0

            # Clean up terminal aggregates with no remaining events
            await conn.execute(
                """
                DELETE FROM aggregates
                WHERE status IN ('completed', 'failed')
                  AND updated_at < $1
                  AND NOT EXISTS (
                      SELECT 1 FROM events
                      WHERE events.aggregate_id = aggregates.aggregate_id
                  )
                """,
                cutoff,
            )

            return deleted

    async def count_eligible_events(self, cutoff: datetime) -> int:
        """Count events eligible for pruning (dry-run support)."""
        if self._pool is None:
            raise RuntimeError("PostgreSQLEventStore not initialized")

        async with self._pool.acquire(timeout=10.0) as conn:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS cnt
                FROM events e
                INNER JOIN snapshots s ON s.aggregate_id = e.aggregate_id
                WHERE e.version <= s.version
                  AND e.created_at < $1
                """,
                cutoff,
            )
            return row["cnt"] if row else 0

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
    pool_size: int = 20,  # v3.4: C5 — raised from 10 to match UVICORN_WORKERS
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
    pool_size: int = 20,  # v3.4: C5 — raised from 10 to match UVICORN_WORKERS
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
