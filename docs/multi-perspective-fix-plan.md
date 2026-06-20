# Multi-Perspective Bug Hunt — Fix Plan

**Source:** Multi-perspective Reasoner self-analysis run 2026-06-08  
**Research:** 5 parallel code-explorer agents covering all flagged areas  
**Scope:** SSE/CQRS gap, mixin MRO, Redis SPOF, PipelineState races, event store compaction

---

## Priority Levels

| Priority | Meaning |
|----------|---------|
| P0 | Silent data corruption or financial damage — fix before next deploy |
| P1 | Availability or security degradation under real failure conditions |
| P2 | Growing technical debt with production impact on the horizon |
| P3 | Architectural hygiene, latent risks |

---

## P0 — Critical (Fix Before Next Deploy)

### P0-A: Webhook Double-Processing on Redis Failure

**File:** `src/reasoner/infrastructure/billing/webhooks.py:54–95`

**What happens:** When Redis is unavailable, the dedup check (`redis.get`), the atomic claim (`redis.set NX`), and the completion marker (`redis.setex`) all silently fail-open and proceed. A Stripe webhook that arrives twice (Stripe retries all events) will be processed twice — duplicate charge, duplicate invoice.

**Exact sequence:**
1. `redis.get("stripe_webhook:evt_123:completed")` → exception → ignored, proceeds (line 59–69)
2. `redis.set("stripe_webhook:evt_123:processing", nx=True)` → exception → ignored, proceeds (line 64–67)
3. Webhook processed: customer charged, DB record created
4. `redis.setex("stripe_webhook:evt_123:completed", ...)` → exception → ignored, silently skipped (line 84–89)
5. Stripe retries same event 5 min later → steps 1–4 repeat → **duplicate charge**

**Fix:** Add a database-backed idempotency guard that runs *before* the Redis check. Use a `processed_webhooks` table with a unique constraint on `(event_id, provider)`. If the DB insert succeeds, process. If it raises `UniqueViolation`, skip. Redis dedup can remain as a fast-path, but the DB guard is the safety net.

```python
# In _process_stripe_event(), before Redis check:
async with db.transaction():
    inserted = await db.execute(
        "INSERT INTO processed_webhooks (event_id, provider, processed_at) "
        "VALUES ($1, 'stripe', NOW()) ON CONFLICT DO NOTHING",
        event_id
    )
    if inserted == 0:
        return  # Already processed — idempotent skip

# Existing Redis path follows (performance optimization only, no longer safety-critical)
```

**Migration needed:** `CREATE TABLE processed_webhooks (event_id TEXT, provider TEXT, processed_at TIMESTAMPTZ, PRIMARY KEY (event_id, provider));`

**Test:** Simulate Redis down (mock raises `ConnectionError`), send same event twice, assert DB record count = 1 and handler invoked once.

---

### P0-B: Event Bus Silently Drops Non-Critical Phase Events

**File:** `src/reasoner/application/event_bus/bus.py:159–173`

**What happens:** When the queue is full (default max 1000), non-critical events are dropped with `put_nowait()` which raises `QueueFull`, caught and dead-lettered asynchronously. Phase events (`PHASE_STARTED`, `PHASE_COMPLETED`) are currently non-critical. Any downstream subscriber (metrics, audit, neuro learn) relying on these events misses them silently.

**Root cause:** `state._emit()` in `pipeline_state.py:1378–1411` creates fire-and-forget tasks without checking drop status.

**Fix — two-part:**

1. **Mark phase lifecycle events as critical** in `src/reasoner/core/events/domain_events.py`:
```python
# Change PHASE_STARTED and PHASE_COMPLETED is_critical = True
# This switches them from put_nowait (drop) to await put (backpressure)
```

2. **Add dead-letter monitoring** — the DLQ writes to `logs/dead_letter_events.jsonl` but nothing reads it. Add a counter metric at the drop site:
```python
# bus.py:170 — after dead-letter task is created:
self._dropped_event_count += 1
# Expose via /health endpoint and log a WARNING (currently logs ERROR but no metric)
```

