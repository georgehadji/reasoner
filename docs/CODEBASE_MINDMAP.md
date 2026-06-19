# CODEBASE_MINDMAP.md — Reasoner (v3.0 Post-Refactor)

> High-fidelity codebase reconstruction.  
> **Last updated:** 2026-06-15  
> **Python source files:** 400 | **Models:** 146 | **Presets:** 50 | **Methods:** 30 | **Phase modules:** 32

---

## 1. System Overview

**Reasoner** is a production-grade AI reasoning orchestrator that decomposes complex problems into structured multi-phase pipelines, leverages 131+ LLM models from diverse training ecosystems in parallel, applies independent critique, stress-tests solutions, and synthesizes actionable recommendations with epistemic labeling (`VERIFIED` / `HYPOTHESIS` / `UNKNOWN`).

### Key Characteristics

- **Multi-Method Reasoning** — 19 specialized methods (Orchestrated, Debate, Jury, Research, Scientific, Socratic, Pre-Mortem, Bayesian, Dialectical, Analogical, Delphi, CoVE, SoT, ToT, PoT, Self-Discover, Writing, Brainstorming, Coding)
- **Cross-Lab Diversity** — Phase 2 generates perspectives from 3-4 different AI labs (Google, Mistral, Qwen, etc.) to prevent echo chambers
- **Independent Critique** — Phase 3 scorer always from different lab than dominant generator
- **Epistemic Labeling** — Solutions marked as VERIFIED, HYPOTHESIS, or UNKNOWN based on confidence
- **HyperGate Pre-Router** — 5 parallel sub-agents + TieBreaker determine whether request needs DIRECT answer, WEB_SEARCH, or full PIPELINE
- **Event-Sourced State** — Immutable event log enables state replay + audit trail
- **Long-Term Memory** — Neuro L1/L2/L3 tiered cache with embedding search for context recall

### Key Stats

| Component | Count |
|-----------|-------|
| Python modules | 375 |
| LLM models (whitelist) | 131 |
| Presets | 49 |
| Reasoning methods | 19 |
| Phase prompt modules | 32 |
| FastAPI routes | 30+ |
| Domain events | 18 |
| Frontend pages | 12 |

### Architecture Entry Points

| Entry Point | Location | Purpose |
|-------------|----------|---------|
| **Web API** | `src/reasoner/api/__init__.py` | FastAPI app factory |
| **SSE Streaming** | `src/reasoner/api/streaming.py` | Core SSE handlers |
| **CLI** | `src/reasoner/main.py` | Command-line reasoning |
| **Frontend** | `ui-next/src/app/` | Next.js App Router |

---

## 2. Structural View

### Top-Level Directory Map

```
src/reasoner/
├── api/                     # FastAPI HTTP/SSE interface
├── application/             # CQRS, flows, services, event bus
├── core/                    # Domain protocols, events, constants
├── domain/                  # State models, presets, business logic
├── infrastructure/          # LLM providers, persistence, search
├── hypergate/               # Request pre-router (5 sub-agents)
├── phases/                  # 32 phase prompt templates
├── subagents/               # Sub-agents for enhancement/decomposition
├── neuro/                   # Long-term memory L1/L2/L3
├── healing/                 # Self-healing CI/CD introspection
├── security/                # Auth, encryption, rate limiting
├── instrumentation/         # Metrics, tracing, logging
└── [shims & utilities]      # Backward-compat shims, helpers

ui-next/src/
├── app/                     # Next.js App Router
├── components/              # React components (chat, phases, layout, ui, widgets)
├── hooks/                   # React hooks (SSE, history, presets, etc.)
├── lib/                     # Utilities (API client, DB, security, markdown)
└── stores/                  # Zustand global state
```

### Module Dependency Flow

```
API Layer (api/)
    ↓ (depends on)
Application Layer (application/)
    ├─ Orchestrator (preflight/execute/postflight)
    ├─ Pipeline (phase execution)
    ├─ Flows (phase function registry)
    ├─ Services (preset, search, render)
    └─ Event Bus (CQRS subscribers)
    ↓ (depends on)
Domain Layer (domain/)
    ├─ PipelineState (state model)
    ├─ Preset Registry (49 presets)
    └─ Core Types (candidates, scores, etc.)
    ↓ (depends on)
Core Layer (core/)
    ├─ Ports (abstract interfaces)
    ├─ Events (immutable event hierarchy)
    ├─ Constants (token budgets, thresholds)
    └─ Settings (configuration)
    ↓ (depends on)
Infrastructure Layer (infrastructure/)
    ├─ LLM providers (31+ adapters)
    ├─ Persistence (SQLite, PostgreSQL)
    ├─ Search (SearXNG, Perplexity)
    ├─ Redis (cache, rate limiter)
    └─ WebSocket (real-time)
```

