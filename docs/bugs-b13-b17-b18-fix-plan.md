# Fix Plan: B-13, B-17, B-18

**Date:** 2026-06-07  
**Scope:** Three deferred bugs from the Bayesian bug-hunt session.  
**Architecture:** Hexagonal DDD + CQRS + Event Sourcing + Mixin Composition (FastAPI, Python 3.12+).

---

## B-13 — SSE Generator Orphan on Client Disconnect

### Problem

When a browser tab is closed mid-stream, FastAPI's `StreamingResponse` stops consuming the
outermost async generator (`_run_stream_with_metrics`), but **inner generators keep running**
because Python async generators are not automatically closed when iteration stops externally.

**Confirmed orphan sites (call chain top-to-bottom):**

```
/api/run  (api/__init__.py:425)
  └─ StreamingResponse(_run_stream_with_metrics)          ← no request propagated
       └─ async for chunk in run_stream_cached(...)       ← NO try/finally
            └─ async for chunk in run_stream(...)         ← continues running
                 ├─ run_phase_with_keepalive(fn, state)   ← HAS finally ✓
                 └─ _broadcast_ws() × 15-20 per run      ← tasks never cancelled
```

**Root causes:**
1. `run_stream_cached()` (`streaming.py:881`) iterates `run_stream()` with a bare `async for` — no `try/finally` means `run_stream()` is never `aclose()`d on disconnect.
2. `_broadcast_ws()` (`sse_utils.py`) spawns `asyncio.create_task()` tasks that are not tracked per-run and never cancelled when the run ends early.
3. The phase loop in `run_stream()` never checks `request.is_disconnected()`, so it continues executing phases even after the client is gone.

### Fix

**Step 1 — Propagate `Request` through the call chain.**

`/api/run` already has the `Request` object. Pass it as a parameter:

```python
# api/__init__.py
return StreamingResponse(
    _run_stream_with_metrics(req, request, user, ...),   # add `request`
    ...
)

async def _run_stream_with_metrics(req, request: Request, user, ...):
    async for chunk in run_stream_cached(req, request=request, ...):
        yield chunk
```

```python
# streaming.py
async def run_stream_cached(req, ..., request: Request | None = None):
    ...
    async for chunk in run_stream(req, ..., request=request):
        ...

async def run_stream(req, ..., request: Request | None = None):
    ...
```

**Step 2 — Wrap `run_stream_cached()`'s iteration in `try/finally` + explicit `aclose()`.**

```python
async def run_stream_cached(req, ..., request: Request | None = None):
    key = _cache_key(req)
    # ... cache hit path unchanged ...

    collected: list[dict] = []
    gen = run_stream(req, ...)               # get generator object
    try:
        async for chunk in gen:
            yield chunk
            # ... collect for cache ...
    finally:
        await gen.aclose()                   # always close inner generator
```

`aclose()` propagates `GeneratorExit` into `run_stream()`, triggering its existing `finally`
block that calls `await _run_store.remove(run_id)`.

**Step 3 — Track and cancel per-run WS broadcast tasks.**

Inside `run_stream()`, replace the direct `await _broadcast_ws(...)` calls with a tracked version:

```python
# run_stream() preamble
_run_tasks: set[asyncio.Task] = set()

def _tracked_broadcast(run_id: str, payload: dict) -> None:
    task = asyncio.create_task(_broadcast_ws(run_id, payload))
    _run_tasks.add(task)
    task.add_done_callback(_run_tasks.discard)
```

In the existing `finally` block:

```python
finally:
    # Cancel all pending broadcast tasks for this run
    for t in list(_run_tasks):
        if not t.done():
            t.cancel()
    if _run_tasks:
        await asyncio.gather(*_run_tasks, return_exceptions=True)
    await _run_store.remove(run_id)
```

**Step 4 — Add `request.is_disconnected()` poll in the phase loop.**

The phase loop in `run_stream()` iterates phases sequentially. Between phases, poll:

