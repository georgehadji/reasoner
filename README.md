<div align="center">

<!-- ASCII Banner -->
<pre>
 █████╗ ██████╗  █████╗         ██████╗ ██╗██████╗ ███████╗██╗     ██╗███╗   ██╗███████╗
██╔══██╗██╔══██╗██╔══██╗        ██╔══██╗██║██╔══██╗██╔════╝██║     ██║████╗  ██║██╔════╝
███████║██████╔╝███████║        ██████╔╝██║██████╔╝█████╗  ██║     ██║██╔██╗ ██║█████╗  
██╔══██║██╔══██╗██╔══██║        ██╔═══╝ ██║██╔══██╗██╔══╝  ██║     ██║██║╚██╗██║██╔══╝  
██║  ██║██║  ██║██║  ██║        ██║     ██║██║  ██║███████╗███████╗██║██║ ╚████║██╔════╗
╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝        ╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝╚═╝╚═╝  ╚═══╝╚══════╝
v2.2 — Reasoner
</pre>

<!-- Badges -->
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688.svg?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js_16-000000.svg?style=flat-square&logo=next.js&logoColor=white)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6.svg?style=flat-square&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-06B6D4.svg?style=flat-square&logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
<br>
[![Tests](https://img.shields.io/badge/tests-800%2B%20passing-brightgreen.svg?style=flat-square&logo=pytest&logoColor=white)](./tests)
[![Coverage](https://img.shields.io/badge/coverage-~70%25-yellow.svg?style=flat-square)](.)
[![License](https://img.shields.io/badge/license-MIT-blue.svg?style=flat-square)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/tesse/Reasoner?style=flat-square&logo=github)](https://github.com/tesse/Reasoner)

**A production-grade reasoning engine that orchestrates 16+ LLM methodologies — from multi-perspective analysis to scientific hypothesis testing — with automatic method selection, cross-lab diversity, and real-time streaming.**

[🚀 Quick Start](#quick-start) · [🧠 Methods](#reasoning-methods) · [🎛️ Presets](#available-presets) · [💻 Development](#development)

</div>

---

## 🎯 Project Overview

Reasoner is a **reasoning orchestrator** that decomposes complex problems into structured phases, leverages multiple LLMs in parallel from diverse training ecosystems, applies rigorous independent critique, stress-tests solutions under adversarial conditions, and synthesizes actionable recommendations with epistemic labeling. It features a HyperGate Pre-Router for automatic method selection, supports 16 reasoning methods, ensures cross-lab diversity, and provides real-time streaming of progress and cost.

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

Reasoner supports **16 specialized reasoning methodologies** beyond the default orchestrated pipeline:

| Method | Description | Best For |
|--------|-------------|----------|
| **Orchestrated** | Default 6-phase pipeline with multi-perspective generation | General complex problems |
| **Debate** | Two models compete; a third judges the winner | Polarized decisions |
| **Scientific** | Hypothesis generation, falsification tests, evidence scoring | Research & validation |
| **Socratic** | Elenchus questioning to expose assumptions | Clarifying ambiguous problems |
| **Jury** | Multiple generators scored by an independent panel of critics | High-stakes decisions |
| **Research** | Web-grounded deep research with iterative SearXNG search | Evidence-heavy questions |
| **Pre-Mortem** | Prospective hindsight failure analysis (Gary Klein methodology) | Risk assessment |
| **Bayesian** | Prior → likelihood → posterior → sensitivity reasoning | Probabilistic reasoning |
| **Dialectical** | Hegelian thesis-antithesis-synthesis progression | Philosophical analysis |
| **Analogical** | Structure-mapping and cross-domain transfer | Creative problem solving |
| **Delphi** | Expert consensus with convergence tracking | Forecasting |
| **Chain-of-Verification** | Draft → verify → answer → revise | Fact-checking |
| **Skeleton-of-Thought** | Skeleton → parallel solve → assemble | Latency reduction |
| **Tree-of-Thoughts** | Reasoning as tree search with evaluation and backtracking | Planning & optimization |
| **Program-of-Thoughts** | Executable code as intermediate reasoning | Quantitative problems |
| **Self-Discover** | Dynamic selection and composition of reasoning modules | Novel problem types |

---

## 🎛️ Available Presets

Every method has a **Budget** (~$0.02/run) and **Premium** (~$0.15–$0.30/run) variant.

| Preset | Tier | Primary | Phase 2 Diversity |
|--------|------|---------|-------------------|
| `multi-perspective-budget` | Budget | `gemini-flash-lite` | Google + Mistral + Zhipu |
| `multi-perspective-premium` | Premium | `gemini-pro` | Moonshot + DeepSeek + Anthropic + Mistral |
| `debate-budget` | Budget | `gemini-flash-lite` | DeepSeek + Qwen + GLM |
| `debate-premium` | Premium | `gemini-pro` | Gemini + Moonshot + Perplexity |
| `scientific-budget` | Budget | `gemini-flash-lite` | DeepSeek + Qwen + GLM |
| `scientific-premium` | Premium | `gemini-pro` | Gemini + Claude + Moonshot |
| `research-budget` | Budget | `gemini-flash-lite` | DeepSeek + Qwen + Gemma |
| `research-premium` | Premium | `gemini-pro` | Gemini + Claude + Moonshot + DeepSeek |
| `jury-budget` | Budget | `gemini-flash-lite` | DeepSeek + Qwen + GLM + Gemma + Mistral |
| `jury-premium` | Premium | `gemini-pro` | Claude + Moonshot + DeepSeek + Alibaba |
| `cove-budget` | Budget | `gemini-flash-lite` | DeepSeek draft → Qwen verify → GLM answer → Gemma revise |
| `cove-premium` | Premium | `gemini-pro` | Gemini + Claude + Moonshot |
| `sot-budget` | Budget | `gemini-flash-lite` | DeepSeek skeleton → Qwen parallel solve → GLM assemble |
| `sot-premium` | Premium | `gemini-pro` | Gemini + Claude + Moonshot |
| `tot-budget` | Budget | `gemini-flash-lite` | DeepSeek decompose → Qwen generate → GLM evaluate → Gemma backtrack |
| `tot-premium` | Premium | `gemini-pro` | Gemini + Claude + Moonshot |
| `pot-budget` | Budget | `gemini-flash-lite` | DeepSeek code generation + Qwen execution + GLM interpretation |
| `pot-premium` | Premium | `gemini-pro` | Gemini + Claude + Moonshot |
| `self-discover-budget` | Budget | `gemini-flash-lite` | DeepSeek selection → Qwen adaptation → GLM implementation |
| `self-discover-premium` | Premium | `gemini-pro` | Gemini + Claude + Moonshot |
| `pre-mortem-budget` | Budget | `gemini-flash-lite` | DeepSeek + Qwen + GLM |
| `pre-mortem-premium` | Premium | `gemini-pro` | Gemini + Claude + Moonshot |
| `bayesian-budget` | Budget | `gemini-flash-lite` | DeepSeek + Qwen + GLM |
| `bayesian-premium` | Premium | `gemini-pro` | Gemini + Claude + Moonshot |
| `dialectical-budget` | Budget | `gemini-flash-lite` | DeepSeek + Qwen + GLM |
| `dialectical-premium` | Premium | `gemini-pro` | Gemini + Claude + Moonshot |
| `analogical-budget` | Budget | `gemini-flash-lite` | DeepSeek + Qwen + GLM |
| `analogical-premium` | Premium | `gemini-pro` | Gemini + Claude + Moonshot |
| `delphi-budget` | Budget | `gemini-flash-lite` | DeepSeek + Qwen + GLM + Gemma |
| `delphi-premium` | Premium | `gemini-pro` | Gemini + Claude + Moonshot + DeepSeek |
| `writing-budget` | Budget | `gemini-flash-lite` | DeepSeek + Mistral + Moonshot + GLM |
| `writing-premium` | Premium | `gemini-pro` | Gemini + Claude + GLM + xAI |
| `cross-language-budget` | Budget | `gemini-flash-lite` | DeepSeek + Mistral + Gemma |
| `cross-language-premium` | Premium | `gemini-pro` | DeepSeek + Qwen + Claude + Gemini |

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
