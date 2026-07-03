# Architecture Remediation Plan v2 — Raise Score from ~7.8 → 9.5

**Baseline:** `ARCHITECTURE_REMEDIATION_PLAN.md` (v1, dated 2026-06-23)  
**Current state:** `remediation-status-report.md` (~7.5–8.0, 5 CRITICALs resolved, 4 HIGHs partially resolved)  
**Target:** 9.5/10 — all layers separated, patterns consistent, observable, testable, scalable, with production polish margin.  
**Date:** 2026-06-23

---

## 0. Gap Analysis — What Separates 7.8 from 9.5

Per the audit rubric, 9.5 requires:

> All layers correctly separated, patterns consistent, observable, testable, scalable — with margin items (shared caching, connection pooling, e2e trace tests) that distinguish 9.0 from 9.5.

The gaps:

| # | Gap | Current state | Points to recover | Priority |
|---|---|---|---|---|
| G1 | PipelineState God Object (1245 lines, event I/O still on domain) | R6 partially resolved | ~0.4 | **P0** |
| G2 | PhaseOutput not applied to 6+ parallel phase sites — shared-mutation hazard | C1 partial | ~0.3 | **P0** |
| G3 | import-linter has 46 exceptions — architectural enforcement is symbolic | C2 partial | ~0.3 | **P1** |
| G4 | 3 residual `get_event_loop()` in `subprocess_executor.py` | A1 nearly done | ~0.1 | **P2** |
| G5 | `application→api` import in `handlers.py:109` (permitted, not clean) | A3 1 residual | ~0.1 | **P2** |
| G6 | Per-phase observability spans + e2e trace test unverified | F2 partial | ~0.2 | **P1** |
| G7 | Provider httpx pool reuse + global LLM semaphore unverified | F3 unknown | ~0.1 | **P2** |
| G8 | CI workflow for import-linter unverified | C2 gap | ~0.1 | **P2** |
| G9 | No truncation baseline — compression-vs-denoising mechanism not probed | New finding | ~0.1 | **P3** |
| G10 | Coverage ≥ 80% on refactored modules not verified | Rubric item | ~0.2 | **P1** |

**Total recoverable: ~1.9 points.** With ~1.5 conservatively achievable, 7.8 + 1.5 = **9.3**, and full closure of G1+G2+G3+G6+G10 pushes to **9.5+**.

---

## 1. Phased Roadmap

### PHASE 1 — Domain Object Slim-Down (P0, ~3 days)

Close the R6/C1/C3 gap. PipelineState is the single largest architectural drag.

#### 1.1 — Move event emission off PipelineState

**Current:** `PipelineState.wire_event_bus()` (line 975) and `PipelineState._emit()` (line 985) are on the domain object.  
**Action:** Move both into a new `application/services/event_emission_service.py`. The orchestrator wires the event bus during pipeline construction and passes it to phase functions — the domain object never touches it.  
**Files:**

```
domain/pipeline_state.py         — remove wire_event_bus(), _emit(),
                                   append_pending_event()
application/services/event_emission_service.py  — new: host wire+bind, emit,
                                                   flush_pending
application/orchestrator.py      — inject EventEmissionService
application/flows/pipeline_flow.py — receive emitter from orchestrator
```

**Verification:** `grep -n "event_bus\|_emit\|wire_event" src/reasoner/domain/pipeline_state.py` returns zero.

#### 1.2 — Move `to_context_dict()` out of PipelineState

**Current:** `to_context_dict()` (lines 1045–1220, ~175 lines of serialization logic).  
**Action:** Move to `application/services/pipeline_service.py` (already exists). `PipelineState` exposes a minimal `to_summary()` (≤ 30 lines) that returns raw data; `PipelineService.to_context_dict(state)` does the heavy serialization.  
**Files:**

```
domain/pipeline_state.py         — delete to_context_dict(), 
                                   add to_summary() (~25 lines)
application/services/pipeline_service.py  — add to_context_dict(state)
```

**Verification:** `grep -n "to_context_dict" src/reasoner/domain/pipeline_state.py` returns zero.

#### 1.3 — Strip redundant property boilerplate

**Current:** ~60 property getter/setter pairs, each ~6 lines of `if not hasattr` / `raise AttributeError`.  
**Action:** Replace with a descriptor-based pattern (single `PipelineField` descriptor class, ~15 lines) that provides typed access with lazy-init for every field. Cuts ~200 lines of boilerplate.  
**Files:**

