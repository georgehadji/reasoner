<!-- Generated: 2026-06-11 | Files scanned: 380 | Token estimate: ~800 -->

# Architecture — Reasoner (v3.0 Post-Refactor)

## System Type
Monorepo: Python 3.12 backend (FastAPI) + Next.js 16 frontend + SearXNG search

## Deployment Model
- **Backend:** Uvicorn (async FastAPI) on port 8003
- **Frontend:** Next.js App Router on port 3000
- **Search:** SearXNG (Docker) on port 8080
- **Persistence:** SQLite (default) or PostgreSQL (production)
- **Cache:** Redis (optional, for multi-worker rate limiting)
- **Memory:** Neuro L1/L2/L3 tiered (in-process + disk + remote)

## High-Level Data Flow

```
User (Browser - Next.js 16)
  │ SSE / WebSocket / REST
  ▼
FastAPI (uvicorn :8003)
  │
  ├─ CSRF Validation (HMAC-SHA256)
  │  └─ Rate Limiter (token-bucket per IP)
  │
  ├─ PipelineOrchestrator.preflight()
  │  ├─ HyperGate: 5 sub-agents in parallel
  │  │  ├─ LanguageDetector
  │  │  ├─ ComplexityEstimator
  │  │  ├─ DirectDetector
  │  │  ├─ WebSearchDetector
  │  │  ├─ MethodClassifier
  │  │  └─ TieBreaker (resolve conflicts)
  │  ├─ Fast-path regex checks (before LLM)
  │  ├─ Preset resolution + router construction
  │  └─ Neuro recall (long-term memory)
  │
  ├─ Decision: DIRECT | WEB_SEARCH | PIPELINE
  │  ├─ DIRECT → Instant answer (fastest model)
  │  ├─ WEB_SEARCH → Research method with SearXNG
  │  └─ PIPELINE → Full 6-phase reasoning
  │
  ├─ PipelineOrchestrator.execute()
  │  └─ ReasonerPipeline.run()
  │     ├─ Phase 0: Classification (task_type, language, complexity)
  │     ├─ Phase 1: Decomposition (≤5 sub-problems, failure modes)
  │     ├─ Phase 2: Multi-Perspective Generation (parallel, 3-4 labs)
  │     ├─ Phase 3: Critique & Pruning (independent scoring 0-10, top-k)
  │     ├─ Phase 4: Stress Testing (optimal/constraint/adversarial scenarios)
  │     └─ Phase 5: Synthesis (VERIFIED/HYPOTHESIS/UNKNOWN + blueprint)
  │
  ├─ PipelineOrchestrator.postflight()
  │  ├─ Neuro learn (save synthesis to L1/L2/L3)
  │  ├─ Event persist (domain events → SQLite)
  │  ├─ History save (user query log)
  │  └─ Metrics update (cost, tokens, duration)
  │
  ├─ Event Bus (CQRS)
  │  ├─ HistorySubscriber
  │  ├─ WebSocketSubscriber (broadcast to frontend)
  │  ├─ NeuroSubscriber (extract memory)
  │  └─ MetricsSubscriber (track costs)
  │
  └─ SSE stream phases → Chat UI (real-time render)

Infrastructure Layer
  ├─ LLM Providers (131 models, 12 direct adapters + OpenRouter)
  ├─ Search (SearXNG, Perplexity Sonar, BM25)
  ├─ Persistence (SQLite events, PostgreSQL audit)
  ├─ Redis (cache, rate limiter, circuit breaker)
  └─ WebSocket (real-time event broadcasting)
```

## Dependency Rule (Hexagonal DDD)

```
Interfaces → Infrastructure → Application → Core/Domain
Domain ←→ Core (only)
Core has zero outward dependencies
```

**Layer Ordering:**
1. **Interfaces** — `api/`, `main.py` (HTTP/CLI entry)
2. **Application** — `application/`, `orchestrator.py` (CQRS, flows, services)
3. **Domain** — `domain/` (state, presets, business logic)
4. **Core** — `core/` (ports, events, constants)
5. **Infrastructure** — `infrastructure/` (providers, persistence, search)

