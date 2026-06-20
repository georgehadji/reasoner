# P2-A: Event Retention & Compaction — Implementation Plan

**Priority:** P2 (medium; no production incident today, but unbounded growth will become one)  
**Estimated effort:** 4–6 hours  
**Risk level:** Medium — touches persistence layer, requires careful ordering of snapshot and event operations

---

## 1. Problem Statement

Both event stores grow without bound:

| Store | File | Schema |
|-------|------|--------|
| SQLite | `src/reasoner/infrastructure/events.db` | `events`, `aggregates`, `snapshots` |
| PostgreSQL | `DATABASE_URL` | Partitioned `events`, `aggregates`, `snapshots` |

At 100 pipeline runs/day, the `events` table receives ~500–800 rows per run (one per phase/sub-phase event), yielding **~50,000–80,000 rows/day**. AI reasoning payloads stored as JSON/JSONB are large (1–10 KB each). No TTL, no cleanup, no size cap.

**Critical constraint inherited from P2-D (already implemented):** `load_aggregate_with_snapshot()` now raises `EventStoreCorruptionError` on any version gap. Any compaction that deletes events not covered by a snapshot will trigger this error on the next reload. The prune operation must be snapshot-aware.

---

## 2. Architecture Decisions

### 2.1 Dependency Rule Compliance

Compaction is an **application-layer concern** (it decides *when* and *how much* to compact based on business rules). The actual deletion is an **infrastructure concern** (it knows the SQL dialect).

```
api/__init__.py (lifespan)
    → application/services/compaction_service.py  [NEW]
        → infrastructure/persistence/event_store.py     [MODIFIED: prune_events_before]
        → infrastructure/persistence/postgres_store.py  [MODIFIED: prune_events_before]
```

No circular imports: `CompactionService` imports from infrastructure; infrastructure does not import from application.

### 2.2 Two Stores, One Interface (Duck Typing)

Both `EventStore` and `PostgreSQLEventStore` get a `prune_events_before(cutoff: datetime, batch_size: int) -> int` method. No shared ABC is introduced — duck typing is sufficient since `get_event_store()` already returns whichever is active.

### 2.3 Snapshot Coverage Invariant

The prune operation must never delete an event unless a snapshot at version ≥ that event's version exists for the same aggregate. The SQL enforces this as a JOIN, not as application-layer logic. This is safer than checking in Python first because the DB enforces it atomically.

### 2.4 Batch Deletion to Avoid Lock Contention

Delete in batches of N rows (default 500) rather than a single unbounded DELETE. Each batch commits independently. This keeps write locks short and allows other operations to interleave.

### 2.5 Aggregate Row Cleanup

After events are pruned, rows in the `aggregates` table for fully-pruned aggregates (no remaining events, terminal status) are also cleaned up. This keeps `list_pipelines()` queries fast.

### 2.6 Snapshot Table Schema — Important Limitation

**The current schema stores exactly one snapshot per aggregate** (`aggregate_id` is the PRIMARY KEY). The plan mentions `SNAPSHOT_RETENTION_COUNT = 3`, but this requires a schema migration to change the PRIMARY KEY to `(aggregate_id, version)` and add a query to keep only the N most recent.

**Decision:** `SNAPSHOT_RETENTION_COUNT` is defined as a constant but is NOT enforced in P2-A. Its implementation (multi-snapshot schema migration) is tracked as a separate task in section 9. P2-A only prunes events covered by the existing single snapshot.

---

## 3. Constants & Settings

### 3.1 `src/reasoner/core/constants_limits.py`

Add to the DEFAULTS section (pure constants, no env reads):

```python
# ── Event Store Compaction ──────────────────────────────────────────
EVENT_RETENTION_DAYS: int = 365         # Events older than this are eligible for pruning
SNAPSHOT_RETENTION_COUNT: int = 3       # Target: keep N snapshots per aggregate
                                        # NOTE: current schema only supports 1 (single PK).
                                        # This constant is reserved for a future schema migration.
                                        # See docs/p2a-event-retention-compaction-plan.md §9.
COMPACTION_BATCH_SIZE: int = 500        # Rows deleted per batch to limit lock contention
```

### 3.2 `src/reasoner/core/settings.py`

Add to the `# ── Rate Limiter / Circuit Breaker Mode ──` section (or create a new `# ── Event Store ──` section):

```python
# ── Event Store Compaction ──
COMPACTION_ENABLED: bool = os.getenv("COMPACTION_ENABLED", "true").lower() in ("1", "true", "yes")
COMPACTION_RUN_HOUR_UTC: int = int(os.getenv("COMPACTION_RUN_HOUR_UTC", "3"))   # 3 AM UTC
EVENT_RETENTION_DAYS: int = int(os.getenv("EVENT_RETENTION_DAYS", "365"))
```

