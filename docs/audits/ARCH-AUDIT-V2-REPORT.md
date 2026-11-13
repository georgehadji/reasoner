# ARCH-AUDIT-V2: Reasoner Architecture Audit

**Project:** Reasoner v2.0  
**Date:** 2026-06-24  
**Protocol:** EGFV — every finding labeled

---

## Input Gate

| Input | Status |
|-------|--------|
| Full codebase | ✅ Present (540+ source files) |
| Primary entry points | ✅ `main.py` (CLI), `api/__init__.py` (FastAPI:8003) |
| ADRs | [UNKNOWN — not provided] |
| README / design docs | ✅ `ARCHITECTURE_REMEDIATION_PLAN.md`, `remediation-plan-v2-9.5.md` |
| Dependency manifests | ✅ `requirements.txt` |
| Deployment manifests | ✅ `Dockerfile` (root + `ui-next/`) |
| CI/CD configs | ✅ 5 workflows in `.github/workflows/` |

---

## Phase 1 — Architectural Fingerprinting

**DETECTED ARCHITECTURE: Layered CQRS with Event-Driven Orchestration**

6-layer stack with import-linter enforcement:

```
api/            → HTTP/SSE transport (FastAPI)
application/    → CQRS handlers, services, phase flows
infrastructure/ → LLM providers, persistence, Redis, auth
subagents/      → Intra-phase reasoning agents
core/           → Constants, protocols, ports, settings
domain/         → Pure data (PipelineState, core_types)
```

**Evidence:**

1. [VERIFIED] Import-linter contract at `.importlinter` defines explicit layer order with 27 documented exceptions. CI enforcement via `pr-architecture.yml` fails if >45.

2. [VERIFIED] Three execution paths converge on single orchestrator: SSE path (`PipelineExecutionService.execute_run()`, 595 lines), CQRS handler path (`RunPipelineCommandHandler.handle()` via injected `PipelineExecutionPort`), CLI path (`PipelineOrchestrator.execute()`).

3. [VERIFIED] Domain layer is pure data: `PipelineState` (671 lines) has zero infrastructure imports, zero event I/O. All properties delegated via `PipelineField` descriptor. Event emission in `EventEmissionService` (application layer). Serialization in `PipelineService`.

4. [VERIFIED] Dependency inversion at three boundaries: `handlers→api` (`PipelineExecutionPort` protocol), `core→infra` (`set_build_provider`/`set_searxng_circuit_breaker` DI), infrastructure→application (ports/adapters pattern).

5. [VERIFIED] SSE backpressure via `asyncio.Queue(maxsize=256)` at `api/streaming.py:124`. LLM concurrency bounded by `_LLM_CONCURRENCY_SEMAPHORE` (default 30) at `router.py:126-137`.

---

## Phase 2 — Compliance Matrix

| Module | Detected | Intended | Drift | Violations | Sev | Evidence |
|--------|----------|----------|-------|------------|-----|----------|
| `domain/pipeline_state.py` (671 lines) | Pure data + descriptor | Pure data | None | 0 | — | [VERIFIED] 0 infra/event I/O |
| `application/services/event_emission_service.py` (167 lines) | App-layer event service | App-layer | None | 0 | — | [VERIFIED] Contextvar, no api imports |
| `api/execution/pipeline.py` (595 lines) | SSE adapter | Transport | None | 0 | — | [VERIFIED] Calls app-layer services |
| `application/handlers/handlers.py` (523 lines) | CQRS registry | CQRS | None (fixed) | 0 | — | [VERIFIED] `PipelineExecutionPort` injected |
| `infrastructure/llm/router.py` (401 lines) | Provider abstraction | Provider abs | None | 0 | — | [VERIFIED] Shared pool/cache/semaphore |
| `core/observability/phase_span.py` (97 lines) | Cross-cutting span | Cross-cutting | Minor | 1 infra import (lazy) | **LOW** | [VERIFIED] `langfuse_subscriber` import for observability |
| `core/protocol.py` | Protocol defs | Protocol defs | Minor | 1 infra import (TYPE_CHECKING) | **NONE** | [VERIFIED] False positive — not runtime |
| `core/search.py` | Search utilities | Search utils | None (fixed) | 0 | — | [VERIFIED] DI via setters, no infra imports |
| `api/streaming.py` (269 lines) | SSE router | Transport | None (fixed) | 0 | — | [VERIFIED] Decomposed into 4 execution modules |

---

## Phase 3 — Dependency & Coupling Analysis

### 3.1 Circular Dependencies

| Pair | Status | Evidence |
|------|--------|----------|
| `models.py` ↔ `pipeline_service.py` | ✅ FIXED | Lazy wrappers in `models.py:48-54` |
| `handlers.py` → `api.execution.pipeline` | ✅ FIXED | `PipelineExecutionPort` protocol + DI |

### 3.2 Layer Leaks

| Leak | Severity | Status |
|------|----------|--------|
| `core.protocol → infrastructure.llm.router` | NONE | [VERIFIED] TYPE_CHECKING — false positive |
| `core.search → infrastructure.circuit_breaker` | NONE | [VERIFIED] DI via `set_searxng_circuit_breaker()` |
| `core.search → infrastructure.llm.registry` | NONE | [VERIFIED] DI via `set_build_provider()` |
| `core.observability.phase_span → infrastructure.observability.langfuse_subscriber` | LOW | [VERIFIED] Lazy import inside try/except — graceful degradation |

### 3.3 Shared Mutable State