**Known Violations:**
- `domain/preset_core.py` imports `infrastructure.llm.registry` (model validation)
- `api/streaming.py` directly instantiates `ReasonerPipeline` (should route through CQRS)
- `application/flows/__init__.py` imports `api.serializers` (backward compat)

## Service Boundaries

| Service | Port | Transport | Purpose |
|---------|------|-----------|---------|
| FastAPI backend | 8003 | HTTP/SSE/WebSocket | Main API |
| Next.js frontend | 3000 | HTTP | Chat UI |
| SearXNG | 8080 | HTTP (Docker) | Meta-search |
| Neuro LTM | in-process | internal | Memory |
| Redis | 6379 | TCP | Cache + rate limit (optional) |
| PostgreSQL | 5432 | TCP | Audit log (optional) |

## Key Architectural Patterns

### Hexagonal Architecture (Ports & Adapters)
- **Ports:** `core/ports/` define abstract interfaces (LLMPort, SearchPort, FileSearchPort)
- **Adapters:** `infrastructure/` implements ports (31+ LLM providers, SearXNG, Perplexity)
- **Domain:** Business logic depends on ports, not concrete adapters

### Event Sourcing
- **Immutable events:** `core/events/domain_events.py` defines 18 event types
- **Event store:** SQLite append-only `events` table
- **Snapshots:** `PipelineSnapshot` for fast recovery from checkpoint
- **Subscribers:** CQRS subscribers react to domain events (history, WebSocket, metrics)

### CQRS (Command Query Responsibility Segregation)
- **Commands:** RunPipelineCommand, ResumePipelineCommand, etc. → handlers in `application/handlers/`
- **Queries:** GetPipelineQuery, GetHistoryQuery, etc.
- **Event bus:** Domain events flow from command handlers to subscribers

### Strategy Pattern (Methods)
- **19 reasoning methods:** Each method is a Strategy implementation (Debate, Jury, Research, etc.)
- **Flow registry:** `application/flows/__init__.py` binds method names to phase functions
- **Mixins:** `application/mixins/` contain method-specific phase logic
- **Presets:** `domain/preset_registry.py` configures method + model routing for 49 presets

### Dependency Injection (implicit via application layer)
- **Orchestrator:** Single entry point, orchestrates all dependencies
- **Router:** `infrastructure/llm/router.py` injects correct LLM adapter based on role
- **Services:** `application/services/` are singleton-like (preset, search, render)

## Reasoning Methods (19)

| # | Method | Phases | Complexity | Best For |
|---|--------|--------|-----------|----------|
| 1 | **Orchestrated** | 6 (0-5) | High | Default, balanced reasoning |
| 2 | **Debate** | 6 | High | Controversial topics, multiple perspectives |
| 3 | **Jury** | 6 | High | Expert consensus, complex judgment |
| 4 | **Research** | 6 + Prism | Very High | Fact-intensive, real-time data needed |
| 5 | **Scientific** | 6 | High | Empirical validation, hypothesis testing |
| 6 | **Socratic** | 6 | Medium | Assumption exposure, questioning |
| 7 | **Pre-Mortem** | 6 | Medium | Risk mitigation, failure analysis |
| 8 | **Bayesian** | 6 | Medium | Belief updating, probabilistic reasoning |
| 9 | **Dialectical** | 6 | Medium | Thesis-antithesis-synthesis |
| 10 | **Analogical** | 6 | Medium | Cross-domain mapping |
| 11 | **Delphi** | 6 | Medium | Expert consensus, forecasting |
| 12 | **CoVE** | 6 | Medium | Verification, hallucination reduction |
| 13 | **SoT** | 6 | Medium | Skeleton decomposition |
| 14 | **ToT** | 6 | High | Tree search with backtracking |
| 15 | **PoT** | 6 | High | Code-based reasoning |
| 16 | **Self-Discover** | 6 | Very High | Dynamic module composition |
| 17 | **Writing** | Custom | Low | Creative writing |
| 18 | **Brainstorming** | Custom | Low | Idea generation |
| 19 | **Coding** | Custom | High | Code generation + review |

## Preset Tiers (49 total)

