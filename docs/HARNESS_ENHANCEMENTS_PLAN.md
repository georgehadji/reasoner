# Reasoner Harness Enhancements — Implementation Plan

**Source:** Analysis of *Code as Agent Harness* (arXiv:2605.18747) against the Reasoner codebase.  
**Scope:** Five targeted enhancements that close gaps between existing infrastructure and the paper's telemetry/memory/optimization patterns.  
**Architecture:** Hexagonal DDD + CQRS + Event Sourcing. All changes respect the dependency rule: Domain ← Application ← Infrastructure ← Interfaces.

---

## Confirmed Gaps (post deep-read)

The following already exist and are **excluded** from this plan:
- Quality-gated retry: `PhaseLifecycleManager` (`application/flows/phase_lifecycle.py`)
- Cost/token tracking: `CostTrackingState` (`domain/pipeline_state.py`)
- Tiered memory: Neuro L1/L2/L3 (`neuro/`)

The five real gaps follow.

---

## Gap Inventory

| # | Gap | Affected Files | Effort | Priority |
|---|-----|---------------|--------|----------|
| E1 | Quality data not saved to Neuro postflight | `application/orchestrator.py:postflight` | ~25 LoC | **High** |
| E4 | Fallback events invisible to PipelineState | `infrastructure/llm/router.py`, `domain/pipeline_state.py` | ~50 LoC | **High** |
| E2 | No queryable per-phase telemetry table | `infrastructure/persistence/` (new file) | ~120 LoC | **Medium** |
| E3 | `smart_compress` not wired at Phase 2→3 | `application/pipeline.py` or phase service | ~20 LoC | **Medium** |
| E5 | Healing loop has no runtime telemetry connection | `healing/run_healing.py` (new helper) | ~80 LoC | **Lower** |

**Build order:** E1 → E4 → E2 → E5 (sequential, each builds on previous). E3 is independent.

---

## Enhancement E1: Quality-Rich Neuro Persistence

### Problem

`PipelineOrchestrator.postflight` (`application/orchestrator.py`, lines 206–241) calls `/api/neuro/learn` with:

```python
"metadata": {
    "preset": getattr(state, "preset_name", ""),
    "type": "pipeline",
}
```

`state.meta.quality_history`, `state.meta.phase_durations`, `state.cost_state.phase_costs`, and `state.cost_state.total_cost_usd` are never written. Each run's quality signal is permanently lost. Future Neuro recall cannot return quality-annotated context.

**Paper concept:** Experiential Memory — failure-indexed history enabling cross-run transfer (§3.2.2).

### Design

This is a pure Application-layer change. No new files, no domain model changes. The metadata dict already exists; we enrich it before the HTTP call.

`state.meta.quality_history` is `list[dict]` with entries `{phase, attempt, score, passed}`. We cap at 10 entries to keep the Neuro payload bounded. Phase durations and costs are small dicts already on the state.

Neuro metadata is schemaless JSON, so no migration is needed on the memory side.

### Files to Modify

**`src/reasoner/application/orchestrator.py`**

In `postflight`, replace the metadata literal:

```python
# Before (line ~233):
"metadata": {
    "preset": getattr(state, "preset_name", ""),
    "type": "pipeline",
},

# After:
"metadata": {
    "preset": getattr(state, "preset_name", ""),
    "type": "pipeline",
    "method": getattr(state.meta, "method", None),
    "total_cost_usd": round(state.cost_state.total_cost_usd, 6),
    "phase_costs": dict(state.cost_state.phase_costs),
    "phase_durations": {k: round(v, 2) for k, v in state.meta.phase_durations.items()},
    "quality_history": state.meta.quality_history[-10:],
    "fallback_events": getattr(state.meta, "fallback_events", []),  # populated by E4
},
```

`state.cost_state` is `CostTrackingState`. `state.meta` is `PipelineMeta`. Both are dataclass fields on `PipelineState` — no imports needed.

### Tests

