# Plan: Strategy A — Step 5 (RunStateStore) + Full Test Suite

## Context Summary

From the Architectural Reaper V5 audit and Strategy A Execution Summary:
- Steps 1-4 are complete (bus.py, circular import check, TOCTOU fix, EventStore concurrency)
- **Step 5 is pending**: Create a `RunStateStore` wrapper around `_run_cancel_events`
- **Tests are missing**: No tests cover the cancellation fix, EventStore threading, or bus isolation

Current code state (from exploration):
- `_run_cancel_events: dict[str, asyncio.Event]` and `_run_events_lock: asyncio.Lock` exist at module level in `api/__init__.py` (lines 183-188)
- **The lock is declared but NEVER used** — dict mutations are unprotected
- Cancel events are created in `run_stream()`, checked in the phase loop, set by `stop_pipeline()`, cleaned up in `finally`
- `event_store.py` already has `threading.Lock` + `ThreadPoolExecutor` (Strategy A Step 4)
- `bus.py` has `init_default_subscribers()` and `reset_event_bus()` but no test coverage
- Test infrastructure: pytest + pytest-asyncio, flat `tests/` directory, `conftest.py` with fixtures

---

## Part 1: Implement Step 5 — RunStateStore Wrapper

### Goal
Encapsulate all per-run state (cancel events, active run tracking) into a single class with proper async locking, making future refactors safe and the code testable.

### Approach: Extract + Wrap + Replace

#### 1.1 Create `RunStateStore` class in `src/reasoner/api/__init__.py`

Location: After the module-level globals (around line 189), before route handlers.

```python
class RunStateStore:
    """
    Thread-safe / asyncio-safe store for per-run cancellation state.

    Encapsulates the _run_cancel_events dict and _active_runs set,
    using an asyncio.Lock for async-context safety.
    """

    def __init__(self) -> None:
        self._cancel_events: dict[str, asyncio.Event] = {}
        self._active_runs: set[str] = set()
        self._lock = asyncio.Lock()

    async def add(self, run_id: str) -> asyncio.Event:
        """Register a new run and return its cancel event."""
        async with self._lock:
            event = asyncio.Event()
            self._cancel_events[run_id] = event
            self._active_runs.add(run_id)
            return event

    async def remove(self, run_id: str) -> None:
        """Clean up a run's state. Safe to call multiple times."""
        async with self._lock:
            self._active_runs.discard(run_id)
            self._cancel_events.pop(run_id, None)

    async def get_cancel_event(self, run_id: str) -> asyncio.Event | None:
        """Get the cancel event for a run, or None if not found."""
        async with self._lock:
            return self._cancel_events.get(run_id)

    async def request_cancel(self, run_id: str) -> bool:
        """
        Signal cancellation for a run.
        Returns True if the run was found and cancelled, False otherwise.
        """
        async with self._lock:
            event = self._cancel_events.get(run_id)
            if event is not None:
                event.set()
                return True
            return False

    async def request_cancel_all(self) -> list[str]:
        """
        Signal cancellation for all active runs.
        Returns the list of run_ids that were cancelled.
        """
        async with self._lock:
            targets = list(self._active_runs)
            for rid in targets:
                event = self._cancel_events.get(rid)
                if event is not None:
                    event.set()
            return targets

    def is_active(self, run_id: str) -> bool:
        """Check if a run is currently active (non-locking, best-effort)."""
        return run_id in self._active_runs

    @property
    def active_runs(self) -> set[str]:
        """Return a snapshot of active run IDs."""
        return set(self._active_runs)
```

#### 1.2 Replace module-level globals with `RunStateStore` instance

**Before:**
```python
_run_cancel_events: dict[str, asyncio.Event] = {}
_run_events_lock = asyncio.Lock()
_active_runs: set[str] = set()
```

**After:**
```python
_run_store = RunStateStore()
```

#### 1.3 Update all call sites in `api/__init__.py`

| Location | Current Code | New Code |
|----------|-------------|----------|
| `run_stream()` start (line ~535) | `cancel_event = asyncio.Event(); _run_cancel_events[run_id] = cancel_event; _active_runs.add(run_id)` | `cancel_event = await _run_store.add(run_id)` |
| `run_stream()` finally (line ~856) | `_active_runs.discard(run_id); _run_cancel_events.pop(run_id, None)` | `await _run_store.remove(run_id)` |
| `stop_pipeline()` (line ~1134) | `_run_cancel_events[rid].set()` | `await _run_store.request_cancel(rid)` or `request_cancel_all()` |
| `stop_pipeline()` targets | `targets = [run_id] if run_id in _active_runs else []` / `list(_active_runs)` | `targets = [run_id] if _run_store.is_active(run_id) else []` / `_run_store.active_runs` |
| Phase loop check (line ~731) | `cancel_event.is_set()` | Already has `cancel_event` local — no change needed |
| `_stream_direct_answer()` | `cancel_event.is_set()` | No change (receives event object) |
| `_stream_web_search_results()` | `cancel_event.is_set()` | No change (receives event object) |

