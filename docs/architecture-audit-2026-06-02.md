# REASONER v2.2 — Architecture Audit Report

**Auditor**: Senior Software Architect  
**Date**: 2026-06-02  
**Scope**: Full codebase — `src/reasoner/`, `tests/`, `ui-next/`, CI/CD, infrastructure  
**Methodology**: Deep static analysis + architectural consistency validation + layer-boundary enforcement check  
**Evidence basis**: Direct file reads of 40+ key modules; cross-layer import pattern search (200+ files); metrics via code execution

---

## 1. Executive Summary

### Overall Architecture Score: **5.8 / 10**

| Dimension | Score | Assessment |
|-----------|-------|------------|
| Layered Architecture Enforcement | 5/10 | Core/Domain boundaries decent; application & API layers leak |
| CQRS / Event Sourcing | 4/10 | Commands/queries defined but handlers unused; dual-state split |
| Hexagonal / Ports & Adapters | 6/10 | Good port abstractions (LLM, search); but streaming bypasses services |
| Composition / Strategy Pattern | 7/10 | Mixin→WorkflowStrategy migration complete; factory clean |
| Infrastructure Quality | 7/10 | ProviderRouter is well-built; Redis/persistence solid; config leakage |
| API Design | 5/10 | SSE streaming well-structured but 1100+ line file; init file 1000+ lines |
| Testing Architecture | 5/10 | pytest config solid; test structure unclear; CI gates aspirational |
| Observability | 5/10 | Prometheus metrics defined; Sentry wired; Langfuse subscriber exists |
| Security | 6/10 | Auth/CSRF/rate-limit/sanitization all present; layered but scattered |
| Dependency Health | 5/10 | No circular imports detected; 105 files import models.py (shared kernel) |

### Architectural Maturity Level: **Adolescent (Transitioning)**

The codebase is actively undergoing a significant architectural refactoring from mixin-based monolith to strategy-pattern composition. This transition is ~90% complete. However, the documentation (AGENTS.md) describes an architecture that no longer exists (mixins directory deleted), and the CQRS/event-sourcing layer is a "nice-to-have" adjunct that the actual pipeline execution ignores.

### Primary Risks (Top 5)
1. **Documentation drift** — AGENTS.md describes 14 mixins that no longer exist; CQRS/ES claims are aspirational
2. **PipelineAggregate / PipelineState split** — Two parallel state representations create consistency risk
3. **streaming.py God Function** — `run_stream()` is 400+ lines of orchestration mixed with SSE I/O
4. **Settings bypass** — 15+ files read `os.environ`/`os.getenv` directly, bypassing `core/settings.py`
5. **models.py shared kernel** — 1648 lines, imported by 105 files; coupled to parsing, rendering, phases

### Refactor Urgency Assessment: **MODERATE — Not blocking, but accumulating technical debt**

The system functions correctly in production and has strong fundamentals. The identified issues are architectural hygiene problems that will increase maintenance cost and onboarding friction over time. No single violation is production-critical today, but the compound effect of documentation drift + streaming.py bloat + dual state management will degrade velocity within 6–12 months.

---

## 2. Intended vs Actual Architecture

### Intended (from AGENTS.md + code comments)

```
┌─────────────────────────────────────────┐
│  api/          FastAPI routes/SSE       │
├─────────────────────────────────────────┤
│  application/  CQRS handlers, event bus │
│  application/  flows (WorkflowStrategy) │
│  application/  services                 │
├─────────────────────────────────────────┤
│  domain/       Domain models            │
├─────────────────────────────────────────┤
│  core/         Protocols, events, const │
├─────────────────────────────────────────┤
│  infrastructure/ LLM, DB, Redis, auth   │
└─────────────────────────────────────────┘
     ↑ Dependency direction (inward)
```

