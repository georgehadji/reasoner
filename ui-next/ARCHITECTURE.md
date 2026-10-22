# Reasoner Next.js UI — Architecture Overview

This document describes the architecture of the production-grade Next.js frontend (`ui-next/`) that proxies to the existing FastAPI backend (`api.py`).

---

## 1. Authentication Flow

### Current State (Pass-Through Proxy)

The Next.js app acts as a **transparent frontend layer**. Authentication is currently handled by the FastAPI backend.

```
┌─────────────┐      (1) Request       ┌─────────────────┐
│   Browser   │ ───────────────────────>│   Next.js App   │
│  (ui-next)  │                         │  (App Router)   │
└─────────────┘                         └─────────────────┘
                                                │
                                                │ (2) Proxy
                                                ▼
                                       ┌─────────────────┐
                                       │   FastAPI       │
                                       │   (api.py)      │
                                       │  HTTPBearer     │
                                       └─────────────────┘
```

**How it works:**
- FastAPI's `api.py` uses `HTTPBearer(auto_error=False)` and an `auth_manager` to protect routes.
- The Next.js API route proxies forward the **original headers** (including `Authorization`) to the backend.
- No secrets are exposed to the client bundle. The backend URL lives in `.env.local` as `NEXT_PUBLIC_API_BASE_URL`.

### Production Extension Path

To add auth in the Next.js layer (e.g., for a public deployment):

1. **Middleware** (`middleware.ts`): Validate a session token or JWT at the edge.
2. **API Routes**: Inject an internal service token (from `process.env`) before proxying to FastAPI.
3. **Client**: Store a short-lived access token in `httpOnly` cookies, managed by Next.js API routes.

---

## 2. API Structure

### Next.js App Router Routes

| Route | File | Purpose |
|-------|------|---------|
| `GET /` | `app/page.tsx` | Main chat interface (static prerender) |
| `POST /api/run` | `app/api/run/route.ts` | Proxy SSE stream to FastAPI |
| `POST /api/stop` | `app/api/stop/route.ts` | Proxy stop command |
| `DELETE /api/cache` | `app/api/cache/route.ts` | Proxy cache clear |
| `GET /api/presets` | `app/api/presets/route.ts` | Proxy preset metadata |
| `GET /api/weather` | `app/api/weather/route.ts` | Proxy weather widget |
| `GET /api/stocks` | `app/api/stocks/route.ts` | Proxy stock widget |
| `POST /api/calculate` | `app/api/calculate/route.ts` | Proxy calculator widget |

All proxies use the same pattern:

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';
```

### Why Proxy Instead of Direct Fetch?

- **CORS elimination**: The browser talks to the same origin (`localhost:3000`).
- **Header injection**: You can add auth, rate-limiting, or logging in the Next.js layer later without touching the Python backend.
- **Secret isolation**: The FastAPI URL is a server-side env var.

---

## 3. Data Flow

### 3.1 High-Level Overview

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Browser   │<--->│  Zustand     │<--->│  React UI       │
│             │     │  (app-store) │     │  Components     │
└─────────────┘     └──────────────┘     └─────────────────┘
        │                                              │
        │ (SSE Stream)                                 │ (CRUD)
        ▼                                              ▼
┌─────────────┐                              ┌─────────────────┐
│  usePipeline │                              │   IndexedDB     │
│  Stream      │                              │   Reasoner_Pipeline  │
└─────────────┘                              └─────────────────┘
        │                                              ▲
        │ Proxy POST /api/run                          │ load/save
        ▼                                              │
┌─────────────────┐                          ┌─────────────────┐
│   Next.js API   │                          │ useConversation │
│   Proxy         │                          │ History Hook    │
└─────────────────┘                          └─────────────────┘
        │
        ▼
┌─────────────────┐
│   FastAPI       │
│   /api/run      │
│   (SSE source)  │
└─────────────────┘
```

### 3.2 State Management Layers

#### A. Client State — Zustand (`stores/app-store.ts`)

**Responsibilities:**
- `running`: boolean — is a pipeline currently streaming?
- `method`: selected reasoning method (`multi-perspective`, `jury`, etc.)
- `presetIndex`, `isSequential`, `isExpert`, `sidebarCollapsed`
- `composerText`: controlled textarea value
- `activeRun`: transient run metadata (progressId, phases accumulated so far)

**Persistence:** Zustand is configured with `persist` middleware using `localStorage` for user preferences (method, preset index, toggles).