- `tests/unit/test_orchestrator_postflight.py` (new or extend existing)
  - Assert the Neuro learn call receives all 5 new metadata keys when the pipeline has a non-empty `quality_history`
  - Assert no metadata keys appear when state fields are empty (graceful empty-dict/empty-list case)
  - Mock the neuro HTTP client via `unittest.mock.AsyncMock`

### Definition of Done

`postflight` passes `quality_history`, `phase_durations`, `phase_costs`, `total_cost_usd`, and `method` in the Neuro metadata payload. Tests pass. No existing tests regress.

---

## Enhancement E4: Fallback Event Surfacing

### Problem

`ProviderRouter.call` (`infrastructure/llm/router.py`, line 134) uses `is_fallback: bool = False` inside the `_execute_call` closure to differentiate fallback calls. This flag is local — it never surfaces to `PipelineState` or any telemetry sink. Fallback events are only visible in log files.

You cannot currently answer: "How many times did `multi-perspective-premium` fall back to its secondary model last week?" without parsing logs.

**Paper concept:** Deep Telemetry — structured traces connecting model decisions to outcomes (§3.3.1).

### Design

**Architectural constraint:** `ProviderRouter` lives in the Infrastructure layer. It must not import `PipelineState` (Domain layer). The Dependency Rule prohibits this direction.

**Solution — Callback injection (Observer pattern).**

1. Add a `FallbackEvent` value object to `domain/pipeline_state.py` or inline as a `TypedDict`.
2. Add `fallback_events: list[dict]` to `PipelineMeta`.
3. Add an optional `on_fallback: Callable[[str, str, str, str], None] | None` parameter to `ProviderRouter.__init__`. Signature: `(role, intended_model, actual_model, reason)`.
4. In `_execute_call` when a fallback fires, call `self.on_fallback(...)` if set.
5. In `PipelineOrchestrator.execute` (or wherever the pipeline state is bound to the router), wire a lambda that appends to `state.meta.fallback_events`.

The callback is a plain Python callable — no new abstractions, no new files needed.

### Files to Modify

**`src/reasoner/domain/pipeline_state.py`**

In `PipelineMeta` dataclass, add one field:

```python
@dataclass
class PipelineMeta:
    # ... existing fields ...
    fallback_events: list[dict] = field(default_factory=list)
```

Each entry shape: `{"role": str, "intended": str, "actual": str, "reason": str, "ts": float}`.

---

**`src/reasoner/infrastructure/llm/router.py`**

In `ProviderRouter.__init__`, add parameter:

```python
def __init__(
    self,
    primary: BaseLLMProvider,
    routing_table: dict[str, BaseLLMProvider] | None = None,
    fallback_table: dict[str, BaseLLMProvider] | None = None,
    verbose: bool = False,
    cascading_routing: dict[str, list[str]] | None = None,
    on_fallback: "Callable[[str, str, str, str], None] | None" = None,
) -> None:
    # ... existing assignments ...
    self.on_fallback = on_fallback
```

In `_execute_call` (line ~134), when a fallback fires (before the recursive call), add:

```python
if self.on_fallback:
    import time
    self.on_fallback(role, assigned.model, fallback.model, "timeout")
    # or "llm_error" depending on branch
```

Concretely: the timeout branch and the LLMError branch each call `self.on_fallback` with the correct reason string before invoking `_execute_call(fallback, is_fallback=True)`.

---

**`src/reasoner/application/orchestrator.py`**

In `execute`, after the `PipelineState` is resolved, wire the callback:

```python
async def execute(self, decision, initial_state=None, **pipeline_kwargs):
    pipeline = self.create_pipeline(decision, initial_state=initial_state, **pipeline_kwargs)
    state = initial_state or PipelineState(
        problem=decision.problem,
        preset_name=decision.effective_preset_name,
    )
    if decision.recalled_chunks:
        state.neuro_context = decision.recalled_chunks

    # Wire fallback telemetry
    import time
    def _record_fallback(role: str, intended: str, actual: str, reason: str) -> None:
        state.meta.fallback_events.append({
            "role": role, "intended": intended,
            "actual": actual, "reason": reason,
            "ts": time.time(),
        })
    decision.router.on_fallback = _record_fallback

    return await pipeline.run(decision.problem)
```

