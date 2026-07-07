# FIX-1: Consolidate Phase-Execution Paths — Implementation Plan

**Status:** 📋 Planned  
**Severity:** P2  
**Effort:** Medium (~4 files, ~250 lines changed)  

---

## 1. Discovery Summary

The audit reported "two parallel phase-execution paths." Investigation found the actual situation is different:

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| `WorkflowRunner.run_phase()` | `application/flows/runner.py` | ~145 | ✅ Active — used by all WorkflowStrategy flows |
| `PhaseLifecycleManager.execute_phase()` | `application/flows/phase_lifecycle.py` | ~190 | ❌ **Dead code** — never imported or called anywhere |
| SSE inline phase loop | `api/execution/pipeline.py` | ~280-520 | ✅ Active — handles SSE-specific concerns (keepalive, cancellation, event emission) |
| `run_phase_with_keepalive()` | `api/phase_executor.py` | ~90 | ✅ Active — only handles timeout + keepalive, not retry/quality |

### Root cause

`PhaseLifecycleManager` was extracted from `api/streaming.py` as a refactoring exercise, but the streaming pipeline execution in `api/execution/pipeline.py` **was never updated to use it**. The pipeline.py file kept its own inline phase loop with duplicated retry, quality, error handling, and event logic. `PhaseLifecycleManager` became dead code the moment it was extracted.

---

## 2. Target Architecture

```
                    ┌──────────────────────────────────┐
                    │     PhaseExecutor (NEW)           │
                    │  flows/phase_executor.py          │
                    │                                   │
                    │  execute() → PhaseRunResult       │
                    │  - retry loop                     │
                    │  - quality check (PhaseMonitor)   │
                    │  - timeout via run_with_timeout() │
                    │  - event publishing (EventBus)    │
                    │  - error classification           │
                    └──────────┬───────────────────────┘
                               │
            ┌──────────────────┼──────────────────┐
            │                  │                  │
    ┌───────▼──────┐  ┌───────▼───────┐  ┌───────▼──────────┐
    │ WorkflowRunner│  │ pipeline.py   │  │ run_phase_       │
    │ (CLI path)    │  │ (SSE path)    │  │ with_keepalive() │
    │               │  │               │  │ (timeout util)   │
    │ calls executed│  │ calls executed│  │                  │
    │ synchronously │  │ via async for │  │ SSE keepalive    │
    └───────────────┘  └───────────────┘  └──────────────────┘
```

### Design principles

1. **`PhaseExecutor` owns retry + quality + events** — the invariant logic that must be identical across both paths.
2. **`run_phase_with_keepalive()` stays in `api/phase_executor.py`** — it's an SSE protocol concern (keepalive comments), not a phase execution concern. The SSE path composes `PhaseExecutor` with `run_phase_with_keepalive`.
3. **`PhaseLifecycleManager` is deleted** — dead code.
4. **The `api/execution/pipeline.py` inline loop** is refactored to use `PhaseExecutor` — removing ~170 lines of duplicated retry/quality/event logic.

---

## 3. Step-by-Step Plan

### Step 1: Create `application/flows/phase_executor.py`

Extract the shared retry + quality + event logic into a single class.

```python
@dataclass
class PhaseRunResult:
    success: bool
    fatal: bool
    phase_name: str
    duration: float = 0.0
    error: str | None = None
    quality_score: float | None = None
    retries_used: int = 0
    events: list[Any] = field(default_factory=list)

class PhaseExecutor:
    def __init__(self, monitor: PhaseMonitor, bus, run_id: str = ""):
        ...

    async def execute(
        self,
        state: PipelineState,
        name: str,
        fn: Callable,
        *,
        critical: bool = False,
        timeout_seconds: float = 120.0,
        timeout_fn: Callable | None = None,  # SSE: run_phase_with_keepalive
    ) -> PhaseRunResult:
        """Shared phase execution: retry, quality, timeout, events."""
```

Key design:
- `timeout_fn` is optional — when provided (SSE path), `PhaseExecutor` calls `timeout_fn(fn, state)` instead of `asyncio.wait_for(fn(state), timeout)`. This lets the SSE path inject keepalive comments.
- `run_id` is used as the `aggregate_id` for events — defaults to empty string for CLI path.
- The retry loop, quality check, error classification, and event publishing are identical to the current `WorkflowRunner.run_phase()` logic.

