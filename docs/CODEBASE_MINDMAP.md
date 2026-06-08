# CODEBASE_MINDMAP.md — Reasoner (ARA Pipeline v2.2 + HyperGate)

> High-fidelity architectural reconstruction.  
> Last updated: 2026-06-08  
> HyperGateAgent added: 2026-04-17

---

## 1. SYSTEM OVERVIEW

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              REASONER (ARA v2.2)                            │
│                    Adaptive Reasoning Architecture Pipeline                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  A multi-method reasoning engine that routes user problems through          │
│  16+ domain-specific phase pipelines, orchestrates LLM calls via            │
│  OpenRouter / Ollama / Anthropic / Google, performs web discovery           │
│  (SearXNG), and streams results back to a Next.js frontend over             │
│  Server-Sent Events (SSE).                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Classification of Entry Points

| Entry Point | File | Purpose |
|-------------|------|---------|
| **Web UI** | `ui-next/src/app/page.tsx` | Primary user interface (Next.js App Router) |
| **API Server** | `api.py` | FastAPI — SSE `/api/run`, auth, widgets, history, REST proxies |
| **CLI** | `main.py` | argparse-driven terminal runner with rich output |
| **Startup Orchestrator** | `start_all.py` | Boots FastAPI + optional SearXNG together |

### Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend Runtime** | Python 3.12, asyncio |
| **Web Framework** | FastAPI + uvicorn |
| **Frontend Framework** | Next.js, React 19, TypeScript 5 |
| **Styling** | Tailwind CSS 4, CSS variables (`--method-accent-rgb`) |
| **State (FE)** | Zustand (persisted to `localStorage`) |
| **LLM Routing** | OpenRouter REST API, Ollama local, Anthropic, Google GenAI |
| **Search** | SearXNG meta-search engine (`core/search.py`) |
| **Caching** | Disk-based JSON token cache (`cache/tokens/`) + SSE run cache (`cache/`) |
| **Persistence** | SQLite (default), optional PostgreSQL (`infrastructure/persistence/`) |
| **Testing** | pytest + pytest-asyncio |

---

## 2. STRUCTURAL VIEW

### 2.1 Top-Level Directory Map

```
Reasoner/
│
├── api.py                     ← FastAPI app & SSE orchestrator
├── main.py                    ← CLI entry point
├── pipeline.py                ← ARAPipeline core orchestrator
├── llm.py                     ← Provider abstraction, routing, retry logic
├── models.py                  ← Domain dataclasses (PipelineState, etc.)
├── phases.py                  ← Prompt templates for every method/phase
├── parsing.py                 ← Robust JSON extraction from LLM prose
├── presets.py                 ← 32 routing presets (budget/premium) + get_method_from_preset
├── renderer.py                ← Rich terminal output
├── widgets.py                 ← Legacy widget engine (weather, stocks, calc, search)
├── auth.py                    ← API key / admin auth
├── rate_limiter.py            ← Token-bucket rate limiting
├── circuit_breaker.py         ← Circuit breaker for LLM calls
├── token_cache.py             ← Disk-backed token-aware LLM response cache
├── scraper.py                 ← Web scraping for deep-read phase
├── exceptions.py              ← Custom exception hierarchy
├── sanitization.py            ← Input sanitization helpers
├── start_all.py               ← SearXNG + API startup orchestrator
│
├── gate_agent.py              ← Legacy GateAgent (preserved) + lazy HyperGateAgent re-export
├── hypergate/                 ← HyperGate multi-agent pre-router
│   ├── hyperagent.py          ← HyperGateAgent: Phase-1 gather → synthesize → optional Phase-2
│   ├── base_sub_agent.py      ← BaseSubAgent ABC: LLM wiring, per-class LRU cache, temperature guard
│   ├── models.py              ← SubAgentInput, SubAgentOutput (frozen), HyperContext
│   └── sub_agents/
│       ├── language_detector.py     ← ONE JOB: detect input language
│       ├── complexity_estimator.py  ← ONE JOB: simple / medium / complex
│       ├── direct_detector.py       ← ONE JOB: does this need a pipeline at all?
│       ├── web_detector.py          ← ONE JOB: is real-time web data required?
│       ├── method_classifier.py     ← ONE JOB: opaque taxonomy B–Q → method name
│       └── tie_breaker.py           ← ONE JOB: Phase-2 conflict resolution
│
├── core/                      ← Shared protocols, constants, search
│   ├── constants.py           ← Single source of truth: timeouts, budgets, URLs, aliases, HYPERGATE_* thresholds
│   ├── settings.py            ← One-time dotenv loader (Settings singleton)
│   ├── temperatures.py        ← Per-phase temperature registry
│   ├── search.py              ← SearXNG DiscoveryClient + smart_search
│   ├── protocol.py            ← Internal protocol definitions
│   ├── perspectives.py        ← Perspective type enums/helpers
│   ├── memory.py              ← Memory-related utilities
│   └── __init__.py
│
├── ui-next/                   ← Next.js frontend
│   ├── src/app/               ← App router (page.tsx, layout.tsx, globals.css)
│   │   └── api/               ← API routes: /api/run, /api/weather, /api/stocks, etc.
│   ├── src/components/        ← Chat, phases, layout, modals, widgets
│   ├── src/hooks/             ← SSE stream, scroll anchor, keyboard shortcuts
│   ├── src/stores/            ← Zustand app-store
│   └── src/lib/               ← Config, markdown builder, DB client, types
│
├── infrastructure/            ← Adapter layer (CQRS / event-sourcing / widgets)
│   ├── llm/
│   │   ├── ports.py           ← Port/adapter definitions for LLM providers
│   │   ├── new_pipeline.py    ← Alternative pipeline implementation
│   │   └── exceptions.py
│   ├── persistence/
│   │   ├── event_store.py     ← Event sourcing store
│   │   ├── snapshots.py       ← Snapshot persistence
│   │   └── postgres_store.py  ← PostgreSQL async pool
│   ├── websocket/
│   │   └── manager.py         ← WebSocket connection manager
│   └── widgets/
│       ├── protocol.py        ← Widget type definitions
│       ├── registry.py        ← Widget detection & dispatch
│       ├── weather.py
│       ├── stocks.py
│       ├── calculator.py
│       ├── discover.py
│       ├── image_search.py
│       └── video_search.py
│
├── application/               ← New-arch commands, handlers, event bus
│   ├── commands/__init__.py
│   ├── handlers/handlers.py
│   ├── event_bus/bus.py
│   └── queries/__init__.py
│
├── neuro/                     ← Long-term memory (Recall / Learn / compression)
│   ├── server.py
│   ├── providers.py
│   └── compression.py
│
├── healing/                   ← Auto-generated test collections / introspection
├── tests/                     ← pytest suites (36 files)
├── cache/                     ← SHA256-keyed JSON SSE caches + token cache
├── history/                   ← JSON run histories
└── uploads/                   ← File upload storage
```