**Test:** Fill queue to capacity (mock 1001 events), assert critical events block (backpressure) rather than dropping, assert non-critical events increment drop counter.

---

### P0-C: Fire-and-Forget Error Events Lose Audit Trail

**File:** `src/reasoner/infrastructure/persistence/postgres_store.py:442, 465, 659, 747, 768`

**What happens:** When event deserialization fails (corrupted JSONB payload), `_fire_and_forget(bus.publish(error_event))` creates an asyncio task. If the event bus is down or crashes, the task exception is caught only by a `done_callback` that logs to stderr. The audit trail entry (which error occurred, for which aggregate, at what version) is lost permanently.

**5 call sites:**
- Line 442: `_deserialize_event` JSONDecodeError
- Line 465: `_deserialize_event` generic Exception  
- Line 659: `get_snapshot` JSONDecodeError
- Line 747: `get_read_model` JSONDecodeError
- Line 768: `get_read_model` ValueError

**Fix:** Write the error directly to the `events` table as a fallback when bus publish fails. The event store is always available (it's what we're in), so this is safe:

```python
async def _publish_error_or_persist(self, error_event, label: str) -> None:
    try:
        await asyncio.wait_for(self._bus.publish(error_event), timeout=5.0)
    except Exception as e:
        logger.warning("%s bus publish failed (%s) — persisting directly", label, e)
        # Fallback: write raw error record directly to DB, bypassing bus
        await self._persist_error_direct(error_event)
```

Replace all 5 `_fire_and_forget(bus.publish(...))` calls with `await self._publish_error_or_persist(...)`.

**Test:** Mock `bus.publish` to raise, call each of the 5 code paths, assert error record appears in DB.

---

## P1 — High (Fix in Next Sprint)

### P1-A: Circuit Breaker Fail-Open Propagates to All Workers

**File:** `src/reasoner/infrastructure/circuit_breaker.py:358–426`

**What happens:** When Redis is down, `can_execute()` returns `True` (fail-open) for every call. A provider that is returning 500s will not be circuit-broken across workers — each worker fails independently until it observes enough local failures. Under multi-worker load this means hundreds of redundant calls to dead providers before any worker opens its local breaker.

**Fix:** Add a short-circuit local in-memory cache for Redis-backed state. On Redis failure, the circuit breaker falls back to its in-memory state from the last successful Redis read (TTL 60s), rather than defaulting to `CLOSED`:

```python
# In RedisCircuitBreaker.can_execute():
if self._redis_failed:
    # Fall back to local state (may be stale by up to 60s, but not blindly open)
    return self._local_state != CircuitState.OPEN
# ... existing Redis path
```

**Keep the fail-open sentinel** but make it conditional: only fail-open if local state is also `CLOSED` or unknown. If last known state was `OPEN`, stay `OPEN` even without Redis.

**Test:** Set circuit to OPEN via Redis, mock Redis to fail, assert `can_execute()` returns `False` (not fail-open).

---

### P1-B: Rate Limiter Per-Worker Fallback Allows 4× Bypass

**File:** `src/reasoner/infrastructure/rate_limiter.py:252–296`

**What happens:** When Redis fails, each worker falls back to its own in-memory limiter. With 4 workers and a 60 req/min limit, a client can distribute requests across workers and effectively get 240 req/min. DoS window opens for the duration of the Redis outage.

**Fix:** When Redis fails in production, **fail-closed** (return rate-limited response) rather than falling back to per-worker memory. Add a config flag:

```python
# In settings.py:
RATE_LIMITER_REDIS_FAILURE_MODE: Literal["fail_open", "fail_closed"] = "fail_closed"
```

In `is_allowed()`:
```python
except ConnectionError:
    if settings.RATE_LIMITER_REDIS_FAILURE_MODE == "fail_closed":
        logger.warning("Rate limiter Redis unavailable — denying request (fail-closed)")
        return RateLimitResult(allowed=False, reason="rate_limiter_unavailable")
    # else: existing in-memory fallback
```

Default to `fail_closed` in production (`ENVIRONMENT=production`), `fail_open` in dev.

**Test:** Mock Redis to fail with `ENVIRONMENT=production`, assert requests are denied with `rate_limiter_unavailable` reason.