**Acceptance:** `PhaseExecutor` passes all existing `test_e2e_budget_presets_mock.py` tests when used via WorkflowRunner.

### Step 2: Refactor `WorkflowRunner.run_phase()` to use `PhaseExecutor`

```python
# Before: ~145 lines of inline retry/quality/event logic
# After: delegates to PhaseExecutor

async def run_phase(self, step: PhaseStep, state: PipelineState, **kwargs) -> bool:
    result = await self._executor.execute(
        state, step.name, step.fn,
        critical=step.critical,
        timeout_seconds=get_phase_timeout(step.name),
    )
    if result.fatal:
        return False
    return result.success or not step.critical
```

`WorkflowRunner` becomes a thin adapter — keeps the method signature that flow strategies expect, delegates all execution logic to `PhaseExecutor`.

**Acceptance:** All `WorkflowRunner`-based tests pass unchanged.

### Step 3: Refactor `api/execution/pipeline.py` inline loop

Remove the inline retry/quality/event block (~170 lines at lines 280-450) and replace with `PhaseExecutor`:

```python
# Before: inline retry loop with quality, error handling, event emission
executor = PhaseExecutor(phase_monitor, event_bus, run_id=run_id)

for num, name, fn, serializer in phases:
    result = await executor.execute(
        state, name, fn,
        critical=name in critical_phases,
        timeout_seconds=get_phase_timeout(name),
        timeout_fn=lambda fn, s: run_phase_with_keepalive(fn, s, cancel_event, ...)
    )
    # SSE-specific: emit phase_start, phase_complete, phase_error events
    # based on result (already handled by executor's events, just format for SSE)
```

The `timeout_fn` parameter lets `PhaseExecutor` use SSE keepalive instead of `asyncio.wait_for`.

**Acceptance:** SSE pipeline produces identical SSE event stream for the same input.

### Step 4: Delete `application/flows/phase_lifecycle.py`

The file is dead code — never imported or called. `PhaseLifecycleManager` and its `PhaseRunResult` dataclass are superseded by the new `PhaseExecutor`.

**Acceptance:** No imports break. `grep -r "phase_lifecycle" src/` returns zero results.

### Step 5: Verify

```bash
# Unit: PhaseExecutor in isolation
pytest tests/test_phase_executor.py -v

# Integration: all flow strategies still work
pytest tests/test_e2e_budget_presets_mock.py -v

# Streaming: SSE events unchanged
pytest tests/integration/test_preset_pipeline.py -v -k "budget"

# No dead imports
grep -r "phase_lifecycle" src/
# Expected: no matches

# Regression: existing tests
pytest tests/test_augmented_article.py tests/test_augmentation_metrics.py -v
```

---

## 4. Risk Matrix

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `PhaseExecutor` breaks retry behavior | Medium | Extract logic verbatim from `WorkflowRunner.run_phase()` — don't rewrite, just move |
| SSE events change shape | Medium | Compare SSE event stream before/after with same input; use snapshot test |
| `timeout_fn` abstraction is wrong | Low | Keep it simple — just a callable; if undefined, use `asyncio.wait_for` |
| `WorkflowRunner` backwards compat | Low | Keep the same public API (`run_phase(step, state) -> bool`); internal delegation only |

---

## 5. Files Summary

| File | Action | Lines |
|------|--------|-------|
| `application/flows/phase_executor.py` | **NEW** — shared PhaseExecutor class | ~130 |
| `application/flows/runner.py` | Refactor — delegate to PhaseExecutor | -100 / +20 |
| `api/execution/pipeline.py` | Refactor — replace inline loop with PhaseExecutor | -170 / +30 |
| `application/flows/phase_lifecycle.py` | **DELETE** — dead code | -190 |
| `tests/test_phase_executor.py` | **NEW** — 6 tests | ~80 |

---

## 6. Completion Checklist

- [ ] Step 1: `phase_executor.py` created with `PhaseExecutor` + `PhaseRunResult`
- [ ] Step 2: `WorkflowRunner.run_phase()` delegates to `PhaseExecutor`
- [ ] Step 3: `api/execution/pipeline.py` inline loop replaced
- [ ] Step 4: `phase_lifecycle.py` deleted
- [ ] Step 5: All tests pass (existing + new)
- [ ] `grep -r "phase_lifecycle" src/` returns zero matches
- [ ] SSE event stream identical for same input
