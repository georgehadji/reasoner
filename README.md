<div id="top" align="center">

<!-- ASCII Banner -->
<pre>
 █████╗ ██████╗  █████╗         ██████╗ ██╗██████╗ ███████╗██╗     ██╗███╗   ██╗███████╗
██╔══██╗██╔══██╗██╔══██╗        ██╔══██╗██║██╔══██╗██╔════╝██║     ██║████╗  ██║██╔════╝
███████║██████╔╝███████║        ██████╔╝██║██████╔╝█████╗  ██║     ██║██╔██╗ ██║█████╗  
██╔══██║██╔══██╗██╔══██║        ██╔═══╝ ██║██╔══██╗██╔══╝  ██║     ██║██║╚██╗██║██╔══╝  
██║  ██║██║  ██║██║  ██║        ██║     ██║██║  ██║███████╗███████╗██║██║ ╚████║██╔════╗
╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝        ╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝╚═╝  ╚═══╝╚══════╝
v2.3 — Reasoner — Augmented Reasoning Engine
</pre>

<!-- Badges -->
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Harness Enhanced](https://img.shields.io/badge/harness-E1%E2%80%93E5%20enhanced-brightgreen)]
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js_16-000000.svg?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6.svg?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4.svg?style=flat-square&logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
<br>
[![Tests](https://img.shields.io/badge/tests-800%2B%20passing-brightgreen.svg?style=flat-square&logo=pytest&logoColor=white)](./tests)
[![Coverage](https://img.shields.io/badge/coverage-~70%25-yellow.svg?style=flat-square)](.)
[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/tesse/Reasoner?style=flat-square&logo=github)](https://github.com/tesse/Reasoner)

### A production-grade multi-agent reasoning orchestrator that coordinates 20 reasoning methodologies and 48 presets with automatic method selection, cross-lab model diversity, self-healing telemetry, and real-time streaming.

[🚀 Quick Start](#-quick-start) · [🧠 Core Architecture](#-core-architecture) · [🎛️ Preset Matrix](#%EF%B8%8F-presets-master-matrix) · [📊 Telemetry & Healing](#-telemetry--self-healing) · [🔒 Security](#-security--encryption) · [🤖 Agent API](#-agent-api) · [💻 Development](#-development)

</div>

---

## 🎯 Project Overview

**Reasoner** is a sophisticated, highly modular multi-agent reasoning system designed to decompose complex questions, strategic decisions, and deep research tasks into structured, phase-by-phase execution pipelines. Instead of relying on one-shot language model outputs, Reasoner orchestrates parallel model ensembles across different model-provider ecosystems (Anthropic, OpenAI, Google, DeepSeek, Mistral, and more). It critiques competing perspectives, performs recursive web-grounded RAG, stress-tests candidate answers under adversarial conditions, and synthesizes final solutions marked with precise epistemic confidence labels.

It is designed for enterprise environments, featuring real-time Server-Sent Events (SSE) streaming, sub-cent pricing telemetry, a self-healing loop utilizing runtime execution context, zero-trust container security, application-layer envelope encryption (AES-256-GCM), and native programmatic endpoints optimized for integration with AI agents.

---

## 🧠 Core Architecture

Reasoner executes structured reasoning using an **8-Phase Pipeline** managed by the `ReasonerPipeline` engine. The entire flow is modeled asynchronously, allowing for massive parallel generation, context vetting, and synthesis:

```
                  ┌─────────────────────────────────────┐
                  │      User Question / Problem        │
                  └──────────────────┬──────────────────┘
                                     │
                        [ Phase 1: Classification ]
                                     │
                       [ Phase 2: Decomposition ]
                                     │
                       [ Phase 3: Context Vetting ] <── (Iterative RAG Loop, Max 3)
                                     │
                       [ Phase 4: Deep Source Reading ]
                                     │
                        [ Phase 5: Generation ] ───────┐
                                     │                 │ (Cross-Lab
                       [ Phase 6: Critique & Scoring ] │  Perspective Ensembles)
                                     │                 │
                      [ Phase 7: Stress Testing ] <────┘
                                     │
                        [ Phase 8: Synthesis ]
                                     │
                  ┌──────────────────▼──────────────────┐
                  │    Verified Solution with Citations │
                  └─────────────────────────────────────┘
```

1. **Classification (Phase 1):** Identifies task type (e.g., math, research, creative, coding) and primary language, enabling optimal routing.
2. **Decomposition (Phase 2):** Breaks down complex problems into atomic sub-questions and key underlying assumptions.
3. **Context Vetting (Phase 3):** Performs universal context vetting via iterative RAG. Includes smart token compression at Phase 2 ➔ 3 handoff.
4. **Deep Reading (Phase 4):** Parses the full contents of critical sources when web-retrieved snippets are insufficient.
5. **Generation (Phase 5):** Leverages cross-lab model ensembles to produce multiple competing answers and perspectives.
6. **Critique & Scoring (Phase 6):** Independent LLM judges critique the generated answers against standard quality dimensions.
7. **Stress Testing (Phase 7):** Subject survivors to adversarial stress testing to surface hidden logical flaws or factual errors.
8. **Synthesis (Phase 8):** Consolidates verified perspectives into an evidence-grounded final response, complete with epistemic confidence labeling (`VERIFIED`, `HYPOTHESIS`, or `UNRESOLVED`) and citation references.

---

## 🚀 Quick Start

### Prerequisites

* **Python 3.12+**
* **Node.js 20+** (for frontend web UI)
* **OpenRouter API Key** (recommended — single billing interface for 350+ models)
* **SearXNG** (optional — local search provider; defaults to free mock search if unavailable)
* **Redis** (optional — recommended in production for distributed rate limiting)

### 1. Installation & Environment Setup

```bash
# Clone the repository
git clone https://github.com/tesse/Reasoner.git
cd Reasoner

# Set up Python virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and insert your API credentials (e.g., OPENROUTER_API_KEY="sk-or-v1-...")
```

### 2. Launch Services

Start the FastAPI backend, the Next.js frontend, and the local SearXNG search engine with a single orchestration command:

```bash
python start_all.py
```

* **FastAPI Backend:** `http://localhost:8003` (Port configurable via `SERVER_PORT`)
* **Next.js Frontend:** `http://localhost:3000`
* **SearXNG Instance:** `http://localhost:8888`

### 3. Command-Line Interface (CLI) Examples

Perform deep, multi-agent reasoning directly from your terminal:

```bash
# Run with the default balanced reasoning preset
python main.py --problem "How should we prioritize our Q3 engineering roadmap?"

# Run with a highly optimized budget preset (~$0.02 cost)
python main.py --problem "Explain the long-term impact of quantum cryptography." --preset debate-budget

# Run a premium multi-perspective analysis using top-tier models (~$0.20 cost)
python main.py --problem "Evaluate microservices vs monolithic architecture for a startup." --preset multi-perspective-premium

# Stream the reasoning steps sequentially to prevent rate limits
python main.py --problem "Analyze the Fermat's Last Theorem proof." --preset scientific-premium --sequential
```

---

## 🎛️ Presets Master Matrix

Reasoner ships with **48 presets** across **20 methodologies**. Each method contains highly optimized model combinations divided into cost-efficient **Budget** and quality-focused **Premium** tiers. 

| Methodology | Budget Preset (`-budget`) | Premium Preset (`-premium`) | Core Model Strategy & Diversity | Recommended Use Case |
| :--- | :--- | :--- | :--- | :--- |
| **Multi-Perspective** | `multi-perspective-budget` | `multi-perspective-premium` | Cross-lab synthesis (Google + Mistral + Zhipu + DeepSeek) | General complex reasoning |
| **Debate** | `debate-budget` | `debate-premium` | Generator A vs Generator B, adjudicated by a third independent model | Deciding between binary options |
| **Jury / Orchestrated** | `jury-budget` | `jury-premium` | Large expert panel (4-6 models) scored by an autonomous judge | High-stakes strategic decisions |
| **Research** | `research-budget` | `research-premium` | Iterative SearXNG queries, context-vetting, and Sonar Pro fact-checking | Evidence-heavy, real-world search |
| **Scientific** | `scientific-budget` | `scientific-premium` | Hypothesis generation, falsification checks, and empirical scoring | Technical, medical, & scientific questions |
| **Socratic** | `socratic-budget` | `socratic-premium` | Recursive question-and-answer loops designed to expose bias | Uncovering hidden assumptions |
| **Pre-Mortem** | `pre-mortem-budget` | `pre-mortem-premium` | Gary Klein's prospective failure analysis and safety back-testing | Project planning and risk assessment |
| **Bayesian** | `bayesian-budget` | `bayesian-premium` | Prior probability generation, likelihood updating, and sensitivity tests | Probabilistic forecasting |
| **Dialectical** | `dialectical-budget` | `dialectical-premium` | Hegelian thesis-antithesis-synthesis progression | Philosophical & conceptual queries |
| **Analogical** | `analogical-budget` | `analogical-premium` | Cross-domain structure-mapping and conceptual transfer | Creative problem solving |
| **Delphi** | `delphi-budget` | `delphi-premium` | Structured multi-round expert consensus with convergence tracking | Estimations and future forecasting |
| **Chain-of-Verification**| `cove-budget` | `cove-premium` | Draft ➔ verify queries ➔ answer queries ➔ final revision loop | Detailed fact-checking |
| **Skeleton-of-Thought** | `sot-budget` | `sot-premium` | Skeleton outline extraction with parallel chunk generation | Low-latency long-form generation |
| **Tree-of-Thoughts** | `tot-budget` | `tot-premium` | Depth-first/Breadth-first search with heuristic evaluations | Planning and multi-step math |
| **Program-of-Thought** | `pot-budget` | `pot-premium` | Generating and executing python code to compute the exact answer | Quantitative, statistical analysis |
| **Self-Discover** | `self-discover-budget` | `self-discover-premium` | Selects, adapts, and implements reasoning styles on-the-fly | Novel, unstructured problems |
| **Writing / Article** | `writing-budget` | `writing-premium` | CoVE + SoT + Pre-Mortem pipeline with concept augmentation | Professional documentation & publishing |
| **Brainstorming** | `brainstorming-budget` | `brainstorming-premium` | Verbalized Sampling (VS-CoT/Standard) with clustering | Idea generation & divergent thinking |
| **Coding** | `coding-budget` | `coding-premium` | Spec ➔ parallel generation ➔ adversarial review ➔ test writing | Production code & test coverage |
| **Iterative Critique** | `iterative-critique-budget`| `iterative-critique-premium`| Prompt generator-critic debate loops with convergence guards | Polishing creative/technical copy |

### 🌟 Special & Experimental Presets

* **`multi-perspective-ultra-budget`** (<$0.01): Leverages ultra-light models (Ministral-3B + Gemini Flash Lite) in a streamlined 5-phase execution pipeline.
* **`subagent-budget` / `subagent-premium`**: Routes every individual pipeline sub-task (e.g., classification, scoring, synthesis) to specialized models.
* **`image-gen-budget` / `image-gen-premium`**: Orchestrates text-to-image and image-to-image workflows across Midjourney, Flux 2 Pro, and Stable Diffusion architectures.
* **`nvidia-nemotron-test`**: Experimental preset utilizing high-parameter NVIDIA Nemotron models through official NIM API keys.

---

## 📊 Telemetry & Self-Healing

Reasoner incorporates a production-grade runtime telemetry system inspired by the *Code as Agent Harness* framework (arXiv:2605.18747). This pipeline gathers execution metadata to optimize pricing, route around model failures, and feed context into automated self-healing loops.

### Key Telemetry Pillars

| Pillar | Feature Name | Core Mechanism |
| :--- | :--- | :--- |
| **E1** | **Quality-Rich Memory** | Sends `method`, `total_cost_usd`, `phase_durations`, `quality_history`, and `fallback_events` to the central Neuro memory for historical analysis. |
| **E2** | **Phase Telemetry Store** | App-level `TelemetryStore` running on SQLite/PostgreSQL. Records exact model behavior, cost, and duration per phase. |
| **E3** | **Context Compression** | Automatically applies context compression algorithms (`smart_compress`) at the handoff between Decomposition and Critique to minimize token cost. |
| **E4** | **Fallback Surfacing** | Detects model failures in `ProviderRouter` and immediately triggers `on_fallback()` callbacks to route around dead endpoints. |
| **E5** | **Healing Exporter** | Connects `healing/telemetry_exporter.py` to static codebase analysis tools. Generates runtime context data to help heal pipeline code. |

### Accessing Telemetry Programmatically

You can query the telemetry database using python or SQL:

```python
import asyncio
from reasoner.infrastructure.persistence.telemetry_store import get_telemetry_store

async def view_stats():
    store = get_telemetry_store()
    stats = await store.get_preset_stats("multi-perspective-premium")
    print(f"Average Cost: ${stats['avg_cost_usd']:.4f}")
    print(f"Success Rate: {stats['success_rate'] * 100}%")

asyncio.run(view_stats())
```

---

## 🌐 Language-Bias Mitigation

Language choice significantly influences model outputs and ideological leans (Buyl et al., *npj AI* 2026). Reasoner implements a robust, two-part system to neutralize linguistic bias:

### 1. The English Pivot (Always On)
No matter what language a user questions in, Reasoner internally translates the query to **English**, executes the entire deep reasoning pipeline, and translates the finalized synthesis back to the user's native tongue.
* **Fallback Chain:** Leverages DeepL first. If no API key is set, falls back to lightweight translation LLMs, and finally to local identity matching.
* **Preservation Exceptions:** Creative writing, creative brainstorming, and specific article generation models bypass the pivot to maintain stylistic fidelity.

### 2. The Cross-Lingual Probe (Canary)
For highly sensitive geopolitical, historical, or religious topics, the Cross-Lingual Probe evaluates the divergence between English reasoning and native-language reasoning.
* **Sensitivity Classifier:** Automatically flags queries covering 5 critical domains: geopolitics, governance, history, religion, and politics.
* **Divergence Metric:** If semantic cosine distance exceeds threshold `0.15`, the system automatically downgrades the solution confidence rating (e.g., `VERIFIED ➔ HYPOTHESIS`) and appends an epistemic linguistic warning.

---

## 🧪 Augmented Article Pipeline

For abstract or philosophical inquiries, Reasoner dynamically triggers pre-processing augmentation before launching the primary long-form writing pipeline:

```
[ Philosophical / Abstract Query ]
               │
               ▼
[ HyperGate Deep Concept Guard ]
               │
               ▼  (Triggers parallel preprocessing)
 ┌─────────────┼─────────────┬──────────────────────┐
 │             │             │                      │
 ▼             ▼             ▼                      ▼
[ Debate ]  [ Jury ]  [ Socratic ]  [ Iterative Critique ]
 └─────────────┼─────────────┴──────────────────────┘
               │
               ▼
  [ Consolidated Pre-Research Context ]
               │
               ├─► Retrievals (Refined search keywords)
               ├─► Outlines (Enriched argumentative maps)
               └─► Drafting (Integrated synthesis)
```

### Configuration Variables

```bash
AUGMENTATION_ENABLED=true             # Toggle the pre-processing pipeline
AUGMENTATION_CACHE_ENABLED=true       # Cache results to prevent redundant LLM calls
AUGMENTATION_CACHE_TTL_SECONDS=86400  # Cache lifetime (Default: 24 hours)
AUGMENTATION_AB_TEST=false            # Enables 50/50 split testing of augmented vs baseline outputs
```

---

## 🔒 Security & Encryption

Reasoner features an enterprise-grade security layer guarding data in transit and at rest.

* **Mutual TLS (mTLS):** All internal microservices (Redis, DB, Web UI, API) communicate strictly over secure TLS 1.3/1.2 tunnels. Reasoner automatically provisions unique, ephemeral cryptographic certificates for internal containers on startup.
* **At-Rest AES-256-GCM Envelope Encryption:** Sensitive tables — such as API keys, user data, and long-term execution traces — are encrypted at the application layer.
* **Blind Indexing:** Search queries on encrypted fields utilize one-way HMAC-SHA256 blind indexing to allow searching without revealing plaintext to the database.

### Encryption Migration Script

To safely migrate legacy plain or older format databases to Reasoner v2.3's blind index format:

```bash
python scripts/migrate_encryption_v2.py \
  --connection-string "postgresql://user:pass@host:port/dbname" \
  --encryption-key "your_base64_fernet_key" \
  --blind-index-key "your_hmac_sha256_key" \
  --batch-size 1000 \
  --delay-seconds 0.05
```

---

## 🤖 Agent API

Reasoner was built native for **Autonomous AI Agents** (Cursor, custom LLM tools, LangChain, CrewAI). It exposes endpoints that utilize Bearer token authentication, avoiding CSRF restrictions.

### How an agent should call Reasoner

1. Fetch the tool contract from `GET /api/agent/tools` or the full OpenAPI schema from `GET /openapi.json`.
2. Send every agent request with `Authorization: Bearer <API_KEY>`.
3. Prefer `POST /api/agent/run/sync` for autonomous agents because it returns one JSON response.
4. Use `POST /api/agent/run` only if your agent can consume SSE streams.
5. Put the task in `problem`, and set `preset` explicitly when you want a specific cost/quality tradeoff.
6. Read `synthesis` as the final answer, then inspect `citations`, `errors`, and `models_used`.

### Primary Endpoints

| Endpoint | Method | Format | Description |
| :--- | :--- | :--- | :--- |
| `/api/agent/run/sync` | `POST` | `application/json` | Block and return full compiled pipeline output. |
| `/api/agent/run` | `POST` | `text/event-stream`| Stream pipeline progress and text chunks in real-time. |
| `/api/agent/tools` | `GET` | `application/json` | Retrieve standard OpenAPI-spec schemas for agent tools. |

### 1. Synchronous Integration Example

Use `/api/agent/run/sync` to gather all reasoning steps, citations, and models used into a structured JSON payload:

```bash
curl -X POST http://localhost:8003/api/agent/run/sync \
  -H "Authorization: Bearer YOUR_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "problem": "Verify whether the prime number spiral has a mathematical pattern.",
    "preset": "scientific-premium"
  }'
```

### 2. Minimal JSON Payload

```json
{
  "problem": "Evaluate whether we should migrate to a monorepo.",
  "preset": "research-premium",
  "top_k": 2,
  "sequential": false,
  "no_cache": false,
  "force_pipeline": false,
  "enhance_prompt": false,
  "expert": false,
  "web_search": false,
  "smart_search": true,
  "source_type": "general",
  "domain": null,
  "attachments": [],
  "file_ids": [],
  "client_run_id": "optional-idempotency-key"
}
```

### 3. Response Handling

- `synthesis` is the final answer.
- `citations` contains source references when available.
- `errors` lists pipeline failures or provider issues.
- `models_used` shows which models participated in the run.
- If `synthesis` is empty, retry with a different `preset` or set `web_search=true`.

**JSON Output Schema:**
```json
{
  "preset": "scientific-premium",
  "errors": [],
  "total_tokens": { "input": 4821, "output": 7412, "total": 12233 },
  "duration_seconds": 38.4,
  "synthesis": "### Prime Number Spiral Analysis\nThe Ulam spiral exhibits...",
  "critical_insights": [
    "Ulam spiral generates diagonal patterns based on quadratic polynomials."
  ],
  "open_questions": [
    "Are there asymptotic limits to prime density along specific diagonals?"
  ],
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

### 4. LangChain Integration Script

Easily embed the multi-model Reasoner pipeline as a structured tool inside standard AI Agent libraries:

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

---

## ⚙️ Configuration Reference

Configure your Reasoner instance using environment variables inside your `.env` file:

### API Keys & Providers
* `OPENROUTER_API_KEY`: Key for OpenRouter integration (Unified Model Access).
* `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`: Direct provider access keys.
* `DEEPSEEK_API_KEY`, `MISTRAL_API_KEY`, `XAI_API_KEY`: Optional direct provider keys.
* `DEEPL_API_KEY`: Key for premium translations in the Language Pivot.

### Application Infrastructure
* `SERVER_PORT` (Default: `8003`): Port for the FastAPI backend.
* `ADMIN_API_KEY`: Admin authentication token for accessing cache and managing encryption keys.
* `RATE_LIMITER_MODE` (Default: `memory`): Mode for rate limits. Set to `redis` in production.
* `REDIS_URL` (Default: `redis://localhost:6379/0`): URL of your Redis cache and rate limiter.
* `DATABASE_URL` (Default: `sqlite:///./reasoner.db`): SQLAlchemy database path (PostgreSQL recommended in production).
* `SEARXNG_URL` (Default: `http://localhost:8888`): Direct address to local Search Engine.

---

## 💻 Development

Reasoner enforces strict type compliance, automated linting, and comprehensive unit coverage.

### Project Structure Overview

```
E:/Documents/Vibe-Coding/Reasoner/
├── main.py                     # CLI Entry Point
├── asgi.py                     # FastAPI ASGI Server Entry Point
├── src/
│   └── reasoner/
│       ├── api/                # API controllers & route mappings
│       ├── application/        # Application services and logic
│       ├── core/               # Main orchestration models
│       ├── domain/             # Entities, value objects & models
│       ├── infrastructure/     # Database persistence, telemetry & cache stores
│       ├── phases/             # Phase-specific execution schemas and prompts
│       ├── security/           # Application-layer encryption & PKI setup
│       └── utils/              # Token, logging & scraper utilities
├── tests/                      # Unit, integration & behavioral tests
├── ui-next/                    # Next.js Web UI
└── scripts/                    # Database, encryption & build scripts
```

### Running the Test Suite

We use `pytest` for executing and asserting our test suites:

```bash
# Execute the entire test suite
python -m pytest tests/ -v

# Run lightweight tests only (excluding slow integration tests)
python -m pytest tests/ -v -m "not slow and not integration"

# Run with test coverage calculations
python -m pytest tests/ --cov=src/reasoner --cov-report=html
```

### Linting & Formatting Standards

Before staging or committing any code changes, run the automated linting checks:

```bash
# Lint the Python codebase
ruff check src/reasoner/

# Format Python files automatically
ruff format src/reasoner/

# Lint the Frontend React codebase
cd ui-next && npm run lint
```

---

<div align="center">

**[⬆ Back to Top](#top)**

Built with precision and robust engineering standards.

</div>
