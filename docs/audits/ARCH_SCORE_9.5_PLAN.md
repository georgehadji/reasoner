# Architecture Remediation Plan — Target Score 9.5 / 10

**Baseline:** 7 / 10 (ARCH-AUDIT-V2, 2026-06-24)
**Target:** 9.5 / 10
**Maturity transition:** Early Production → Production
**Estimated effort:** 5 work-streams, ~12–16 focused days
**Refactor strategy:** Port-first, additive-then-subtractive. Every step keeps `lint-imports`, `pytest`, and the app boot green before the next.

---

## 0. Scoring Model

The 2.5-point gap maps to concrete, verifiable deltas. No step lands credit until its acceptance gate passes.

| # | Work-stream | Resolves | Δ Score | Cumulative |
|---|-------------|----------|---------|------------|
| WS-1 | Reverse + circular dependency elimination | Anti-Patterns 3, 4 (HIGH) | +0.8 | 7.8 |
| WS-2 | Port-wire application→infrastructure (kill 25 ignores) | Anti-Pattern 2 (HIGH) | +0.7 | 8.5 |
| WS-3 | Test integrity (42 collection errors → 0) | Anti-Pattern 7 (MEDIUM) | +0.5 | 9.0 |
| WS-4 | Backpressure + state-immutability hardening | Anti-Patterns 5, 6 (MEDIUM) | +0.3 | 9.3 |
| WS-5 | Shim retirement + boundary lock-in (CI guard) | Anti-Pattern 1 (downgraded → LOW) | +0.2 | 9.5 |

**Why not 10:** Reaching 10 requires full event-sourced state replacement of mutable `PipelineState` and observable end-to-end tracing parity — a multi-quarter evolution, out of scope here. 9.5 = all layers correctly separated, zero tolerated import violations, trustworthy test signal, bounded concurrency.

---

## 1. Current-State Corrections (vs. raw audit)

Verified facts that *reduce* scope from the initial audit:

- **Root flat modules are mostly shims.** `auth.py`, `circuit_breaker.py`, `rate_limiter.py`, `sanitization.py`, `gate_agent.py`, `pipeline.py`, `parsing.py` are 2–4 line backward-compat re-exports. Real implementations already live in proper layers. → Anti-Pattern 1 downgraded **CRITICAL → LOW** (shim cleanup, not structural rescue).
- **Real root modules >10 lines:** only `start_all.py` (472, dev launcher — acceptable at root), `main.py` (422, CLI entry — acceptable), `presets.py` (164, partial re-export), `models.py` (57, re-export), `phases.py` (31, re-export).
- **`core/ports/` already exists** with `llm_port.py`, `search_port.py`, `circuit_breaker_port.py`, `file_search_port.py`, `telemetry_port.py`, `code_executor.py`. The scaffolding is present; the wiring is missing.
- **`LLMPort` Protocol is defined but unused** — `ProviderRouter` does not declare it, no consumer imports it. This is the single highest-leverage fix in WS-2.
- **DI precedent established** — `core/search.py` already uses `set_build_provider()` / `set_searxng_circuit_breaker()` injection hooks. WS-1/WS-2 follow this exact pattern, no new mechanism invented.

---

## 2. WS-1 — Reverse & Circular Dependency Elimination (+0.8)

### 2.1 Kill `application/handlers/handlers.py → reasoner.api`

**Root cause:** Cancel state lives in `api`-reachable singleton `_run_state_manager` (`infrastructure/redis/run_state.py:279`); handler reaches it via `import reasoner.api as api` (`handlers.py:260`).

**Fix — define a port, inject the existing manager:**

1. Add `core/ports/run_state_port.py`:
   ```python
   @runtime_checkable
   class RunStatePort(Protocol):
       async def request_cancel(self, pipeline_id: str) -> None: ...
       async def is_cancelled(self, pipeline_id: str) -> bool: ...
       async def register(self, pipeline_id: str) -> None: ...
   ```