This is the Application layer orchestrating Domain state with an Infrastructure callback — fully legal under the dependency rule.

**Note on `PresetService.build_router`:** The router is constructed in `preflight`, before the state exists. Since `on_fallback` defaults to `None`, the existing build path needs no change. We set it post-construction in `execute`.

### Tests

- `tests/unit/test_provider_router_fallback.py`
  - Assert `on_fallback` is called exactly once when a primary provider raises `LLMError` and a fallback succeeds
  - Assert `on_fallback` is called with `reason="timeout"` when `asyncio.TimeoutError` fires
  - Assert `on_fallback` is NOT called when no fallback occurs
- `tests/unit/test_orchestrator_execute.py`
  - Assert `state.meta.fallback_events` has an entry after a mock router triggers `on_fallback`

### Definition of Done

`state.meta.fallback_events` is populated during pipeline execution whenever a model fallback fires. Events are included in the Neuro metadata from E1. Tests pass. Zero behavior change on happy path.

---

## Enhancement E2: Phase Telemetry Table

### Problem

`EventStore` (`infrastructure/persistence/event_store.py`) stores full `PipelineState` snapshots as opaque JSON blobs, queryable only by `aggregate_id`, `event_type`, and `timestamp`. Cross-run analytics require deserializing every snapshot.

There is no way to efficiently compute: "average Phase 3 cost for `debate-premium` over the last 100 runs" or "which preset has the highest fallback rate." The `feedback_store.py` pattern shows the team already reached for per-concern stores — this follows that precedent.

**Paper concept:** Deep Telemetry substrate — queryable structured traces enabling harness optimization (§3.3.1, §4.2).

### Design

New file: `src/reasoner/infrastructure/persistence/telemetry_store.py`.

**Architecture:**
- Lives in Infrastructure (like `event_store.py`, `feedback_store.py`)
- Uses same SQLite DB file as event store (passed as `db_path`)
- Exposes a new `phase_telemetry` table
- Port/protocol defined in `core/ports/telemetry_port.py` (following the pattern of `llm_port.py`)
- Called from `orchestrator.postflight` after E1 enrichment

**Why a separate file, not adding to `EventStore`:** `EventStore` already has one responsibility: append-only event log with aggregate reconstruction. Adding analytics tables mixes two concerns. `FeedbackStore` sets the project precedent for per-concern stores.

### Files to Create

**`src/reasoner/core/ports/telemetry_port.py`**

```python
"""Port: telemetry persistence."""
from __future__ import annotations
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class TelemetryStorePort(Protocol):
    async def save_run(
        self,
        run_id: str,
        preset: str,
        method: str | None,
        phase_results: list[dict[str, Any]],
        fallback_events: list[dict[str, Any]],
        total_cost_usd: float,
    ) -> None: ...

    async def query_by_preset(
        self, preset: str, limit: int = 100
    ) -> list[dict[str, Any]]: ...

    async def query_recent(
        self, limit: int = 100
    ) -> list[dict[str, Any]]: ...

    async def get_preset_stats(
        self, preset: str
    ) -> dict[str, Any]: ...
```

---

**`src/reasoner/infrastructure/persistence/telemetry_store.py`**

