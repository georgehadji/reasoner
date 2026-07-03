# Architecture Remediation Plan — Reasoner ARA

**Goal:** Raise architecture score from **5.5/10** to **> 9/10**.
**Date:** 2026-06-23 | **Branch baseline:** `main`
**Source:** `ARCH-AUDIT-V2` findings (this session).

---

## 0. Scoring Target — What 9+ Requires

Per the audit rubric:

> **9–10** = All layers correctly separated, patterns consistent, observable, testable, scalable.

Current **5.5** is held down by five confirmed issues:

| # | Issue | Severity | Phase ref |
|---|-------|----------|-----------|
| R1 | `api/streaming.py` God Function (969 lines, orchestrator bottleneck) | CRITICAL | P2, P5 |
| R2 | Run cancellation broken across workers (process-local in-mem fallback) | CRITICAL | P2, P4 |
| R3 | SQLite shared event store under 8 workers (write contention) | CRITICAL | P2, P4, P6 |
| R4 | CQRS permanently bypassed — two competing execution models | HIGH | P2, P5 |
| R5 | Layer boundary leaks (domain→infra, app→api, infra→api) | HIGH/MED | P3, P5 |

Plus four supporting issues:

| # | Issue | Severity |
|---|-------|----------|
| R6 | `PipelineState` God Object (1654 lines, mutable, owns I/O + event bus) | HIGH |
| R7 | `asyncio.get_event_loop()` deprecation (4 files) + `asyncio.run()` reentrancy | MED/HIGH |
| R8 | `asyncio.gather` without `return_exceptions` (4 sites) | MED |
| R9 | HyperGate per-process LRU cache (no cross-worker sharing) | HIGH |

**Score model.** Each CRITICAL fully resolved ≈ +0.8–1.0. Each HIGH ≈ +0.4–0.6. Closing R1–R5 + R6 + observability/test gates clears the 9.0 bar with margin.

---

## 1. Guiding Constraints

1. **No behavior regressions.** Every phase ships behind tests proving identical pipeline output.
2. **Incremental & reversible.** Each work item is an independent PR. No big-bang rewrite.
3. **Dependency-ordered.** Immutability (R6) precedes CQRS activation (R4) precedes streaming decomposition (R1).
4. **Verify before done.** No item marked complete without passing tests + a diff demonstrating the boundary fix (e.g., grep proving zero cross-layer imports).

---

## 2. Phased Roadmap

### PHASE A — Stabilize Foundations (Immediate, ~3 days)

Low-risk, mechanical fixes. Unblocks everything downstream. No architectural change.

#### A1 — Kill deprecated async patterns (R7)
- **Files:** `infrastructure/persistence/event_store.py:71`, `error_store.py:103`, `feedback_store.py:95`, `telemetry_store.py:83`
- **Action:** Replace `asyncio.get_event_loop()` → `asyncio.get_running_loop()`.
- **File:** `healing/telemetry_exporter.py:58`
- **Action:** Split `_build_context()` (async) from caller. Provide two entrypoints: `export_healing_context_sync()` (uses `asyncio.run`, for cron/CLI) and `await export_healing_context_async()` (for in-loop callers). Detect running loop with `asyncio.get_running_loop()` in a try/except and route accordingly.
- **Test:** `pytest -W error::DeprecationWarning tests/` passes for persistence + healing modules.
- **Done when:** `grep -rn "get_event_loop()" src/reasoner` returns zero (excluding tests).

#### A2 — Harden gather call sites (R8)
- **Files:** `application/flows/pipeline_flow.py:89`, `application/services/scorecard_service.py:59`, `core/rerank.py:312`, `documents/vector_store.py:133`
- **Action:** Add `return_exceptions=True`; iterate results, log + degrade per-task on `BaseException`. For `pipeline_flow.py` DAG executor: a failed non-critical phase must not cancel siblings; a failed critical phase produces a structured error event, not an uncaught raise.
- **Test:** New unit test injecting a phase that raises — assert siblings complete and SSE error event emitted.