2. Confirm `RunStateManager` (`infrastructure/redis/run_state.py`) already satisfies the signatures (it does — `request_cancel` exists). Add explicit `RunStatePort` conformance if any method names drift.
3. Inject the manager into `RunPipelineCommandHandler` / `StopPipelineCommandHandler` constructors (composition root: `application/handlers/__init__.py` or wherever handlers are built).
4. Replace `import reasoner.api as api; api._run_store...` with `self._run_state.request_cancel(...)`.
5. Delete the runtime `import reasoner.api` line.

**Gate:** `grep -rn "import reasoner.api" src/reasoner/application/` returns 0. Handler unit-testable with a mock `RunStatePort`.

### 2.2 Break `event_bus ↔ postgres_store` cycle

**Root cause:** `application/event_bus/bus.py → infrastructure/persistence/event_store` AND `infrastructure/persistence/postgres_store.py → application/event_bus/bus.py`.

**Fix — invert via port:**

1. Define `core/ports/event_store_port.py` (`append`, `load`, `subscribe` as needed).
2. `event_bus/bus.py` depends on `EventStorePort` only; concrete `event_store` injected at startup (mirror `set_build_provider` pattern → add `set_event_store(store)` or constructor injection).
3. `postgres_store.py` must stop importing `bus`. If it emits events, have it accept an `event_emitter` callback / port injected at construction rather than importing the bus module.
4. Remove both `.importlinter` ignore lines for this pair.

**Gate:** `lint-imports` passes with the 2 ignore entries deleted. App boots. `pytest tests/test_aggregates.py tests/ -k event` green.

**Δ +0.8** lands when 2.1 and 2.2 both gate-pass.

---

## 3. WS-2 — Port-Wire Application → Infrastructure (+0.7)

**Goal:** Drive the 25-entry `.importlinter` ignore list toward ≤3 (only legitimate composition-root wiring remains).

### 3.1 LLM access (highest fan-in — 6+ ignores)

Ignores targeted:
- `application.handlers.handlers → infrastructure.llm.router`
- `application.orchestrator → infrastructure.llm.router`
- `application.services.pipeline_service → infrastructure.llm.router`
- `application.services.preset_service → infrastructure.llm.{router,registry}`
- `application.services.pricing_service → infrastructure.llm.registry`

**Steps:**
1. Declare `ProviderRouter(LLMPort)` — make conformance explicit; reconcile any method-name mismatch (`call`, `get`).
2. For registry needs (`build_provider`, model metadata), define `core/ports/model_registry_port.py`. Application consumes the port; `infrastructure/llm/registry.py` implements it.
3. Change application-layer type hints from `ProviderRouter` → `LLMPort` and from registry imports → `ModelRegistryPort`. Concrete instances injected at the composition root (`PipelineOrchestrator` construction in `api/__init__.py` lifespan + `main.py`).
4. Remove corresponding `.importlinter` ignores.

### 3.2 Persistence access (telemetry, quota, subscription, event store)

Ignores targeted: `scorecard_service → telemetry_store`, `data_eraser → event_store`, `billing_service → subscription_repo`, `cached_quota_repo`, `quota_repo_postgres`.

**Steps:** Each already has a port partner in many cases (`quota_repository`, `auth_port`, `billing_port` exist under `application/ports/`). Where a service imports a concrete store, swap to the existing port and inject. Where no port exists (`telemetry_store`), add `core/ports/telemetry_store_port.py` (note: `telemetry_port.py` exists — verify whether it covers store ops or only emission; extend or add as needed).

### 3.3 Flows → infrastructure execution/search

Ignores targeted: `flows.services → infrastructure.execution.{noop,subprocess}_executor`, `flows.research_phases → infrastructure.prism.file_search`.