#### 1.4 Keep helper signatures unchanged

`_stream_direct_answer()` and `_stream_web_search_results()` already receive `cancel_event` as a parameter — this stays the same. Only the *creation* and *cleanup* of events moves into `RunStateStore`.

#### 1.5 Add `reset()` method for testing

```python
    async def reset(self) -> None:
        """Clear all state (for test isolation)."""
        async with self._lock:
            for event in self._cancel_events.values():
                event.set()
            self._cancel_events.clear()
            self._active_runs.clear()
```

---

## Part 2: Write Tests for Strategy A

### Test Strategy Overview

| Category | Tests | Target | Markers |
|----------|-------|--------|---------|
| **Unit** | 5 tests | RunStateStore, Bus isolation | — |
| **Integration** | 3 tests | EventStore concurrency, cancellation | `integration` |
| **Contract** | 1 test | End-to-end cancellation under load | `slow` |

### 2.1 Test File: `tests/test_run_state_store.py` (NEW)

**Purpose:** Unit-test the `RunStateStore` class in isolation.

```python
import asyncio
import pytest

# RunStateStore will be imported from api/__init__.py
# To avoid importing the entire FastAPI app, we may need to extract it to
# a separate module (e.g., src/reasoner/api/run_state.py) OR import selectively.
```

**Decision:** To avoid importing the entire 2000-line `api/__init__.py` in tests, **extract `RunStateStore` to its own module** `src/reasoner/api/run_state.py` and import it from both `api/__init__.py` and tests.

**Tests:**

1. **`test_add_creates_event_and_marks_active`**
   - Call `await store.add("run-1")`
   - Assert return value is an `asyncio.Event`
   - Assert `store.is_active("run-1")` is True
   - Assert `"run-1" in store.active_runs`

2. **`test_remove_cleans_up_state`**
   - Add a run, then `await store.remove("run-1")`
   - Assert `store.is_active("run-1")` is False
   - Assert `await store.get_cancel_event("run-1")` is None

3. **`test_request_cancel_sets_event`**
   - Add a run, get its event
   - `await store.request_cancel("run-1")` → returns True
   - Assert `event.is_set()` is True

4. **`test_request_cancel_returns_false_for_missing_run`**
   - `await store.request_cancel("missing")` → returns False

5. **`test_request_cancel_all_cancels_all_active`**
   - Add 3 runs
   - `await store.request_cancel_all()` → returns list of 3 IDs
   - Assert all 3 events are set

6. **`test_isolation_between_runs`**
   - Add 2 runs
   - Cancel run-1
   - Assert run-1 event is set, run-2 event is NOT set

7. **`test_reset_clears_all_state`**
   - Add 3 runs
   - `await store.reset()`
   - Assert all events are set (so any waiters unblock)
   - Assert `active_runs` is empty

8. **`test_concurrent_add_remove_no_race`**
   - Launch 50 concurrent `add()` calls
   - Launch 50 concurrent `remove()` calls for the same IDs
   - Assert final state is consistent (no leaked events, no crashes)

### 2.2 Test File: `tests/test_event_bus_isolation.py` (NEW)

**Purpose:** Verify `init_default_subscribers()` only runs on startup and `reset_event_bus()` works.

**Tests:**

1. **`test_subscribers_not_registered_at_import`**
   - Import a fresh module context (or use `importlib.reload`)
   - Assert subscriber list is empty after import
   - Call `init_default_subscribers()`
   - Assert subscribers are now registered

2. **`test_reset_event_bus_clears_handlers`**
   - Call `init_default_subscribers()`
   - Call `reset_event_bus()`
   - Assert bus is None or has zero handlers

3. **`test_duplicate_init_is_idempotent`**
   - Call `init_default_subscribers()` twice
   - Assert handlers are not duplicated

4. **`test_event_published_after_init`**
   - Call `init_default_subscribers()`
   - Publish a `PipelineStarted` event
   - Assert at least one handler received it (if global handler exists)

### 2.3 Test File: `tests/test_event_store_concurrency.py` (NEW)

**Purpose:** Verify `EventStore` is safe under concurrent writes.

**Tests:**

1. **`test_concurrent_event_appends_no_corruption`** (`integration`)
   - Create an `EventStore` with a temp DB
   - Launch 10 async tasks, each appending 100 events
   - Wait for completion
   - Read back all events
   - Assert count == 1000 and no duplicates / corruption

2. **`test_concurrent_snapshot_writes`** (`integration`)
   - Create an `EventStore` with a temp DB
   - Launch 5 tasks writing snapshots for the same aggregate
   - Assert final snapshot is valid JSON and one of the written versions

3. **`test_delete_aggregate_during_concurrent_writes`** (`integration`)
   - Start background task appending events
   - Midway, call `delete_aggregate()`
   - Assert no exceptions raised
   - Assert aggregate is deleted

4. **`test_executor_shutdown_releases_resources`**
   - Create store, append an event, call `close()`
   - Assert executor is shut down
   - Assert subsequent append raises (or creates new executor)

