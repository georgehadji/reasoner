# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 1. Project Overview

**Reasoner** (Adaptive Reasoning Architecture) is a production-grade AI reasoning orchestrator that decomposes complex problems into structured multi-phase pipelines, leverages 131 LLM models from diverse training ecosystems in parallel, applies independent critique, stress-tests solutions, and synthesizes actionable recommendations with epistemic labeling (`VERIFIED` / `HYPOTHESIS` / `UNKNOWN`).

- **Version:** 2.2 (Python package 2.1.0) | **Python:** 3.12+ | **Frontend:** Next.js 16 / React 19 / TypeScript 5

> This is not a chatbot. Reasoning is a first-class engineering problem: classify → decompose → vet context → generate (parallel, cross-lab) → critique → stress-test → synthesize → epistemic label → action blueprint.

### Architecture Style

Hexagonal DDD + CQRS + Event Sourcing + Mixin Composition. `PipelineState` (~60 fields, `domain/pipeline_state.py`) is the primary state model. `PipelineAggregate` provides event-sourced replay.

**Dependency Rule:** Domain has no outer dependencies → Application depends on Domain/Core only → Infrastructure implements Core ports → API/Interface depends on Application.

**Known violations:** `domain/preset_core.py` imports from `infrastructure.llm.registry`. `api/streaming.py` directly instantiates the pipeline rather than routing through CQRS handlers. `application/flows/__init__.py` imports from `api.serializers`.

---

## 2. Technology Stack

| Layer | Technology |
|-------|------------|
| Runtime | Python 3.12+, FastAPI 0.109+, uvicorn, Pydantic v2, httpx |
| LLM Routing | OpenRouter (primary, 350+ models); 12 direct adapters (Anthropic, OpenAI, Google, Perplexity, DeepSeek, Mistral, xAI, Qwen, Kimi, GLM, MiniMax, Ollama) |
| Search | SearXNG (Docker), Perplexity Sonar |
| Database | SQLite (event store), PostgreSQL (asyncpg), aiosqlite |
| Memory | Neuro L1/L2/L3 tiered cache with embedding search |
| Security | Auth, rate limiter, circuit breaker, sanitization, prompt-injection defense, CSRF |
| Frontend | Next.js 16 (App Router), React 19, TypeScript 5, Tailwind CSS v4, Zustand v5, SWR v2, IndexedDB |

**Critical:** Tailwind CSS v4 does **NOT** use `tailwind.config.ts`. Config is CSS-native via `@import "tailwindcss"` in `globals.css`. Do not create `tailwind.config.ts`.

---

## 3. Project Structure

```
src/reasoner/
├── api/                    # FastAPI HTTP/SSE (~30 endpoints)
│   ├── __init__.py         # App factory, CORS, middleware, route mounting
│   ├── streaming.py        # Core SSE: run_stream(), run_followup_stream(), run_stream_cached()
│   ├── serializers.py      # SSE serialization by phase (_ser_0 through _ser_5)
│   ├── schemas.py          # Pydantic request/response models
│   ├── middleware.py       # Security headers, memory limits, timeouts
│   ├── auth_deps.py        # Auth dependencies with scoped permissions
│   └── routes/             # Modular route handlers
├── application/            # CQRS commands, queries, event bus, flows, mixins
│   ├── pipeline.py         # ReasonerPipeline orchestrator (real impl — pipeline.py root is a shim)
│   ├── orchestrator.py     # PipelineOrchestrator + preflight (HyperGate, preset resolution)
│   ├── flows/              # Phase functions bound to ReasonerPipeline by flow registry
│   ├── handlers/           # RunPipelineCommandHandler, ResumePipelineCommandHandler, etc.
│   ├── mixins/             # Method-specific mixins (debate, jury, research, writing, etc.)
│   └── services/           # PresetService, SearchService, RendererService
├── core/                   # Domain core: protocols, constants, settings, events, aggregates
│   ├── constants.py        # → re-exports constants_limits + constants_models
│   ├── constants_limits.py # Token budgets, timeouts, HyperGate thresholds, truncation
│   ├── settings.py         # Settings (pydantic-settings), dotenv load, CSRF/auth config
│   ├── ports/              # Hexagonal ports: LLMPort, SearchServicePort, FileSearchPort
│   ├── events/             # DomainEvent hierarchy + make_event() factory
│   └── aggregates/         # PipelineAggregate (event-sourced), WidgetAggregate
├── domain/                 # Business entities and declarative routing configs
│   ├── pipeline_state.py   # PipelineState (~60 fields) — canonical state model
│   ├── preset_core.py      # PipelinePreset, build_auto_preset(), _KNOWN_ROUTING_ROLES
│   └── preset_registry.py  # 48 preset configs with model routing and fallbacks
├── infrastructure/         # Adapters implementing Core ports
│   ├── llm/
│   │   ├── registry.py     # _MODEL_WHITELIST (131 models), _REGISTRY, build_provider()
│   │   ├── router.py       # ProviderRouter: role-based routing, fallback chain
│   │   └── providers/      # OpenAICompatibleProvider, OpenRouterProvider, etc.
│   ├── persistence/        # EventStore (SQLite), snapshots, postgres_store
│   └── websocket/          # WebSocket connection manager
├── hypergate/              # HyperGate pre-router: 5 parallel sub-agents + TieBreaker
│   ├── hyperagent.py       # HyperGateAgent orchestrator + fast-path regexes
│   ├── base_sub_agent.py   # Abstract base with LRU caching
│   └── sub_agents/         # language, complexity, direct, web_detector, method, tiebreaker
├── phases/                 # 31 prompt modules: _shared, _universal + 29 method modules
├── subagents/              # Phase sub-agents (enhancement, decomposition, critique, synthesis, search)
├── neuro/                  # Long-term memory: L1/L2/L3 tiered cache, compression, sessions
├── healing/                # Self-healing: introspection_engine, test_generation_engine
├── models.py               # Backward-compat shim → domain/pipeline_state.py + domain/models.py
└── pipeline.py             # Backward-compat shim → application/pipeline.py

ui-next/src/
├── app/                    # App Router (layout, page, providers, error, api routes)
├── components/             # chat/, layout/, phases/, ui/, widgets/
├── hooks/                  # usePipelineStream (SSE), useConversationHistory, useKeyboardShortcuts
├── lib/                    # api-client, db (IndexedDB), types, utils, security, markdown
└── stores/                 # app-store.ts (Zustand global state with persistence)

tests/                      # pytest suite (~60+ test files)
scripts/
└── update_mindmap_meta.py  # Patches live counts into ARCHITECTURE_MINDMAP.md (runs post-commit)
```