---

### P1-C: cost_state Dict Mutations During Concurrent LLM Calls (Verify + Fix)

**Files:** `src/reasoner/infrastructure/llm/executor.py`, `src/reasoner/domain/pipeline_state.py`

**What happens:** `cost_state.phase_costs` (dict[str, float]) and `cost_state.detailed_token_usage` (dict[str, dict[str, int]]) are mutated by LLMExecutor after each LLM call. Phase 2 runs up to 4 concurrent LLM calls via `asyncio.gather()`. If executor writes to `cost_state` inside the concurrent tasks (not after gather returns), these are real concurrent dict writes.

**Action:** Read `executor.py` to confirm whether cost tracking writes happen inside the concurrent task body or after gather returns.

If writes are inside task body (race exists):
```python
# Add to CostTrackingState:
_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

# In executor, wrap cost writes:
async with state.cost_state._lock:
    state.cost_state.phase_costs[phase_key] = cost
    state.cost_state.detailed_token_usage[phase_key] = usage
```

**Test:** Run 4 concurrent LLM mocks that all write cost data, assert final totals are correct (no dropped updates).

---

## P2 — Medium (Fix Within 30 Days)

### P2-A: Event Store Has No Retention Policy — Unbounded Growth

**Files:** `src/reasoner/infrastructure/persistence/event_store.py`, `src/reasoner/infrastructure/persistence/postgres_store.py`, `src/reasoner/core/constants_limits.py`

**What happens:** Events are appended forever with no TTL, no compaction, no cleanup. AI reasoning payloads are large (multi-KB JSON). At 100 pipeline runs/day, the event store will grow by ~50 MB/day with no bound.

**Fix — three parts:**

1. **Add retention constants** to `constants_limits.py`:
```python
EVENT_RETENTION_DAYS: int = 365          # Keep 1 year of events
SNAPSHOT_RETENTION_COUNT: int = 3        # Keep last 3 snapshots per aggregate
COMPACTION_BATCH_SIZE: int = 500         # Events deleted per compaction run
```

2. **Add `prune_events_before()` to EventStore**:
```python
async def prune_events_before(self, cutoff_date: datetime, batch_size: int = 500) -> int:
    """Delete events older than cutoff where a snapshot exists at or after that point.
    Never deletes events if no snapshot covers them (prevents unrecoverable aggregates)."""
    # Verify snapshot coverage before deletion
    # Delete in batches to avoid lock contention
```

3. **Register a nightly compaction job** (use existing scheduler or a FastAPI startup background task):
```python
@app.on_event("startup")  
async def schedule_compaction():
    asyncio.create_task(_run_nightly_compaction())
```

**Critical constraint:** Never prune events unless a snapshot exists at a version ≥ the pruned event's version. The aggregate replay strict version check (`pipeline.py:64`) will raise `ValueError` on gaps.

**Test:** Insert 1000 events with a snapshot at version 500, run compaction, assert events 1–499 deleted, events 500–1000 retained, aggregate reloads correctly.

---

### P2-B: Move `pricing.py` Out of Domain Layer

**File:** `src/reasoner/domain/pricing.py:90–92`

**What happens:** `domain/pricing.py` imports `_REGISTRY` from `infrastructure.llm.registry` — a domain→infrastructure violation. Breaks the hexagonal dependency rule.

**Fix:** Move `get_pricing()` to `src/reasoner/application/services/pricing_service.py`. Domain `pricing.py` retains only `ModelPricing` dataclass and constants. Application service imports both domain types and infrastructure registry.

**Effort:** ~30 min. Update 2–3 call sites.

---

### P2-C: Remove Dead Import in pipeline.py

**File:** `src/reasoner/application/pipeline.py:56`

```python
from reasoner.infrastructure.llm.exceptions import LLMError  # never used
```

**Fix:** Delete the line.

---

### P2-D: Add Snapshot-to-Event Gap Validation

**File:** `src/reasoner/infrastructure/persistence/snapshots.py:197–240`