### Layered Architecture (Hexagonal DDD)

| Layer | Modules | Responsibility | Dependencies |
|-------|---------|-----------------|--------------|
| **Interfaces** | `api/`, `main.py` | HTTP/CLI entry points | Application, Domain |
| **Application** | `application/`, `orchestrator.py` | CQRS handlers, flows | Domain, Core |
| **Domain** | `domain/` | Business entities, state, presets | Core only |
| **Core** | `core/` | Protocols, events, constants | No outer deps |
| **Infrastructure** | `infrastructure/` | Adapter implementations | Core only |

**Known Violations:**
- `domain/preset_core.py` imports `infrastructure.llm.registry` (model validation)
- `api/streaming.py` directly instantiates `ReasonerPipeline`
- `application/flows/__init__.py` imports `api.serializers`

---

## 3. Behavioral View

### Request/Response Lifecycle (Web Path)

```
User Problem (Chat UI)
    │
    ├─→ CSRF token validation (api/csrf)
    │   └─→ HMAC-SHA256 signature check
    │
    ├─→ POST /api/run (SSE endpoint)
    │   └─→ api/streaming.py:run_stream()
    │       │
    │       ├─→ PipelineOrchestrator.preflight()
    │       │   ├─ HyperGate decision (5 sub-agents + TieBreaker)
    │       │   │  ├─ LanguageDetector (language confidence)
    │       │   │  ├─ ComplexityEstimator (simple/medium/complex)
    │       │   │  ├─ DirectDetector (instant answer feasible)
    │       │   │  ├─ WebSearchDetector (real-time data needed)
    │       │   │  └─ MethodClassifier (best method for problem)
    │       │   ├─ Fast-path check (regex patterns)
    │       │   │  ├─ Creative writing → DIRECT
    │       │   │  ├─ Real-time query → WEB_SEARCH
    │       │   │  └─ Factual lookup → DIRECT
    │       │   ├─ Preset resolution + router construction
    │       │   └─ Neuro recall (long-term memory)
    │       │
    │       ├─→ PipelineOrchestrator.execute()
    │       │   └─→ ReasonerPipeline.run()
    │       │       ├─ Phase 0: Classification (task_type, language)
    │       │       ├─ Phase 1: Decomposition (≤5 sub-problems)
    │       │       ├─ Phase 2: Generation (3-4 labs, parallel perspectives)
    │       │       ├─ Phase 3: Critique (independent scoring, top-k)
    │       │       ├─ Phase 4: Stress Testing (adversarial scenarios)
    │       │       └─ Phase 5: Synthesis (epistemic labels + blueprint)
    │       │
    │       ├─→ PipelineOrchestrator.postflight()
    │       │   ├─ Neuro learn (save synthesis)
    │       │   ├─ Event persist + history save
    │       │   └─ Metrics update
    │       │
    │       └─→ SSE stream phases → Chat UI
    │
    └─→ Chat UI renders (real-time phase updates)
```

### HyperGate Decision Tree

```
Problem Input
    │
    ├─→ Fast-path regex checks (BEFORE LLM)
    │   ├─ Creative writing (poem, story, joke) → DIRECT (instant)
    │   ├─ Real-time query (price/news/weather) → WEB_SEARCH (live)
    │   ├─ Factual lookup (what is X, define Y) → DIRECT (knowledge)
    │   └─ Default → proceed to sub-agents
    │
    ├─→ Parallel sub-agent execution
    │   ├─ LanguageDetector: {language, confidence}
    │   ├─ ComplexityEstimator: {complexity: simple|medium|complex}
    │   ├─ DirectDetector: {is_direct, confidence}
    │   ├─ WebSearchDetector: {needs_web, confidence}
    │   └─ MethodClassifier: {method: debate|jury|research|...}
    │
    ├─→ Consensus check
    │   ├─ High confidence → accept
    │   └─ Conflict/ambiguous → TieBreaker phase
    │
    └─→ Route decision
        ├─ DIRECT: fastest model, instant response
        ├─ WEB_SEARCH: research method with live data
        └─ PIPELINE: full 6-phase reasoning (method auto-selected)
```