```
domain/pipeline_state.py         — add PipelineField descriptor,
                                   replace all getter/setter pairs
```

**Target:** `domain/pipeline_state.py` ≤ **800 lines** (down from 1245).

**Verification:**

```
wc -l src/reasoner/domain/pipeline_state.py  # ≤ 800
```

#### 1.4 — Apply PhaseOutput to all parallel phase sites

**Current:** Only `perspective_phases.py` and `pipeline_flow.py` use `PhaseOutput`. Six other parallel sites mutate `PipelineState` directly — concurrent-write hazard remains.

**Sites to fix:**

```
application/flows/cognitive_phases.py:110   — parallel sub-problem solving
application/flows/coding_phases.py:101      — parallel file generation
application/flows/debate_phases.py:43,88,133 — opening, rebuttal, synthesis
application/flows/delphi_phases.py:27,111    — estimate + revision rounds
application/flows/jury_phases.py:107,156     — jury generation + critique
application/flows/article_phases.py:39       — parallel article search
application/flows/research_phases.py:118     — parallel research search
```

**Action:** Each parallel site returns a list of `PhaseOutput` (or `(name, output)` tuples). The calling orchestrator/flow applies deltas sequentially in a single-threaded reducer — no concurrent mutation.  
**Pattern:**

```python
# Before (unsafe)
results = await asyncio.gather(*tasks, return_exceptions=True)
for r in results:
    state.candidates.append(r)  # shared mutation

# After (safe)
deltas = await asyncio.gather(*tasks, return_exceptions=True)
for delta in deltas:
    if isinstance(delta, PhaseOutput):
        delta.apply_to(state)
```

**Verification:** Property test — run each parallel site 100×, assert candidate list deterministic + complete (no dropped/duplicated entries).

**Phase 1 score impact:** +0.5–0.7 (G1, G2, C1 fully closed). → **~8.3–8.5**

---

### PHASE 2 — Architectural Enforcement (P1, ~2 days)

#### 2.1 — Eliminate 46 import-linter exceptions

**Current:** `.importlinter` has 46 `ignore_imports` entries. Many are legitimate (ports/adapters pattern for infrastructure implementing application ports), but several are architectural leaks.

**Action — classify exceptions into three buckets:**

| Bucket | Count (est.) | Treatment |
|--------|-------------|-----------|
| **Ports/adapters** (infrastructure implements application port) | ~25 | Keep with explicit `# pragma: ports-adapter` annotation + separate contract |
| **Orchestrator wiring** (application→infrastructure for phase construction) | ~12 | Refactor to dependency injection — infrastructure passed into application layer, not imported |
| **Straight violations** (e.g., `handlers→api`, `domain→core`) | ~9 | Fix directly by moving imports or extracting interfaces |

**Action — per fixed violation:** Move the dependency to the correct layer or introduce a protocol/interface.

**Files affected:**

```
application/handlers/handlers.py    — remove `from reasoner.api.execution.pipeline`
                                      import (G5 fix)
application/orchestrator.py         — inject infra deps instead of importing
application/pipeline.py             — inject infra deps
domain/pipeline_state.py            — remove core imports, use domain events
domain/preset_core.py               — remove core imports, use domain constants
```

**Target:** Reduce ignore_imports from 46 to ≤ 15 (ports/adapters only, clearly documented).

#### 2.2 — Add CI enforcement

**Current:** `.importlinter` exists but CI workflow unverified.

**Action:**
- Confirm or create `.github/workflows/pr-architecture.yml` (or add to existing lint workflow)
- Add step: `import-linter` — fails PR on any new cross-layer violation
- Add step: `grep -c "ignore_imports" .importlinter` — fails if exceptions > 15

**Verification:** A PR that adds a `from reasoner.infrastructure import X` in `src/reasoner/domain/` must fail CI.

#### 2.3 — Fix residual boundary leak (G5)

**Current:** `application/handlers/handlers.py:109` imports `PipelineExecutionService` from `api.execution.pipeline`.

**Action:** Move `PipelineExecutionService` to `application/services/pipeline_execution_service.py`. The handler imports from application layer. The `api/execution/pipeline.py` module calls it (application is allowed from api). Invert the dependency — the handler owns the execution logic; api adapts it.