```python
for num, name, fn, serializer in phases:
    # Disconnect check — bail before starting next phase
    if request is not None and await request.is_disconnected():
        logger.info("Client disconnected before phase %s (run %s)", name, run_id)
        yield _event({"type": "cancelled", "run_id": run_id,
                      "reason": "client_disconnected"})
        return

    if cancel_event.is_set():
        ...
```

`request.is_disconnected()` is an async method in Starlette that checks the underlying ASGI
receive channel — it is safe to call between phases without blocking.

### Files Changed

| File | Change |
|------|--------|
| `src/reasoner/api/__init__.py` | Pass `request` to `_run_stream_with_metrics` |
| `src/reasoner/api/streaming.py` | `run_stream_cached()` try/finally + aclose(); `run_stream()` accepts `request`, adds `_run_tasks` set and cancels in finally; phase loop disconnect check |
| `src/reasoner/api/sse_utils.py` | No change needed (task already has done_callback from B-20b fix) |

### Verification

```bash
# Unit: mock request.is_disconnected() returning True after 2 events
pytest tests/unit/test_sse_disconnect.py -v

# Integration: start server, begin stream, kill connection, verify no orphan tasks
# Check: asyncio.all_tasks() count drops back to baseline after disconnect
```

---

## B-17 — Circuit Breaker In-Memory Only (No Cross-Worker State)

### Problem

`CIRCUIT_BREAKER_MODE` defaults to `"redis"` in `settings.py` but **no Redis backend exists**.
Each Uvicorn worker maintains its own `_circuit_breakers` dict (`circuit_breaker.py:312`), so:
- Worker A opens the circuit for `openai/gpt-4o` after 5 failures
- Workers B and C never learn about it — they keep sending requests to the failing provider
- On restart, all circuits reset to CLOSED regardless of real provider health

### Architecture Alignment

Follow the **rate limiter pattern** exactly:
- `RATE_LIMITER_MODE=redis` → loads a Lua script, executes atomically via Redis
- `CIRCUIT_BREAKER_MODE=redis` → same pattern, same directory

The `api/__init__.py:107-113` already logs a warning when mode is `memory` with multiple
workers. The Redis backend fulfils what the code already expects.

### Redis State Schema

Store per-circuit-breaker state as a Redis Hash (all fields in one HSET):

```
Key:  cb:{name}
TTL:  7 days (auto-expire stale circuits; active circuits are refreshed on every call)

Fields:
  state                  "CLOSED" | "OPEN" | "HALF_OPEN"
  consecutive_failures   int
  consecutive_successes  int
  half_open_calls        int    (concurrent calls currently in HALF_OPEN)
  last_state_change_ms   int    (wall-clock Unix ms — not monotonic, safe across workers)
```

Monitoring-only counters (`total_calls`, `failed_calls`, etc.) are kept in-memory only —
they are per-worker stats, not shared state.

### Lua Script

Create `src/reasoner/infrastructure/redis/scripts/circuit_breaker.lua` implementing three
atomic operations selected by `ARGV[1]`:

**`can_execute`** — check if a call slot is available:
```lua
if state == "OPEN" then
    if (current_ms - last_state_change_ms) >= timeout_ms then
        -- transition OPEN → HALF_OPEN, reset counters, allow this call
        HSET key state "HALF_OPEN" consecutive_successes 0 half_open_calls 1 last_state_change_ms current_ms
        return {1, "HALF_OPEN"}
    end
    return {0, "OPEN"}
elseif state == "HALF_OPEN" then
    if half_open_calls >= max_half_open_calls then
        return {0, "HALF_OPEN_FULL"}
    end
    HINCRBY key half_open_calls 1
    return {1, "HALF_OPEN"}
else  -- CLOSED
    return {1, "CLOSED"}
end
```

**`record_success`** — after a successful call:
```lua
if state == "HALF_OPEN" then
    HINCRBY key consecutive_successes 1
    HINCRBY key half_open_calls -1
    if consecutive_successes >= success_threshold then
        HSET key state "CLOSED" consecutive_failures 0 consecutive_successes 0
    end
elseif state == "CLOSED" then
    HSET key consecutive_failures 0   -- reset streak on success
end
```