`settings.EVENT_RETENTION_DAYS` overrides `constants_limits.EVENT_RETENTION_DAYS` at runtime. The constant is the safe default when no env var is set.

---

## 4. SQLite EventStore — `prune_events_before()`

**File:** `src/reasoner/infrastructure/persistence/event_store.py`

Add as a new public method on `EventStore`, following the existing `_run_in_executor` pattern:

```python
async def prune_events_before(
    self,
    cutoff: datetime,
    batch_size: int = 500,
) -> int:
    """Delete events older than cutoff that are covered by a snapshot.

    Safety guarantee: only deletes events where a snapshot exists for the
    same aggregate at a version >= the event's version. Never creates gaps
    that would trigger EventStoreCorruptionError on replay.

    Returns:
        Number of event rows deleted.
    """
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    def _prune_sync() -> int:
        conn = self._get_connection()
        try:
            # Delete events covered by a snapshot AND older than the cutoff.
            # The JOIN with snapshots ensures we never delete events that
            # are not yet represented in a snapshot.
            cursor = conn.execute("""
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
            """, (cutoff_str, batch_size))
            deleted = cursor.rowcount

            # Clean up terminal aggregates with no remaining events.
            conn.execute("""
                DELETE FROM aggregates
                WHERE status IN ('completed', 'failed')
                  AND updated_at < ?
                  AND NOT EXISTS (
                      SELECT 1 FROM events
                      WHERE events.aggregate_id = aggregates.aggregate_id
                  )
            """, (cutoff_str,))

            conn.commit()
            return deleted
        except sqlite3.Error as e:
            conn.rollback()
            logger.error("prune_events_before failed: %s", e)
            raise

    return await self._run_in_executor(_prune_sync)
```

---

## 5. PostgreSQL EventStore — `prune_events_before()`

**File:** `src/reasoner/infrastructure/persistence/postgres_store.py`

Add as a new public method on `PostgreSQLEventStore`:

```python
async def prune_events_before(
    self,
    cutoff: datetime,
    batch_size: int = 500,
) -> int:
    """Delete events older than cutoff that are covered by a snapshot.

    Uses a CTE to batch-delete in at most `batch_size` rows per call.
    The JOIN on snapshots ensures no gaps are created.

    Returns:
        Number of event rows deleted.
    """
    if self._pool is None:
        raise RuntimeError("PostgreSQLEventStore not initialized")

    async with self._pool.acquire() as conn:
        result = await conn.execute("""
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
        """, cutoff, batch_size)

        # asyncpg returns "DELETE N" string
        deleted = int(result.split()[-1]) if result else 0

        # Clean up terminal aggregates with no remaining events
        await conn.execute("""
            DELETE FROM aggregates
            WHERE status IN ('completed', 'failed')
              AND updated_at < $1
              AND NOT EXISTS (
                  SELECT 1 FROM events
                  WHERE events.aggregate_id = aggregates.aggregate_id
              )
        """, cutoff)

        return deleted
```

Note: the partitioned `events` table in PostgreSQL does NOT support `LIMIT` in a top-level `DELETE`. The CTE + inner SELECT with `LIMIT` is the correct workaround for partitioned tables.

---

## 6. CompactionService

**File:** `src/reasoner/application/services/compaction_service.py` (new file)