| Tier | Count | Cost | Model Strategy | Use Case |
|------|-------|------|-----------------|----------|
| **Budget** | 19 | <$0.05 | 1-2 labs, cost-optimized | Exploration, quick answers |
| **Premium** | 19 | $0.15–$0.30 | 3-4 labs, top-tier | Complex reasoning, publication-ready |
| **Balanced** | 6 | $0.05–$0.10 | 2-3 labs | Production default |
| **Experimental** | 5 | Varies | New method pilots | R&D |

## Key Entry Points

- `src/reasoner/api/__init__.py` — FastAPI app factory, CORS, middleware, route mounting
- `src/reasoner/asgi.py` — ASGI app for uvicorn
- `src/reasoner/api/streaming.py` — Core SSE handlers (`run_stream()`, `run_followup_stream()`)
- `src/reasoner/application/orchestrator.py` — 3-phase orchestration (preflight/execute/postflight)
- `src/reasoner/application/pipeline.py` — ReasonerPipeline (phase execution)
- `src/reasoner/hypergate/hyperagent.py` — HyperGate decision tree (5 sub-agents + TieBreaker)
- `src/reasoner/main.py` — CLI entry point
- `ui-next/src/app/layout.tsx` — Next.js root layout
- `ui-next/src/app/chat/page.tsx` — Primary chat interface
- `start_all.py` — Dev launcher (backend + frontend + SearXNG)

## Cross-Layer Communication

**Request Path:**
```
HTTP/SSE → api/streaming.py → PipelineOrchestrator.preflight()
        → HyperGate decision
        → ReasonerPipeline.run()
        → Phase execution (with LLM calls via ProviderRouter)
        → PipelineOrchestrator.postflight()
        → Event bus subscribers
        → SSE/WebSocket response
```

**Event Path:**
```
Domain event (e.g., PhaseCompleted)
  → EventBus.emit()
  → Subscribers react
    ├─ HistorySubscriber → save to PostgreSQL
    ├─ WebSocketSubscriber → broadcast to frontend
    ├─ NeuroSubscriber → extract + store in L1/L2/L3
    └─ MetricsSubscriber → update cost/token gauges
```

## Observability Instrumentation

**Metrics (Prometheus):**
- `reasoner_pipeline_cost_usd` — Cost gauge
- `reasoner_pipeline_tokens_total` — Token count
- `reasoner_pipeline_duration_seconds` — Execution time
- `reasoner_active_users` — Gauge (updated every 60s via background task)

**Tracing (Langfuse):**
- All LLM calls traced (if `LANGFUSE_*` keys present)
- Critical validation in production (missing keys → warning)

**Logging (SafeLoggingFilter):**
- Redacts API keys, tokens, PII automatically
- Applied globally via `logging.getLogger().addFilter(SafeLoggingFilter())`

**Errors (Sentry):**
- Initialized in `api/sentry.py`
- Captures unhandled exceptions with breadcrumbs

## Security Model

**Defense in Depth:**
1. CSRF token validation (HMAC-SHA256)
2. Auth token check (OAuth2 JWT, scoped permissions)
3. Rate limiting (token-bucket per IP, Memory/Redis modes)
4. Input sanitization (XSS, null-bytes, prompt-injection regex, NFKC)
5. Prompt injection defense (regex patterns block suspicious templates)
6. Circuit breaker (auto-fallback on LLM provider failures)
7. Error masking (generic 500 to client, full logs on server)
8. Envelope encryption (AES-256-GCM for PII)
9. Blind indexing (searchable encrypted fields)

## Production Considerations

**Scaling:**
- Multi-worker mode requires **Redis for rate limiter** (not memory mode)
- Event store on PostgreSQL for distributed event persistence
- WebSocket broadcasting requires shared event bus (not in-memory)

**Reliability:**
- Circuit breaker on all LLM providers (fallback chain)
- Event sourcing enables state recovery and audit trails
- Snapshots for fast recovery from checkpoints

**Monitoring:**
- Langfuse integration for LLM observability (production requirement)
- Prometheus metrics for cost + token tracking
- Sentry for error alerting
- Background task updates active user gauge every 60s