```python
"""Phase-level telemetry store — queryable per-run analytics."""
from __future__ import annotations

import json
import logging
import sqlite3
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CREATE_PHASE_TELEMETRY = """
CREATE TABLE IF NOT EXISTS phase_telemetry (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT    NOT NULL,
    preset      TEXT    NOT NULL,
    method      TEXT,
    phase       TEXT    NOT NULL,
    cost_usd    REAL    NOT NULL DEFAULT 0.0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    retries     INTEGER NOT NULL DEFAULT 0,
    quality_score REAL,
    quality_passed INTEGER,
    models      TEXT,           -- JSON array
    is_fallback INTEGER NOT NULL DEFAULT 0,
    ts          TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pt_preset  ON phase_telemetry(preset);
CREATE INDEX IF NOT EXISTS idx_pt_run     ON phase_telemetry(run_id);
CREATE INDEX IF NOT EXISTS idx_pt_ts      ON phase_telemetry(ts);
"""

_CREATE_RUN_TELEMETRY = """
CREATE TABLE IF NOT EXISTS run_telemetry (
    run_id          TEXT PRIMARY KEY,
    preset          TEXT NOT NULL,
    method          TEXT,
    total_cost_usd  REAL NOT NULL DEFAULT 0.0,
    fallback_count  INTEGER NOT NULL DEFAULT 0,
    fallback_events TEXT,       -- JSON array
    ts              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rt_preset ON run_telemetry(preset);
CREATE INDEX IF NOT EXISTS idx_rt_ts     ON run_telemetry(ts);
"""


class TelemetryStore:
    """Queryable per-phase telemetry for cross-run analytics."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path(__file__).parent / "events.db"
        self.db_path = Path(db_path)
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._executor: ThreadPoolExecutor | None = None
        self._init_db()

    def _get_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="telemetry_store"
            )
        return self._executor

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path), check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection

    async def _run_in_executor(self, func, *args) -> Any:
        loop = asyncio.get_event_loop()
        def locked():
            with self._lock:
                return func(*args)
        return await loop.run_in_executor(self._get_executor(), locked)

    def _init_db(self) -> None:
        conn = self._get_connection()
        conn.executescript(_CREATE_PHASE_TELEMETRY)
        conn.executescript(_CREATE_RUN_TELEMETRY)
        conn.commit()

    async def save_run(
        self,
        run_id: str,
        preset: str,
        method: str | None,
        phase_results: list[dict[str, Any]],
        fallback_events: list[dict[str, Any]],
        total_cost_usd: float,
    ) -> None:
        def _sync():
            conn = self._get_connection()
            try:
                # Per-phase rows
                for pr in phase_results:
                    conn.execute("""
                        INSERT INTO phase_telemetry
                        (run_id, preset, method, phase, cost_usd, duration_ms,
                         retries, quality_score, quality_passed, models, is_fallback)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        run_id, preset, method,
                        pr.get("phase_name", ""),
                        round(pr.get("cost_usd", 0.0), 6),
                        int(pr.get("duration_ms", 0)),
                        pr.get("retries_used", 0),
                        pr.get("quality_score"),
                        int(bool(pr.get("quality_passed"))) if pr.get("quality_passed") is not None else None,
                        json.dumps(pr.get("models") or []),
                        0,
                    ))
                # Fallback rows (one per event, is_fallback=1)
                for fe in fallback_events:
                    conn.execute("""
                        INSERT INTO phase_telemetry
                        (run_id, preset, method, phase, cost_usd, duration_ms,
                         retries, models, is_fallback)
                        VALUES (?, ?, ?, ?, 0, 0, 0, ?, 1)
                    """, (
                        run_id, preset, method,
                        fe.get("role", ""),
                        json.dumps([fe.get("actual", "")]),
                    ))
                # Run-level summary
                conn.execute("""
                    INSERT OR REPLACE INTO run_telemetry
                    (run_id, preset, method, total_cost_usd,
                     fallback_count, fallback_events)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    run_id, preset, method,
                    round(total_cost_usd, 6),
                    len(fallback_events),
                    json.dumps(fallback_events),
                ))
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                logger.error("TelemetryStore.save_run failed: %s", exc)
                raise

        await self._run_in_executor(_sync)

    async def query_by_preset(
        self, preset: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        def _sync():
            conn = self._get_connection()
            cursor = conn.execute("""
                SELECT * FROM run_telemetry
                WHERE preset = ?
                ORDER BY ts DESC LIMIT ?
            """, (preset, limit))
            return [dict(row) for row in cursor.fetchall()]
        return await self._run_in_executor(_sync)

    async def query_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        def _sync():
            conn = self._get_connection()
            cursor = conn.execute("""
                SELECT * FROM run_telemetry
                ORDER BY ts DESC LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
        return await self._run_in_executor(_sync)

    async def get_preset_stats(self, preset: str) -> dict[str, Any]:
        """Aggregate stats for a preset: avg cost, avg fallback rate, phase retries."""
        def _sync():
            conn = self._get_connection()
            run_cur = conn.execute("""
                SELECT
                    COUNT(*)            AS run_count,
                    AVG(total_cost_usd) AS avg_cost,
                    SUM(fallback_count) AS total_fallbacks
                FROM run_telemetry WHERE preset = ?
            """, (preset,))
            run_row = dict(run_cur.fetchone())

            phase_cur = conn.execute("""
                SELECT
                    phase,
                    AVG(cost_usd)     AS avg_cost,
                    AVG(retries)      AS avg_retries,
                    AVG(quality_score) AS avg_quality,
                    SUM(is_fallback)  AS fallback_count
                FROM phase_telemetry
                WHERE preset = ?
                GROUP BY phase
            """, (preset,))
            phases = [dict(r) for r in phase_cur.fetchall()]
            return {**run_row, "phases": phases}
        return await self._run_in_executor(_sync)

    def close(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None


_telemetry_store: TelemetryStore | None = None

def get_telemetry_store(db_path: str | Path | None = None) -> TelemetryStore:
    global _telemetry_store
    if _telemetry_store is None:
        _telemetry_store = TelemetryStore(db_path)
    return _telemetry_store

def reset_telemetry_store() -> None:
    global _telemetry_store
    if _telemetry_store:
        _telemetry_store.close()
    _telemetry_store = None
```