```python
"""Application-layer compaction service.

Decides when to compact (age threshold, batch size, enabled flag) and
delegates actual deletion to the infrastructure event store. Lives in the
application layer to keep policy decisions out of infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from reasoner.core.settings import settings
from reasoner.core.constants_limits import COMPACTION_BATCH_SIZE, EVENT_RETENTION_DAYS

logger = logging.getLogger(__name__)


class CompactionService:
    """Prunes old events from the event store in daily batches."""

    def __init__(self, event_store: Any) -> None:
        # Accepts EventStore or PostgreSQLEventStore (duck typing)
        self._store = event_store

    def _cutoff(self) -> datetime:
        retention_days = settings.EVENT_RETENTION_DAYS
        return datetime.now(tz=timezone.utc) - timedelta(days=retention_days)

    async def run_once(self, dry_run: bool = False) -> dict[str, int]:
        """Run one full compaction pass.

        Loops in batches until no more eligible rows remain.

        Args:
            dry_run: If True, count eligible rows without deleting.

        Returns:
            {"deleted_events": N, "batches": M}
        """
        if not settings.COMPACTION_ENABLED:
            logger.info("Compaction disabled (COMPACTION_ENABLED=false)")
            return {"deleted_events": 0, "batches": 0}

        cutoff = self._cutoff()
        logger.info(
            "Compaction starting (cutoff=%s, dry_run=%s, retention_days=%d)",
            cutoff.isoformat(), dry_run, settings.EVENT_RETENTION_DAYS,
        )

        if dry_run:
            return await self._count_eligible(cutoff)

        total_deleted = 0
        batches = 0
        while True:
            try:
                deleted = await self._store.prune_events_before(
                    cutoff=cutoff,
                    batch_size=COMPACTION_BATCH_SIZE,
                )
            except Exception as exc:
                logger.error("Compaction batch %d failed: %s", batches + 1, exc)
                break

            batches += 1
            total_deleted += deleted
            logger.info("Compaction batch %d: deleted %d rows", batches, deleted)

            if deleted < COMPACTION_BATCH_SIZE:
                break  # Last batch was partial → nothing left to prune

            # Yield to event loop between batches to avoid starving other tasks
            await asyncio.sleep(0)

        logger.info("Compaction complete: %d events deleted in %d batches", total_deleted, batches)
        return {"deleted_events": total_deleted, "batches": batches}

    async def _count_eligible(self, cutoff: datetime) -> dict[str, int]:
        """Count how many rows would be deleted without deleting them."""
        # Not all stores implement count_eligible_events; degrade gracefully.
        if hasattr(self._store, "count_eligible_events"):
            n = await self._store.count_eligible_events(cutoff)
            return {"eligible_events": n, "dry_run": True}
        return {"eligible_events": -1, "dry_run": True, "note": "count not supported by this store"}


async def run_nightly_compaction_loop(event_store: Any) -> None:
    """Background loop that runs compaction once per day at COMPACTION_RUN_HOUR_UTC.

    Designed to run as a long-lived asyncio task from the FastAPI lifespan.
    Cancellation via asyncio.CancelledError is handled cleanly.
    """
    service = CompactionService(event_store)

    while True:
        now = datetime.now(tz=timezone.utc)
        target_hour = settings.COMPACTION_RUN_HOUR_UTC

        # Calculate seconds until next scheduled run
        next_run = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)

        sleep_seconds = (next_run - now).total_seconds()
        logger.info(
            "Compaction loop sleeping %.0fs until %s UTC",
            sleep_seconds, next_run.isoformat(),
        )

        try:
            await asyncio.sleep(sleep_seconds)
        except asyncio.CancelledError:
            logger.info("Compaction loop cancelled during sleep")
            return

        try:
            await service.run_once()
        except asyncio.CancelledError:
            logger.info("Compaction loop cancelled during run")
            return
        except Exception as exc:
            # Never crash the loop — log and wait until next day
            logger.error("Nightly compaction failed: %s", exc, exc_info=True)
```

---

## 7. Lifespan Wiring

**File:** `src/reasoner/api/__init__.py`

In the `lifespan()` context manager, after the token cache cleanup task (around line 128):

```python
# ── Startup section, after _cache_cleanup_task ──

# Background task: nightly event store compaction (P2-A)
from reasoner.infrastructure.persistence.event_store import get_event_store
from reasoner.application.services.compaction_service import run_nightly_compaction_loop
_compaction_store = get_event_store()
_compaction_task = asyncio.create_task(
    run_nightly_compaction_loop(_compaction_store),
    name="event_store_compaction",
)
```

In the shutdown section (after `_cache_cleanup_task.cancel()`), mirror the existing cancellation pattern:

```python
_compaction_task.cancel()
try:
    await _compaction_task
except asyncio.CancelledError:
    pass
```

**Note:** `get_event_store()` returns the SQLite store. If `DATABASE_URL` is set and `PostgreSQLEventStore` is used, a separate lookup is needed. Verify which store is active at wiring time by checking `settings.DATABASE_URL`. If PostgreSQL is active, pass the Postgres store instead.

The correct routing:

```python
if settings.DATABASE_URL:
    # PostgreSQL path — requires the store to be initialized first
    from reasoner.infrastructure.persistence.postgres_store import PostgreSQLEventStore
    _compaction_store = PostgreSQLEventStore(settings.DATABASE_URL)
    await _compaction_store.initialize()
else:
    from reasoner.infrastructure.persistence.event_store import get_event_store
    _compaction_store = get_event_store()
```

Alternatively, create a `get_active_event_store()` helper in a new `infrastructure/persistence/__init__.py` to encapsulate this selection logic.

---

## 8. Admin API Endpoint (Manual Trigger)