### 2.2 Module Dependency Graph

```
                    ┌─────────────┐
                    │   presets   │
                    └──────┬──────┘
                           │ builds
                           ▼
┌────────┐    ┌─────────────────────┐    ┌─────────────┐
│ main.py│───►│   ProviderRouter    │◄───│    llm.py   │
│ api.py │    │     (llm.py)        │    └─────────────┘
└───┬────┘    └──────────┬──────────┘         ▲
    │                    │                    │
    │                    │ shared router      │
    │                    ▼                    │
    │         ┌──────────────────────────┐    │
    │         │   HyperGateAgent         │    │
    │         │   (hypergate/)           │    │
    │         │                          │    │
    │         │  Phase 1 (parallel):     │    │
    │         │  LanguageDetector        │    │
    │         │  ComplexityEstimator     │    │
    │         │  DirectDetector          │    │
    │         │  WebSearchDetector       │    │
    │         │  MethodClassifier        │    │
    │         │                          │    │
    │         │  Phase 2 (conditional):  │    │
    │         │  TieBreakerSubAgent      │    │
    │         └──────────┬───────────────┘    │
    │                    │ GateDecision        │
    │                    │ (action + method)   │
    │ routes to          ▼                    │
    ▼                    │ dispatches         │ implements
┌──────────────────────────────────────┐      │
│         ARAPipeline (pipeline.py)    │      │
│  ┌─────────┐ ┌─────────┐ ┌────────┐ │      │
│  │phases.py│ │models.py│ │parsing │ │      │
│  └────┬────┘ └────┬────┘ └───┬────┘ │      │
│       └───────────┴──────────┘      │      │
│                   ▼                  │      │
│         PipelineState (mutable)      │      │
└──────────────────────────────────────┘      │
         │ serializes to                      │
         ▼                                    │
   ┌─────────────┐                            │
   │  api.py SSE │────────────────────────────┘
   │   stream    │
   └──────┬──────┘
          ▼
   ┌─────────────┐
   │  ui-next    │
   │  (Next.js)  │
   └─────────────┘

Foundation layer (imported by almost everything):
   ┌─────────────┐   ┌─────────────┐
   │  constants  │   │   settings  │
   │  (incl.     │   │    (.py)    │
   │  HYPERGATE) │   │             │
   └─────────────┘   └─────────────┘
```

### 2.3 Layered Architecture