#### A3 — Fix layer-boundary leaks (R5)
- **`domain/preset_core.py:278`** (domain→infra): Remove the inline `_REGISTRY` import. Move model-alias validation into `application/services/preset_service.py::validate_preset(preset)`, called explicitly after construction. Domain `__post_init__` validates only routing-role keys (already pure).
- **`application/services/data_eraser.py:51`** (app→api): Move `clear_memory_cache` to `infrastructure/cache_manager.py`. Inject as a `Callable` into `UserDataEraser.__init__`.
- **`infrastructure/server_check.py:75`** (infra→api): Pass `app` as a function parameter; caller in `api/` supplies it.
- **Done when:** all three greps return zero:
  ```
  grep -rn "from reasoner.infrastructure" src/reasoner/domain
  grep -rn "from reasoner.api" src/reasoner/application
  grep -rn "from reasoner.api" src/reasoner/infrastructure
  ```
- **Guard:** Add an import-linter contract (see C2) so these never regress.

**Phase A score impact:** +0.5 (R5, R7, R8 closed). → **~6.0**

---

### PHASE B — Production Correctness (Next Sprint, ~5 days)

The two CRITICAL deployment bugs. These are correctness, not aesthetics.

#### B1 — Reliable cross-worker cancellation (R2)
- **File:** `infrastructure/redis/run_state.py`
- **Problem:** In-memory fallback is process-local; cancel on worker-A invisible to worker-B.
- **Action:**
  - In `ENVIRONMENT=production`, Redis is **mandatory**. Add a startup probe in `api/__init__.py` lifespan that pings Redis and **fails fast** (`RuntimeError`) if unreachable in production.
  - Keep in-memory fallback **only** for `development`/`test`, logged at WARNING.
  - Add a `health` sub-check reporting `redis: ok|degraded` so the degraded state is observable.
- **Test:** Integration test with 2 simulated workers (2 `RunStateManager` instances sharing a Redis testcontainer) — cancel via instance A, assert instance B observes it. Assert production startup raises when Redis down.
- **Done when:** cancellation propagates across instances backed by Redis; production refuses to boot without Redis.

#### B2 — Migrate event store to PostgreSQL (R3)
- **Files:** `infrastructure/persistence/event_store.py`, `postgres_store.py` (exists), `docker-compose.yml` (Postgres already provisioned).
- **Problem:** SQLite serializes writes; 8 workers contend on one file; `events.db` already 12 MB.
- **Action:**
  - Promote `postgres_store` to the production `EventStore` implementation behind the existing port. SQLite remains the dev/test default.
  - Select via settings: `EVENT_STORE_BACKEND = postgres|sqlite` (default `sqlite` dev, `postgres` when `DATABASE_URL` present + `ENVIRONMENT=production`).
  - Per-worker `asyncpg` pool (already a dependency).
  - One-shot migration script `scripts/migrate_events_sqlite_to_pg.py` for existing `events.db`.
- **Test:** Run existing event-store test suite against both backends (parametrize fixture). Concurrency test: 50 parallel appends, assert zero lost writes + bounded latency.
- **Done when:** production path uses Postgres pool; SQLite write-contention ceiling removed.

**Phase B score impact:** +1.6 (two CRITICALs closed). → **~7.6**

---

### PHASE C — Tame the Domain & Boundaries (Next Sprint, ~5 days)

Prerequisite for the CQRS activation in Phase D. Immutability first.

#### C1 — Make `PipelineState` transition-safe (R6, part 1)
- **File:** `domain/pipeline_state.py` (1654 lines)
- **Problem:** Mutated in place by ~30 phase functions via `set_*`; shared by reference across `asyncio.gather` perspectives → interleave risk.
- **Action (incremental, not full immutability yet):**
  - Introduce a `StateTransition` discipline: phase functions return a typed delta (`PhaseOutput`) instead of mutating `state`. A single reducer applies deltas sequentially in the orchestrator — eliminates concurrent-write hazard for parallel perspectives.
  - Start with the parallel hotspot: `flows/perspective_phases.py:103`. Each perspective coroutine returns its `SolutionCandidate`; the gather result is reduced once, single-threaded.
  - Sequential phases may keep mutation short-term; flag for C3.
- **Test:** Property test — run perspectives in parallel 100×, assert candidate list deterministic + complete (no dropped/duplicated candidates).