Plus:
- Event Sourcing: PipelineAggregate + EventStore + EventBus
- CQRS: application/commands/ + application/queries/ + application/handlers/
- 14 Mixins composing method-specific behavior via PipelineMixinProtocol
- Hexagonal ports: LLM abstraction, search abstraction

### Actual (from code analysis)

```
┌────────────────────────────────────────────────────────┐
│  api/__init__.py (1067 lines — endpoints, middleware,   │
│                  DI, health, billing, metrics ALL here) │
│  api/streaming.py (1133 lines — entire pipeline         │
│                    orchestration, retry, quality,       │
│                    neuro recall, history, SSE I/O)      │
├────────────────────────────────────────────────────────┤
│  pipeline.py (373 lines — core orchestrator)            │
│  models.py  (1648 lines — shared kernel, 105 importers) │
├────────────────────────────────────────────────────────┤
│  application/flows/ (31 files — Strategy pattern ✓)    │
│  application/commands/  (message types only — NO exec)  │
│  application/queries/   (message types only — NO exec)  │
│  application/handlers/  (CQRS handlers — used? PARTIAL)│
│  application/mixins/    (DELETED — directory gone)      │
├────────────────────────────────────────────────────────┤
│  core/ (protocols, events, aggregates, constants)       │
│  domain/ (preset registry, SaaS models)                 │
├────────────────────────────────────────────────────────┤
│  infrastructure/ (LLM router ✓, event store ✓,          │
│                   Redis ✓, auth, billing, websocket)    │
└────────────────────────────────────────────────────────┘
```

### Key Drifts

| Claim | Reality | Severity |
|-------|---------|----------|
| "14 mixins with PipelineMixinProtocol" | Directory `application/mixins/` does not exist. Removed during WorkflowStrategy migration. | **DOC-BUG** |
| "CQRS — Separate command and query handlers" | Commands/queries are message-type dataclasses. Handlers exist in `application/handlers/` but the pipeline never calls them. Pipeline uses `ReasonerPipeline.run()` directly. | **HIGH** |
| "Event Sourcing — State derived from domain events" | PipelineAggregate is event-sourced but only in the (unused) handler path. Actual execution uses PipelineState, a mutable dataclass with 50+ flat property aliases. | **HIGH** |
| "core/ — zero I/O, no infrastructure deps" | `core/search.py` reads `os.environ` directly for SEARXNG_URL. `core/settings.py` reads ALL env vars at class-load time. | **MEDIUM** |
| "SSE for data, WebSocket ONLY for control" | Substantially correct. WebSocket routes handle stop/status. SSE carries all phase data. Minor: `_broadcast_ws` in streaming.py sends phase_start/complete as WS broadcasts too. | **LOW** |

---

## 3. Architecture Compliance Matrix