**File:** `src/reasoner/api/routes/admin.py` (existing file — add a new route)

```python
@router.post("/api/admin/compaction/run")
async def trigger_compaction(
    dry_run: bool = False,
    _auth=Depends(require_admin),
):
    """Manually trigger event store compaction. Use dry_run=true to audit first."""
    from reasoner.infrastructure.persistence.event_store import get_event_store
    from reasoner.application.services.compaction_service import CompactionService
    store = get_event_store()
    service = CompactionService(store)
    result = await service.run_once(dry_run=dry_run)
    return {"status": "ok", **result}
```

This allows ops to:
1. Run `POST /api/admin/compaction/run?dry_run=true` to audit eligible row counts before the first real run.
2. Run `POST /api/admin/compaction/run` to compact immediately without waiting for the next scheduled 3 AM run.

---

## 9. Schema Notes — Future Work

### 9.1 Multiple Snapshots Per Aggregate

The current snapshots table uses `aggregate_id` as PRIMARY KEY (one row per aggregate). `SNAPSHOT_RETENTION_COUNT = 3` cannot be honored without a schema migration.

**Future migration (NOT in P2-A scope):**

```sql
-- Step 1: rename current table
ALTER TABLE snapshots RENAME TO snapshots_v1;

-- Step 2: new table with version in PK
CREATE TABLE snapshots (
    aggregate_id TEXT NOT NULL,
    version      INTEGER NOT NULL,
    state        TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (aggregate_id, version)
);

-- Step 3: migrate data
INSERT INTO snapshots SELECT aggregate_id, version, state, created_at FROM snapshots_v1;
DROP TABLE snapshots_v1;
```

After this migration, the `prune_events_before()` SQL should join on `MAX(s.version)` per aggregate to find the highest available snapshot, and a `prune_snapshots()` method can keep only the N most recent.

### 9.2 PostgreSQL Partitioned Events Table and Compaction

The `events` table in PostgreSQL is partitioned by `aggregate_type`. The `DELETE ... WHERE id IN (CTE)` pattern works correctly across partitions in PostgreSQL 10+. However, partition-level pruning (dropping entire old partitions) would be faster if the table were also partitioned by time. That is a future optimization that requires re-partitioning the table.

---

## 10. Testing Strategy

### 10.1 Unit Test — SQLite EventStore.prune_events_before

File: `tests/unit/test_compaction_sqlite.py`

```python
@pytest.mark.asyncio
async def test_prune_does_not_delete_without_snapshot():
    store = EventStore(":memory:")
    # Insert 3 events for an aggregate with no snapshot
    await store.save_events([make_pipeline_event(aggregate_id="agg-1", version=i) for i in range(3)])
    deleted = await store.prune_events_before(
        cutoff=datetime.now(timezone.utc) + timedelta(days=1)
    )
    assert deleted == 0, "must not prune events with no covering snapshot"

@pytest.mark.asyncio
async def test_prune_deletes_events_covered_by_snapshot():
    store = EventStore(":memory:")
    await store.save_events([make_pipeline_event(aggregate_id="agg-2", version=i) for i in range(5)])
    await store.save_snapshot("agg-2", version=3, state={"dummy": True})
    deleted = await store.prune_events_before(
        cutoff=datetime.now(timezone.utc) + timedelta(days=1)
    )
    assert deleted == 4  # versions 0, 1, 2, 3 (covered by snapshot at v3)
    remaining = await store.get_events("agg-2")
    assert [e.version for e in remaining] == [4], "only post-snapshot event remains"

@pytest.mark.asyncio
async def test_prune_respects_cutoff_date():
    store = EventStore(":memory:")
    await store.save_events([make_pipeline_event(aggregate_id="agg-3", version=0)])
    await store.save_snapshot("agg-3", version=0, state={})
    deleted = await store.prune_events_before(
        cutoff=datetime.now(timezone.utc) - timedelta(days=1)  # only prune PAST the cutoff
    )
    assert deleted == 0, "event is too recent to prune"

@pytest.mark.asyncio
async def test_load_aggregate_after_prune_succeeds():
    """Verifying no EventStoreCorruptionError after valid compaction."""
    from reasoner.infrastructure.persistence.snapshots import SnapshotManager, DefaultSnapshotStrategy
    store = EventStore(":memory:")
    # Save events 0-4, snapshot at 3, prune 0-3
    await store.save_events([make_pipeline_event("agg-4", v) for v in range(5)])
    await store.save_snapshot("agg-4", 3, {"version": 3})
    await store.prune_events_before(cutoff=datetime.now(timezone.utc) + timedelta(days=1))
    # Snapshot + event[4] should reconstruct without error
    manager = SnapshotManager(store, DefaultSnapshotStrategy())
    aggregate = await manager.load_aggregate_with_snapshot("agg-4")
    assert aggregate is not None
```