**What happens:** `load_aggregate_with_snapshot()` loads events since snapshot version but does not validate that there are no gaps. If compaction (P2-A) is implemented incorrectly, corrupt aggregates are loaded silently.

**Fix:** After loading events since snapshot, assert contiguity:
```python
if events:
    expected_versions = range(snapshot_version + 1, snapshot_version + 1 + len(events))
    actual_versions = [e.version for e in events]
    if list(actual_versions) != list(expected_versions):
        raise EventStoreCorruptionError(
            f"Event gap detected for aggregate {aggregate_id}: "
            f"expected {list(expected_versions)}, got {actual_versions}"
        )
```

---

## P3 — Low (Architectural Housekeeping)

### P3-A: Mixin Violations (Residual — Already Mostly Fixed)

**Status:** Mixins directory was deleted May 2026 (commit c7f3104). MRO concern is resolved.

Remaining: P2-B (`pricing.py`) and P2-C (dead import) cover the two residual violations.

---

### P3-B: PipelineState Dict Mutations — Add Latent Protection

**What happens:** Currently safe (phases sequential, gather results processed serially). If a future refactor runs phases concurrently, `method_state.data` dict mutations would race.

**Fix (defensive):** Add a docstring to `MethodState` and a comment to every `asyncio.gather()` call site that mutates shared state:

```python
class MethodState:
    """
    NOT thread-safe. Mutations must only occur after asyncio.gather() returns,
    never inside concurrent task bodies. See docs/pipeline-concurrency-contract.md.
    """
```

No code change needed until phases actually run concurrently. The cost_state fix (P1-C) is the priority.

---

### P3-C: Expose Dead-Letter Queue Metrics

**File:** `src/reasoner/application/event_bus/bus.py`

Add `dropped_event_count` to `/health` response and log a WARNING (not just ERROR) when DLQ grows. This makes the P0-B drop monitoring actionable.

---

## Implementation Order

```
Week 1 (P0):
  P0-A: DB-backed webhook idempotency (2–3h)
  P0-B: Mark phase events critical + DLQ counter (1h)
  P0-C: Replace fire-and-forget error publishes (2h)

Week 2 (P1):
  P1-A: Circuit breaker local state fallback (2h)
  P1-B: Rate limiter fail-closed mode (1h)
  P1-C: Verify + fix cost_state concurrent writes (1–2h)

Week 3-4 (P2):
  P2-A: Event retention + nightly compaction (4–6h)
  P2-D: Snapshot gap validation (1h)
  P2-B/C: Pricing service move + dead import removal (30min)
```

---

## Files Changed Summary

| File | Change | Priority |
|------|--------|----------|
| `infrastructure/billing/webhooks.py` | DB-backed idempotency guard | P0-A |
| `infrastructure/persistence/postgres_store.py` | Replace 5× fire-and-forget with awaited fallback | P0-C |
| `application/event_bus/bus.py` | Drop counter metric, phase events → critical | P0-B |
| `core/events/domain_events.py` | Mark PHASE_STARTED/COMPLETED as critical | P0-B |
| `infrastructure/circuit_breaker.py` | Local state fallback on Redis failure | P1-A |
| `infrastructure/rate_limiter.py` | fail_closed mode in production | P1-B |
| `infrastructure/llm/executor.py` | Lock cost_state writes (if race confirmed) | P1-C |
| `infrastructure/persistence/event_store.py` | Add prune_events_before() | P2-A |
| `infrastructure/persistence/postgres_store.py` | Add compaction job | P2-A |
| `core/constants_limits.py` | EVENT_RETENTION_DAYS, SNAPSHOT_RETENTION_COUNT | P2-A |
| `infrastructure/persistence/snapshots.py` | Gap validation on load | P2-D |
| `domain/pricing.py` | Remove _REGISTRY import | P2-B |
| `application/services/pricing_service.py` | New file: pricing logic lives here | P2-B |
| `application/pipeline.py` | Remove dead LLMError import | P2-C |

**New migration:**
```sql
CREATE TABLE processed_webhooks (
    event_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (event_id, provider)
);
CREATE INDEX idx_processed_webhooks_provider ON processed_webhooks(provider);
```