### 2.4 Test File: `tests/test_cancellation_contract.py` (NEW)

**Purpose:** End-to-end contract test for the cancellation mechanism.

**Tests:**

1. **`test_cancel_stops_active_run`** (`slow`)
   - Start a background coroutine that simulates a long pipeline run
   - After 0.1s, call `stop_pipeline(run_id)`
   - Assert the pipeline coroutine exits within 1s with `cancelled` event

2. **`test_concurrent_cancellations_no_lost_signals`** (`slow`, `integration`)
   - Start 20 concurrent "pipeline" coroutines
   - Cancel all 20 simultaneously
   - Assert all 20 exit with `cancelled` event
   - Assert no orphaned tasks remain

3. **`test_cancel_one_run_does_not_affect_other`**
   - Start 2 pipeline coroutines
   - Cancel only run-1
   - Assert run-1 exits with cancelled
   - Assert run-2 continues (does not exit early)

### 2.5 Update Existing Test: `tests/test_event_bus.py`

**Purpose:** Ensure existing event bus tests still pass after the import-time fix.

- Add a test that verifies `reset_event_bus()` is called in setup/teardown
- Add a test that verifies `get_event_bus()` returns a fresh instance after reset

---

## Part 3: Extraction Decision — `RunStateStore` Module

### Problem
`api/__init__.py` is 2009 lines. Importing it in unit tests triggers:
- FastAPI app initialization
- Route decorator execution
- All module-level imports (pipeline, renderer, presets, etc.)

### Solution
Extract `RunStateStore` to a dedicated module:

```
src/reasoner/api/
  __init__.py          (imports RunStateStore from run_state)
  run_state.py         (NEW — contains RunStateStore class only)
```

**Benefits:**
- Unit tests import only `run_state.py` (no FastAPI bloat)
- The class can be reused in other interfaces (CLI, gRPC) without dragging in HTTP
- Follows the audit's recommendation to decouple layers

**Refactor steps:**
1. Create `src/reasoner/api/run_state.py`
2. Move `RunStateStore` class there
3. Update `api/__init__.py` to import it: `from .run_state import RunStateStore`
4. Update test imports: `from reasoner.api.run_state import RunStateStore`

---

## Part 4: Implementation Order

| Step | Task | Files | Effort |
|------|------|-------|--------|
| 1 | Create `src/reasoner/api/run_state.py` with `RunStateStore` | NEW | 30 min |
| 2 | Update `api/__init__.py`: replace globals with `_run_store`, update all call sites | `api/__init__.py` | 45 min |
| 3 | Verify app still starts, no syntax errors | — | 15 min |
| 4 | Write `test_run_state_store.py` (8 tests) | NEW | 60 min |
| 5 | Write `test_event_bus_isolation.py` (4 tests) | NEW | 45 min |
| 6 | Write `test_event_store_concurrency.py` (4 tests) | NEW | 60 min |
| 7 | Write `test_cancellation_contract.py` (3 tests) | NEW | 60 min |
| 8 | Update `test_event_bus.py` with reset/isolation tests | `test_event_bus.py` | 20 min |
| 9 | Run full test suite, fix failures | — | 45 min |
| 10 | Run `ruff check` and `mypy` on modified files | — | 15 min |

**Total estimated effort:** ~7 hours (fits in a single focused session)

---

## Part 5: Validation Checklist

### Before merge
- [ ] `pytest tests/test_run_state_store.py` — 8/8 pass
- [ ] `pytest tests/test_event_bus_isolation.py` — 4/4 pass
- [ ] `pytest tests/test_event_store_concurrency.py` — 4/4 pass
- [ ] `pytest tests/test_cancellation_contract.py` — 3/3 pass
- [ ] `pytest tests/test_event_bus.py` — all pass
- [ ] `pytest tests/test_api_gate.py tests/test_api_phase_errors.py tests/test_api_memory_cache.py` — all pass
- [ ] `ruff check src/reasoner/api/run_state.py src/reasoner/api/__init__.py` — zero warnings
- [ ] `mypy src/reasoner/api/run_state.py` — clean
- [ ] Manual: start backend, trigger a run, hit /api/stop, verify cancellation

### Coverage targets
- `src/reasoner/api/run_state.py` — 100%
- `src/reasoner/api/__init__.py` cancellation paths — ≥80%
- `src/reasoner/infrastructure/persistence/event_store.py` — ≥50%
- `src/reasoner/application/event_bus/bus.py` — ≥60%

---

## Appendix: Test Fixtures Needed

Add to `tests/conftest.py`:

```python
@pytest.fixture
async def run_state_store():
    """Provide a fresh RunStateStore for each test."""
    from reasoner.api.run_state import RunStateStore
    store = RunStateStore()
    yield store
    await store.reset()

@pytest.fixture
async def temp_event_store(tmp_path):
    """Provide an EventStore backed by a temporary SQLite file."""
    from reasoner.infrastructure.persistence.event_store import EventStore
    db_path = tmp_path / "test_events.db"
    store = EventStore(db_path=str(db_path))
    yield store
    store.close()
```