**`record_failure`** — after a failed call:
```lua
if state == "HALF_OPEN" then
    -- Any failure in HALF_OPEN immediately reopens
    HSET key state "OPEN" consecutive_failures 0 consecutive_successes 0 last_state_change_ms current_ms
    HINCRBY key half_open_calls -1
elseif state == "CLOSED" then
    HINCRBY key consecutive_failures 1
    if consecutive_failures >= failure_threshold then
        HSET key state "OPEN" last_state_change_ms current_ms
    end
end
```

All three operations must also refresh the key TTL: `EXPIRE key 604800`.

### Factory / Backend Pattern

Add a `RedisCircuitBreaker` class that implements the same `can_execute()` / `record_success()`
/ `record_failure()` async interface but delegates to the Lua script:

```python
# src/reasoner/infrastructure/circuit_breaker.py  (new section)

class RedisCircuitBreaker:
    """Circuit breaker with Redis-backed shared state."""

    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self._script: aioredis.client.Script | None = None
        # Per-worker monitoring counters only (not shared)
        self._stats = CircuitBreakerStats()

    async def _get_script(self):
        if self._script is None:
            redis = get_redis()
            script_path = Path(__file__).parent / "redis" / "scripts" / "circuit_breaker.lua"
            self._script = redis.register_script(script_path.read_text())
        return self._script

    async def can_execute(self) -> bool:
        try:
            script = await self._get_script()
            result = await script(
                keys=[f"cb:{self.name}"],
                args=["can_execute", int(time.time() * 1000),
                      int(self.config.timeout_seconds * 1000),
                      self.config.max_half_open_calls],
            )
            return bool(result[0])
        except Exception:
            logger.warning("Redis circuit breaker unavailable for %s — allowing call", self.name)
            return True   # fail-open: never block on Redis failure

    async def record_success(self) -> None: ...
    async def record_failure(self) -> None: ...
```

Update `get_circuit_breaker()` to check `settings.CIRCUIT_BREAKER_MODE`:

```python
def get_circuit_breaker(name: str) -> CircuitBreaker | RedisCircuitBreaker:
    mode = settings.CIRCUIT_BREAKER_MODE.lower()
    if mode == "redis":
        return _get_redis_circuit_breaker(name)
    return _get_memory_circuit_breaker(name)
```

Two separate registries: `_circuit_breakers` (existing, memory) and
`_redis_circuit_breakers` (new dict, also with threading.Lock + size limit).

**Graceful degradation:** If Redis is unreachable, `can_execute()` returns `True` (fail-open)
and logs a warning — never let Redis failure block LLM calls.

### Files Changed

| File | Change |
|------|--------|
| `src/reasoner/infrastructure/redis/scripts/circuit_breaker.lua` | New Lua script (3 operations) |
| `src/reasoner/infrastructure/circuit_breaker.py` | Add `RedisCircuitBreaker` class; update `get_circuit_breaker()` factory |
| `src/reasoner/core/settings.py` | No change — `CIRCUIT_BREAKER_MODE` already exists |

### Verification

```bash
# Unit: mock Redis, test all 6 state transitions atomically
pytest tests/unit/test_redis_circuit_breaker.py -v

# Integration: spin two processes sharing one Redis, trip circuit in one,
#              verify other worker sees it as OPEN within 1 state-check cycle
pytest tests/integration/test_circuit_breaker_multiworker.py -v -m integration
```

---

## B-18 — Token Cache: No Background Eviction (Memory Leak)

### Problem

`TokenAwareCache` uses **lazy TTL deletion** (expired entries removed only on access) plus
**write-time LRU eviction** (triggered when `max_entries` or `max_tokens` would be exceeded).

This leaves two classes of leak:
1. **In-memory:** Entries that expire but are never accessed again stay in `self._entries`
   until a write forces LRU eviction — potentially indefinitely.
2. **On-disk:** JSON files in `cache/tokens/` are only cleaned up on startup
   (`_load_from_disk()`) and on entry access — not between restarts or for entries that fall
   below `max_entries` but are still expired.

At 1,000 max entries × 50 KB average = 50 MB peak; without proactive cleanup, memory grows
until a write triggers eviction. Under read-heavy workloads this never happens.

### Fix