| Layer | Files | Responsibility |
|-------|-------|----------------|
| **Presentation** | `ui-next/src/app/page.tsx`, `renderer.py` | Render outputs to user (web + terminal) |
| **Interface/API** | `api.py`, `auth.py`, `rate_limiter.py`, `uploader.py`, `sanitization.py` | HTTP ingress, auth, rate limits, upload handling |
| **Pre-Pipeline Routing** | `gate_agent.py`, `hypergate/hyperagent.py`, `hypergate/sub_agents/*` | HyperGate: classify query intent and route to direct answer, web search, or specific pipeline method |
| **Application / Orchestration** | `pipeline.py`, `application/handlers/handlers.py`, `application/event_bus/bus.py` | Route requests, execute phase sequences, publish domain events |
| **Domain** | `models.py`, `phases.py`, `core/protocol.py`, `core/perspectives.py`, `presets.py` | Business entities, prompts, reasoning methods, preset configs |
| **Infrastructure** | `llm.py`, `core/search.py`, `token_cache.py`, `scraper.py`, `infrastructure/persistence/*`, `neuro/*`, `infrastructure/widgets/*` | External services, caching, persistence, widgets |
| **Foundation** | `core/constants.py`, `core/settings.py`, `core/temperatures.py` | Pure constants, env-aware settings, temperature registry |

---

## 3. BEHAVIORAL VIEW

### 3.1 Request/Response Lifecycle (Web Path)

```
1. User submits problem in Next.js Composer
         │
         ▼
2. POST /api/run  (JSON: problem, preset, top_k, sequential, source_type)
         │
         ▼
3. FastAPI: validate RunRequest → rate limit check → auth check
         │
         ▼
4. Cache lookup (SHA256 of request params)
   ├─ HIT  → replay cached SSE events
   └─ MISS → start new pipeline run
         │
         ▼
5. Build ProviderRouter from preset/routing
         │
         ▼
5a. HyperGateAgent.decide(problem)  [skipped if force_pipeline=True]
    ├── Phase 1: 5 sub-agents in parallel (asyncio.gather)
    │     LanguageDetector + ComplexityEstimator + DirectDetector
    │     + WebSearchDetector + MethodClassifier
    ├── _synthesize(): pure Python decision tree
    │     ├─ action="direct"     → answer immediately, emit virtual phase, done
    │     ├─ action="web_search" → run live search, return results
    │     └─ action="pipeline"   → continue to step 6 (method pre-selected)
    └── Phase 2 (if ambiguous): TieBreakerSubAgent
         │
         ▼
6. ARAPipeline.run(state)  ← mutates PipelineState across phases
   For each phase in method-specific sequence:
   a. Emit phase_start SSE
   b. Execute phase function (LLM call)
   c. Parse JSON response
   d. Mutate state
   e. Emit phase_complete SSE with serializer
         │
         ▼
7. Synthesis phase generates FinalSolution
         │
         ▼
8. Emit done SSE with total_tokens & phase_models
         │
         ▼
9. Persist HistoryEntry to history/ + TaggedMemory index
         │
         ▼
10. Write full SSE event list to cache/
         │
         ▼
11. Frontend renders phase cards progressively
```

### 3.2 Method-Specific Phase Sequences

| Method | Phase Sequence |
|--------|----------------|
| **multi-perspective** | 0 Classify → 1 Decompose → 1.5 Deep Read → 2 Perspectives → 3 Critique → 4 Stress → 5 Synthesis |
| **debate** | 0 → 1 → 1.5 → 2 Opening → 3 Rebuttals → 4 Judge → 5 Synthesis |
| **scientific** | 0 → 1 → 1.5 → 2 Hypotheses → 3 Falsification → 4 Stress → 5 Synthesis |
| **socratic** | 0 → 1 → 1.5 → 2 Questions → 3 Answers → 4 Synthesis |
| **research** | 0 → 1 → 2 Deep Research → 3 Perspectives → 4 Critique → 5 Synthesis |
| **jury** | 0 → 1 → 1.5 → 2 Generation → 3 Critique → 4 Verification/Meta → 5 Ranking → 6 Synthesis |
| **iterative** | 0 → 1 → 1.5 → 2 R1-Gen → 3 R1-Crit → 4 R2-Ref → 5 R2-Crit → 6 R3-Fin → 7 R3-Crit → 8 Synthesis |
| **pre-mortem** | 0 → 1 → 1.5 → 2 Failure → 3 Backtrack → 4 Signals → 5 Redesign → 6 Synthesis |
| **cove** | 0 → 1 → 1.5 → 2 Draft → 3 Verify → 4 Answer → 5 Revise → 6 Synthesis |
| **sot** | 0 → 1 → 1.5 → 2 Skeleton → 3 Parallel Solve → 4 Assemble → 5 Synthesis |
| **tot** | 0 → 1 → 1.5 → 2 Decompose → 3 Generate → 4 Evaluate → 5 Select → 6 Synthesis |
| **pot** | 0 → 1 → 1.5 → 2 Code Gen → 3 Execute → 4 Interpret → 5 Synthesis |
| **self-discover** | 0 → 1 → 1.5 → 2 Select Modules → 3 Adapt → 4 Execute → 5 Reflect → 6 Synthesis |
| **bayesian** | 0 → 1 → 1.5 → 2 Priors → 3 Likelihood → 4 Posterior → 5 Sensitivity → 6 Synthesis |
| **dialectical** | 0 → 1 → 1.5 → 2 Thesis → 3 Antithesis → 4 Contradictions → 5 Aufhebung → 6 Synthesis |
| **analogical** | 0 → 1 → 1.5 → 2 Abstraction → 3 Domain Search → 4 Mapping → 5 Transfer → 6 Synthesis |
| **delphi** | 0 → 1 → 1.5 → 2 R1 → 3 Aggregation → 4 R2 → 5 Convergence → 6 Dissent → 7 Synthesis |