#### C2 — Enforce boundaries automatically (R5 guard)
- **Action:** Add `import-linter` (`importlinter`) with layered contract:
  ```
  domain  -> (nothing in reasoner.*)
  core    -> domain
  application -> core, domain
  infrastructure -> core, domain  (NOT api)
  api -> application, infrastructure, core, domain
  ```
- Wire into `.github/workflows/pr-architecture.yml` as a blocking check.
- **Done when:** CI fails on any new cross-layer violation. The Phase A fixes make the contract pass green on merge.

#### C3 — Relocate I/O off the domain object (R6, part 2)
- **Action:** Move `PipelineState.save()/load()/save_to()/load_from()` → `application/services/pipeline_service.py` (serialization is application concern). Move `bind_event_bus()`/event emission → orchestrator. `PipelineState` becomes pure data + pure derivations.
- **Target:** `domain/pipeline_state.py` < 800 lines, zero I/O, zero event-bus references.
- **Test:** Existing `--resume` round-trip tests pass via the relocated service API.

**Phase C score impact:** +0.7 (R6 closed, boundary guard institutionalized). → **~8.3**

---

### PHASE D — Unify the Execution Model (Next Sprint, ~5 days)

Kill the dead CQRS / live-orchestrator split. One path.

#### D1 — Make CQRS the real SSE path (R4)
- **Files:** `application/handlers/handlers.py` (`RunPipelineCommandHandler`), `api/streaming.py`, `core/settings.py:82`.
- **Action:**
  - Extend `RunPipelineCommandHandler.handle(command, sse_emit: Callable[[dict], Awaitable])` so it drives the pipeline and yields SSE events via the injected emitter — no business logic in the transport.
  - `api/streaming.py::run_stream()` builds the command + an emitter that `yield`s, then awaits the handler. All preflight/branching logic moves into the handler (or a `PipelineExecutionService` it calls).
  - Flip default `CQRS_BYPASS_STREAMING=false`. Run both paths in parallel under a feature flag for one release to compare output parity.
- **Test:** Golden-output test — same problem + preset through old path and new path, assert byte-identical SSE event stream (modulo timestamps/ids).

#### D2 — Delete the bypass + legacy path (R4 cleanup)
- **Action:** Once D1 parity holds in staging, remove `CQRS_BYPASS_STREAMING` flag and the direct-instantiation branch (`streaming.py:354`). Delete dead handler-skipping code.
- **Done when:** `grep -rn "CQRS_BYPASS" src/reasoner` returns zero; only one execution path exists.

**Phase D score impact:** +0.5 (R4 closed, single coherent model). → **~8.8**

---

### PHASE E — Decompose the Transport Bottleneck (Next Sprint, ~4 days)

#### E1 — Split `api/streaming.py` (R1)
- **Problem:** 969 lines, ~16 module couplings, all execution concerns in one generator.
- **Action:** After D1 moved logic into the handler/service, the residual transport shrinks. Extract what remains into:
  ```
  api/execution/direct.py        # _stream_direct_answer
  api/execution/web_search.py    # _stream_web_search_results
  api/execution/pipeline.py      # main pipeline SSE adaptation
  api/execution/cancel.py        # run cancellation + WS broadcast wiring
  api/streaming.py               # thin router: dispatch by preflight.action (<150 lines)
  ```
- **Target:** every file ≤ 250 lines; `run_stream` is a dispatcher.
- **Test:** Existing streaming tests pass unchanged. Add per-module unit tests now possible in isolation.

#### E2 — Resolve the hidden flows↔serializers circular dep (R5/P3)
- **File:** `application/flows/__init__.py` (exports commented out to hide cycle).
- **Action:** Move SSE serialization out of `api.serializers` dependency from flows. Flows should emit domain `PhaseResult`; serialization is api-layer. Restore real exports in `flows/__init__.py`.
- **Done when:** `flows/__init__.py` exports `PhaseStep`, `PipelineFlow` with no commented cycle-breaker; import-linter passes.

**Phase E score impact:** +0.4 (R1 closed, last circular dep resolved). → **~9.2**

---

### PHASE F — Cross-Worker State & Observability Polish (Backlog, ~3 days)