### Files to Modify

**`src/reasoner/application/orchestrator.py`**

Inject `TelemetryStore` as an optional constructor argument (following the existing `neuro_client` pattern):

```python
class PipelineOrchestrator:
    def __init__(
        self,
        preset_service,
        pipeline_service,
        search_service=None,
        neuro_client=None,
        telemetry_store=None,   # <-- new
    ):
        ...
        self._telemetry_store = telemetry_store
```

At the end of `postflight`, after the Neuro learn call, add:

```python
# ── Telemetry Persist ──
if self._telemetry_store and run_id:
    try:
        from reasoner.infrastructure.persistence.telemetry_store import get_telemetry_store
        store = self._telemetry_store or get_telemetry_store()
        phase_results = [
            {
                "phase_name": r.phase_name,
                "cost_usd": state.cost_state.phase_costs.get(r.phase_key, 0.0),
                "duration_ms": int(state.meta.phase_durations.get(r.phase_key, 0.0) * 1000),
                "retries_used": r.retries_used,
                "quality_score": r.quality_score,
                "quality_passed": r.quality_passed,
                "models": r.models or [],
            }
            for r in (state.meta.phase_results or [])
        ]
        await store.save_run(
            run_id=run_id,
            preset=getattr(state, "preset_name", ""),
            method=getattr(state.meta, "method", None),
            phase_results=phase_results,
            fallback_events=getattr(state.meta, "fallback_events", []),
            total_cost_usd=state.cost_state.total_cost_usd,
        )
    except Exception as exc:
        logger.debug("Telemetry persist failed: %s", exc)
```

**Note on `run_id`:** `postflight` already receives `run_id` as an optional parameter. Callers should pass the pipeline run UUID; if not available, use `state.conversation_id` as a fallback.

### Tests

- `tests/unit/test_telemetry_store.py` (new)
  - `save_run` writes correct rows to `phase_telemetry` and `run_telemetry` tables
  - `query_by_preset` returns only rows for requested preset, ordered by descending ts
  - `get_preset_stats` computes correct averages from multiple `save_run` calls
  - Fallback events appear as `is_fallback=1` rows in `phase_telemetry`
  - Store handles empty `phase_results` and empty `fallback_events` without error
  - Use `tmp_path` pytest fixture for DB isolation; call `reset_telemetry_store()` in teardown