---

## 4. Commands

### Development

```bash
python start_all.py                                          # backend + frontend + SearXNG
uvicorn asgi:app --reload --host 0.0.0.0 --port 8003        # backend only
cd ui-next && npm run dev                                    # frontend only
docker-compose -f docker-compose.searxng.yml up -d          # SearXNG
pip install -r requirements.txt                             # install deps
```

### Testing

```bash
python -m pytest tests/ -v                                  # all tests
python -m pytest tests/ -v -m "not slow and not integration"
pytest tests/ --cov=src/reasoner --cov-report=html
pytest -n auto                                              # parallel
python -m pytest -m searxng                                 # requires live SearXNG
```

### CLI

```bash
python main.py --list-presets
python main.py --list-models
python main.py --problem "..." --preset debate-premium
python main.py --problem-file problem.txt --output result.json --preset multi-perspective-premium
python main.py --problem "..." --sequential                 # for rate-limited providers
python main.py --save-state state.json --problem "..." && python main.py --resume state.json
```

### Frontend

```bash
cd ui-next && npm run dev
cd ui-next && npm run build
cd ui-next && npx tsc --noEmit
cd ui-next && npx playwright test
```

---

## 5. Key Architecture Details

### HyperGate Pre-Router

Every request passes through `HyperGateAgent` before any pipeline. Five sub-agents run **in parallel** with fail-safe fallback. Real method names are never exposed to LLMs; only opaque letters (B–Q) appear in sub-agent prompts.

```
Problem → [LanguageDetector | ComplexityEstimator | DirectDetector | WebSearchDetector | MethodClassifier]
                                                          ↓ TieBreaker
                        DIRECT (instant) | WEB_SEARCH (real-time) | PIPELINE (method auto-selected)
```

Fast-path order before sub-agents fire: short prompt → writing intent → realtime patterns → factual patterns.

### Core Pipeline Flow

```
HyperGate → Phase 0: Classification (task type, language)
          → Phase 1: Decomposition (≤5 sub-problems, failure modes)
          → Phase 2: Multi-Perspective Generation (parallel, cross-lab: constructive/destructive/systemic/minimalist)
          → Phase 3: Critique & Pruning (independent scoring 0–10, retains top-k)
          → Phase 4: Stress Testing (optimal / constraint-violation / adversarial)
          → Phase 5: Synthesis (VERIFIED/HYPOTHESIS/UNKNOWN + Action Blueprint)
```

### Reasoning Methods (19 top-level + Verbalized Sampling sub-phases)