---

## 4. Domain View

### PipelineState Structure (~60 fields)

**Execution Core:**
- `problem: str` — User input
- `enhanced_problem: str` — Rewritten for clarity
- `task_type: TaskType` — RESEARCH, CODING, MATH, ANALYSIS, etc.
- `language: str` — Detected language
- `complexity: str` — simple, medium, or complex

**Phase Outputs:**
- `decomposition: Decomposition` — Phase 1 (sub-problems, failure modes)
- `candidates: list[SolutionCandidate]` — Phase 2 (multi-perspective solutions)
- `scores: list[CritiqueScore]` — Phase 3 (0-10 scores)
- `top_candidates: list[SolutionCandidate]` — Phase 3 (top-k filtered)
- `stress_results: list[StressTestResult]` — Phase 4 (stress scenarios)
- `final_solution: FinalSolution` — Phase 5 (synthesis + VERIFIED/HYPOTHESIS/UNKNOWN)

**Cost & Token Tracking:**
- `total_cost_usd: float`
- `phase_costs: dict[str, float]`
- `detailed_token_usage: dict[str, dict[str, int]]`

**Conversation:**
- `conversation_history: list[dict]`
- `conversation_id: str`
- `turn_number: int`
- `previous_synthesis: str`

**Metadata:**
- `started_at: datetime`
- `phase_logs: list[str]`
- `phase_tokens: dict[str, dict[str, int]]`
- `phase_durations: dict[str, float]`

**Method-Specific State:**
- `method_state: MethodState` — Generic `dict[str, Any]` per method
  - `debate.rounds`, `debate.judge_verdict`
  - `jury.generator_solution`, `jury.critic_feedback`
  - `research.prism_iterations`, `research.sources`

### Reasoning Methods (19)

| # | Method | Strengths | Best For |
|---|--------|-----------|----------|
| 1 | **Orchestrated** | Balanced 6-phase pipeline | Default: most problems |
| 2 | **Debate** | Adversarial refinement | Controversial/nuanced topics |
| 3 | **Jury** | Expert consensus building | Complex judgments |
| 4 | **Research** | Web-grounded RAG (Prism loop) | Fact-intensive problems |
| 5 | **Scientific** | Hypothesis + falsification | Empirical validation |
| 6 | **Socratic** | Elenchus questioning | Exposing assumptions |
| 7 | **Pre-Mortem** | Prospective failure analysis | Risk mitigation |
| 8 | **Bayesian** | Prior → likelihood → posterior | Belief updating |
| 9 | **Dialectical** | Thesis-antithesis-synthesis | Hegelian reasoning |
| 10 | **Analogical** | Cross-domain mapping | Novel problem solving |
| 11 | **Delphi** | Structured expert consensus | Forecasting |
| 12 | **CoVE** | Chain-of-Verification | Hallucination reduction |
| 13 | **SoT** | Skeleton-of-Thought | Structured decomposition |
| 14 | **ToT** | Tree-of-Thoughts | Search + backtracking |
| 15 | **PoT** | Program-of-Thoughts | Code-based reasoning |
| 16 | **Self-Discover** | Dynamic module composition | Novel approaches |
| 17 | **Writing** | Creative + hallucination guards | Creative writing |
| 18 | **Brainstorming** | Divergent ideation | Idea generation |
| 19 | **Coding** | Code generation + review | Software engineering |

### Preset Taxonomy (49)

**Budget** (19): <$0.05 per run, 1-2 labs
**Premium** (19): $0.15–$0.30 per run, 3-4 labs
**Balanced** (6): $0.05–$0.10 per run, sweet-spot
**Experimental** (5): New method pilots

### Domain Events

**Pipeline Lifecycle:**
- `PipelineStarted`, `PhaseStarted`, `PhaseCompleted`, `PhaseFailed`, `PipelineCompleted`, `PipelineFailed`