**Steps:** `code_executor.py` port and `file_search_port.py` already exist in `core/ports/`. Wire flows to consume the port; inject concrete executor/searcher through the `FlowServices` container passed into `runner.py`. This is the cleanest of the three — ports pre-exist.

**Acceptance gate (WS-2):**
- `.importlinter` ignore count ≤ 3 (document each survivor with a one-line justification comment).
- Every application module importable with `infrastructure` absent from `sys.modules` at type-check time (spot-check with a stub composition root).
- Full `pytest` suite ≥ prior pass count.

**Δ +0.7.**

---

## 4. WS-3 — Test Integrity: 42 → 0 Collection Errors (+0.5)

**Root cause (verified):** stale imports of symbols deleted during prior refactors, e.g. `tests/test_followup_context.py:5` → `ImportError: cannot import name '_stream_direct_answer' from 'reasoner.api.streaming'`.

**Steps:**
1. Enumerate all 42:
   ```bash
   python -m pytest tests/ --co -q 2>&1 | grep -E "^ERROR" > arch/test_collection_errors.txt
   ```
2. Bucket by failure class:
   - **Renamed/removed symbol** → update import to current public name, or restore a thin re-export if the symbol was legitimately public API.
   - **Moved module** → fix import path.
   - **Genuinely obsolete test** → delete only with a one-line rationale in the PR; do not mass-delete to "fix" collection.
3. Fix import-path-only failures first (mechanical, low-risk), then symbol renames, then content review of any test asserting against removed behavior.
4. Add a CI guard: a job step that fails if `pytest --co -q` reports **any** collection error. Prevents silent regression.

**Acceptance gate:** `pytest --co -q` → 0 errors. CI step enforces it. Coverage number becomes trustworthy; re-baseline coverage and record it.

**Δ +0.5.**

---

## 5. WS-4 — Backpressure + State Hardening (+0.3)

### 5.1 Bound the web-search SSE queue (MEDIUM, one-line)

`api/execution/web_search.py:50` — `asyncio.Queue()` → `asyncio.Queue(maxsize=256)`, matching `api/streaming.py:124`. Verify producer handles `QueueFull` / awaits `put()` with the same backpressure discipline as the main path.

**Gate:** parity test — slow consumer on web-search path does not grow RSS unbounded (assert queue depth caps at 256).

### 5.2 Event-bus semaphore sanity

`event_bus/bus.py:55` — `Semaphore(200)`. Validate against real provider rate limits. If LLM concurrency must be globally bounded, lower to a config-driven value (`settings.MAX_CONCURRENT_HANDLERS`) and document the rationale. Not a correctness bug today; a scaling foot-gun.

### 5.3 `PipelineState` mutation discipline

Full freeze is out of scope (would break the phase-mutation model). Instead, contain the risk:
1. Document the invariant: `PipelineState` is single-writer per run; concurrent phases (e.g. parallel Phase-2 perspectives) **must** write to disjoint fields or append to dedicated collections, never read-modify-write a shared scalar.
2. Add a test asserting parallel Phase-2 perspective writes target distinct list slots / keys (regression guard against future data races).
3. Where parallel writes already occur (`perspective_phases.py:106` gather), confirm each task returns its result and the *parent* assembles into state — not each task mutating state concurrently. Refactor any in-task mutation to return-then-assemble.

**Gate:** concurrency regression test passes; documented invariant in `domain/pipeline_state.py` module docstring.

**Δ +0.3.**

---

## 6. WS-5 — Shim Retirement + Boundary Lock-In (+0.2)

### 6.1 Retire backward-compat shims

The 2–4 line root shims (`auth.py`, `circuit_breaker.py`, `rate_limiter.py`, `sanitization.py`, `gate_agent.py`, `pipeline.py`, `parsing.py`) re-export from real layer locations.

