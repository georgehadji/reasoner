# Reasoner

**A production-grade, multi-agent reasoning orchestrator that decomposes complex problems into structured multi-phase pipelines, executes them across diverse LLM ecosystems in parallel, and synthesizes verified answers with epistemic confidence labels.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js 16](https://img.shields.io/badge/Next.js_16-000000.svg?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6.svg?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tests](https://img.shields.io/badge/tests-2%2C700%2B_passing-brightgreen.svg?style=flat-square)](./tests)
[![Coverage](https://img.shields.io/badge/coverage-~64%25-yellow.svg?style=flat-square)](.)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)

[Quick Start](#quick-start) · [Architecture](#architecture) · [Reasoning Methods & Presets](#reasoning-methods--presets) · [Programmatic Usage](#programmatic-usage) · [Security](#security--encryption) · [Configuration](#configuration-reference) · [Development](#development) · [Deployment](#deployment)

---

## Overview

Reasoner treats reasoning as a first-class engineering problem rather than a one-shot LLM call. Given a question, strategic decision, or research task, it:

1. **Classifies and routes** the request to one of 24 reasoning methodologies via the HyperGate pre-router — 5 parallel sub-agents plus a tie-breaker, deciding between an instant direct answer, a real-time web search, or the full pipeline.
2. **Decomposes** the problem into atomic sub-questions and key assumptions in the same call that classifies it.
3. **Vets context** through iterative, web-grounded retrieval (Perplexity Sonar / Brave / Tavily) with token-aware compression.
4. **Generates competing answers** from cross-lab, cross-bloc model ensembles (172 registered models across 28 vendors — Anthropic, OpenAI, Google, DeepSeek, Mistral, xAI, Qwen, and more — plus 350+ additional models reachable through OpenRouter) to reduce single-vendor and single-geopolitical-bloc bias.
5. **Critiques and stress-tests** candidates with independent LLM judges under adversarial conditions.
6. **Synthesizes** a final, evidence-grounded answer labeled `VERIFIED`, `HYPOTHESIS`, or `UNKNOWN`, with citations.

The system is built for production deployment: real-time Server-Sent Events (SSE) streaming, per-phase cost telemetry, a self-healing CI loop, internal TLS with an auto-provisioned PKI, application-layer envelope encryption, per-user quotas and Stripe/PayPal billing, and Bearer-token endpoints designed for autonomous AI agents.

**Version:** 2.1.0 (single source of truth: `src/reasoner/__init__.py`) · **License:** MIT · **Python:** 3.12+

---

## Architecture

Every request passes through the **HyperGate pre-router** before any pipeline work begins, then — for requests that warrant it — through the **default multi-perspective pipeline**, managed by the `ReasonerPipeline` engine and expressed as a `WorkflowStrategy` (22 implementations under `application/flows/`). The flow is fully asynchronous:

```
                  ┌─────────────────────────────────────┐
                  │      User Question / Problem        │
                  └──────────────────┬──────────────────┘
                                     │
     ┌──────────────────── HyperGate Pre-Router ────────────────────┐
     │  5 parallel sub-agents (language, complexity, direct,        │
     │  web-search, method) → TieBreaker                            │
     └──────┬─────────────────────┬─────────────────────┬───────────┘
            │                     │                     │
       DIRECT answer        WEB_SEARCH            PIPELINE (method
       (instant)            (real-time)            auto-selected)
                                                          │
                                          [ Phase 0/1: Fusion — classification
                                            + decomposition, merged ]
                                                          │
                                          [ Phase 1.5: Evidence Search ] <── (iterative
                                                          │                    RAG, method-gated)
                                          [ Phase 2: Perspectives ] ──────┐
                                                          │              │ (cross-lab, cross-bloc
                                          [ Phase 3: Critique & Pruning ]│  generation ensembles)
                                                          │              │
                                          [ Phase 4: Stress Testing ] <──┘  (skipped when
                                                          │                  complexity = simple)
                                          [ Phase 5: Synthesis ]
                                                          │
                  ┌───────────────────────────────────────▼──────────────────┐
                  │  Synthesis: VERIFIED / HYPOTHESIS / UNKNOWN + citations  │
                  └────────────────────────────────────────────────────────┘
```

| Phase | Responsibility |
| :--- | :--- |
| HyperGate | Routes to DIRECT / WEB_SEARCH / PIPELINE; real method names are never exposed to the classifying LLMs, only opaque letters. |
| 0/1. Fusion | Combines task classification (math, research, creative, coding, ...) and problem decomposition into atomic sub-questions in a single call. |
| 1.5. Evidence Search | Iterative, web-grounded retrieval with smart token compression at the phase handoff; gated per method. |
| 2. Perspectives | Cross-lab, cross-bloc model ensembles produce competing answers (constructive / destructive / systemic / minimalist). |
| 3. Critique & Pruning | Independent LLM judges score candidates 0–10 and retain the top-k; this gate is critical — a failure here halts the run. |
| 4. Stress Testing | Adversarial probing of surviving candidates (optimal / constraint-violation / adversarial conditions); skipped for simple-complexity requests. |
| 5. Synthesis | Consolidates verified perspectives into one answer with epistemic labels and citations. |

Other methods (Debate, Jury, Research, Scientific, ToT, Coding, ...) compose their own `WorkflowStrategy` with a different phase sequence — see the [Reasoning Methods & Presets](#reasoning-methods--presets) table below.

Internally, the codebase follows **hexagonal DDD** (domain logic depends on ports, not providers) with **CQRS + event sourcing** (`PipelineAggregate` replay) and a **provider router with automatic cross-lab fallback**. See `AGENTS.md` for the full architectural map, including the small set of documented, intentional layer-boundary exceptions.

---

## Quick Start

### Prerequisites

- **Python 3.12+**
- **Node.js 20+** (frontend web UI)
- **OpenRouter API key** (recommended — one billing interface for 350+ models)
- **Redis** (optional for local development; required in production — the rate limiter and circuit breaker refuse to start in-memory when `ENVIRONMENT=production`)

### 1. Installation

```bash
git clone https://github.com/georgehadji/Reaseoner.git
cd Reaseoner

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # then edit .env — at minimum set OPENROUTER_API_KEY
```

### 2. Launch

Start the FastAPI backend and the Next.js frontend with one command:

```bash
python start_all.py
```

| Service | Address | Configurable via |
| :--- | :--- | :--- |
| FastAPI backend | `http://localhost:8003` | `SERVER_PORT` |
| Next.js frontend | `http://localhost:3000` | — |

For the full containerized production stack (Caddy reverse proxy with automatic HTTPS, backend, frontend, PostgreSQL, Redis):

```bash
docker compose up -d
```

### 3. CLI Examples

```bash
# Default preset (multi-perspective-budget)
python main.py --problem "How should we prioritize our Q3 engineering roadmap?"

# Budget preset — low-cost run
python main.py --problem "Explain the long-term impact of quantum cryptography." --preset debate-budget

# Premium multi-perspective analysis with top-tier models
python main.py --problem "Evaluate microservices vs monolithic architecture for a startup." --preset multi-perspective-premium

# Sequential generation for rate-limited providers
python main.py --problem "Analyze the Fermat's Last Theorem proof." --preset scientific-premium --sequential

# Discovery
python main.py --list-presets      # All presets with API-key status
python main.py --list-models       # All model IDs grouped by ecosystem
```

Useful flags: `--top-k N`, `--source-type {general,academic,social,news,code}`, `--domain DOMAIN`, `--enhance-prompt`, `--force-pipeline`, `--output PATH`, `--save-state PATH` / `--resume PATH`, `--quiet`. Full reference: `python main.py --help`.

---

## Reasoning Methods & Presets

Reasoner ships with **50 presets across 24 methodologies**. Each method ships a cost-efficient **Budget** preset and a quality-focused **Premium** preset; the UI orders methods from most to least cost-effective.

| Methodology | Budget | Premium | Strategy | Recommended Use Case |
| :--- | :--- | :--- | :--- | :--- |
| **Multi-Perspective** | `multi-perspective-budget` | `multi-perspective-premium` | Parallel constructive / destructive / systemic / minimalist analysis | General complex reasoning |
| **Debate** | `debate-budget` | `debate-premium` | Two generators argue opposing sides; a third independent model adjudicates | Binary decisions |
| **Jury** | `jury-budget` | `jury-premium` | Large expert panel (4–6 models) scored by an autonomous judge | High-stakes strategic decisions |
| **Research** | `research-budget` | `research-premium` | Iterative web queries, context vetting, Sonar fact-checking | Evidence-heavy, real-world search |
| **Scientific** | `scientific-budget` | `scientific-premium` | Hypothesis generation, falsification checks, empirical scoring | Technical and scientific questions |
| **Socratic** | `socratic-budget` | `socratic-premium` | Recursive question-and-answer loops exposing bias | Uncovering hidden assumptions |
| **Pre-Mortem** | `pre-mortem-budget` | `pre-mortem-premium` | Prospective failure analysis (Gary Klein) with safety back-testing | Project planning, risk assessment |
| **Bayesian** | `bayesian-budget` | `bayesian-premium` | Prior generation, likelihood updating, sensitivity tests | Probabilistic forecasting |
| **Dialectical** | `dialectical-budget` | `dialectical-premium` | Thesis–antithesis–synthesis progression | Philosophical and conceptual queries |
| **Analogical** | `analogical-budget` | `analogical-premium` | Cross-domain structure mapping and conceptual transfer | Creative problem solving |
| **Delphi** | `delphi-budget` | `delphi-premium` | Structured multi-round expert consensus with convergence tracking | Estimation and forecasting |
| **Chain-of-Verification** | `cove-budget` | `cove-premium` | Draft → verification queries → answers → revision | Detailed fact-checking |
| **Skeleton-of-Thought** | `sot-budget` | `sot-premium` | Skeleton outline with parallel chunk generation | Low-latency long-form generation |
| **Tree-of-Thoughts** | `tot-budget` | `tot-premium` | DFS/BFS search with heuristic evaluation | Planning and multi-step math |
| **Program-of-Thoughts** | `pot-budget` | `pot-premium` | Generates and executes Python to compute exact answers | Quantitative analysis |
| **Self-Discover** | `self-discover-budget` | `self-discover-premium` | Selects, adapts, and composes reasoning modules on the fly | Novel, unstructured problems |
| **Writing** | `writing-budget` | `writing-premium` | Long-form generation with hallucination guards | Professional documentation |
| **Article** | `article-budget` | `article-premium` | Augmented pre-research (debate/jury/socratic) before drafting | Publication-grade articles |
| **Brainstorming** | `brainstorming-budget` | `brainstorming-premium` | Verbalized sampling with clustering | Divergent ideation |
| **Coding** | `coding-budget` | `coding-premium` | Spec → parallel generation → adversarial review → tests | Production code and coverage |
| **Iterative Critique** | `iterative-critique-budget` | `iterative-critique-premium` | Generator–critic loops with convergence guards | Polishing creative/technical copy |
| **Cross-Language** | `cross-language-budget` | `cross-language-premium` | Cross-lingual probe reasoning to detect language-driven divergence | Sensitive geopolitical/historical topics |

### Special & Experimental Presets

- **`multi-perspective-ultra-budget`** — Ultra-light models (Ministral-3B, Gemini Flash Lite) in a streamlined 5-phase pipeline; sub-cent runs.
- **`subagent-budget` / `subagent-premium`** — Routes every pipeline sub-task (classification, scoring, synthesis, ...) to specialized models.
- **`image-gen-budget` / `image-gen-premium`** — Orchestrates text-to-image and image-to-image workflows.
- **`nvidia-nemotron-test`** — Experimental preset using NVIDIA Nemotron models via the NIM API.

---

## Programmatic Usage

Reasoner is designed to be called by autonomous AI agents (Cursor, LangChain, CrewAI, custom tools) as well as humans. There are three integration surfaces.

### Option 1 — Agent API (HTTP, Bearer auth)

Agent endpoints authenticate with `Authorization: Bearer <API_KEY>` and are exempt from CSRF requirements.

| Endpoint | Method | Format | Description |
| :--- | :--- | :--- | :--- |
| `/api/agent/run/sync` | `POST` | `application/json` | Block and return the full compiled pipeline output. |
| `/api/agent/run` | `POST` | `text/event-stream` | Stream pipeline progress and chunks in real time (SSE). |
| `/api/agent/tools` | `POST` | `application/json` | Compact function-calling schema describing the endpoints. |
| `/api/health` | `GET` | `application/json` | Liveness/readiness probe. |

Recommended flow for an agent:

1. Fetch the tool contract from `POST /api/agent/tools` (or the full OpenAPI schema at `GET /openapi.json`).
2. Prefer `POST /api/agent/run/sync` unless the agent can consume SSE streams.
3. Put the task in `problem`; set `preset` explicitly to control the cost/quality trade-off.
4. Read `synthesis` as the final answer, then inspect `citations`, `errors`, and `models_used`.

```bash
curl -X POST http://localhost:8003/api/agent/run/sync \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "problem": "Verify whether the prime number spiral has a mathematical pattern.",
    "preset": "scientific-premium"
  }'
```

The response conforms to the `RunResult` schema (`src/reasoner/api/schemas.py`):

```json
{
  "preset": "scientific-premium",
  "errors": [],
  "total_tokens": { "input": 4821, "output": 7412, "total": 12233 },
  "duration_seconds": 38.4,
  "synthesis": "### Prime Number Spiral Analysis\nThe Ulam spiral exhibits...",
  "critical_insights": ["Ulam spiral generates diagonal patterns based on quadratic polynomials."],
  "open_questions": ["Are there asymptotic limits to prime density along specific diagonals?"],
  "citations": [
    {
      "url": "https://mathworld.wolfram.com/UlamSpiral.html",
      "title": "Ulam Spiral",
      "snippet": "A visual representation of prime distribution...",
      "source_type": "academic"
    }
  ],
  "models_used": ["anthropic/claude-3-5-sonnet", "google/gemini-2-pro", "perplexity/sonar-pro"]
}
```

LangChain tool example:

```python
import httpx
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

REASONER_API_KEY = "sk-your-reasoner-key"

class ReasonerInput(BaseModel):
    problem: str = Field(description="The problem to reason about")
    preset: str = Field(default="scientific-budget")

async def reasoner_tool(problem: str, preset: str) -> str:
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(
            "http://localhost:8003/api/agent/run/sync",
            json={"problem": problem, "preset": preset},
            headers={"Authorization": f"Bearer {REASONER_API_KEY}"},
        )
        return r.json()["synthesis"]

tool = StructuredTool.from_function(
    name="reasoner",
    description="Research complex issues utilizing multi-provider reasoning networks.",
    func=reasoner_tool,
    args_schema=ReasonerInput,
)
```

### Option 2 — Headless in-process Python (no server)

For CI jobs, one-off scripts, or embedding in another Python process, use the dedicated `reasoner.headless` module — no FastAPI/uvicorn process required:

```python
import sys
sys.path.insert(0, "/path/to/Reasoner/src")   # or: pip install -e .

from reasoner import headless

result = await headless.ask("Is X better than Y?", preset="research-budget")

if result.action == "pipeline":
    print(result.state.final_synthesis)
elif result.action == "direct":
    print(result.answer)
else:  # "web_search"
    print(result.search_results)

# Once, at the host application's own shutdown (not per call):
await headless.shutdown()
```

Notes:

- `ask()` accepts the same options as the CLI (`top_k=3`, `sequential=True`, `source_type="academic"`, `domain="github.com"`, `enhance_prompt=True`, ...); it routes through the real argparse parser so defaults and validation stay authoritative in one place.
- Shared httpx connection pools are process-wide singletons. Call `headless.shutdown()` once at host shutdown — never per `ask()` call, or concurrent callers will tear down each other's pools.
- `.env` must be loadable before the first import; `reasoner.core.settings` reads it at import time.

### Option 3 — CLI subprocess (any language)

Stable contract: parse the `--output` JSON file, not stdout (stdout is progress logging; its format is not guaranteed).

```python
import json
import subprocess

subprocess.run(
    ["python", "main.py", "--problem", problem, "--preset", "debate-budget",
     "--output", "result.json", "--quiet"],
    check=True, cwd="/path/to/Reasoner",
)
with open("result.json") as f:
    result = json.load(f)
```

---

## Telemetry & Self-Healing

Reasoner records structured runtime telemetry to optimize pricing, route around failing models, and feed an automated self-healing CI loop.

| Pillar | Feature | Mechanism |
| :--- | :--- | :--- |
| E1 | Quality-rich memory | Sends `method`, `total_cost_usd`, `phase_durations`, `quality_history`, and `fallback_events` to the Neuro long-term memory for historical analysis. |
| E2 | Phase telemetry store | App-level `TelemetryStore` (SQLite/PostgreSQL) recording model, cost, and duration per phase. |
| E3 | Context compression | `smart_compress` applied at pipeline handoffs to minimize token cost. |
| E4 | Fallback surfacing | `ProviderRouter` detects model failures and fires `on_fallback()` callbacks to route around dead endpoints. |
| E5 | Healing exporter | `healing/telemetry_exporter.py` connects runtime context to static analysis tooling in CI. |

Querying telemetry programmatically:

```python
import asyncio
from reasoner.infrastructure.persistence.telemetry_store import get_telemetry_store

async def view_stats():
    store = get_telemetry_store()
    stats = await store.get_preset_stats("multi-perspective-premium")
    print(f"Runs:            {stats['run_count']}")
    print(f"Average cost:    ${stats['avg_cost']:.4f}")
    print(f"Total fallbacks: {stats['total_fallbacks']}")
    for phase in stats["phases"]:
        print(phase["phase"], f"avg ${phase['avg_cost']:.5f}")

asyncio.run(view_stats())
```

The CI pipeline (`.github/workflows/self-healing-ci.yml`) adds three healing loops on top: static introspection and test generation, runtime circuit-breaker/health checks, and evolutionary failure-pattern analysis, with coverage gates at 60% (fail) and 80% (warn).

---

## Language-Bias Mitigation

Language choice measurably influences model outputs and ideological stance (Buyl et al., *"Large Language Models Reflect the Ideology of Their Creators"*, npj Artificial Intelligence, 2026; [arXiv:2410.18417](https://arxiv.org/abs/2410.18417)). Reasoner mitigates this with two mechanisms:

**1. The English Pivot (always on).** Regardless of input language, the query is translated to English, the full reasoning pipeline executes in English, and the final synthesis is translated back to the user's language. Translation uses DeepL when `DEEPL_API_KEY` is set, falls back to lightweight translation LLMs, and finally to identity pass-through. Creative writing, brainstorming, and article presets bypass the pivot to preserve stylistic fidelity.

**2. The Cross-Lingual Probe (canary).** For sensitive topics (geopolitics, governance, religion, and related domains flagged by the sensitivity classifier), the probe compares English reasoning against native-language reasoning. If the semantic cosine distance exceeds the configured threshold (`LANGUAGE_DIVERGENCE_COSINE = 0.15`, `src/reasoner/core/constants_limits.py`), the system downgrades the epistemic confidence label (e.g., `VERIFIED` → `HYPOTHESIS`) and appends a linguistic-variance warning.

---

## Augmented Article Pipeline

For abstract or philosophical inquiries, Reasoner can trigger pre-processing augmentation before the primary long-form writing pipeline:

```
[ Philosophical / Abstract Query ]
               │
               ▼
[ HyperGate Deep Concept Guard ]
               │
               ▼  (Triggers parallel preprocessing)
 ┌─────────────┼─────────────┬──────────────────────┐
 ▼             ▼             ▼                      ▼
[ Debate ]  [ Jury ]  [ Socratic ]  [ Iterative Critique ]
 └─────────────┼─────────────┴──────────────────────┘
               │
               ▼
  [ Consolidated Pre-Research Context ]
               │
               ├─► Retrievals (refined search keywords)
               ├─► Outlines (enriched argumentative maps)
               └─► Drafting (integrated synthesis)
```

Configuration (defaults shown; see `src/reasoner/core/settings.py`):

```bash
AUGMENTATION_ENABLED=true             # Toggle the pre-processing pipeline
AUGMENTATION_CACHE_ENABLED=true       # Cache results to prevent redundant LLM calls
AUGMENTATION_CACHE_TTL_SECONDS=86400  # Cache lifetime (default: 24 hours)
AUGMENTATION_CACHE_MAX_ENTRIES=128    # Max cached augmentation results
AUGMENTATION_LLM_CONFIRM=false        # Extra LLM confirmation step before augmenting
AUGMENTATION_AB_TEST=false            # 50/50 split test: augmented vs baseline
```

---

## Security & Encryption

Reasoner implements a zero-trust security architecture covering data in transit and at rest. The authoritative reference is [`ENCRYPTION.md`](ENCRYPTION.md).

**Data in transit**

- External traffic is served over TLS 1.3/1.2 by the Caddy reverse proxy with automatic Let's Encrypt certificates and HSTS.
- The Docker Compose stack includes a `cert-generator` init container that creates a local root CA and per-service certificates on first boot; PostgreSQL requires SSL, Redis runs TLS-only, and the backend serves TLS natively via Gunicorn/Uvicorn.

**Data at rest**

- Sensitive fields (API keys, user data, execution traces) are encrypted at the application layer using authenticated symmetric encryption (Fernet) with seamless key rotation via `MultiFernet`.
- Searchable encrypted fields use one-way HMAC-SHA256 **blind indexes**, allowing equality lookups without exposing plaintext to the database.

**Application security**

- Input sanitization and prompt-injection filtering on all user input before it reaches LLM prompts.
- Token-bucket rate limiting per client IP (Redis-backed mode available for multi-worker deployments), circuit breakers with provider fallback, scoped Bearer-token auth, CSRF protection (HMAC-SHA256), hardened security headers, and strict CORS.
- Admin endpoints require both a JWT with `admin` scope and a separate `X-Admin-Key` header (constant-time comparison).

To migrate legacy plaintext data to the encrypted, blind-indexed format:

```bash
python scripts/migrate_encryption_v2.py \
  --connection-string "postgresql://user:pass@host:port/dbname" \
  --encryption-key "your_base64_fernet_key" \
  --blind-index-key "your_hmac_sha256_key" \
  --batch-size 1000 \
  --delay-seconds 0.05
```

---

## Configuration Reference

All configuration is environment-driven via `.env` (copy `.env.example`; `src/reasoner/core/settings.py` is the only env reader). Highlights:

### API Keys & Providers

| Variable | Purpose |
| :--- | :--- |
| `OPENROUTER_API_KEY` | Unified access to 350+ models (recommended). |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY` | Direct provider access (optional). |
| `DEEPSEEK_API_KEY`, `MISTRAL_API_KEY`, `XAI_API_KEY`, `PERPLEXITY_API_KEY` | Additional direct providers (optional). |
| `DEEPL_API_KEY` | Premium translation for the English Pivot (optional). |

### Application Infrastructure

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `SERVER_PORT` | `8003` | FastAPI bind port. |
| `ADMIN_API_KEY` | — | Admin token for cache/admin endpoints. Generate with `secrets.token_urlsafe(32)`. |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/reasoner` | SQLAlchemy/asyncpg database DSN. |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis cache / rate-limiter backend. |
| `RATE_LIMITER_MODE` | `memory` | Set to `redis` for multi-worker production deployments. |
| `CIRCUIT_BREAKER_MODE` | `memory` | Set to `redis` for multi-worker production deployments. |

The full variable reference (auth, billing, telemetry, feature flags) lives in `.env.example` and [`docs/ENVIRONMENT.md`](docs/ENVIRONMENT.md). **Never commit `.env` with real values.**

---

## Development

### Project Structure

```
Reasoner/
├── main.py                     # CLI entry point
├── asgi.py                     # ASGI entry point (uvicorn asgi:app --port 8003)
├── src/
│   └── reasoner/
│       ├── api/                # FastAPI app, routes, middleware, schemas
│       ├── application/        # CQRS, event bus, workflow strategies, services
│       ├── core/               # Protocols, ports, constants, settings
│       ├── domain/             # Entities, preset registry, SaaS models
│       ├── infrastructure/     # LLM router, persistence, Redis, billing, websocket
│       ├── phases/             # Reasoning-method phase implementations
│       ├── security/           # Application-layer encryption & blind indexing
│       └── utils/              # Shared utilities
├── tests/                      # pytest suite (unit, integration, architecture)
├── ui-next/                    # Next.js 16 web UI (React 19, TypeScript, Tailwind v4)
├── scripts/                    # Maintenance, migration & smoke-test scripts
└── migrations/                 # SQL migrations and Alembic versions
```

See `AGENTS.md` for the exhaustive directory map and contributor conventions.

### Tests

```bash
# Full suite (parallel by default via pytest-xdist)
python -m pytest -v

# Fast subset — skip slow and integration tests
python -m pytest -m "not slow and not integration"

# Include slow tests
python -m pytest --run-slow

# Coverage report
python -m pytest tests/ --cov=src/reasoner --cov-report=html
```

The suite contains 2,700+ tests across 250+ files, including architecture fitness functions (`tests/architecture/test_layer_boundaries.py`) that enforce layer dependency rules. Frontend unit tests use Vitest (`cd ui-next && npm run test`); E2E tests use Playwright (`npm run test:e2e`).

To run every CI gate locally in one command — useful when GitHub Actions runners aren't available, or before opening a PR:

```bash
./scripts/verify_ci.sh              # every gate: pytest, coverage, import-linter, tsc, eslint, build, secret scan
./scripts/verify_ci.sh --backend    # skip the frontend gates (no Node required)
./scripts/verify_ci.sh --fast       # skip the coverage re-run (the slowest gate)
```

### Linting & Formatting

Configuration for Ruff and mypy lives in `pyproject.toml`; there are no separate config files.

```bash
ruff check src/reasoner/          # Lint
ruff format src/reasoner/         # Format
cd ui-next && npm run lint        # Frontend ESLint (flat config)
```

---

## Deployment

Reasoner ships as a self-contained Docker Compose stack (Caddy reverse proxy with automatic HTTPS, FastAPI backend, Next.js frontend, PostgreSQL, Redis, internal mTLS) — no Kubernetes or serverless platform required; the pipeline holds long-lived SSE streams for minutes per run, which fights typical serverless timeouts.

```bash
python scripts/preflight_check.py --generate   # prints ADMIN_API_KEY, CSRF_SECRET,
                                                 # ENCRYPTION_KEY, BLIND_INDEX_KEY, POSTGRES_PASSWORD
python scripts/preflight_check.py               # validates .env before you bring the stack up —
                                                 # catches empty values, unedited placeholders,
                                                 # malformed keys, and unsafe production settings

docker compose up -d --build
curl https://your-domain/api/health
```

`ENVIRONMENT=production` is hardcoded in `docker-compose.yml`; in that mode the app refuses to boot without an encryption key pair, a CSRF secret, a Supabase auth configuration, and at least one observability backend (Prometheus is a hard dependency, so `/api/metrics` satisfies this on a default install). Full walkthrough, secret generation commands, and the observability/backup checklist: [`DEPLOY.md`](DEPLOY.md). Strategy-level guidance — spend caps, a four-dashboard measurement plan, and portfolio/sale packaging — is in [`docs/GO_LIVE_PLAYBOOK.md`](docs/GO_LIVE_PLAYBOOK.md).

---

## Documentation

| Document | Contents |
| :--- | :--- |
| [`AGENTS.md`](AGENTS.md) | Exhaustive architecture map, conventions, and agent-contributor guide. |
| [`ENCRYPTION.md`](ENCRYPTION.md) | Zero-trust encryption architecture (transit + at-rest). |
| [`DEPLOY.md`](DEPLOY.md) | Deployment guide — secrets, Docker Compose, TLS, observability, backups. |
| [`docs/GO_LIVE_PLAYBOOK.md`](docs/GO_LIVE_PLAYBOOK.md) | Deployment strategy, spend protection, measurement plan, portfolio/sale packaging. |
| [`SAAS.md`](SAAS.md) | Multi-tenant SaaS design (auth, billing, quotas). |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history. |
| [`docs/ENVIRONMENT.md`](docs/ENVIRONMENT.md) | Full environment-variable reference. |
| [`docs/`](docs/) | Architecture plans, audits, ADRs, and research notes. |

---

## Contributing

Contributions are welcome. Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request, keep changes minimal and covered by tests, and follow the conventional-commit style (`feat:`, `fix:`, `docs:`, ...).

## License

[MIT](LICENSE) © 2026 Georgios-Chrysovalantis Chatzivantsidis.