### Definition of Done

`phase_telemetry` and `run_telemetry` tables are populated after each pipeline run. `get_preset_stats("multi-perspective-premium")` returns meaningful data after 3+ runs. Tests pass. Zero changes to EventStore.

---

## Enhancement E3: Context Compression at Phase 2→3 Handoff

### Problem

`src/reasoner/application/pipeline.py` declares:

```python
TOKEN_OPTIMIZATION = {
    "context_compression": True,  # flag exists
    ...
}
```

This flag is not acted on. Phase 3 (critique) receives full Phase 2 perspective text verbatim. On Premium presets with 4+ large perspectives, this inflates Phase 3 input tokens materially.

`smart_compress` from `neuro/compression.py` already exists and is called in `infrastructure/llm/executor.py` for code snippets. It is not called in the Phase 2→3 handoff.

**Paper concept:** Context Compaction / State Offloading — separating decision-relevant context from durable full-fidelity artifacts (§3.3.3).

### Design

**Locate the handoff point** by reading `application/pipeline.py` (the real impl) and `application/flows/` to find where `state.candidates` or `state.perspectives` are serialized into Phase 3 prompts.

Two architectural options:

**Option A — Phase prompt assembly (preferred):**  
The Phase 3 prompt module (`phases/<method>_phase3.py` or shared) concatenates candidates into the prompt string. Insert a compression step there, gated by `TOKEN_OPTIMIZATION["context_compression"]`. Compression is a pure text transformation — it belongs in the prompt assembly layer, which is already Application layer code.

**Option B — Pipeline-level middleware:**  
In `ReasonerPipeline.run()`, between Phase 2 and Phase 3, compress `state.candidates` in place. This is cleaner if candidate serialization happens in a single location.

Option A is preferred if each method has its own prompt assembly. Option B is preferred if there is a shared serialization path. **Reading `application/pipeline.py` at the start of implementation will resolve this.**

### Implementation Steps

1. Read `src/reasoner/application/pipeline.py` to identify the Phase 2→3 handoff.
2. Identify where `state.candidates` (or `state.perspectives`) are serialized into prompt text for Phase 3.
3. Import `smart_compress`:
   ```python
   from reasoner.neuro.compression import smart_compress
   ```
4. Apply at the handoff, gated by the existing flag:
   ```python
   if TOKEN_OPTIMIZATION.get("context_compression"):
       compressed_candidates = [
           {**c, "solution": smart_compress(c.get("solution", ""), level="Minimal")}
           for c in state.candidates
       ]
   else:
       compressed_candidates = state.candidates
   ```
   Pass `compressed_candidates` to Phase 3 prompt assembly, not `state.candidates` directly. Do **not** mutate `state.candidates` — preserve the originals for serialization and postflight.

5. Verify token counts drop by running a before/after comparison on a Premium preset with a long problem.

### Files to Modify

- Primary: `src/reasoner/application/pipeline.py` or `src/reasoner/phases/<relevant_file>.py` (exact file determined at implementation time)
- No new files, no domain model changes

### Tests

- `tests/unit/test_compression_gate.py`
  - With `context_compression=True`, compressed text is shorter than original for a long input
  - With `context_compression=False`, original text passes through unchanged
  - `smart_compress` raises no error on empty string input

### Definition of Done

`TOKEN_OPTIMIZATION["context_compression"]` controls actual compression at Phase 2→3. Phase 3 token counts decrease measurably on Premium presets. `state.candidates` is not mutated.

---

## Enhancement E5: Runtime-Aware Self-Healing

### Problem

`healing/run_healing.py` is a subprocess orchestrator that calls `introspection_engine.py` and `test_generation_engine.py`. These are static analysis tools with no access to runtime data. They cannot suggest: "Phase 4 stress-test is the most expensive phase for `multi-perspective-premium` — consider a cheaper model."