#### F1 — Share HyperGate cache across workers (R9)
- **File:** `hypergate/hyperagent.py:242` (instance LRU dict).
- **Action:** Back the gate-decision cache with Redis (keyed by `problem_hash`, short TTL). Per-process LRU stays as L1; Redis as L2 shared. Under 8 workers, repeated prompts hit the shared cache.
- **Test:** Two manager instances; warm via A, assert B hits L2.

#### F2 — Observability gates
- **Action:** Ensure every phase emits a span/metric (latency, model, fallback, cost). Confirm Langfuse keys enforced in production (already warned at `api/__init__.py:38`). Add a synthetic end-to-end trace test.
- **Rubric tie-in:** "observable" is an explicit 9–10 requirement.

#### F3 — Provider pool reuse
- **File:** `infrastructure/llm/router.py` (`_resolved_cache` per-instance).
- **Action:** Hoist provider/httpx client pool to a module/process-level shared resource with bounded connection pool + a global semaphore bounding concurrent LLM calls per worker (addresses the unbounded-concurrency hypothesis from P4).

**Phase F score impact:** +0.3 (R9 + observability/testability). → **~9.5**

---

## 3. Sequencing & Dependencies

```
A1 A2 A3  (parallel, independent)
   │
   ├─> B1  (independent)
   ├─> B2  (independent)
   │
   └─> C1 ──> C3        C2 (anytime after A3)
          │
          └─> D1 ──> D2 ──> E1 ──> E2
                              │
                              └─> F1 F2 F3
```

- **A** unblocks everything; ship first.
- **B** is parallel to **C/D** (deployment-correctness track vs. architecture track).
- **C1 immutability MUST precede D1** — CQRS handler driving parallel phases needs transition-safe state.
- **D MUST precede E1** — moving logic into the handler is what shrinks `streaming.py` enough to split cleanly.

---

## 4. Verification Gates (per PR)

Every PR must satisfy:

- [ ] `pytest tests/ -v -m "not slow and not integration"` green
- [ ] `pytest -W error::DeprecationWarning` green for touched modules
- [ ] `import-linter` contract passes (after C2)
- [ ] Coverage ≥ 80% on changed files (CI gate already at 60% fail / 80% warn)
- [ ] For boundary fixes: the relevant `grep` returns zero violations (paste in PR body)
- [ ] For execution-path changes: golden-output parity test attached

---

## 5. Score Trajectory

| Milestone | Closes | Score |
|-----------|--------|-------|
| Baseline | — | 5.5 |
| After Phase A | R5, R7, R8 | ~6.0 |
| After Phase B | R2, R3 | ~7.6 |
| After Phase C | R6, boundary guard | ~8.3 |
| After Phase D | R4 | ~8.8 |
| After Phase E | R1, last cycle | ~9.2 |
| After Phase F | R9, observability | ~9.5 |

**Target > 9.0 reached at end of Phase E.** Phase F provides margin and addresses the scalability-headroom items that distinguish 9 from 9.5.

---

## 6. Effort Summary

| Phase | Days | Risk | Track |
|-------|------|------|-------|
| A | 3 | Low | Foundation |
| B | 5 | Med | Deployment correctness |
| C | 5 | Med | Domain/boundaries |
| D | 5 | Med | Execution unification |
| E | 4 | Low (post-D) | Transport decomposition |
| F | 3 | Low | Polish/scale |
| **Total** | **~25 dev-days** | | ~5 working weeks single dev; ~3 weeks with B parallelized |

---

## 7. Definition of Done (Architecture ≥ 9/10)

1. Zero cross-layer import violations (import-linter enforced in CI).
2. Single execution model — CQRS handler is the only SSE path; no bypass flag.
3. `api/streaming.py` and `domain/pipeline_state.py` both < 800 lines; no God Function / God Object.
4. Production correctness: Redis-backed cancellation, Postgres event store, no SQLite write contention.
5. Parallel phases are transition-safe (no shared-mutation hazard).
6. Every phase observable (span + cost + fallback metric); Langfuse enforced in prod.
7. No deprecated asyncio patterns; all `gather` sites handle partial failure.
8. ≥ 80% coverage on all refactored modules; golden-output parity proven.