| Method | Description |
|--------|-------------|
| **Orchestrated** | Default 6-phase multi-perspective |
| **Debate** | Adversarial opening, rebuttal, judge |
| **Jury** | Expert panel: generator, critic, verifier |
| **Research** | Web-grounded iterative RAG (Prism loop) |
| **Scientific** | Hypothesis generation + falsification |
| **Socratic** | Elenchus questioning to expose assumptions |
| **Pre-Mortem** | Prospective failure analysis |
| **Bayesian** | Prior → likelihood → posterior belief updating |
| **Dialectical** | Hegelian thesis-antithesis-synthesis |
| **Analogical** | Cross-domain structure-mapping |
| **Delphi** | Structured expert consensus |
| **CoVE** | Chain-of-Verification: draft → verify → revise |
| **SoT** | Skeleton-of-Thought: skeleton → parallel solve → assemble |
| **ToT** | Tree-of-Thoughts: search + evaluate + backtrack |
| **PoT** | Program-of-Thoughts: executable code as reasoning |
| **Self-Discover** | Dynamic reasoning module composition |
| **Writing** | Creative writing with hallucination guards |
| **Brainstorming** | Divergent idea generation |
| **Coding** | Code-focused structured reasoning |

### Presets (48)

Every method has **Budget** (~$0.02/run) and **Premium** (~$0.15–$0.30/run) tiers. The UI orders Budget → Balanced → Premium, defaulting to the first (cheapest) method/preset.

### Model Routing Philosophy

Cross-lab diversity prevents echo chambers:
- **Phase 2 (Perspectives):** ≥3 different labs in Budget, ≥4 in Premium
- **Scoring:** Scorer must be from a different ecosystem than the dominant generator
- **Fallbacks:** Fail to cross-lab equivalent, never blindly to preset primary

### Key Invariants

- Method-specific state uses `dict[str, Any]` fields with `field(default_factory=dict)`. Always access via `.get()`, never direct subscript — enables `--resume` with older state files.
- All LLM responses parsed via `parsing.extract_json()`, never direct `json.loads`.
- `sanitize_for_prompt()` must gate all user-supplied text before it enters any prompt.
- `CSRF_ENFORCE_BACKEND=false` in CI envs (no `CSRF_SECRET` available).

---

## 6. Working with Neuro & Compression

- **Recall:** `neuro.server.create_neuro_router()` → `/neuro/recall` — auto-called in pipeline run.
- **Learn:** `/neuro/learn` saves final synthesis at pipeline end.
- **Compression:** `neuro.compression.smart_compress(text, ext, level)` — `Aggressive` keeps only signatures; `Minimal` does general cleanup.
- **L1/L2/L3:** L1=memory, L2=disk JSON, L3=Neuro LTM with embedding search.
- **Tenant isolation:** Use `agent_id` in Neuro requests → `~/.neuro/agents/<id>`.

---

## 7. Cross-Cutting Concerns

### Security (Defense in Depth)
- **Input:** `sanitization.sanitize_for_prompt()` — XSS stripping, null-byte removal, prompt-injection regex, unicode NFKC normalization
- **Auth:** Token-based with scoped permissions (`auth.py`)
- **Rate limiting:** Token-bucket per client IP (`rate_limiter.py`)
- **CSRF:** HMAC-SHA256 signed tokens in Next.js API routes and FastAPI `require_csrf`
- **Circuit breaker:** Automatic provider fallback (`circuit_breaker.py`)
- **Headers:** X-Frame-Options, X-Content-Type-Options, Referrer-Policy, HSTS, CSP

### Self-Healing CI/CD

`.github/workflows/self-healing-ci.yml` — healing-profile → loop1-static → loop2-runtime → loop3-evolutionary → searxng-integration → healing-verification. Coverage gates: 60% fail, 80% warn.

---

## 8. Workflow Orchestration

1. **Plan First** — Enter plan mode for any non-trivial task (3+ steps or architectural decisions).
2. **Subagent Strategy** — Use subagents liberally to keep main context clean. Offload research and parallel analysis.
3. **Verification Before Done** — Never mark a task complete without proving it works (tests, logs, diffs).
4. **Autonomous Bug Fixing** — When given a bug report, just fix it. Point at logs, errors, failing tests — then resolve them.

---

## 9. Core Principles

- **Simplicity First** — Make every change as simple as possible. Impact minimal code.
- **Root Causes** — No temporary fixes. Senior developer standards.
- **Minimal Impact** — Changes should only touch what's necessary.

---

## 10. Living Documentation

| Doc | How it updates |
|-----|---------------|
| `ARCHITECTURE_MINDMAP.md` | `post-commit` hook patches date + counts (models, presets, files) automatically via `scripts/update_mindmap_meta.py` |
| `graphify-out/` | `post-commit` and `post-checkout` hooks rebuild the knowledge graph automatically |
| `AGENTS.md` | Manual — update when adding methods, presets, or major architectural changes |

*For complete architectural analysis see `ARCHITECTURE_MINDMAP.md`. For dependency graph see `graphify-out/GRAPH_REPORT.md`.*