**Files:**

```
application/services/pipeline_execution_service.py  — new: host PipelineExecutionService
api/execution/pipeline.py                           — import from application, not reverse
application/handlers/handlers.py                    — remove api import
```

**Verification:** `grep -rn "from reasoner.api" src/reasoner/application` returns zero.

**Phase 2 score impact:** +0.3–0.4 (G3, G5, G8 closed). → **~8.6–8.9**

---

### PHASE 3 — Production Hardening (P2, ~2 days)

#### 3.1 — Subprocess executor deprecation (G4)

**Current:** 3 `asyncio.get_event_loop().time()` calls in `infrastructure/execution/subprocess_executor.py`.  
**Action:** Replace with `time.monotonic()` — the calls are for elapsed-time measurement, not loop introspection. `time.monotonic()` is monotonic and loop-agnostic.  
**Verification:** `grep -rn "get_event_loop()" src/reasoner` returns zero.

#### 3.2 — Provider httpx pool reuse (G7)

**Current:** `infrastructure/llm/router.py` — `_resolved_cache` per-instance; unbounded concurrent LLM calls per worker.  
**Action:**
- Hoist `_resolved_cache` to module level — shared across instances within a worker process.
- Add a global `asyncio.Semaphore(N)` (N = `LLM_MAX_CONCURRENT`, default 8) bounding concurrent LLM calls.
- Add `httpx.AsyncClient` connection pool reuse — single client per provider with `limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)`.

**Files:**

```
infrastructure/llm/router.py       — hoist cache, add semaphore
infrastructure/llm/providers/*.py  — add shared httpx client pool
core/settings.py                   — add LLM_MAX_CONCURRENT setting
```

**Verification:** Load test — 100 concurrent pipeline runs against 8-worker deployment, assert no connection exhaustion.

#### 3.3 — Redis mandatory in production (B1 completion check)

**Current:** `RunStateManager.is_authoritative()` exists; called in `api/__init__.py:509`.  
**Action:** Verify the production startup probe: `api/__init__.py` lifespan must `await run_state_manager.is_authoritative()` and raise `RuntimeError("Redis required in production")` if False and `ENVIRONMENT=production`. If probe already exists, verify with integration test.  
**Verification:** Test — start in production mode with Redis down, assert process exits with clear error.

**Phase 3 score impact:** +0.2–0.3 (G4, G7, B1 completion). → **~8.8–9.2**

---

### PHASE 4 — Observability & Testability (P1, ~2 days)

#### 4.1 — Per-phase observability spans (G6)

**Current:** Langfuse configured but per-phase span coverage unverified.

**Action:**
- Audit every phase function call site in `application/flows/` — ensure each phase wraps its execution in a Langfuse span with: phase name, model used, token count (input/output), latency, fallback flag, cost.
- Add a `@observable_phase` decorator (or context manager) that handles span creation + error capture uniformly.
- Add a synthetic e2e trace test: run a pipeline with a known preset, assert the trace contains one span per phase with all required fields.

**Files:**

```
application/flows/*_phases.py         — apply decorator/context manager
core/observability.py                 — new: @observable_phase, ObservablePhaseContext
tests/test_observability.py           — new: e2e trace test
```

**Verification:** E2e test passes; manual trace inspection shows one span per phase.

#### 4.2 — Coverage gate verification (G10)

**Current:** CI gate at 60% fail / 80% warn. Refactored modules need ≥ 80%.

**Action:**
- Run `pytest --cov=src/reasoner/domain/pipeline_state --cov=src/reasoner/api/execution --cov=src/reasoner/application/handlers --cov-report=term-missing`
- Add missing tests for uncovered branches in refactored modules.
- Raise CI fail threshold to 75%, warn to 85%.

**Verification:** Coverage report shows ≥ 80% on all Phase 1–3 refactored modules.

#### 4.3 — Golden-output parity for CQRS path

**Not in gap list but a rubric requirement.** The CQRS handler replaced the bypass but no regression test proves identical output.

**Action:** Write a golden-output test — same problem + preset through old streaming path and new CQRS handler path, assert byte-identical SSE event stream (modulo timestamps/ids/nonce fields).

**Files:**

```
tests/test_cqrs_parity.py  — new
```