**Paper concept:** Evolution Agent — meta-level agent reading telemetry to propose harness revisions (§4.3).

**Prerequisite:** Enhancement E2 (TelemetryStore) must be deployed first.

### Design

New helper: `src/reasoner/healing/telemetry_exporter.py`.

This module queries `TelemetryStore` and writes a `healing_context.json` to the project root before the healing scripts run. The healing scripts remain subprocess-based and stateless — they gain runtime awareness by reading this file as an optional hint. This design avoids coupling the subprocess scripts to the async TelemetryStore.

`run_healing.py` calls the exporter synchronously before Loop 1. If the exporter fails (TelemetryStore unavailable, no runs yet), healing continues unaffected.

### Files to Create

**`src/reasoner/healing/telemetry_exporter.py`**

```python
"""Export recent telemetry to healing_context.json for static healing scripts."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
CONTEXT_PATH = Path(__file__).parent.parent.parent.parent / "healing_context.json"


async def _build_context() -> dict[str, Any]:
    from reasoner.infrastructure.persistence.telemetry_store import get_telemetry_store
    store = get_telemetry_store()
    recent = await store.query_recent(limit=200)
    if not recent:
        return {"status": "no_runs", "presets": {}}

    # Aggregate by preset
    presets: dict[str, Any] = {}
    for row in recent:
        preset = row["preset"]
        if preset not in presets:
            presets[preset] = {
                "run_count": 0, "total_cost_usd": 0.0, "total_fallbacks": 0
            }
        presets[preset]["run_count"] += 1
        presets[preset]["total_cost_usd"] += row.get("total_cost_usd", 0.0)
        presets[preset]["total_fallbacks"] += row.get("fallback_count", 0)

    # Preset-level stats for top-5 most-used
    top_presets = sorted(presets, key=lambda p: presets[p]["run_count"], reverse=True)[:5]
    stats = {}
    for preset in top_presets:
        try:
            stats[preset] = await store.get_preset_stats(preset)
        except Exception as exc:
            logger.debug("Stats failed for %s: %s", preset, exc)

    return {
        "status": "ok",
        "run_count": len(recent),
        "presets": presets,
        "preset_stats": stats,
    }


def export_healing_context() -> bool:
    """Write healing_context.json. Returns True on success."""
    try:
        context = asyncio.run(_build_context())
        CONTEXT_PATH.write_text(json.dumps(context, indent=2), encoding="utf-8")
        logger.info("Healing context written to %s (%d runs)", CONTEXT_PATH, context.get("run_count", 0))
        return True
    except Exception as exc:
        logger.warning("Healing context export failed (non-fatal): %s", exc)
        return False
```

### Files to Modify

**`src/reasoner/healing/run_healing.py`**

At the start of `main()`, before Loop 1:

```python
def main():
    logger.info("=" * 80)
    logger.info("STARTING REASONER SELF-HEALING PIPELINE")
    logger.info("=" * 80)

    # ── Export runtime telemetry context (non-fatal if unavailable) ──
    try:
        from reasoner.healing.telemetry_exporter import export_healing_context
        export_healing_context()
    except Exception as exc:
        logger.debug("Telemetry context export skipped: %s", exc)

    # 1. LOOP 1: Static Healing
    # ... existing code unchanged ...
```

**`src/reasoner/healing/introspection_engine.py`** (read-side — low-effort enhancement)

At the start of introspection analysis, optionally load the context:

```python
import json
from pathlib import Path

_CONTEXT_PATH = Path(__file__).parent.parent.parent.parent / "healing_context.json"

def _load_healing_context() -> dict:
    try:
        if _CONTEXT_PATH.exists():
            return json.loads(_CONTEXT_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

# At analysis start:
context = _load_healing_context()
if context.get("status") == "ok":
    logger.info("Healing context: %d runs, top presets: %s",
                context["run_count"],
                list(context.get("presets", {}).keys())[:3])
```

The introspection engine can use `context["preset_stats"]` to prioritize which phases to analyze more deeply. The exact integration depends on what `introspection_engine.py` does — adapt without breaking existing behavior.