**Reasoning Operations:**
- `PerspectiveGenerated`, `CandidateScored`, `StressTestCompleted`, `ContextFetched`, `ContextVetted`, `SourceAdded`, `LLMGenerationCompleted`, `ResearchStepEmitted`, `ResearchCitationsReady`

**Other:**
- `WidgetDetected`, `WidgetExecuted`, `WidgetFailed`
- `MemoryStored`, `MemoryRecalled`
- `UserRegistered`, `SubscriptionCreated`, `QuotaExceeded`, `PaymentSucceeded`

---

## 5. Infrastructure View

### LLM Routing (131 Models)

**Primary:** OpenRouter (350+ models, fallback)

**Direct Adapters (12):**
1. Anthropic (Claude Opus, Sonnet 4.6, Haiku 4.5)
2. OpenAI (GPT-5, GPT-5.3-Codex, GPT-4o, o3, o3-mini)
3. Google (Gemini 2.5 Pro, Flash, Flash-Lite)
4. Perplexity (Sonar, Sonar-Pro, Sonar-Deep-Research, Sonar-Reasoning-Pro)
5. DeepSeek (V3, V3.1, R1, V4-Flash, V4-Pro)
6. Mistral (Large 2512, Medium 3.1, Small 3.2, Codestral, Devstral)
7. xAI (Grok 4.20, 4.3, 4.1-Fast, 3, 3-mini)
8. Qwen (3.7-Max, 3.6-Plus, 3.5-Flash, 3-Coder variants)
9. Kimi (K2.5, K2.6)
10. GLM (5, 5.1, 4.7-Flash)
11. MiniMax (M3, M2.7, M2.5, M1)
12. Ollama (local inference)

**Routing by Role:**
- `prompt_enhancement` — Gemini Flash Lite, GLM-Air
- `classification` — GPT-5-mini (JSON-rigid), GLM-Air
- `decomposition` — DeepSeek V3 (structured)
- `constructive/destructive/systemic/minimalist` — Diverse labs (Google, Mistral, Qwen, GLM)
- `scoring` — Independent lab (never scorer from generator lab)
- `stress_testing` — Adversarial-strong (Mistral Small)
- `synthesis` — High-quality (Qwen 3.7-Max)

### Persistence

**SQLite (default):**
- `events` — Domain events (append-only)
- `snapshots` — PipelineSnapshot (periodic cache)
- WAL mode for concurrent readers

**PostgreSQL (optional):**
- `query_audit_logs` — User history
- `user_settings` — Subscription + quota
- `api_keys` — Auth keys

**Neuro Memory (L1/L2/L3):**
- L1: In-memory (session)
- L2: Disk JSON (`~/.neuro/agents/<id>/`)
- L3: Remote embedding search (optional)

### Search Services

**SearXNG** (Docker, self-hosted): BM25 + 50+ backends
**Perplexity Sonar:** Real-time web search + LLM reasoning
**BM25 Local:** File-based search fallback

### Caching & Rate Limiting

**Token Cache:**
- L1: Memory (instant)
- L2: SQLite (persistent)
- L3: Neuro embedding (semantic)

**Rate Limiting:**
- Memory mode (single worker)
- Redis mode (multi-worker safe)
- Token-bucket per client IP

**Circuit Breaker:**
- Auto-fallback on provider failures
- Threshold: 5 failures in 60s → OPEN
- Half-open recovery timeout

### Security

**Input Sanitization:**
- XSS stripping, null-byte removal
- Prompt-injection regex defense
- Unicode NFKC normalization

**Envelope Encryption:**
- AES-256-GCM for PII
- Blind indexing for search fields

**CSRF Protection:**
- HMAC-SHA256 tokens
- Validated in Next.js + FastAPI

**Auth:**
- OAuth2 + JWT tokens
- Scoped permissions (user, admin, service)

---

## 6. API Surface (30+ Endpoints)