**Phase 4 score impact:** +0.3–0.4 (G6, G10, golden parity). → **~9.2–9.5**

---

### PHASE 5 — Polish (P3, ~1 day)

#### 5.1 — Truncation baseline experiment (G9)

**Action:** Add a simple truncation baseline to the compression evaluation. Compare BabelTele at 30% retention against "take the first 30% of tokens." This isolates compression from denoising — a direct mechanism probe. Not a code change; a test/data addition.

**Verification:** Test shows whether BabelTele beats truncation at equal token budget.

#### 5.2 — Document the import-linter contract

**Action:** Add `docs/architecture-layers.md` — a one-page document listing each layer, its allowed dependencies, and the rationale for each remaining exception. The 15 remaining ports/adapters exceptions get explicit justification.

---

## 2. Dependency Ordering

```
Phase 1 (domain slimming)
  │
  ├── 1.1 (event emission) ──── independent
  ├── 1.2 (to_context_dict) ─── after 1.1 (shared file)
  ├── 1.3 (boilerplate) ──────── independent
  └── 1.4 (PhaseOutput) ─────── after 1.1 (event emission refactored)
        │
        └── Phase 2 (enforcement)
              ├── 2.1 (reduce exceptions) ─── after 1.1, 1.2, 1.4 (leaks removed)
              ├── 2.2 (CI gate) ───────────── after 2.1
              └── 2.3 (handlers.py leak) ──── independent
                    │
                    └── Phase 3 (hardening) ── independent of 2
                          │
                          └── Phase 4 (observability) ── independent
                                │
                                └── Phase 5 (polish) ── independent
```

---

## 3. Score Trajectory

| Milestone | Closes | Score |
|-----------|--------|-------|
| Current | — | ~7.8 |
| After Phase 1 | G1, G2 | ~8.5 |
| After Phase 2 | G3, G5, G8 | ~8.9 |
| After Phase 3 | G4, G7, B1-check | ~9.1 |
| After Phase 4 | G6, G10, golden parity | ~9.4 |
| After Phase 5 | G9, docs | ~9.5 |

---

## 4. Verification Gates (per PR)

Every PR:

- [ ] `pytest tests/ -v -m "not slow and not integration"` green
- [ ] `pytest -W error::DeprecationWarning` green for touched modules
- [ ] `import-linter` passes (exceptions ≤ 15)
- [ ] `grep -rn "from reasoner.api" src/reasoner/application` returns zero
- [ ] `grep -rn "get_event_loop()" src/reasoner` returns zero
- [ ] `wc -l src/reasoner/domain/pipeline_state.py` ≤ 800
- [ ] Coverage ≥ 80% on changed files
- [ ] For parallel phase changes: property test — run 100×, assert deterministic
- [ ] For execution-path changes: golden-output parity test

---

## 5. Effort Summary

| Phase | Days | Risk | Track |
|-------|------|------|-------|
| 1 — Domain slimming | 3 | Med | Core architecture |
| 2 — Architectural enforcement | 2 | Low | Boundary cleanup |
| 3 — Production hardening | 2 | Low | Correctness |
| 4 — Observability | 2 | Low | Rubric requirements |
| 5 — Polish | 1 | Low | Nice-to-have |
| **Total** | **~10 dev-days** | | ~2 working weeks single dev |

---

## 6. Definition of Done (Architecture ≥ 9.5)

1. PipelineState ≤ 800 lines, zero I/O, zero event-bus references, zero serialization — pure data + pure derivations only.
2. Zero cross-layer import violations — import-linter enforced in CI with ≤ 15 documented exceptions (all ports/adapters).
3. All parallel phase sites use PhaseOutput delta pattern — no shared-mutation hazard.
4. Streaming is decomposed — single execution model, no bypass flag, handler owns logic, api adapts.
5. Production correctness: Redis-mandatory startup probe, PostgreSQL event store with migration path, shared httpx pools with bounded concurrency.
6. Every phase observable: span with model, tokens, latency, fallback, cost. E2e trace test automates verification.
7. No deprecated asyncio patterns; all gather sites handle partial failure.
8. ≥ 80% coverage on all refactored modules; golden-output parity for CQRS path.
9. Squeeze margin: HyperGate cross-worker Redis L2, truncation baseline probed, layer architecture documented.