### 3.3 Data Flow: LLM Call Within a Phase

```
Phase Function (pipeline.py)
         │
         ▼
_call_llm_cached(role, system_prompt, user_prompt, state, ...)
         │
         ├─ 1. Check token_cache (disk cache keyed by hash)
         │      ├─ HIT → return cached response, log tokens
         │      └─ MISS → continue
         │
         ▼
         ├─ 2. ProviderRouter.call(role, ...)
         │         │
         │         ▼
         │   OpenRouterProvider.complete()  OR  OllamaProvider.complete()
         │         │
         │         ▼
         │   httpx.AsyncClient POST
         │         │
         │         ▼
         │   Parse JSON response, extract metadata
         │         (input_tokens, output_tokens, cost_usd, model)
         │
         ▼
         ├─ 3. Update state.phase_tokens[phase_key]
         ├─ 4. Update state.detailed_token_usage[role]
         ├─ 5. Update state.phase_models[role]
         ├─ 6. Update state.phase_costs[role]
         └─ 7. Write to token_cache
         │
         ▼
   Return (raw_text, metadata)
```

### 3.4 State Management

#### Backend: `PipelineState` (`models.py`)
- **Type**: Mutable `@dataclass`, passed by reference through all phases.
- **Lifecycle**: Born in `api.py` → mutated by each phase → serialized by `_ser_N` → persisted to `history/`.
- **Key Buckets**:
  - `problem`, `task_type`, `language`, `decomposition`
  - `candidates`, `scores`, `top_candidates`, `stress_results`, `final_solution`
  - Method-specific sub-states: `scientific_state`, `socratic_state`, `bayesian_state`, `dialectical_state`, `analogical_state`, `delphi_state`, `pre_mortem_state`, `debate_rounds`, `generation_candidates`, `verification_results`, `meta_evaluation`, `cove_state`, `sot_state`, `tot_state`, `pot_state`, `self_discover_state`
  - Discovery: `web_discovery_results`, `vetted_context`
  - Memory: `reflexion_memory` (bounded `deque[str]`, maxlen=50)
  - Observability: `phase_models`, `phase_tokens`, `detailed_token_usage`, `phase_costs`, `total_cost_usd`, `phase_logs`, `errors`

#### Frontend: Zustand + Local React State
- **Zustand Store** (`stores/app-store.ts`):
  - Persisted: `presetIndex`, `method`, `isSequential`, `isExpert`, `sidebarCollapsed`
  - Ephemeral: `running`, `composerText`
- **Page Local State** (`page.tsx`):
  - `messages: ChatFeedMessage[]`
  - `completedPhases`, `errorPhases`, `currentPhase`
  - `useScrollAnchor` for smart auto-scroll

---

## 4. DOMAIN VIEW

### 4.1 Core Business Entities

| Entity | File | Description |
|--------|------|-------------|
| `PipelineState` | `models.py` | Monolithic state container for an entire reasoning run |
| `SolutionCandidate` | `models.py` | One perspective/generator output |
| `CritiqueScore` | `models.py` | Evaluation of a candidate across dimensions |
| `FinalSolution` | `models.py` | Synthesis output: insights, blueprint, claims, sources |
| `Decomposition` | `models.py` | Sub-problems, assumptions, failure modes |
| `HistoryEntry` | `models.py` | Persisted run metadata |