#### B. Server State — SWR (`hooks/usePresets.ts`)

**Responsibilities:**
- `usePresets()` fetches `/api/presets` with 60-second stale-while-revalidate.
- `useServerStatus()` pings `/api/presets` every 10 seconds to update the server status dot.

#### C. Browser Persistence — IndexedDB (`lib/db.ts`)

**Schema:**
- Database: `Reasoner_Pipeline`
- Store: `conversations` (keyPath: `id`)
- Records: `{ id, timestamp, problem, phases[], errors, preset, method, total_tokens }`

**Lifecycle:**
1. Pipeline finishes (`done` SSE event).
2. `page.tsx` constructs a `Conversation` object.
3. `saveConversation()` writes to IndexedDB.
4. `useConversationHistory` refreshes the sidebar list.

---

### 3.3 Streaming Data Flow (SSE)

The most complex data path is the **pipeline run**:

```typescript
// 1. User submits from Composer
handleSubmit() -> usePipelineStream.startRun(req, onEvent)

// 2. Hook opens fetch() to /api/run with ReadableStream
const reader = resp.body.getReader();
while (true) {
  const { done, value } = await reader.read();
  buffer += decoder.decode(value, { stream: true });
  // Parse SSE lines: "data: {json}
"
  const ev: PhaseEvent = JSON.parse(line.slice(6));
  onEvent(ev);
}

// 3. page.tsx onEvent dispatcher handles each event type:
//    - 'start' / 'cached' -> visual badge
//    - 'phase_start' -> progress card active step
//    - 'phase_complete' -> add PhaseDispatcher component to message list
//    - 'phase_error' -> mark step error
//    - 'cancelled' -> InfoCard
//    - 'done' -> ErrorCard (if errors), RunFooter, save to IndexedDB
```

**Abort/Stop Flow:**
- User presses `Esc` or clicks **Stop**.
- `stopRun()` aborts the `fetch()` via `AbortController` and sends `POST /api/stop` to the backend.
- The backend terminates the active pipeline run.

---

### 3.4 Component Rendering Flow

Messages are stored as a discriminated union in `page.tsx`:

```typescript
type MessageItem =
  | { type: 'problem'; text: string }
  | { type: 'progress'; id: string }
  | { type: 'phase'; id: string; phase: number; name: string; data: unknown }
  | { type: 'error'; id: string; errors: string[] }
  | { type: 'info'; id: string; messages: string[] }
  | { type: 'footer'; id: string; tokens: TokenCount };
```

Rendering in `page.tsx`:

```tsx
{messages.map((msg) => {
  if (msg.type === 'problem') return <ProblemBubble ... />;
  if (msg.type === 'progress') return <ProgressCard ... />;
  if (msg.type === 'phase') return <PhaseDispatcher phase={...} data={...} />;
  if (msg.type === 'error') return <ErrorCard ... />;
  if (msg.type === 'info') return <InfoCard ... />;
  if (msg.type === 'footer') return <RunFooter ... />;
})}
```

`PhaseDispatcher` maps `(method, phase, data)` to the correct renderer:
- `ClassificationRenderer`
- `DecompositionRenderer`
- `PerspectivesRenderer` / `ScoringRenderer` / `StressRenderer`
- `SynthesisRenderer`
- Method-specific variants: `SocraticRenderer`, `ScientificRenderer`, `DebateRenderer`, `JuryRenderer`

---

## 4. File-to-Responsibility Map

| Concern | Entry Point |
|---------|-------------|
| **App Shell** | `app/layout.tsx` |
| **Main Page** | `app/page.tsx` |
| **API Proxies** | `app/api/*/route.ts` |
| **Global State** | `stores/app-store.ts` |
| **SSE Stream** | `hooks/usePipelineStream.ts` |
| **Canvas Background** | `hooks/useLiquidCanvas.ts` + `components/canvas/LiquidCanvas.tsx` |
| **IndexedDB** | `lib/db.ts` |
| **Phase Rendering** | `components/phases/PhaseDispatcher.tsx` |
| **Config/Constants** | `lib/config.ts` |
| **Types** | `lib/types.ts` |

---

## 5. Security & Performance Notes

- **No server secrets leak to the client**: `API_BASE` is only used in API Route handlers or `next.config.ts` rewrites.
- **CSP-friendly**: No inline `eval()` or dangerous DOM operations; widgets use typed data props.
- **Reduced motion support**: `useLiquidCanvas` checks `prefers-reduced-motion` and skips animation.
- **Error boundaries**: Can be added at `app/error.tsx` to catch render crashes without white-screening the app.