**Steps:**
1. `grep -rn` each shim's symbols across `src/`, `tests/`, `scripts/` to find live importers.
2. Rewrite importers to the canonical layer path.
3. Delete the shim once fan-in is 0.
4. Keep `models.py`, `presets.py`, `phases.py` re-exports **only if** external/CLI contracts depend on them; otherwise retire likewise. `main.py`, `start_all.py` stay at root (legitimate entry points).

### 6.2 Lock boundaries in CI

1. Add `lint-imports` as a required CI gate (fail build on any new violation).
2. Add a guard that fails if a new `*.py` appears at `src/reasoner/` root without an allowlist entry (prevents flat-module regrowth).
3. Reduce `.importlinter` ignore list to its documented minimum; each remaining entry carries an inline `# JUSTIFIED:` comment.

**Gate:** root `*.py` count drops to entry-points + justified re-exports only; CI blocks regressions.

**Δ +0.2 → 9.5 total.**

---

## 7. Execution Order & Dependencies

```
WS-3 (test integrity)  ─────────────┐   run FIRST — gives trustworthy signal for all later gates
                                     ▼
WS-1 (reverse/cyclic deps) ──► WS-2 (port-wire app→infra) ──► WS-5 (shim + CI lock)
                                     ▲
WS-4 (backpressure/state) ───────────┘   parallelizable; low coupling to others
```

- **WS-3 first** — cannot trust any acceptance gate while 42 tests silently don't run.
- **WS-1 before WS-2** — breaking the reverse/cyclic deps simplifies the port-wiring surface.
- **WS-5 last** — boundary lock-in CI guard should land only after violations are actually resolved, else it red-walls the build.
- **WS-4 independent** — assign in parallel.

---

## 8. Per-Step Risk Register

| Step | Risk | Mitigation |
|------|------|------------|
| 2.1 RunStatePort | Cancel semantics differ between in-memory vs Redis impl | Conformance test against both adapters before swap |
| 2.2 event_store cycle break | Import-order ImportError if injection mis-wired | Boot smoke test in CI; inject at single composition root |
| 3.1 LLMPort wiring | Method signature drift (`call` vs `complete`) | Reconcile Protocol to actual router API first, then conform |
| 4.0 web_search maxsize | Producer not written for blocking `put` | Audit producer; use `put_nowait` + drop-or-await policy matching main path |
| 5.3 PipelineState | Hidden in-task mutations cause silent races post-refactor | Add concurrency regression test BEFORE refactor (red→green) |
| 6.1 shim deletion | External script/import breaks | Full-repo grep + CI before delete; deprecation pass if any external contract |

---

## 9. Definition of Done (9.5 Gate)

- [ ] `pytest --co -q` → **0** collection errors; CI enforces.
- [ ] `grep -rn "import reasoner.api" src/reasoner/application src/reasoner/domain` → **0**.
- [ ] `.importlinter` ignore list ≤ **3**, each `# JUSTIFIED:`-annotated.
- [ ] `lint-imports` green and **required** in CI.
- [ ] `event_bus ↔ postgres_store` cycle gone (both ignore lines deleted).
- [ ] `ProviderRouter` declares `LLMPort`; application layer type-hints the port, not the concrete.
- [ ] `web_search.py` queue bounded (`maxsize=256`); parity backpressure test passes.
- [ ] `PipelineState` single-writer invariant documented + concurrency regression test green.
- [ ] Root `src/reasoner/*.py` = entry points + justified re-exports only; CI guards regrowth.
- [ ] Full suite pass count ≥ pre-remediation baseline; coverage re-baselined and recorded.

---

## 10. Out of Scope (would push toward 10, not 9.5)

- Full immutable / event-sourced replacement of mutable `PipelineState`.
- Cross-worker shared rate-limiter state (Redis-backed) — only needed when scaling past single-process async.
- End-to-end distributed tracing parity (OpenTelemetry spans across every phase + provider call).
- Container-boundary alignment with service boundaries (Docker decomposition).

These are tracked as the post-9.5 evolution backlog.