| State | Risk | Mitigation |
|-------|------|-----------|
| `_GLOBAL_RESOLVED_CACHE` (router.py:124) | Low | Per-worker, write-once |
| `_LLM_CONCURRENCY_SEMAPHORE` (router.py:126) | None | Correct pattern |
| `pipeline_owners.json` | Low | Empty file, non-critical |

### 3.4 Coupling Hotspots

| Module | Efferent (imports) | Assessment |
|--------|-------------------|-----------|
| `api/execution/pipeline.py` | 25 | High — expected for orchestrator |
| `domain/pipeline_state.py` | 3 (core dirs) | Expected — central data type |
| `infrastructure/llm/router.py` | 5 (providers) | Expected — central routing |

---

## Phase 4 — AI Orchestrator Review

### 4.1 Orchestration Model

| Aspect | Finding |
|--------|---------|
| Centralized/Distributed | [VERIFIED] Centralized. `PipelineExecutionService.execute_run()` drives full lifecycle. |
| Routing/Business separation | [VERIFIED] Well-separated. `HyperGateAgent` routes; phases generate prompts. |
| Provider abstraction | [VERIFIED] `ProviderRouter` selects by role. 4 provider types behind `BaseLLMProvider`. |

### 4.2 Async & Concurrency

| Aspect | Finding |
|--------|---------|
| Async consistency | [VERIFIED] All LLM calls `async/await`. No sync-over-async. |
| Backpressure | [VERIFIED] SSE: `Queue(maxsize=256)`. LLM: semaphore(30). Events: drops oldest 10%. |
| Gather safety | [VERIFIED] All 34 `asyncio.gather` sites use `return_exceptions=True`. |

### 4.3 State & Context

| Aspect | Finding |
|--------|---------|
| Session state | [VERIFIED] `PipelineState` per run, pure data, descriptor access. |
| Context propagation | [VERIFIED] Explicit via params. `_current_emitter` ContextVar for deep callers. |
| Memory | [VERIFIED] `neuro/` subsystem for external recall/learn. |

### 4.4 Failure Semantics

| Aspect | Finding |
|--------|---------|
| Retry | [VERIFIED] Per-phase retry budget with configurable timeout. |
| Fallback | [VERIFIED] `router.on_fallback` captures and replays into state. |
| Partial failure | [VERIFIED] Non-critical phases continue; critical abort DAG. |

### 4.5 Scalability

| Bottleneck | Assessment |
|------------|-----------|
| Centralized orchestrator | [VERIFIED] Single `execute_run()`. Acceptable for current worker model. |
| LLM concurrency | [VERIFIED] Semaphore(30), httpx pool(max_connections=100). |
| SSE buffer | [VERIFIED] Queue(maxsize=256) with backpressure. |

---

## Phase 5 — Anti-Pattern Detection

| Pattern | Evidence | Severity |
|---------|----------|----------|
| God module (RESOLVED) | `pipeline_state.py`: 1245→671 lines | ✅ |
| God module (RESOLVED) | `streaming.py`: 969→269 lines | ✅ |
| Infrastructure leakage (RESOLVED) | core→infra: 3 leaks→0 | ✅ |
| Orchestrator bottleneck | Single `execute_run()` drives pipeline | MEDIUM — inherent |
| Premature abstraction | `PipelineExecutionPort` with single impl | LOW — justified for DI boundary |
| JSON file state | `pipeline_owners.json` (empty) | LOW |

---

## Phase 6 — Executive Summary

**ARCHITECTURE SCORE: 9 / 10**

- 10 = All layers correctly separated, patterns consistent, observable, testable, scalable
- **9 = Minor drift: 1 observability lazy import in core, 1 orchestrator bottleneck (inherent)**

**MATURITY LEVEL: Production**

Clean layer boundaries enforced by import-linter CI. Dependency inversion at three boundaries. All gather sites hardened. Deprecation resolved. Observability spans enriched. SSE backpressure. 24 tests.

**PRIMARY RISKS:**

1. **Centralized orchestrator** — single `PipelineExecutionService.execute_run()` is the only execution path. Under 10x load, becomes bottleneck. Mitigation: worker separation (refactoring roadmap).
2. **SSE queue backpressure untested under load** — `Queue(maxsize=256)` is theoretically correct but not load-tested.
3. **DI setters non-atomic** — `set_build_provider()`/`set_searxng_circuit_breaker()` are single-assignment, called once at startup. Safe in practice.

**CRITICAL VIOLATIONS: None.**

**REFACTOR URGENCY: Backlog** — No blocking issues. Current architecture supports production deployment.

---

## Phase 7 — Refactoring Roadmap

### Immediate (none required)

No critical or high violations remain.

### High-Impact (next sprint)

| Finding | Action | Outcome |
|---------|--------|---------|
| P4.5 | Add load test for SSE queue backpressure | Verify Queue(maxsize=256) handles sustained slow consumers |
| P4.5 | Add multi-worker integration test | Verify cross-worker cancellation and HyperGate L2 cache |

### Long-Term (architectural evolution)

Target-state: worker separation

```
Current:                          Target:
[FastAPI + Pipeline in one]       [API Gateway] → [Pipeline Worker(s)]
                                  Separate SSE bridge, message queue
```

Migration sequence: (1) Extract pipeline into standalone service, (2) Redis Streams as work queue, (3) Scale workers horizontally. Risk: Medium.

### Switching Triggers

| Condition | Action |
|-----------|--------|
| 8+ concurrent workers | Move pipeline to separate worker process |
| Phase count exceeds 100 | Lazy-load phase registry |
| Multi-region deployment | Cross-region provider routing |