### Tests

- `tests/unit/test_telemetry_exporter.py`
  - `export_healing_context()` writes a valid JSON file when TelemetryStore has data
  - Returns `False` without raising when TelemetryStore is unavailable (mock failure)
  - Written JSON contains `status`, `run_count`, `presets` keys
  - `healing_context.json` is not written when no runs exist (`status: "no_runs"`)
- Use `tmp_path` and monkeypatch `CONTEXT_PATH` for test isolation

### Definition of Done

`healing_context.json` is written before every healing loop with current runtime telemetry. If TelemetryStore is unavailable, healing continues unaffected. Tests pass.

---

## Build Order and Dependencies

```
E1 (Neuro quality persistence)     ← no dependencies — implement first
    │
E4 (Fallback event surfacing)      ← no dependencies — implement in parallel with E1
    │
    └──► E2 (Phase telemetry table) ← depends on E4 for complete fallback data
              │
              └──► E5 (Runtime healing) ← depends on E2 (TelemetryStore)

E3 (Context compression)           ← no dependencies — implement anytime
```

**Recommended sprint breakdown:**

| Sprint | Enhancements | Rationale |
|--------|-------------|-----------|
| 1 | E1 + E4 | Independent, immediate value, ~75 LoC total |
| 2 | E2 | New infra file; clean up after E4 lands |
| 3 | E3 | Independent; do it when touching pipeline |
| 4 | E5 | Depends on E2; low-risk bridge |

---

## Cross-Cutting Concerns

### Immutability

Following `coding-style.md`: never mutate `state.candidates` in E3. Always build a new list. `PipelineMeta.fallback_events` is a list that is appended to during execution — this is acceptable (same pattern as `quality_history`).

### Error Isolation

All four postflight additions (E1 enrichment, E4 wiring, E2 telemetry save, E5 context export) are wrapped in `try/except Exception`. None can crash the pipeline. Log failures at `DEBUG` level (consistent with existing `postflight` exception handling).

### Backward Compatibility

- `PipelineMeta.fallback_events` uses `field(default_factory=list)` — existing pickled/serialized states without this field will deserialize via `.get()` calls, consistent with the project invariant stated in CLAUDE.md: *"Always access via `.get()`, never direct subscript."*
- `TelemetryStore` creates new tables with `CREATE TABLE IF NOT EXISTS` — safe against existing databases.
- `ProviderRouter.on_fallback` defaults to `None` — all existing callers that construct `ProviderRouter` directly or via `from_model_ids` are unaffected.

### Testing Standards

Per project rules: 80% minimum coverage, pytest with `@pytest.mark.unit` / `@pytest.mark.integration`. All new files require a corresponding test file. Use `AsyncMock` for HTTP clients. Use `tmp_path` for SQLite stores. Do not mock the database in integration tests.

### Security

No new user-facing endpoints. Telemetry data written to SQLite does not include raw problem text (only preset, method, phase name, costs, scores). Run IDs are UUIDs. No new attack surface introduced.

---

## Risk Analysis

| Risk | Mitigation |
|------|-----------|
| `postflight` latency increase from E1+E2 | Both operations are async and fire-and-forget; errors are caught. Measured against existing Neuro learn call which already runs in postflight. |
| `FallbackLog` callback creates closure over mutable state | Callback is a simple `list.append` — no concurrency issue since pipeline execution is single-threaded per run. |
| `healing_context.json` grows unbounded | E5 hardcodes `limit=200` in `query_recent`. File is overwritten on each healing run. |
| SQLite contention between EventStore and TelemetryStore | Both use the same threading model (single `ThreadPoolExecutor` + `threading.Lock`). They share the DB file but operate on separate tables — no cross-table transactions. |
| `smart_compress` behavior change on edge inputs | E3 gates on the existing `TOKEN_OPTIMIZATION` flag; defaults remain unchanged. Unit test covers empty-string and short-string edge cases. |