---

## 4. Build, Test, and Development Commands

### Backend
```bash
# Install dependencies
pip install -r requirements.txt

# Run CLI
python main.py --list-presets
python main.py --list-models
python main.py --problem "..." --preset <id> [--top-k N] [--sequential] [--source-type <type>]
python main.py --resume state.json

# Start API server
uvicorn asgi:app --reload --port 8003

# Run tests
python -m pytest -v
python -m pytest test_parsing.py test_models.py test_perplexity_config.py
python -m pytest -m "not slow"          # Skip slow tests
python -m pytest --run-slow             # Include slow tests
python -m pytest -m searxng             # SearXNG integration tests (requires live instance)

# With coverage
python -m pytest tests/ --cov=src/reasoner --cov-report=html

# Python linting (no formal config file — manual consistency)
ruff check src/reasoner/
ruff format src/reasoner/

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

### Frontend
```bash
cd ui-next
npm install
npm run dev
```

The dev server starts on `http://localhost:3000` by default.

## Environment Variables

Create `.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

This should point to the FastAPI backend (`api.py`).

## Build

```bash
npm run build
```

## Architecture Notes

- **API Proxies:** All `/api/*` routes are proxied to the FastAPI backend to avoid CORS and allow future auth middleware.
- **SSE Streaming:** The run endpoint streams Server-Sent Events via `fetch` + `ReadableStream` in `usePipelineStream`.
- **Canvas Background:** The liquid-lava animation from the legacy UI is ported to `useLiquidCanvas` and tied to the `running` state.
- **Phase Renderers:** All legacy phase rendering logic (`renderer.js`) is ported to typed React components under `components/phases/renderers/`.
- **History:** Conversations are persisted to IndexedDB and surfaced in the sidebar.

---

## 5. Code Style & Naming Conventions

### Python
- **Indentation:** 4 spaces
- **Functions/variables/modules:** `snake_case`
- **Dataclasses, enums, test classes:** `PascalCase`
- **Type hints:** Prefer type hints when intent is unclear; use `from __future__ import annotations` at the top of files when using modern typing
- **Docstrings:** Use triple-double-quote docstrings for modules and public functions
- **Imports:** Group stdlib, third-party, and local imports separately
- **No formal linter config** (no `ruff.toml`, `mypy.ini`, or `.pre-commit-config.yaml`) exists at repo root. Rely on manual consistency.

### TypeScript / Frontend
- **Components:** PascalCase files, default export for page components
- **Hooks:** `useCamelCase`
- **Styling:** Tailwind CSS + Reasoner CSS variable design system
- **Accent colors:** Preserve the `--method-accent-rgb` CSS custom property when adjusting gradients or glass panels
- **UI blocks:** Document new helper UI blocks in the same file rather than scattering markup elsewhere
- **ESLint:** Uses ESLint 9 flat config (`eslint.config.mjs`) extending `eslint-config-next/core-web-vitals` and `eslint-config-next/typescript`

---

## 6. Testing Strategy

- **Framework:** pytest with pytest-asyncio, pytest-timeout
- **Location:** `tests/` directory at repo root
- **Count:** 140+ test files
- **Naming:** `test_*.py` files, `Test…` classes
- **Configuration:** `pytest.ini` sets `testpaths = tests` and `pythonpath = src`
- **Markers:**
  - `slow` — deselect with `-m "not slow"`; include with `--run-slow`
  - `integration` — integration tests
  - `timeout` — tests with timeout threshold (requires pytest-timeout)
  - `searxng` — tests requiring a live SearXNG instance
- **Async config:** `asyncio_mode = auto` and `asyncio_default_fixture_loop_scope = session` in `pytest.ini`. All async fixtures share a single event loop for the entire test session because the project uses in-memory singletons (rate limiter, circuit breaker, auth store) that persist across tests.
- **Fixtures:** Defined in `tests/conftest.py`:
  - `sample_pipeline_state`, `sample_llm_messages`, `sample_llm_config`, `mock_llm_response`
  - `sample_widget_params`, `sample_domain_events`
  - `searxng_container` (session-scoped Docker compose fixture), `searxng_client`
  - `run_state_store`, `temp_event_store`
  - `event_loop_policy` (Windows-compatible selector event loop)
  - `writable_temp_dirs` (session-scoped autouse)
  - `clear_token_cache` (async autouse to prevent stale cache hits)
- **Test environment:** `CSRF_ENFORCE_BACKEND` is set to `"false"` in `conftest.py` so tests do not need CSRF tokens.
- **Coverage target:** ~70%, minimum gate 60% (enforced in CI)
- **Guidelines:**
  - Add regression coverage when fixing parsing, routing, or UI rendering bugs
  - Assert on both happy and fallback paths
  - Use `pytest --run-slow` to include slow tests
  - `--durations=10` is enabled by default to show the 10 slowest tests per run

---

## 7. Configuration & Environment

### Required Environment Variables (`.env`)
Copy `.env.example` to `.env` and fill in:

**LLM API Keys**
| Variable | Purpose |
|----------|---------|
| `OPENROUTER_API_KEY` | Primary LLM access (recommended single key for 346+ models) |
| `OPENAI_API_KEY` | Direct OpenAI access (optional) |
| `ANTHROPIC_API_KEY` | Direct Anthropic access (optional) |
| `GOOGLE_API_KEY` | Direct Google Gemini access (optional) |
| `DEEPSEEK_API_KEY` | Direct DeepSeek access (optional) |
| `MISTRAL_API_KEY` | Direct Mistral access (optional) |
| `XAI_API_KEY` | Direct xAI Grok access (optional) |
| `PERPLEXITY_API_KEY` | Perplexity Sonar access (optional) |
| `DASHSCOPE_API_KEY` | Alibaba Qwen access (optional) |
| `MOONSHOT_API_KEY` | Moonshot Kimi access (optional) | `ZHIPUAI_API_KEY` | ZhipuAI GLM access (optional) |

**Security & Admin**
| Variable | Purpose |
|----------|---------|
| `ADMIN_API_KEY` | Required for production admin endpoints; generate with `secrets.token_urlsafe(32)` |
| `CSRF_SECRET` | HMAC-SHA256 signing secret; generate with `secrets.token_urlsafe(32)` |
| `ENVIRONMENT` | `development` or `production`; omitting defaults CORS to dev mode (insecure) |

**Server & Networking**
| Variable | Purpose |
|----------|---------|
| `DEBUG` | Must be `false` in production |
| `LOG_LEVEL` | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `SERVER_HOST` / `SERVER_PORT` | FastAPI bind address (default 127.0.0.1:8003) |
| `UVICORN_HOST` | Uvicorn bind host (default 127.0.0.1; use 0.0.0.0 in containers) |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins |
| `REASONER_API_URL` | Frontend proxy target (default http://localhost:8003) |
| `TRUSTED_PROXIES` | Comma-separated IPs for X-Forwarded-For parsing (optional) |

**Rate Limiting & Resilience**
| Variable | Purpose |
|----------|---------|
| `RATE_LIMIT_PER_MINUTE` / `RATE_LIMIT_PER_HOUR` / `RATE_LIMIT_BURST` | Token-bucket config |
| `RATE_LIMITER_MODE` | `memory` (default, unsafe for multi-worker) or `redis` |
| `CIRCUIT_BREAKER_MODE` | `memory` (default, unsafe for multi-worker) or `redis` |
| `MEMORY_LIMIT_MB` / `MEMORY_WARNING_MB` | Process memory limits |
| `REQUEST_TIMEOUT_SECONDS` | Request timeout (default 300) |

**Search & Documents**
| Variable | Purpose |
|----------|---------|
| `SEARXNG_URL` | SearXNG instance URL (default: http://localhost:8888) |
| `COHERE_RERANK_ENABLED` | Enable Cohere reranking via OpenRouter |
| `DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED` | Opt-in semantic chunking for uploaded files |
| `DOCUMENT_CHUNK_SIZE` / `DOCUMENT_CHUNK_OVERLAP` / `DOCUMENT_INDEX_MAX_CHARS` | Chunking params; characters indexed per document |

**SaaS Auth**
| Variable | Purpose |
|----------|---------|
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY` | Supabase project credentials |
| `JWT_SECRET_KEY` | Local dev JWT fallback when Supabase is unavailable |
| `ENABLE_LEGACY_API_KEY` | Set `true` for v1 API backward compatibility |

**Database & Cache**
| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string (default with asyncpg driver) |
| `POSTGRES_PASSWORD` | Standalone Postgres password |
| `DB_POOL_SIZE` | Asyncpg connection pool size (default 10) |
| `REDIS_URL` | Redis connection string (default redis://localhost:6379/0) |

**Stripe Billing**
| Variable | Purpose |
|----------|---------|
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | Stripe API and webhook secrets |
| `STRIPE_PRO_PRICE_ID` / `STRIPE_ENTERPRISE_PRICE_ID` | Product price IDs |
| `APP_URL` | Frontend URL for checkout redirects (default http://localhost:3000) |

**Git Integration (Optional)**
| Variable | Purpose |
|----------|---------|
| `ORCHESTRATOR_GIT_ENABLED` | Enable Git integration |
| `ORCHESTRATOR_GIT_STRATEGY` | `manual`, `after_each_task`, `after_phase`, or `after_project` |
| `ORCHESTRATOR_GIT_AUTO_PUSH` | Auto-push to remote (use with caution) |

**NEVER commit `.env` with real values.**

---

## 8. Security Considerations

- **Input Sanitization:** All user inputs pass through `reasoner.sanitization.sanitize_for_prompt()` before reaching LLM prompts
- **Prompt Injection Defense:** Layered filtering in sanitization module + adversarial persuasion defense (`reasoner_persuasion_defense.py`)
- **XSS Prevention:** Regex-based `<script>` stripping, HTML tag removal, NFKC normalization in `RunRequest.validate_problem()`
- **Rate Limiting:** Token-bucket rate limiter per client IP (`rate_limiter.py`); Redis backend available for multi-worker deployments
- **Authentication:** Token-based auth with scoped permissions (`auth.py`); Supabase JWT primary, local JWT fallback
- **Circuit Breaker:** Automatic fallback when providers fail (`circuit_breaker.py`)
- **CSRF Protection:** CSRF token endpoints for state-changing operations (HMAC-SHA256 signed, verified in Next.js API routes **and** FastAPI backend via `require_csrf`)
- **Security Headers:** X-Frame-Options, X-Content-Type-Options, Referrer-Policy, HSTS (production), dynamic CSP with WebSocket origin allowlist
- **CORS:** Restricted to known origins (configurable via `CORS_ORIGINS` env var) with an explicit header whitelist
- **Frontend proxy validation:** Next.js API routes validate upstream URLs against port allowlists and block private IPs in production
- **Admin endpoint hardening:** Admin endpoints require BOTH a valid JWT with `admin` scope AND a correct `X-Admin-Key` header; uses `secrets.compare_digest()` for constant-time comparison
- **Environment guard:** `ENVIRONMENT=development` explicitly logs an insecure-CORS warning on startup
- **Horizontal Scaling Limitations:** Rate limiter, circuit breaker, and auth store are in-memory by default. For multi-worker deployments, enable `AUTH_PERSISTENCE_ENABLED=true`, set `RATE_LIMITER_MODE=redis` / `CIRCUIT_BREAKER_MODE=redis`, and place a shared rate limiter (e.g., Redis or reverse-proxy) in front of the app.

---

## 9. Architecture Patterns

1. **Event Sourcing** — Pipeline state derived from domain events stored in SQLite/PostgreSQL
2. **CQRS** — Separate command and query handlers in `application/`
3. **Hexagonal Architecture** — Domain depends on protocols (Widget, Phase), not concrete implementations
4. **Mixin Pattern** — Method-specific behaviors composed via 13 mixins; explicit `PipelineMixinProtocol` contract
5. **Provider Router with Fallbacks** — Cross-lab diversity with automatic fallback on failure; `_REGISTRY` maps 70+ model IDs
6. **HyperGate Pre-Routing** — 6 parallel sub-agents detect language, complexity, directness, web need, and optimal method
7. **Token Optimization** — Phase-specific budgets (`PHASE_TOKEN_BUDGETS`), context compression (`ContextCompressor`), token-aware caching
8. **Security in Depth** — Input sanitization, prompt injection filtering, rate limiting, scoped auth, CSRF protection, XSS prevention
9. **Dual-Stream Frontend** — SSE carries all phase data/events; WebSocket is used ONLY for control signals (stop, status) to avoid double-processing
10. **SaaS-Ready** — Supabase auth, Stripe billing, Redis caching, PostgreSQL persistence, quota enforcement, tiered presets

---

## 10. Working with Neuro & Compression

- **Recall (Bootstrap):** `neuro.server.create_neuro_router()` provides the `Recall` endpoint. Automatically called in `ReasonerPipeline.run` to fetch relevant context from long-term memory.
- **Learn (Ingest):** The `Learn` endpoint is called at the end of the pipeline to save the final synthesis. Tag entries with metadata (e.g., `preset`, `task_type`).
- **Compression:** Use `neuro.compression.smart_compress(text, ext, level)` to reduce token usage. Modes:
  - `Aggressive` — structural analysis, keeps only signatures
  - `Minimal` — general cleanup
- **Tenant Isolation:** Use `agent_id` in Neuro requests to ensure data is stored in separate directories (`~/.neuro/agents/<id>`).

---

## 11. Reasoning Methods (17)

The pipeline supports 17 reasoning methodologies. Each method has its own phase module and renderer:

1. **Multi-Perspective** — Parallel constructive/destructive/systemic/minimalist analysis
2. **Debate** — Adversarial reasoning with opening, rebuttal, judge phases
3. **Jury** — Expert panel with generator, critic, verifier roles
4. **Research** — Web-grounded iterative RAG with deep discovery
5. **Scientific** — Hypothesis generation and falsification
6. **Socratic** — Deep questioning through dialectic
7. **Pre-Mortem** — Risk analysis via future failure simulation
8. **Bayesian** — Belief updating with probabilistic reasoning
9. **Dialectical** — Thesis-antithesis-synthesis
10. **Analogical** — Cross-domain analogy mapping
11. **Delphi** — Expert panel consensus (structured)
12. **CoVE** — Chain-of-Verification
13. **SoT** — Skeleton-of-Thought
14. **ToT** — Tree-of-Thoughts
15. **PoT** — Program-of-Thoughts
16. **Self-Discover** — Dynamic reasoning module composition
17. **Writing** — Creative writing with hallucination guards

---

## 12. Presets & Model Routing

Presets define which models are used for each phase role. The UI orders methods (and their Budget → Balanced → Premium presets) from most cost-effective to least and defaults to the first method/preset.

- **Budget** — Cheapest models, fastest
- **Balanced** — Mid-tier quality/cost tradeoff
- **Premium** — Best available models

Key commands:
```bash
python main.py --list-presets      # Show all presets + key status
python main.py --list-models       # Show all model IDs grouped by ecosystem
```

---

## 13. CI/CD

- **File:** `.github/workflows/self-healing-ci.yml`
- **Triggers:** Push to `main`/`develop`, PRs to `main`, nightly cron (2 AM), manual dispatch
- **Jobs:**
  - `healing-profile` — baseline coverage, doc gaps, monitoring gaps
  - `loop1-static-healing` — introspection engine + test generation + coverage gating (60% fail, 80% warn)
  - `loop2-runtime-healing` — circuit breaker + health checks + smoke tests
  - `loop3-evolutionary-healing` — failure patterns, spec drift, optimization proposals
  - `searxng-integration` — SearXNG integration tests
  - `healing-verification` — artifact verification

---

## 14. Commit & Pull Request Guidelines

- Follow short, imperative subjects with Conventional prefixes (`feat:`, `fix:`, `docs:`, etc.)
- Describe UI changes (screenshots if layout shifts) and note commands you ran
- When the feature touches presets, methods, or docs, mention CRITICAL API keys or `.env` expectations in the PR
- Update `README.md`, `CLAUDE.md`, and `QWEN.md` whenever new stages, methods, or UI affordances ship

---

## 15. Workflow Orchestration (Agent Guidelines)

### Plan Node Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- One task per subagent for focused execution

### Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Review lessons at session start for relevant project

### Verification Before Done
- Never mark a task complete without proving it works
- Run tests, check logs, demonstrate correctness
- Ask yourself: "Would a staff engineer approve this?"

### Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky, implement the elegant solution
- Skip this for simple, obvious fixes — don't over-engineer

### Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them

---

## 16. Task Management

1. **Plan First:** Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan:** Check in before starting implementation
3. **Track Progress:** Mark items complete as you go
4. **Explain Changes:** High-level summary at each step
5. **Document Results:** Add review section to `tasks/todo.md`
6. **Capture Lessons:** Update `tasks/lessons.md` after corrections

---

## 17. Core Principles

- **Simplicity First:** Make every change as simple as possible. Impact minimal code.
- **Root Causes:** Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact:** Changes should only touch what's necessary. Avoid introducing bugs.