| Route | Method | Purpose |
|-------|--------|---------|
| `/pipelines/run` | POST | Start pipeline (SSE) |
| `/pipelines/run-followup` | POST | Follow-up turn (SSE) |
| `/pipelines/list` | GET | Past pipelines |
| `/pipelines/resume/<id>` | POST | Resume pipeline |
| `/context/fetch` | POST | Fetch/vet context |
| `/health` | GET | Liveness |
| `/health/deep` | GET | Readiness + deps |
| `/estimate` | POST | Cost estimation |
| `/history/queries` | GET | Query history |
| `/uploads` | POST | File upload |
| `/images/analyze` | POST | Vision LLM |
| `/widgets/*` | POST | Calculator, stocks, weather |
| `/ws` | WebSocket | Event stream |
| `/admin/*` | GET/POST | Admin operations |
| `/feedback` | POST | User feedback |
| `/keys/*` | POST/GET | API key management |
| `/neuro/recall` | POST | Memory retrieval |
| `/neuro/learn` | POST | Memory storage |
| `/csrf` | GET | CSRF token |

---

## 7. Frontend View (Next.js 16 / React 19)

### Component Hierarchy

```
<RootLayout>
  ├─ <Providers> (auth, Zustand, SWR)
  ├─ <SiteHeader> (logo, user menu, theme)
  ├─ <Sidebar> (chat history)
  └─ <ChatPage>
     ├─ <ChatFeed> (message stream)
     │  └─ <ChatMessage>
     │     ├─ <MarkdownRenderer>
     │     ├─ <CodeBlock>
     │     ├─ <PhaseCard>
     │     └─ <WidgetRenderer>
     ├─ <PhaseTimeline> (progress)
     ├─ <Composer> (input + presets)
     └─ <Modals>
        ├─ <ShortcutModal>
        ├─ <SecurityModal>
        ├─ <UpgradeModal>
        └─ <NeuroPanel>
```

### Key Hooks

- **`usePipelineStream()`** — SSE handler (core)
- **`useConversationHistory()`** — Chat history (IndexedDB + API)
- **`useKeyboardShortcuts()`** — Cmd+K palette, Shift+Enter
- **`usePresets()`** — List presets + cost estimation
- **`useQuota()`** — Remaining quota check
- **`useServerStatus()`** — Backend health

### State Management

**Zustand (`app-store.ts`):**
- `currentConversationId`, `messages`, `currentPhase`, `isStreaming`
- `selectedPreset`, `userQuota`, `theme`

**SWR hooks:**
- Presets, quotas, server health (server state)

### Styling (Tailwind CSS v4)

**NO `tailwind.config.ts`** — CSS-native via `@import "tailwindcss"` in `globals.css`

---

## 8. Cross-Cutting Concerns

### Security Chain (Defense in Depth)

```
Input → CSRF Check → Auth → Rate Limit → Input Sanitization 
      → Prompt Injection Defense → Circuit Breaker → Error Masking
```

### Observability

**Metrics:** Prometheus (cost, tokens, duration, active users)
**Tracing:** Langfuse (LLM call observability)
**Logging:** SafeLoggingFilter (redacts secrets, PII)
**Errors:** Sentry (exception tracking)

### Event Bus (CQRS)

Domain events → SQLite persistence → Subscriber callbacks → WebSocket broadcast

---

## 9. Self-Healing CI/CD

`.github/workflows/self-healing-ci.yml`:
1. healing-profile
2. loop1-static (bandit, mypy, pylint)
3. loop2-runtime (unit + integration tests)
4. loop3-evolutionary (auto-generate test coverage)
5. searxng-integration
6. healing-verification

**Coverage gates:** 60% fail, 80% warn, 90%+ green

---

## 10. Development Quick Start

```bash
# All-in-one
python start_all.py

# Separate services
uvicorn asgi:app --reload --host 0.0.0.0 --port 8003
cd ui-next && npm run dev
docker-compose -f docker-compose.searxng.yml up -d

# Testing
pytest tests/ -v
pytest tests/ --cov=src/reasoner --cov-report=html

# CLI
python main.py --list-presets
python main.py --problem "..." --preset debate-premium
```

---

## Metadata

| Field | Value |
|-------|-------|
| **Last Updated** | 2026-06-08 |
| **Version** | v3.0 (post-refactor) |
| **Python Files** | 375 |
| **Models** | 131 |
| **Presets** | 49 |
| **Methods** | 19 |
| **Phase Modules** | 32 |
| **Routes** | 30+ |
| **Frontend Pages** | 12 |
| **Domain Events** | 18 |

*For detailed method reference, see `docs/AGENTS.md`. For architectural decisions, see `docs/ARCHITECTURE_MINDMAP.md`.*