| Module / Layer | Intended Pattern | Actual Implementation | Violations | Severity |
|---|---|---|---|---|
| **core/protocol.py** | Phase Protocol, PhaseConfig, PhaseResult | Clean frozen dataclasses, TypeVar usage. Protocol is `@runtime_checkable`. Correct. | None | — |
| **core/constants.py** | Single source of truth, pure constants | 479 lines. Contains system prompts (GATE_SYSTEM_PROMPT etc.), image gen config, article config, model aliases. Mixed concerns. | Shared kernel becoming dumping ground | MEDIUM |
| **core/settings.py** | Single `.env` reader | Well-structured Settings class with typed properties. But `_ensure_dotenv()` runs at import time — side effect. | Import-time side effect | LOW |
| **core/events/** | Domain event definitions | 18 event types, frozen dataclasses, factory function, registry maps. Well-designed. | None | — |
| **core/aggregates/** | Event-sourced aggregates (DDD) | PipelineAggregate + WidgetAggregate. Proper apply() pattern. Good. | Not used in actual pipeline execution | HIGH |
| **domain/models.py** | Domain model definitions | TaskType, ClaimLabel, PerspectiveType enums. Clean. | None | — |
| **domain/preset_registry.py** | Preset definitions | Complex nested structure. Contains model routing, price tiers. | Closely coupled to infrastructure/llm/registry | MEDIUM |
| **application/commands/** | Command definitions (CQRS) | 9 command dataclasses. Frozen, typed. Good message design. | Never instantiated in pipeline path | MEDIUM |
| **application/queries/** | Query definitions (CQRS) | 11 query dataclasses. Frozen, typed. Good message design. | Never instantiated in pipeline path | MEDIUM |
| **application/handlers/** | CQRS handlers | RunPipelineCommandHandler etc. exist. PipelineAggregate used here. | Pipeline bypasses handlers entirely | HIGH |
| **application/mixins/** | Method-specific mixin composition | **Directory deleted**. Code removed. | AGENTS.md still documents this | DOC-BUG |
| **application/flows/** | WorkflowStrategy composition | 20 strategies registered. WorkflowFactory clean. Base protocol well-defined. | Migration from mixins is complete ✓ | — |
| **application/event_bus/** | In-memory pub/sub event bus | Full implementation: queue worker, backpressure (1000 max), dead-letter, retry (3x), Langfuse subscriber. | Bus started in API lifespan; used for log/metrics only, not domain state | MEDIUM |
| **application/services/** | Application services | PresetService, PipelineService, SearchService properly abstracted. | PipelineService.create_pipeline() just wraps ReasonerPipeline constructor — thin | LOW |
| **infrastructure/llm/** | Provider abstraction (ports & adapters) | BaseLLMProvider ABC, ProviderRouter with circuit breaker + fallback, model registry, executor with caching. Well-architected. | OpenAiCompatibleProvider is the only concrete provider — tightly coupled | LOW |
| **infrastructure/persistence/** | Event store, snapshots, feedback, errors | SQLite EventStore with thread-pool isolation. Proper migrations. FeedbackStore + ErrorStore. | EventStore not called by pipeline.py; called from streaming.py SSE layer | MEDIUM |
| **infrastructure/redis/** | Redis client, RunStateManager | Shared connection pool, proper close. Run cancellation via asyncio.Event. | `_run_state_manager` accessed globally in 5+ files without DI | MEDIUM |
| **api/__init__.py** | FastAPI app factory | 1067 lines. Contains: app creation, lifespan, CORS, auth, rate limit, ALL endpoints, health check, feedback, error reporting, billing. | Should be split into separate route modules | HIGH |
| **api/streaming.py** | SSE streaming generators | 1133 lines. Contains: pipeline orchestration, phase execution loop, retry logic, quality monitoring, neuro recall, history persistence, caching, HyperGate routing, creative writing fallback chain. | Contains business logic that belongs in application/ services | HIGH |
| **phases/** | Method-specific phase implementations | 31 modules. Mix of old-style (direct LLM calls) and new-style (through application/flows). | Inconsistent: some use phases directly, some use flows | MEDIUM |
| **hypergate/** | Pre-routing agent | 6 parallel sub-agents + tie-breaker. LRU caching per agent. Properly structured. | Integrated into streaming.py run_stream, not pipeline.py | MEDIUM |

---

## 4. Dependency Analysis

### Circular Dependencies
- **None detected.** The codebase has no import cycles. This is a significant positive finding.

### Boundary Violations

**CRITICAL:** `api/streaming.py` imports from:
- `reasoner.infrastructure.llm.router` (ProviderRouter)
- `reasoner.infrastructure.llm.registry` (_REGISTRY)  
- `reasoner.infrastructure.redis.run_state` (_run_state_manager)
- `reasoner.infrastructure.persistence.event_store` (get_event_store)

This is the SSE streaming layer directly reaching into infrastructure. It should go through application services.

**HIGH:** `core/search.py` imports `os.environ` for SEARXNG_URL (line 584, 600). Core layer should not read environment directly.

**MEDIUM:** 15+ files bypass `core/settings.py` and read `os.environ`/`os.getenv` directly:
- `api/__init__.py` (10+ instances for MEMORY_LIMIT_MB, ENVIRONMENT, APP_URL, etc.)
- `api/billing_router.py` (APP_URL)
- `api/csrf.py` (CSRF_SECRET)
- `api/dependencies.py` (ENVIRONMENT, DB_POOL_SIZE)
- `api/sentry.py` (SENTRY_DSN, ENVIRONMENT)
- `auth.py` (ADMIN_API_KEY)
- `application/event_bus/bus.py` (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)
- `application/flows/search_phases.py` (REASONER_DEEP_READ_LLM)

### Shared-State Risks
- `_event_bus` global singleton (application/event_bus/bus.py)
- `_event_store` global singleton (infrastructure/persistence/event_store.py)
- `_run_state_manager` global accessed in 5+ files
- `_REGISTRY` module-level dict (infrastructure/llm/registry.py) — 200+ model entries
- `_preset_service` module-level singleton (api/streaming.py)

All singletons use lazy initialization pattern; thread-safe but create hidden coupling.

### Tight Coupling Hotspots

| File | Imported By | Risk |
|------|-------------|------|
| **models.py** | 105 files | Shared kernel anti-pattern — every module depends on it |
| **core/constants.py** | 50+ files | Growing dumping ground (system prompts, image gen config, article config) |
| **pipeline.py** | 20+ files | Central orchestrator — reasonable but creates hard dependency |
| **phases/_shared.py** | 30+ phase modules | Utility module with detect_language, build_followup_context — acceptable |

### File Metrics

| File | Lines | Assessment |
|------|-------|------------|
| models.py | 1,648 | Too large. Contains PipelineState (300+ lines of property aliases), 20+ dataclass types, serialization. Should be split into per-domain modules. |
| api/streaming.py | 1,133 | Too large for an SSE streaming module. ~400 lines of pipeline orchestration should move to application/flows/runner.py. |
| api/__init__.py | 1,067 | Too large for __init__.py. All endpoint definitions should be in api/routes/. |
| core/constants.py | 479 | Acceptable size but mixed concerns (prompts + limits + model aliases + image gen config). |
| pipeline.py | 373 | Good size. 11 methods is modest for an orchestrator. |

---

## 5. AI Orchestrator Specific Review

### Agent Orchestration Model
- **Primary orchestrator**: `ReasonerPipeline` (pipeline.py) — strategy-dispatched via WorkflowFactory
- **Pre-router**: `HyperGateAgent` (hypergate/) — 6 parallel sub-agents for language/complexity/direct/web/method detection
- **Phase sub-agents**: `subagents/` directory — enhancement, decomposition, critique, synthesis, search hyper-agents
- **Quality gate**: `PhaseMonitor` (quality/) — post-phase evaluation with judge models

**Assessment (6/10)**: The orchestration flow is clear but has two entry points. `ReasonerPipeline.run()` handles CLI/direct invocation; `api/streaming.py:run_stream()` handles SSE-based execution. They share the same underlying pipeline but duplicate orchestration logic (phase loop, retry, quality check).

### Workflow Coordination
- `WorkflowFactory` registers 20 methods → dispatches to `WorkflowStrategy` implementations
- Each strategy declares phases via `get_phases()` → returns list of `(num, name, fn, serializer)`
- Phase execution loop in streaming.py iterates phases with retry, timeout, and quality gates
- Method state isolated in `PipelineState.method_state` dict (per-method namespace)

**Assessment (7/10)**: The strategy pattern is well-implemented. The phase declaration as a list of tuples is simple and effective. However, phase execution (retry/timeout/quality) is duplicated in streaming.py rather than being extracted into a `PhaseExecutor` service.

### Message/Event Architecture
- **Domain events**: 18 event types defined (core/events/domain_events.py) — frozen dataclasses, proper factory
- **Event bus**: Full pub/sub with queuing, backpressure, dead-letter, retry
- **Event store**: SQLite append-only log with aggregate snapshots
- **Actual usage**: Events published from streaming.py (not pipeline.py). Handlers subscribed for logging + metrics + Langfuse. Events NOT used for state derivation in the main execution path.

**Assessment (5/10)**: The event infrastructure is solid but disconnected from the primary execution path. Events are a "side channel" for observability, not the source of truth for pipeline state.

### Memory/State Boundaries
- **PipelineState**: Mutable dataclass with 50+ property aliases. Sub-objects: PipelineCore, PipelineMeta, PipelineRemainder, MethodState, CostTrackingState, ConversationState. The sub-object decomposition (v2 refactor) is good.
- **PipelineAggregate**: Event-sourced aggregate in core/aggregates/ — only used in CQRS handler path, not the main pipeline.
- **Neuro memory**: Long-term memory with embedding search, recall at pipeline start, learn at pipeline end.
- **RunStateManager**: Redis-backed cancellation tracking with asyncio.Event.

**Assessment (5/10)**: The state model has been recently refactored from flat to nested (good). However, the dual representation (PipelineState vs PipelineAggregate) creates a "two truths" problem.

### Retry/Failure Semantics
- **LLM level**: Exponential backoff in BaseLLMProvider.complete_with_retry (3 attempts)
- **Circuit breaker**: Per-model circuit breakers with configurable thresholds
- **Phase level**: Retry with quality monitoring in streaming.py (max_retries from PHASE_RETRY_BUDGETS)
- **Pipeline level**: Phase failures are non-fatal unless "critical" phase; errors accumulate in state.errors
- **Fallback chain**: ProviderRouter → explicit fallback → primary fallback → DegradedLLMResponse

**Assessment (8/10)**: This is one of the better-implemented areas. The layered retry (LLM → phase → pipeline) with circuit breaker and fallback chain is production-grade.

### Concurrency Model
- `asyncio.gather` for parallel perspectives
- `asyncio.wait(FIRST_COMPLETED)` for cancellable phase execution
- `asyncio.Semaphore(200)` for bounded event handler concurrency
- `ThreadPoolExecutor` for SQLite operations (avoids blocking event loop)
- `asyncio.create_task` for background workers (event bus worker, active users update)

**Assessment (7/10)**: Solid async patterns. The ThreadPoolExecutor isolation for SQLite is correct. Task lifecycle management is adequate but some fire-and-forget tasks (neuro learn, history save) lack error propagation.

### Multi-Agent Scalability
- 6 HyperGate sub-agents run in parallel (via asyncio.gather)
- Phase sub-agents are opt-in (feature-flagged via USE_PHASE_SUBAGENTS)
- ProviderRouter supports cascading routing (multiple models per role)
- No distributed agent coordination — single-process, single-worker design

**Assessment (5/10)**: The system is fundamentally single-process. Horizontal scaling requires Redis-backed state (rate limiter, circuit breaker, run state). Multi-worker mode exists but with documented caveats. Agent-to-agent communication is through shared PipelineState, not message passing.

---

## 6. Architectural Anti-Patterns

### GOD FUNCTIONS
- **`run_stream()` in api/streaming.py** (~400 lines): Orchestrates the entire pipeline lifecycle mixed with SSE I/O. Should be split into `PipelineOrchestrator` (application service) + SSE adapter.
- **`api/__init__.py`** (1067 lines): App factory, lifespan, ALL endpoints, health check, feedback, billing, error reporting, CORS, auth — everything in one file.

### HIDDEN MONOLITH
- **models.py (1648 lines)**: Imported by 105 files. Acts as a "shared kernel" that every module depends on. Contains PipelineState (with its 50+ property aliases for backward compat), 20+ dataclass types, serialization logic, and migration code. This is the #1 coupling hotspot.

### DUAL STATE (Anemic Domain Model)
- **PipelineState vs PipelineAggregate**: Two parallel representations of pipeline state. PipelineState is the "real" one (used in execution). PipelineAggregate is the "DDD-correct" one (used in the CQRS handler path that the pipeline never calls). They have different update semantics — PipelineState is mutated directly; PipelineAggregate is event-sourced. This is a classic "aspirational architecture" anti-pattern.

### DOCUMENTATION-DRIVEN ARCHITECTURE
- AGENTS.md documents 14 mixins in `application/mixins/` — this directory does not exist.
- AGENTS.md claims "CQRS — Separate command and query handlers" — they exist but are unused.
- AGENTS.md claims "Event Sourcing — Pipeline state derived from domain events" — this is only true for the (unused) handler path.

### ORCHESTRATOR BOTTLENECK
- ReasonerPipeline is the single orchestrator. While it dispatches to strategies, the `run()` method has a hardcoded sequence: enhance → fusion → strategy → post-verify. Adding a new phase to ALL methods requires modifying pipeline.py. The strategy pattern mitigates this somewhat, but the pre/post phases are not composable.

### INFRASTRUCTURE LEAKAGE
- Settings bypass: 15+ files call `os.environ`/`os.getenv` directly
- Core layer leak: `core/search.py` reads `os.environ["SEARXNG_URL"]`
- Streaming layer leak: `api/streaming.py` instantiates ProviderRouter, HyperGateAgent, and ReasonerPipeline directly

### PREMATURE ABSTRACTIONS
- **application/commands/__init__.py** and **application/queries/__init__.py**: Define 20+ message types that are never instantiated in the actual pipeline flow. These are well-designed but unused CQRS scaffolding.

---

## 7. Refactoring Roadmap

### Immediate Fixes (Week 1–2)

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 1 | **Update AGENTS.md** to reflect current architecture (remove mixin references, update CQRS/ES status to "partial") | Documentation accuracy | 30 min |
| 2 | **Extract `api/__init__.py` endpoints** into separate route files (health, feedback, billing, estimate, error-report, keys, csrf already in their own files — move the inline ones) | Code organization | 2 hrs |
| 3 | **Extract `PhaseExecutor` from streaming.py**: Move phase execution loop (retry, timeout, quality) into `application/flows/phase_lifecycle.py` | Separation of concerns | 3 hrs |
| 4 | **Consolidate env reading**: Route all `os.environ`/`os.getenv` calls through `core/settings.py` properties | Configuration architecture | 2 hrs |

### High-Impact Improvements (Month 1)

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 5 | **Decompose models.py**: Split PipelineState property aliases into a compatibility mixin; move GenerationCandidate/CriticScore/etc. into domain/; keep core types in models.py | Coupling reduction | 1 day |
| 6 | **Unify state management**: Decide whether PipelineAggregate (event-sourced) or PipelineState (mutable dataclass) is the canonical state. Remove the unused path. | Architectural clarity | 2 days |
| 7 | **Create `PipelineOrchestrator` application service**: Extract orchestration logic from streaming.py (HyperGate, preset resolution, phase loop, neuro recall) into an application service that streaming.py delegates to. | Layering | 2 days |
| 8 | **Wire DI consistently**: Replace global singletons (_event_bus, _event_store, _run_state_manager) with proper FastAPI dependency injection where possible. | Testability | 1 day |

### Long-Term Architecture Evolution (Quarter 1–2)

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 9 | **Implement event-sourced pipeline execution**: Make ReasonerPipeline.run() use PipelineAggregate + EventStore as the canonical state path, replacing PipelineState direct mutation. Events become the source of truth. | Event sourcing integrity | 1 week |
| 10 | **Extract HyperGate as a true pre-router service**: Currently embedded in streaming.py. Should be a standalone application service with its own interface. | Service boundaries | 2 days |
| 11 | **Add distributed agent coordination**: Enable multi-worker pipeline execution with Redis-backed phase queue. Current single-process model limits throughput. | Scalability | 1–2 weeks |
| 12 | **Implement proper OpenTelemetry tracing**: Span-based tracing across phases, LLM calls, and Neuro operations. Replace ad-hoc log-based phase tracking. | Observability | 1 week |
| 13 | **Extract a shared kernel package** (`reasoner.shared`): Move constants, base exceptions, and utility types out of `core/` into a proper shared kernel with explicit versioning. | Architecture hygiene | 3 days |

### Suggested Target-State Architecture

```
┌──────────────────────────────────────────────────────────┐
│  api/                                                     │
│  ├── routes/         (thin — delegates to services)       │
│  ├── middleware/     (security, audit, memory, timeout)   │
│  ├── streaming.py    (SSE adapter — I/O only)             │
│  └── dependencies.py (FastAPI DI wiring)                  │
├──────────────────────────────────────────────────────────┤
│  application/                                             │
│  ├── orchestrator/   (PipelineOrchestrator service)       │
│  ├── flows/          (WorkflowStrategy — exists ✓)        │
│  ├── services/       (PresetService, SearchService, etc.) │
│  ├── event_bus/      (EventBus — exists ✓)               │
│  └── handlers/       (CQRS handlers — WIRE INTO PIPELINE) │
├──────────────────────────────────────────────────────────┤
│  domain/                                                  │
│  ├── models/         (TaskType, ClaimLabel, Perspective)  │
│  ├── presets/        (PresetRegistry)                     │
│  └── pipeline/       (PipelineAggregate — CANONICAL)      │
├──────────────────────────────────────────────────────────┤
│  core/               (Protocols, ports, shared constants) │
├──────────────────────────────────────────────────────────┤
│  infrastructure/     (LLM, DB, Redis, auth, billing)      │
└──────────────────────────────────────────────────────────┘
```

**Key change**: `PipelineAggregate` becomes the canonical state. `PipelineOrchestrator` is the single entry point (used by both CLI and SSE). `streaming.py` is a pure SSE adapter with no business logic.

---

## 8. Confidence Assessment

### Verified Findings (Evidence-backed, high confidence)

- ✅ application/mixins/ directory does not exist
- ✅ 15+ files bypass core/settings.py for env reading
- ✅ PipelineAggregate only used in handlers, not pipeline execution
- ✅ models.py is 1648 lines, imported by 105 files
- ✅ api/__init__.py is 1067 lines
- ✅ api/streaming.py is 1133 lines
- ✅ WorkflowFactory registers 20 strategies
- ✅ Event bus is fully implemented (not a stub)
- ✅ Event store is fully implemented with thread-pool isolation
- ✅ ProviderRouter has circuit breaker + fallback chain
- ✅ No circular imports detected
- ✅ CI workflow exists but references legacy paths (health_check.py, pipeline.py → ARAPipeline)
- ✅ PipelineState has 50+ property aliases for backward compatibility

### Hypothesis Findings (Reasonable inference, medium confidence)

- ⚠️ The CQRS handlers were built for a future architecture that was never wired in (based on how pipeline.py never imports from application/handlers/)
- ⚠️ The mixin deletion was part of a deliberate v2.2 refactoring (based on pipeline.py comment: "Refactored to eliminate mixin-based God Object")
- ⚠️ Test coverage is below the 70% target (based on CI setting 60% fail, 80% warn gates)

### Areas Lacking Sufficient Evidence

- ❓ Actual test coverage percentage — CI gate is 60% fail, but actual coverage unknown
- ❓ Whether the healing/introspection_engine.py and test_generation_engine.py actually produce useful output
- ❓ Whether the Langfuse subscriber successfully sends traces in production
- ❓ Actual production deployment topology (single-worker vs multi-worker)
- ❓ Whether phase sub-agents (USE_PHASE_SUBAGENTS) are enabled in production or only dev
