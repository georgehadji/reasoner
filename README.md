<div align="center">

<!-- ASCII Banner -->
<pre>
 █████╗ ██████╗  █████╗         ██████╗ ██╗██████╗ ███████╗██╗     ██╗███╗   ██╗███████╗
██╔══██╗██╔══██╗██╔══██╗        ██╔══██╗██║██╔══██╗██╔════╝██║     ██║████╗  ██║██╔════╝
███████║██████╔╝███████║        ██████╔╝██║██████╔╝█████╗  ██║     ██║██╔██╗ ██║█████╗  
██╔══██║██╔══██╗██╔══██║        ██╔═══╝ ██║██╔══██╗██╔══╝  ██║     ██║██║╚██╗██║██╔══╝  
██║  ██║██║  ██║██║  ██║        ██║     ██║██║  ██║███████╗███████╗██║██║ ╚████║██╔════╗
╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝        ╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝╚═╝  ╚═══╝╚══════╝
v2.3 — Reasoner
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

**A production-grade reasoning engine that orchestrates 20 LLM methodologies — from multi-perspective analysis to verbalized sampling brainstorming — with automatic method selection, cross-lab diversity, and real-time streaming.**

[🚀 Quick Start](#quick-start) · [🧠 Methods](#reasoning-methods) · [🎛️ Presets](#available-presets) · [💻 Development](#development)

</div>

---

## 🎯 Project Overview

Reasoner is a **reasoning orchestrator** that decomposes complex problems into structured phases, leverages multiple LLMs in parallel from diverse training ecosystems, applies rigorous independent critique, stress-tests solutions under adversarial conditions, and synthesizes actionable recommendations with epistemic labeling. It features a HyperGate Pre-Router for automatic method selection, supports 20 reasoning methods with 48 presets, ensures cross-lab diversity, and provides real-time streaming of progress and cost.

**New in v2.3:** Harness telemetry pipeline — per-phase cost/duration/model data persisted to queryable SQLite tables, fallback events surfaced through the router call chain, context compression at Phase 2→3 handoff, and a runtime-aware self-healing loop that queries telemetry to inform static analysis.

---

## 📊 Telemetry & Self-Healing

Reasoner v2.3 includes a full telemetry pipeline inspired by *Code as Agent Harness* (arXiv:2605.18747):

| Enhancement | What it does |
|-------------|-------------|
| **E1 — Quality-rich Neuro** | `postflight` sends `method`, `total_cost_usd`, `phase_costs`, `phase_durations`, `quality_history`, and `fallback_events` to the Neuro memory — every run's quality signal is preserved for future recall |
| **E2 — Phase Telemetry Table** | `TelemetryStore` (`phase_telemetry` + `run_telemetry` tables) — queryable SQLite analytics. Ask: *"Average Phase 3 cost for debate-premium over the last 100 runs"* |
| **E3 — Context Compression** | `smart_compress` applied after Decomposition (Phase 2), before Critique (Phase 3). Gated by existing `TOKEN_OPTIMIZATION["context_compression"]` flag |
| **E4 — Fallback Surfacing** | `ProviderRouter` now fires `on_fallback(role, intended, actual, reason)` callbacks — wired at `preflight` so all code paths capture fallback events to `PipelineMeta.fallback_events` |
| **E5 — Healing Exporter** | `healing/telemetry_exporter.py` queries `TelemetryStore`, writes `healing_context.json`. `run_healing.py` loads it before Loop 1 — static healing gets runtime context |

```bash
# Query telemetry
python -c "
from reasoner.infrastructure.persistence.telemetry_store import get_telemetry_store
import asyncio
store = get_telemetry_store()
stats = asyncio.run(store.get_preset_stats('multi-perspective-premium'))
print(stats)
"
```

---

## 🚀 Quick Start

### Prerequisites

-   **Python 3.12+**
-   **Node.js 20+** (for the web UI)
-   **OpenRouter API Key** (recommended — single key, 350+ models)

### 1. Clone & Setup

```bash
git clone https://github.com/tesse/Reasoner.git
cd Reasoner

# Backend
cp .env.example .env
# Edit .env and add: OPENROUTER_API_KEY=sk-or-v1-your-key-here
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd ui-next && npm install && cd ..
```

### 2. Start Everything (One Command)

```bash
python start_all.py
```

This starts:
-   🐍 **FastAPI Backend** on `http://localhost:8003` (configurable via `SERVER_PORT`)
-   ⚛️ **Next.js Frontend** on `http://localhost:3000`
-   🔍 **SearXNG Search** on `http://localhost:8888`

Open [http://localhost:3000](http://localhost:3000) and start reasoning.

### 3. CLI Quick Run

```bash
# Default preset — uses a balanced selection of models for quality and cost
python main.py --problem "How should we prioritize our Q3 product roadmap?"

# Budget option — approximately $0.02 per run
python main.py --problem "..." --preset debate-budget

# Maximum quality — premium models with cross-lab diversity
python main.py --problem "..." --preset multi-perspective-premium
```

---

## ⚙️ Configuration

### Option 1: OpenRouter (Recommended)

One key. 350+ models. Simplest billing.

```bash
# .env
OPENROUTER_API_KEY="sk-or-v1-..."
```

### Option 2: Individual Provider Keys

Mix and match direct provider access:

```bash
OPENAI_API_KEY="sk-..."
ANTHROPIC_API_KEY="sk-ant-..."
GOOGLE_API_KEY="..."
DEEPSEEK_API_KEY="sk-..."
MISTRAL_API_KEY="..."
XAI_API_KEY="..."
PERPLEXITY_API_KEY="..."
OLLAMA_BASE_URL="http://localhost:11434"
```

### Optional Settings

```bash
# Web search engine
SEARXNG_URL="http://localhost:8888"

# Admin API key for cache clearing and key management
ADMIN_API_KEY="your-admin-key"

# Rate limiting (REQUIRED 'redis' mode in production)
# In production environments, RATE_LIMITER_MODE must be set to 'redis'.
# The application will fail to start if 'memory' mode is detected in production
# to prevent unsafe unthrottled access across multiple workers.
RATE_LIMITER_MODE="memory" # or "redis"
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000
```

---

## 🎮 Usage

### CLI

```bash
# List available presets and models
python main.py --list-presets
python main.py --list-models

# Run with specific preset
python main.py --problem "Should we adopt microservices?" --preset debate-premium

# Custom routing per role
python main.py --problem "..." --routing '{"primary":"claude-sonnet","scoring":"sonar-pro"}'

# Load from file and export JSON
python main.py --problem-file problem.txt --output results.json --preset multi-perspective-premium

# Sequential mode for rate-limited environments
python main.py --problem "..." --sequential

# Adjust top-k pruning (default: 2)
python main.py --problem "..." --top-k 3
```

### Programmatic API

```python
import asyncio
from reasoner.pipeline import ReasonerPipeline
from reasoner.llm import ProviderRouter

async def main():
    router = ProviderRouter.from_model_ids(
        primary_id="claude-sonnet",
        routing={"scoring": "sonar-pro", "synthesis": "glm-5"}
    )
    pipeline = ReasonerPipeline(router=router, preset_name="multi-perspective-premium")
    state = await pipeline.run("Your complex problem here")
```
    print(f"Task Type: {state.task_type}")
    print(f"Sub-problems: {state.sub_problems}")
    print(f"Final Answer: {state.final_solution.core_solution}")
    print(f"Epistemic Label: {state.final_solution.epistemic_label}")
    print(f"Cost: ${state.total_cost_usd:.4f}")

asyncio.run(main())
```

---

## 🧠 Reasoning Methods

Reasoner supports **20 specialized reasoning methodologies**:

| Method | Preset Slug | Description | Best For |
|--------|-------------|-------------|----------|
| **Multi-Perspective** | `multi-perspective` | Default 6-phase pipeline with multi-perspective generation across 3–4 labs | General complex problems |
| **Debate** | `debate` | Two models argue opposing positions; a third judges the winner | Polarized decisions |
| **Jury / Orchestrated** | `jury` | Multiple generators scored by an independent panel of critics (4–6 experts) | High-stakes decisions |
| **Research** | `research` | Web-grounded deep research with iterative SearXNG search and article pipeline | Evidence-heavy questions |
| **Scientific** | `scientific` | Hypothesis generation, falsification tests, evidence scoring | Research & validation |
| **Socratic** | `socratic` | Elenchus questioning to expose hidden assumptions | Clarifying ambiguous problems |
| **Pre-Mortem** | `pre-mortem` | Prospective hindsight failure analysis (Gary Klein methodology) | Risk assessment |
| **Bayesian** | `bayesian` | Prior → likelihood → posterior → sensitivity reasoning | Probabilistic reasoning |
| **Dialectical** | `dialectical` | Hegelian thesis-antithesis-synthesis progression | Philosophical analysis |
| **Analogical** | `analogical` | Cross-domain structure-mapping and transfer | Creative problem solving |
| **Delphi** | `delphi` | Structured multi-round expert consensus with convergence tracking | Forecasting & estimation |
| **Chain-of-Verification (CoVE)** | `cove` | Draft → verify → answer → revise self-checking loop | Fact-checking |
| **Skeleton-of-Thought (SoT)** | `sot` | Skeleton → parallel solve → assemble for latency savings | Long structured output |
| **Tree-of-Thoughts (ToT)** | `tot` | Reasoning as tree search with evaluation and backtracking | Planning & optimization |
| **Program-of-Thought (PoT)** | `pot` | Executable code as intermediate reasoning step | Quantitative problems |
| **Self-Discover** | `self-discover` | Dynamic selection and composition of reasoning modules | Novel problem types |
| **Writing / Article** | `writing` | Research-backed article generation: CoVE + SoT + Pre-Mortem pipeline | Long-form writing |
| **Brainstorming** | `brainstorming` | Verbalized Sampling (VS-Standard / VS-CoT): multi-round divergent idea generation with semantic clustering | Creative ideation |
| **Coding** | `coding` | 5-phase production code pipeline: spec → parallel generation → adversarial review → tests → assembly | Production code |
| **Iterative Critique** | `iterative-critique` | Adversarial generator-critic loop with convergence detection (LLM Debate) | Iterative refinement |

---

## 🎛️ Available Presets

Reasoner ships with **48 presets** — every method has at least a **Budget** (~$0.01–$0.05/run) and **Premium** (~$0.15–$0.35/run) variant.

### Multi-Perspective

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `multi-perspective-ultra-budget` | Ultra-Budget | <$0.01 | Ministral-3B + Gemini Flash Lite — minimal 5-phase, top-k=1 |
| `multi-perspective-budget` | Budget | ~$0.02 | Google (constructive) + Mistral (destructive) + Zhipu GLM (systemic) |
| `multi-perspective-premium` | Premium | ~$0.20 | Kimi K2.6 + DeepSeek R1T2 + Qwen 3.6 + Gemini Pro |

### Debate

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `debate-budget` | Budget | ~$0.015 | DeepSeek (Model A) vs Qwen (Model B), judged by GLM |
| `debate-premium` | Premium | ~$0.25 | Gemini Pro vs Kimi K2.6, judged by Perplexity Sonar Pro |

### Jury / Orchestrated

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `jury-budget` | Budget | ~$0.02 | DeepSeek + Qwen + GLM + MiniMax + Mistral (5 different labs) |
| `jury-premium` | Premium | ~$0.30 | Claude + Kimi K2.6 + DeepSeek R1T2 + Qwen 3.6, scored by Sonar Pro |

### Research

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `research-budget` | Budget | ~$0.02 | DeepSeek + Qwen + Gemini — iterative SearXNG search |
| `research-premium` | Premium | ~$0.25 | Claude + Kimi K2.6 + DeepSeek + MiMo V2, live fact-check via Sonar Pro |

### Scientific

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `scientific-budget` | Budget | ~$0.02 | DeepSeek hypothesis, Qwen testing, GLM evaluation |
| `scientific-premium` | Premium | ~$0.25 | Claude hypothesis, Kimi K2.6 testing, Sonar Pro evidence |

### Socratic

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `socratic-budget` | Budget | ~$0.02 | DeepSeek questions, Qwen answers, GLM evaluation |
| `socratic-premium` | Premium | ~$0.25 | Claude questions, Kimi K2.6 answers, Sonar Pro evidence |

### Pre-Mortem

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `pre-mortem-budget` | Budget | ~$0.02 | DeepSeek failure scenarios, Qwen backtracking, GLM signals |
| `pre-mortem-premium` | Premium | ~$0.25 | Claude failure scenarios, Kimi K2.6 backtracking, MiMo V2 synthesis |

### Bayesian

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `bayesian-budget` | Budget | ~$0.02 | DeepSeek priors, Qwen likelihood, GLM posterior |
| `bayesian-premium` | Premium | ~$0.25 | Claude priors, Kimi K2.6 likelihood, Sonar Pro evidence |

### Dialectical

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `dialectical-budget` | Budget | ~$0.02 | DeepSeek thesis, Qwen antithesis, GLM synthesis |
| `dialectical-premium` | Premium | ~$0.25 | Claude thesis, Kimi K2.6 antithesis, MiMo V2 synthesis |

### Analogical

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `analogical-budget` | Budget | ~$0.02 | DeepSeek abstraction, Qwen domain search, GLM mapping |
| `analogical-premium` | Premium | ~$0.25 | Claude abstraction, Kimi K2.6 domain search, MiMo V2 synthesis |

### Delphi

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `delphi-budget` | Budget | ~$0.03 | DeepSeek + Qwen + GLM + Mistral experts (4 different labs) |
| `delphi-premium` | Premium | ~$0.30 | Claude + Kimi K2.6 + DeepSeek R1T2 + Qwen 3.6 experts |

### Chain-of-Verification (CoVE)

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `cove-budget` | Budget | ~$0.02 | DeepSeek draft → Qwen verify → GLM answer → Gemini revise |
| `cove-premium` | Premium | ~$0.25 | Claude draft → Kimi K2.6 verify → DeepSeek R1T2 answer → Qwen revise |

### Skeleton-of-Thought (SoT)

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `sot-budget` | Budget | ~$0.02 | DeepSeek skeleton → Qwen solve → GLM assemble |
| `sot-premium` | Premium | ~$0.25 | Claude skeleton → Kimi K2.6 solve → DeepSeek R1T2 assemble |

### Tree-of-Thoughts (ToT)

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `tot-budget` | Budget | ~$0.02 | DeepSeek decompose → Qwen generate → GLM evaluate → Gemini backtrack |
| `tot-premium` | Premium | ~$0.25 | Claude decompose → Kimi K2.6 generate → DeepSeek R1T2 evaluate |

### Program-of-Thought (PoT)

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `pot-budget` | Budget | ~$0.02 | DeepSeek generate → Qwen execute → GLM interpret |
| `pot-premium` | Premium | ~$0.25 | Claude generate → Kimi K2.6 execute → DeepSeek R1T2 interpret |

### Self-Discover

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `self-discover-budget` | Budget | ~$0.02 | DeepSeek select → Qwen adapt → DeepSeek implement |
| `self-discover-premium` | Premium | ~$0.25 | Claude select → Kimi K2.6 adapt → DeepSeek R1T2 implement |

### Writing / Article Generation

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `writing-budget` | Budget | ~$0.05 | DeepSeek + Mistral + Kimi K2.6 + GLM — CoVE + SoT + Pre-Mortem |
| `writing-premium` | Premium | ~$0.20 | Claude (decompose/CoVE/verify) + GLM-5.1 (SoT/assemble) + Gemini Pro (synthesis/critique) |

### Brainstorming (Verbalized Sampling)

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `brainstorming-budget` | Budget | ~$0.03 | Qwen3-Max generates (3 rounds × 5 ideas), Gemini clusters, DeepSeek develops top 3 |
| `brainstorming-premium` | Premium | ~$0.25 | Claude Sonnet VS-CoT (5 rounds × 5 ideas), Gemini Pro clusters, Kimi K2.6 develops top 5 |

### Coding / Code Generation

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `coding-budget` | Budget | ~$0.05 | Gemini spec → DeepSeek generate → Qwen review → DeepSeek tests → Kimi K2.6 assemble |
| `coding-premium` | Premium | ~$0.30 | Claude spec+tests → Kimi K2.6 generate → DeepSeek R1T2 review → GPT-5 assemble |

### Iterative Critique (LLM Debate)

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `iterative-critique-budget` | Budget | ~$0.02 | DeepSeek generator vs DeepSeek V4 Flash critic |
| `iterative-critique-premium` | Premium | ~$0.25 | GPT-5 generator vs Claude Sonnet critic |

### SubAgent (Per-Subagent Routing)

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `subagent-budget` | Budget | ~$0.02 | Every subagent (synthesis, critique, search) routed to a dedicated cross-lab model |
| `subagent-premium` | Premium | ~$0.30 | Gemini Pro + Claude + DeepSeek R1T2 + Sonar Pro per-subagent |

### Cross-Language (DeepL Translation)

| Preset | Tier | Est. Cost | Key Model Diversity |
|--------|------|-----------|---------------------|
| `cross-language-budget` | Budget | ~$0.02 | Google + Mistral + Zhipu — requires `DEEPL_API_KEY` |
| `cross-language-premium` | Premium | ~$0.20 | Gemini Pro + Claude + Qwen 3.6 — requires `DEEPL_API_KEY` |

### Image Generation

| Preset | Tier | Est. Cost | Primary Models |
|--------|------|-----------|----------------|
| `image-gen-budget` | Budget | varies | Riverflow v2 Fast Preview + Gemini Flash Image; Seedream 4.5 / Flux 2 Pro fallbacks |
| `image-gen-premium` | Premium | varies | Gemini 3 Pro Image + GPT-5 Image; Gemini 3.1 Flash Image fallback |

### Experimental

| Preset | Tier | Notes |
|--------|------|-------|
| `nvidia-nemotron-test` | Experimental | NVIDIA Nemotron-3-Super-120B via NIM free tier. Use with `--sequential` only (40 RPM cap). |

---

## 🔀 Model Routing Philosophy

### Why Cross-Lab Diversity Matters

Different model families are trained on different data distributions, reward functions, and safety paradigms. When multiple perspectives come from the **same lab**, the pipeline converges to an **echo chamber** — the models agree on the same hidden assumptions and miss the same blind spots.

### Design Rules

1.  **Phase 2 (Perspectives)** — Minimum 3 different labs in Budget, 4 in Premium.
2.  **Phase 3 (Scoring)** — Scorer must be from a different ecosystem than the dominant Phase-2 generator.
3.  **Fallbacks** — Failures fall back to a **cross-lab equivalent**, not automatically to the preset primary.
4.  **Phase 0 (Classification)** — Optimized for speed and cost; diversity is secondary.
5.  **Phase 5 (Synthesis)** — Optimized for coherence and depth; diversity is useful but not at the expense of consistency.

---

## 🔒 Security & Encryption

Reasoner v2.1 implements a comprehensive **Zero-Trust** security architecture to ensure your data is protected at every stage.

- **End-to-End Transit Encryption:** All traffic, both external (client-to-proxy) and internal (inter-container), is encrypted via TLS 1.3/1.2.
- **Internal PKI:** An automated certificate generation system provisions unique internal certificates for all services (`backend`, `frontend`, `database`, `redis`) on every startup.
- **At-Rest Protection:** Sensitive data, including API key metadata, user information, and full pipeline execution states, is encrypted at the application layer using **AES-256-GCM** before storage.
- **Zero-Trust Networking:** All internal components (PostgreSQL, Redis, FastAPI, Next.js) strictly require TLS, making the internal network opaque even to local attackers.

### Legacy Data Encryption Migration

To migrate existing encrypted data to the latest envelope encryption format with blind indexing (introduced in Reasoner v2.2), use the standalone migration script. This is an **idempotent** operation and can be run safely multiple times.

```bash
python scripts/migrate_encryption_v2.py \
  --connection-string "postgresql://user:pass@host:port/dbname" \
  --encryption-key "your_base64_fernet_key" \
  --blind-index-key "your_hmac_sha256_key" \
  --batch-size 1000 \
  --delay-seconds 0.05
```

**Important Notes:**
-   **Production:** Run this script during off-peak hours with appropriate batch sizes and delays to minimize database load.
-   **Keys:** Ensure `ENCRYPTION_KEY` and `BLIND_INDEX_KEY` match those used by your running Reasoner application.
-   **Backward Compatibility:** The Reasoner application is designed to gracefully handle both old and new encryption formats during reads, allowing for a zero-downtime migration.

For more technical details, see [ENCRYPTION.md](./ENCRYPTION.md).

---

## 🛠️ Development

### Running Tests

```bash
# Full suite
python -m pytest tests/ -v

# Quick run (skip slow/integration tests)
python -m pytest tests/ -v -m "not slow and not integration"

# With coverage
python -m pytest tests/ --cov=src/reasoner --cov-report=html
```

### Code Quality

```bash
# Python linting
ruff check src/reasoner/
ruff format src/reasoner/

# Frontend linting
cd ui-next && npm run lint
```

---

<div align="center">

**[⬆ Back to Top](#reasoner-v22)**

Made with ❤️ and a lot of reasoning

</div>
es decisions. The epistemic labels (`VERIFIED` / `HYPOTHESIS` / `UNKNOWN`) are heuristic estimates, not guarantees of factual correctness.

---

<div align="center">

**[⬆ Back to Top](#reasoner-v22)**

Made with ❤️ and a lot of reasoning

</div>