### 4.2 Domain Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                    REASONING DOMAIN                         │
│  (methods, phases, prompts, state mutations, scoring)       │
│  Owners: pipeline.py, phases.py, models.py                  │
├─────────────────────────────────────────────────────────────┤
│                   ORCHESTRATION DOMAIN                      │
│  (routing, caching, rate limiting, auth, SSE streaming)     │
│  Owners: api.py, llm.py, token_cache.py, auth.py            │
├─────────────────────────────────────────────────────────────┤
│                   PRESENTATION DOMAIN                       │
│  (UI components, markdown rendering, conversation history)  │
│  Owners: ui-next/src/components/*, renderer.py              │
├─────────────────────────────────────────────────────────────┤
│                   INFRASTRUCTURE DOMAIN                     │
│  (search, scraping, persistence, WebSockets, widgets)       │
│  Owners: core/search.py, scraper.py, infrastructure/*       │
├─────────────────────────────────────────────────────────────┤
│                   FOUNDATION DOMAIN                         │
│  (constants, settings, temperatures — no env I/O at core)   │
│  Owners: core/constants.py, core/settings.py                │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Key Abstractions

- **Method**: A preset-specific reasoning strategy (e.g., scientific, debate) mapped to a hardcoded phase sequence.
- **Phase**: One step in a method (e.g., Classification, Decomposition, Critique). Each phase = one prompt + one LLM call + one state mutation.
- **Role**: A named actor in the provider router (e.g., `constructive`, `destructive`, `scoring`, `synthesis`). Roles map to different LLM providers/models.
- **Preset**: A routing configuration that selects which model handles each role (budget vs premium).
- **Constants / Settings**: `core/constants.py` holds pure constants (no I/O). `core/settings.py` loads `.env` once and exposes typed settings.

---

## 5. INFRASTRUCTURE VIEW

### 5.1 External Integrations

| Service | Purpose | Connection Point |
|---------|---------|------------------|
| **OpenRouter** | Primary LLM gateway (346+ models) | `llm.py` → `OpenRouterProvider` |
| **Ollama** | Local LLM inference | `llm.py` → `OpenAICompatibleProvider` |
| **Anthropic** | Claude models | `llm.py` → `AnthropicProvider` |
| **Google GenAI** | Gemini models | `llm.py` → `GeminiProvider` |
| **SearXNG** | Meta-search engine | `core/search.py` → `DiscoveryClient` |
| **Open-Meteo** | Weather widget data | `infrastructure/widgets/weather_widget.py` |
| **Yahoo Finance** | Stock widget data | `infrastructure/widgets/stock_widget.py` |
| **SQLite / PostgreSQL** | Event store & read models | `infrastructure/persistence/*` |

### 5.2 Caching Strategy

| Cache Layer | Key | Scope | Owner |
|-------------|-----|-------|-------|
| **Token Cache** | `hash(problem + phase + model + prompt)` | LLM response per role | `token_cache.py` |
| **Run Cache** | `hash(problem + preset + top_k + routing)` | Full SSE event list | `api.py` (`cache/`) |
| **Model List Cache** | `openrouter_models.json` | Provider metadata | `api.py` startup |
| **Frontend IndexedDB** | `conversation.id` | Conversation history | `ui-next/src/lib/db.ts` |

### 5.3 Deployment Artifacts

- **Docker Compose**: `docker-compose.searxng.yml` (SearXNG only; FastAPI runs bare-metal via uvicorn)
- **Environment**: `.env` holds API keys (`OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, etc.), rate limits, SearXNG URL
- **Process Model**: Single-process async (FastAPI + asyncio). Not horizontally scaled out of the box.

---

## 6. RELATIONSHIP MAPPING

### 6.1 Module → Module Dependencies

```
pipeline.py
  ├── calls → llm.py (ProviderRouter)
  ├── calls → phases.py (prompt factories)
  ├── mutates → models.py (PipelineState)
  ├── calls → parsing.py (extract_json)
  ├── calls → core/search.py (DiscoveryClient)
  ├── calls → scraper.py (deep read)
  ├── calls → neuro/server.py (Recall/Learn)
  ├── imports → core/constants.py (TRUNCATION, TIMEOUTS, budgets)
  └── imports → core/settings.py (env-aware config)

api.py
  ├── creates → pipeline.py (ARAPipeline)
  ├── instantiates → hypergate/hyperagent.py (HyperGateAgent)
  ├── imports → gate_agent.py (GateDecision type)
  ├── imports → models.py (PipelineState, HistoryEntry)
  ├── imports → presets.py (get_preset, get_method_from_preset)
  ├── imports → llm.py (build_custom_router)
  ├── uses → auth.py, rate_limiter.py
  ├── uses → application/handlers/handlers.py (new-arch path)
  ├── imports → core/constants.py (defaults, CORS, SSE intervals)
  ├── imports → core/settings.py (rate limits, API keys)
  └── serves → ui-next/ (SSE + REST)

hypergate/hyperagent.py
  ├── instantiates → sub_agents/* (6 sub-agents, one per concern)
  ├── calls → llm.py (ProviderRouter, shared router passed in)
  ├── imports → hypergate/models.py (SubAgentInput, SubAgentOutput, HyperContext)
  └── imports → core/constants.py (HYPERGATE_* thresholds + token budgets)

hypergate/base_sub_agent.py
  ├── calls → llm.py (ProviderRouter.call, role="primary")
  └── imports → core/constants.py (HYPERGATE_TIMEOUT_SECONDS, HYPERGATE_CACHE_SIZE)

llm.py
  ├── implements → BaseLLMProvider (Template Method)
  ├── uses → exceptions.py
  ├── depends on → openai, anthropic, google.generativeai, httpx
  ├── imports → core/constants.py (TIMEOUTS, model aliases)
  └── imports → presets.py (routing configs)

ui-next/src/app/page.tsx
  ├── uses → usePipelineStream.ts (SSE consumer)
  ├── uses → useAppStore.ts (Zustand)
  ├── renders → ChatFeed.tsx → PhaseRenderer.tsx
  └── builds markdown → lib/markdown.ts
```

### 6.2 Function Call Chains

#### Chain C: HyperGate Routing Decision
```
api.py::run_stream()
  └── HyperGateAgent.decide(problem)
        ├── _run_phase1()  [asyncio.gather, return_exceptions=True]
        │     ├── LanguageDetectorSubAgent.execute(inp, router)
        │     ├── ComplexityEstimatorSubAgent.execute(inp, router)
        │     ├── DirectDetectorSubAgent.execute(inp, router)
        │     ├── WebSearchDetectorSubAgent.execute(inp, router)
        │     └── MethodClassifierSubAgent.execute(inp, router)
        │           → each: cache_check → router.call(role="primary") → _parse_result()
        │
        ├── HyperContext(lang, complexity, direct, web, method)
        │
        ├── _synthesize(context) → GateDecision | None
        │     STEP 1: is_direct + simple + conf≥0.80 → action="direct"
        │     STEP 2: needs_search + conf≥0.75       → action="web_search"
        │     STEP 3: method_conf≥0.70               → action="pipeline"
        │     STEP 4: any conf≥0.45                  → None (trigger tiebreaker)
        │     STEP 5: all below 0.45                 → fallback pipeline
        │
        └── [if None] _run_tiebreaker()
              └── TieBreakerSubAgent.execute(inp_with_context, router)
                    → GateDecision(action, method, confidence, reasoning)
```

#### Chain A: Web Request to Phase Result
```
api.py::run_stream()
  └── ARAPipeline.run(state)
        └── _call_llm_cached(role="synthesis", ...)
              ├── token_cache.get()
              │     └── HIT or MISS
              └── ProviderRouter.call()
                    └── OpenRouterProvider.complete()
                          └── httpx.AsyncClient.post()
        └── extract_json(raw)
        └── mutate state.final_solution
        └── _ser_5(state)
              └── emit SSE phase_complete
```

#### Chain B: Deep Read / Context Vetting
```
pipeline.py::_phase_context_vetting()
  └── DiscoveryClient.search() (SearXNG)
  └── LLM plan: "more searches needed?"
  └── loop up to 3 iterations
  └── _phase_deep_read()
        └── scraper.fetch() for top results
        └── LLM extraction of summaries/key_facts
```

### 6.3 Data Transformations

| Source | Transformation | Destination |
|--------|----------------|-------------|
| User `problem` string | `detect_language()` + LLM classification | `state.language`, `state.task_type` |
| LLM raw response (markdown fenced JSON) | `extract_json()` (strip fences, repair commas/truncation) | `dict` → dataclass instance |
| `state.to_context_dict()` | heavy truncation + summary | synthesis prompt |
| `state.phase_tokens` | aggregation (`sum(input)`, `sum(output)`) | `done` SSE `total_tokens` |
| Phase event list | `buildMarkdownFromPhases()` | `ChatFeed` markdown fallback |

### 6.4 Implicit Contracts

1. **Serializer Contract**: `_ser_0` through `_ser_5` in `api.py` must return dicts whose top-level keys match what `lib/markdown.ts` and `PhaseRenderer.tsx` expect (e.g., `scores`, `candidates`, `scientific_state`, `debate_rounds`). Breaking a field name in `models.py` silently breaks the UI.
2. **Role Naming Contract**: `presets.py` assigns roles like `constructive`, `destructive`, `scoring`. `pipeline.py` hard-codes these strings in phase functions. A preset with a renamed role will fail at runtime.
3. **SSE Event Contract**: Frontend expects exactly these `PhaseEvent.type` values: `start`, `phase_start`, `phase_complete`, `phase_error`, `error`, `cancelled`, `done`. Missing `error` handling caused prior UI hangs.
4. **Cache Invalidation Contract**: Run cache key is `SHA256(problem + preset + top_k + routing)`. Any change to default routing invalidates all prior caches.
5. **Constants Contract**: `core/constants.py` must remain free of environment I/O. All `.env` loading belongs in `core/settings.py`.
6. **Phase Error Halt Contract**: As of v2.2, `run_stream()` halts the pipeline on critical phase failures (Decomposition, Perspectives, etc.) instead of continuing to Synthesis with empty state.

---

## 7. DESIGN PATTERN & INTENT INFERENCE

| Pattern / Style | Confidence | Evidence |
|-----------------|------------|----------|
| **Provider Router (Strategy)** | [CONFIRMED] | `ProviderRouter` in `llm.py` maps roles → providers with automatic fallback. |
| **Phase-Based Pipeline** | [CONFIRMED] | `ARAPipeline` executes ordered phases; each phase = prompt → LLM → parse → mutate state. |
| **Template Method** | [CONFIRMED] | `BaseLLMProvider.complete_with_retry` defines retry skeleton; subclasses implement `complete()`. |
| **Server-Sent Events (SSE) Streaming** | [CONFIRMED] | `/api/run` returns `StreamingResponse(text/event-stream)`; frontend consumes via `ReadableStream`. |
| **Cache-Aside** | [CONFIRMED] | `token_cache.py` and `api.py` both check external caches before computation. |
| **Adapter** | [CONFIRMED] | `infrastructure/llm/ports.py` defines port; multiple adapters implement it. |
| **Factory** | [CONFIRMED] | `build_provider(model_id)` and `build_custom_router()` instantiate object families. |
| **CQRS / Event Sourcing (Partial)** | [LIKELY] | New architecture uses `application/commands`, `infrastructure/persistence/event_store.py`, snapshots. Legacy pipeline bypasses this. |
| **Decorator / Middleware** | [CONFIRMED] | FastAPI stack: `SecurityHeadersMiddleware`, `CORSMiddleware`, `MemoryLimitMiddleware`, `RequestTimeoutMiddleware`. |
| **Object Pool (Connection Reuse)** | [CONFIRMED] | `OpenAICompatibleProvider._shared_pool` is a shared `httpx.AsyncClient` (thread-safe init via `threading.Lock`). |
| **State Machine (Implicit)** | [LIKELY] | `PipelineState` advances through hardcoded phase sequences per method. |
| **Widget Chain of Responsibility** | [LIKELY] | `infrastructure/widgets/registry.py` auto-detects query type and dispatches handler. |
| **Monolith with Modular Monolith Aspirations** | [CONFIRMED] | Single FastAPI process, but clear separation into `core/`, `infrastructure/`, `application/`. |
| **Singleton Settings** | [CONFIRMED] | `core/settings.py` exposes a single `settings` instance loaded once at import time. |

---

## 8. RISKS, COUPLING & ARCHITECTURAL SMELLS

### 8.1 High-Risk Issues

| # | Risk | Severity | Details |
|---|------|----------|---------|
| 1 | **Tight Coupling: `pipeline.py` ↔ `phases.py`** | High | Adding a new method requires edits to both files plus serializers in `api.py`. No plugin interface exists. |
| 2 | **Serializer/State Hidden Coupling** | High | `_ser_0`–`_ser_5` manually reach into `PipelineState` fields. Renaming a field in `models.py` silently breaks the SSE contract. |
| 3 | **Dual Architecture (Legacy vs New)** | Medium-High | Legacy path (`api.py` → `ARAPipeline`) and new CQRS path (`api.py` → `HandlerRegistry`) coexist. Fixes often need duplication. |
| 4 | **Global Mutable State** | Medium | `_cancelled_runs`, `_active_runs`, `_default_client`, `_event_store` are module-level globals. Unsafe under multi-process deployments (Gunicorn). |
| 5 | **Frontend/Backend Phase ID Drift** | Medium | `ui-next/src/lib/config.ts` hard-codes `METHOD_PHASES`. If backend adds/removes phases, timeline highlighting desyncs. |
| 6 | **ProviderRouter Metadata Side-Effects** | Medium | `llm.py` reads `last_input_tokens`, `last_output_tokens`, `last_cost_usd` from provider instance attributes. Implicit contract. |
| 7 | **Exception Hierarchy Confusion** | Low-Medium | `parsing.py` has `ParseError`; `exceptions.py` has `JSONExtractionError`. Some modules raise one, others catch the other. |
| 8 | **Memory-Intensive Prompts** | Medium | `to_context_dict()` embeds large nested objects (`web_discovery_results`, `debate_rounds`) into every synthesis prompt. Can exceed context windows. |
| 9 | **E2E Test Fragility** | Medium | Live API key dependencies in `test_e2e_real_api.py` and `test_e2e_real_pipeline.py` make CI unreliable without mocks/VCR. |
| 10 | **Cyclic Import Risk** | Low | `models.py` ↔ `core/protocol.py` import each other under `TYPE_CHECKING`. Safe today, fragile tomorrow. |
| 11 | **Foundation Coupling** | Low-Medium | `core/constants.py` is imported by ~20 modules. A breaking rename requires sweeping changes, though the surface is stable. |

### 8.2 Resolved Issues (Recent)

| Issue | Resolution |
|-------|------------|
| `widgets.py` import hang | Moved `yahooquery`/`yfinance` to lazy runtime imports; removed eager module-level import. |
| `asyncio.run()` in `get_discover_content` | Function converted to `async def`; caller in `api.py` now `await`s it. |
| `OpenAICompatibleProvider` race condition | Shared pool initialization wrapped in `threading.Lock` to prevent connection-pool leaks. |
| `run_stream()` bare `except Exception` | Critical phase failures now halt the pipeline before Synthesis instead of returning fabricated results. |
| Hardcoded SearXNG URLs | `widgets.py` and `core/search.py` now use `DEFAULT_SEARXNG_URL` from `core/constants.py`. |

### 8.3 Cyclic Dependencies

```
Detected (compile-time safe, runtime fragile):

models.py ──TYPE_CHECKING──► core/protocol.py (imports PhaseResult)
core/protocol.py ──TYPE_CHECKING──► models.py (imports PipelineState)
```

### 8.4 Blast Radius of Key Changes

| If you change... | These break... |
|------------------|----------------|
| `models.py` field names | `api.py` serializers, `renderer.py`, `phases.py` prompts |
| `phases.py` prompt signature | `pipeline.py` phase functions |
| `presets.py` role names | `pipeline.py` hardcoded role strings, `llm.py` routing |
| `ui-next/src/lib/config.ts` phase IDs | `PhaseTimeline.tsx`, `page.tsx` name lookups |
| `api.py` SSE event shape | `usePipelineStream.ts`, `page.tsx`, `lib/markdown.ts` |
| `core/constants.py` names | ~20 production modules + `tests/test_constants.py` |

---

## 9. SUMMARY MINDMAP (ASCII)

```
                              ┌─────────────┐
                              │   User      │
                              │ (Next.js)   │
                              └──────┬──────┘
                                     │ POST /api/run
                                     ▼
┌────────────────────────────────────────────────────────────────────┐
│                        FastAPI (api.py)                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐ │
│  │ Rate Limit  │  │    Auth     │  │ Cache Check │  │  Router   │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘ │
└────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌────────────────────────────────────────────────────────────────────┐
│                   HyperGateAgent (hypergate/)                      │
│                                                                    │
│  Phase 1 — 5 sub-agents in parallel:                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐  │
│  │ Language │ │Complexity│ │  Direct  │ │   Web    │ │ Method  │  │
│  │ Detector │ │Estimator │ │ Detector │ │ Detector │ │Classify │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └─────────┘  │
│                    Phase 2 (if ambiguous):                         │
│                    ┌──────────────────────┐                        │
│                    │  TieBreakerSubAgent  │                        │
│                    └──────────────────────┘                        │
└────────────┬───────────────────┬──────────────────┬───────────────┘
             │ direct            │ web_search        │ pipeline
             ▼                   ▼                   ▼
     Answer inline          Live search        ┌────────────────────┴────────────────┐
     (virtual phase)        and return         │                                     │
                                               ▼                                     ▼
                                    ┌─────────────────────┐           ┌─────────────────────┐
                                    │  Legacy Pipeline    │           │  New CQRS Pipeline  │
                                    │  ARAPipeline        │           │  (handlers, events) │
                                    │  (pipeline.py)      │           │  (infrastructure/*) │
                                    └──────────┬──────────┘           └─────────────────────┘
                                               │
                                 ┌─────────────┼─────────────┐
                                 │             │             │
                                 ▼             ▼             ▼
                           ┌─────────┐  ┌─────────┐  ┌─────────────┐
                           │phases.py│  │ llm.py  │  │models.py    │
                           │(prompts)│  │(router) │  │(state)      │
                           └────┬────┘  └────┬────┘  └──────┬──────┘
                                └────────────┴──────────────┘
                                             │
                                             ▼
                                    ┌─────────────────┐
                                    │  PipelineState  │
                                    │  (mutable ref)  │
                                    └────────┬────────┘
                                             │
                                  ┌──────────┴──────────┐
                                  │                     │
                                  ▼                     ▼
                            ┌────────────┐       ┌────────────┐
                            │  SSE Stream│──────►│  ui-next   │
                            │  (cache)   │       │  (render)  │
                            └────────────┘       └────────────┘

Foundation layer (imported by all):
   ┌──────────────────────┐   ┌─────────────┐
   │  constants           │   │   settings  │
   │  (incl. HYPERGATE_*) │   │    (.py)    │
   └──────────────────────┘   └─────────────┘
```

---

*End of Codebase Mindmap*