### 10.2 Unit Test — CompactionService

File: `tests/unit/test_compaction_service.py`

```python
@pytest.mark.asyncio
async def test_compaction_service_respects_disabled_flag(monkeypatch):
    monkeypatch.setattr(settings, "COMPACTION_ENABLED", False)
    mock_store = AsyncMock()
    service = CompactionService(mock_store)
    result = await service.run_once()
    mock_store.prune_events_before.assert_not_called()
    assert result["deleted_events"] == 0

@pytest.mark.asyncio
async def test_compaction_service_loops_until_partial_batch():
    mock_store = AsyncMock()
    # First two batches full (500 rows each), third batch partial (100)
    mock_store.prune_events_before.side_effect = [500, 500, 100]
    service = CompactionService(mock_store)
    result = await service.run_once()
    assert result["deleted_events"] == 1100
    assert result["batches"] == 3
```

### 10.3 Integration Test

File: `tests/integration/test_compaction_integration.py` (mark with `@pytest.mark.integration`)

Run against a real SQLite file to verify:
- 1000 events + snapshot at version 500 → compaction deletes 501 (versions 0–500 covered by snapshot)
- Aggregate loads cleanly after compaction
- `COMPACTION_ENABLED=false` env var disables the run

---

## 11. Implementation Order

```
1. constants_limits.py — add EVENT_RETENTION_DAYS, SNAPSHOT_RETENTION_COUNT, COMPACTION_BATCH_SIZE
2. settings.py         — add COMPACTION_ENABLED, COMPACTION_RUN_HOUR_UTC, EVENT_RETENTION_DAYS
3. event_store.py      — add prune_events_before() [SQLite]
4. postgres_store.py   — add prune_events_before() [PostgreSQL]
5. compaction_service.py — new file: CompactionService + run_nightly_compaction_loop
6. tests/unit/         — write and run unit tests (steps 3–5 must pass before proceeding)
7. api/__init__.py     — wire _compaction_task in lifespan
8. api/routes/admin.py — add /api/admin/compaction/run endpoint
9. (Future) Schema migration for multi-snapshot support
```

Do NOT wire the lifespan task (step 7) until steps 3–6 pass. A buggy compaction loop that crashes repeatedly will fill the logs and could interfere with startup health checks.

---

## 12. Rollout Notes

### First Deployment

1. Deploy with `COMPACTION_ENABLED=false` to land the code without any deletion.
2. Call `POST /api/admin/compaction/run?dry_run=true` to audit how many rows are eligible.
3. If the count is large (>500K rows), set `COMPACTION_BATCH_SIZE=100` for the first real run to reduce lock duration.
4. Enable `COMPACTION_ENABLED=true` and observe logs for the next 3 AM UTC run.

### Rollback

`prune_events_before()` is destructive and non-reversible. Before enabling on a production DB, take a backup:

```bash
# SQLite
cp src/reasoner/infrastructure/events.db events.db.bak

# PostgreSQL
pg_dump -Fc $DATABASE_URL -f events_backup_$(date +%Y%m%d).dump
```

The compaction cannot be rolled back after deletion, but the application will not break if it is stopped partway — the batch commit pattern means each batch is atomic and partial runs leave the DB in a consistent state.

---

## 13. Files Changed Summary

| File | Change |
|------|--------|
| `core/constants_limits.py` | Add `EVENT_RETENTION_DAYS`, `SNAPSHOT_RETENTION_COUNT`, `COMPACTION_BATCH_SIZE` |
| `core/settings.py` | Add `COMPACTION_ENABLED`, `COMPACTION_RUN_HOUR_UTC`, `EVENT_RETENTION_DAYS` |
| `infrastructure/persistence/event_store.py` | Add `prune_events_before()` |
| `infrastructure/persistence/postgres_store.py` | Add `prune_events_before()` |
| `application/services/compaction_service.py` | **New file** — `CompactionService`, `run_nightly_compaction_loop` |
| `api/__init__.py` | Wire `_compaction_task` in `lifespan()` |
| `api/routes/admin.py` | Add `POST /api/admin/compaction/run` endpoint |
| `tests/unit/test_compaction_sqlite.py` | **New file** — SQLite store unit tests |
| `tests/unit/test_compaction_service.py` | **New file** — service-layer unit tests |
| `tests/integration/test_compaction_integration.py` | **New file** — full-stack integration test |