**Step 1 — Add `_cleanup_expired()` method to `TokenAwareCache`.**

```python
async def _cleanup_expired(self) -> int:
    """Evict all TTL-expired entries from memory and disk. Returns count removed."""
    now = time.time()
    expired = [
        key for key, entry in self._entries.items()
        if now - entry.created_at > entry.ttl_seconds
    ]
    for key in expired:
        await self._evict(key)
    return len(expired)
```

`_evict()` already exists and handles both memory removal and disk file deletion — no new
deletion logic needed.

**Step 2 — Add a background cleanup loop inside `TokenAwareCache`.**

```python
async def start_background_cleanup(self, interval_seconds: int = 300) -> asyncio.Task:
    """Start a background task that periodically evicts expired entries.

    Returns the Task so the caller can cancel it on shutdown.
    """
    async def _loop():
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                async with self._lock:
                    removed = await self._cleanup_expired()
                if removed:
                    logger.debug("Token cache: evicted %d expired entries", removed)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Token cache cleanup error: %s", exc)

    return asyncio.create_task(_loop(), name="token_cache_cleanup")
```

The `asyncio.sleep` is inside the loop so cancellation is always possible. The lock
(`self._lock`, which is an `asyncio.Lock` already used by `set()` and `_evict()`) prevents
concurrent access during cleanup.

**Step 3 — Register the cleanup task in the FastAPI lifespan.**

`api/__init__.py` already has a lifespan context manager with a background task pattern:

```python
# api/__init__.py — inside @asynccontextmanager async def lifespan(app):
# Existing pattern (active users loop):
_active_users_task = asyncio.create_task(_update_active_users_loop())

# ADD: token cache cleanup
from reasoner.infrastructure.token_cache import get_token_cache
_token_cache = get_token_cache()
_cache_cleanup_task = await _token_cache.start_background_cleanup(interval_seconds=300)

yield  # app running

# Shutdown — cancel in reverse order:
_cache_cleanup_task.cancel()
try:
    await _cache_cleanup_task
except asyncio.CancelledError:
    pass

_active_users_task.cancel()
...
```

The cleanup interval of 300 seconds (5 minutes) is a safe default — short enough to
prevent significant accumulation, long enough to not add CPU overhead.

**Step 4 — Fix the missing `logger` in `_save_to_disk()`.**

```python
# token_cache.py line ~361 — existing:
except (IOError, OSError) as exc:
    logger.warning("Failed to persist cache entry %s to disk: %s", key, exc)
```

Verify that `logger = logging.getLogger(__name__)` is at module level. If absent, add it.
(The exploration report flagged this — verify during implementation.)

### Files Changed

| File | Change |
|------|--------|
| `src/reasoner/infrastructure/token_cache.py` | Add `_cleanup_expired()` and `start_background_cleanup()` methods; verify logger defined |
| `src/reasoner/api/__init__.py` | Start cleanup task in lifespan startup; cancel in lifespan shutdown |

### Verification

```bash
# Unit: populate cache with entries having 1s TTL, sleep 2s,
#       verify cleanup removes them without a get() call
pytest tests/unit/test_token_cache_raw_prompt.py tests/unit/test_token_cache_eviction.py -v

# Manual: watch memory with tracemalloc after 1000 inserts + no reads
```

---

## Implementation Order

| Priority | Bug | Why first |
|----------|-----|-----------|
| 1 | **B-18** | Smallest scope; self-contained; fixes real memory leak with no risk |
| 2 | **B-13** | High user-facing impact (orphaned LLM calls = wasted API spend); medium scope |
| 3 | **B-17** | Largest scope (Lua script + new class); only matters in multi-worker deploy |

## Dependency Notes

- B-13 requires reading `Request` from FastAPI — no external deps.
- B-17 requires a new Lua script and a new Redis key namespace — no conflict with existing
  `rate_limit:*` or `stripe_webhook:*` keys. Use `cb:` prefix.
- B-18 requires the lifespan context manager to exist — it already does. The cleanup task
  must be cancelled before Redis is closed (if Redis-backed cache ever added).
- All three are independent and can be implemented in parallel by different developers.
