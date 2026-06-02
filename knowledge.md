# Project Knowledge — Reasoner v2.2

A production-grade, multi-LLM reasoning orchestrator that decomposes complex problems into structured phases, runs perspectives across diverse model ecosystems, and synthesizes evidence-grounded answers with epistemic labeling. Supports 16 reasoning methodologies (debate, scientific, Bayesian, tree-of-thoughts, etc.) plus a HyperGate auto-router.

## Quickstart

### Prerequisites
- **Python 3.12+**
- **Node.js 20+** (frontend)
- **OpenRouter API key** recommended (single key → 350+ models). Individual provider keys also supported (OpenAI, Anthropic, Google, DeepSeek, Mistral, xAI, Perplexity, Ollama).

### Setup
```bash
# Backend
cp .env.example .env        # then edit: OPENROUTER_API_KEY=sk-or-v1-...
python -m venv .venv
.venv\Scripts\activate      # Windows (bash)
pip install -r requirements.txt

# Frontend
cd ui-next && npm install && cd ..
```

### Dev (start everything)
```bash
python start_all.py
# FastAPI backend  → http://localhost:8003 (SERVER_PORT env var)
# Next.js frontend → http://localhost:3000
# SearXNG search   → http://localhost:8888
```

Individual services:
```bash
uvicorn asgi:app --reload --port 8003
cd ui-next && npm run dev
```

### CLI
```bash
python main.py --problem "Your question"                          # default preset
python main.py --problem "..." --preset debate-budget             # ~$0.02/run
python main.py --problem "..." --preset multi-perspective-premium # ~$0.15–0.30/run
python main.py --list-presets
python main.py --list-models
python main.py --problem "..." --sequential    # for rate-limited providers
python main.py --problem-file problem.txt --output results.json
```

### Test
```bash
python -m pytest tests/ -v                                  # full suite (800+ tests)
python -m pytest tests/ -v -m "not slow and not integration"
python -m pytest tests/ --cov=src/reasoner --cov-report=html
```

### Lint / Format
```bash
ruff check src/reasoner/
ruff format src/reasoner/
cd ui-next && npm run lint
```

## Architecture

### Pipeline phases (orchestrated default)
1. **Classification** — task type + language detection
2. **Decomposition** — break problem into sub-problems + assumptions
3. **Context Vetting (universal RAG)** — iterative search loop, max 3 iterations
4. **Deep read_file** (optional) — fetch full content of critical sources
5. **Generation / Perspectives** — competing answers across diverse models
6. **Critique / Scoring** — independent scorer panel
7. **Stress Testing / Verification** — adversarial checks
8. **Synthesis** — final answer with epistemic label (`VERIFIED` / `HYPOTHESIS` / `UNKNOWN`)

### Key directories
- `src/reasoner/` — core Python package
  - `pipeline.py` — phase orchestrator
  - `phases.py`, `phases/` — per-phase prompts + logic (incl. `_universal.py`)
  - `llm.py` — `ProviderRouter`, model registry, fallback logic
  - `presets.py` — named routing configurations (budget / premium per method)
  - `models.py` — Pydantic data models + pipeline state
  - `parsing.py` — JSON extraction/repair for LLM output
  - `hypergate/` — auto-method-selection pre-router
  - `application/` — event bus, mixins (article pipeline, perspective)
  - `infrastructure/` — provider routing, caching, events DB
  - `api/` — FastAPI serializers + SSE streaming
  - `renderer.py` — CLI terminal rendering
- `main.py`, `asgi.py`, `api.py` — entry points (CLI, ASGI app, API)
- `ui-next/` — Next.js 16 + React 19 + TypeScript 5 + Tailwind CSS 4 frontend
- `tests/` — pytest suites (name pattern: `test_<area>.py`)
- `cache/tokens/` — server-side response cache (JSON files, keyed by hash)
- `src/reasoner/history/` — pipeline state snapshots
- `legacy/` — legacy modules (kept on `PYTHONPATH` in CI)
- `graphify-out/` — knowledge graph outputs (see `graphify-out/GRAPH_REPORT.md`)

### Data flow
CLI/API → `ProviderRouter` (routes each phase to a configured model) → phase modules run via async pipeline → streamed events via SSE → final `state.final_solution` with `core_solution`, `epistemic_label`, `total_cost_usd`.

### Tech stack
- **Backend:** Python 3.12, FastAPI, Uvicorn, Pydantic, asyncio
- **Frontend:** Next.js 16, React 19, TypeScript 5, Tailwind 4
- **LLMs:** native SDKs (Anthropic, Google, Mistral) + OpenAI-compatible endpoints for everything else
- **Persistence:** file-based response cache, SQLite (`events.db`, `errors.db`, `feedback.db`), client-side IndexedDB for history
- **Search:** SearXNG (dockerized)
- **Security:** TLS 1.3 end-to-end, internal PKI, AES-256-GCM at-rest (see `ENCRYPTION.md`)

## Conventions

### Python style
- 4-space indentation
- `snake_case` for functions, variables, modules
- `PascalCase` for classes, Enums, dataclasses
- Type hints required on public APIs and complex logic
- JSON output parsing goes through `parsing.py` (has repair logic) — don't hand-roll `json.loads` on LLM output

### Frontend
- All UI changes confined to `ui-next/`
- React + TypeScript + Tailwind patterns; follow existing component structure

### Testing
- `pytest`, test files named `test_<area>.py`; group related cases in `Test...` classes
- Add regression tests whenever fixing parsing or routing bugs
- Pytest markers: `slow`, `integration` (skippable)

### Commits
- Conventional Commits: `feat:`, `fix:`, `docs:`, `ui:`, etc.
- Note any `.env` or API key changes in the commit message

### Routing philosophy (cross-lab diversity)
- Phase 2 perspectives: ≥3 different labs (budget), ≥4 (premium) — avoids echo chamber
- Phase 3 scorer: different ecosystem from dominant Phase-2 generator
- Fallbacks: route to **cross-lab equivalent**, not always the preset primary
- Phase 0 (classification): optimize for speed/cost over diversity
- Phase 5 (synthesis): optimize for coherence; diversity secondary

## Gotchas

- **Windows shell quirks:** project runs on Windows (`win32`). Use `.venv\Scripts\activate`, `dir`/`del`/`copy` in cmd, or bash equivalents. `mkdir -p` is not valid in cmd.
- **CI `PYTHONPATH`:** `.github/workflows/self-healing-ci.yml` sets `PYTHONPATH=src/reasoner:legacy`. Local imports (`circuit_breaker`, `health_check`, `retry_utils`) rely on this — run scripts from repo root.
- **Server port:** default backend port is **8003** (`SERVER_PORT` env var), not 8000. Only one uvicorn instance per port.
- **Sequential mode:** use `--sequential` (CLI) or UI toggle when hitting rate limits on parallel-heavy methods (jury, multi-perspective).
- **Structured output fragility:** some models (e.g., Perplexity) need specific `response_format` — see `llm.py` provider-specific handling.
- **Epistemic labels are heuristic**, not ground truth — don't treat `VERIFIED` as a factual guarantee.
- **Token cache is hash-keyed** by `(problem_hash, phase, model_id, prompt_hash)` in `cache/tokens/`. Stale/irrelevant entries are safe to delete.
- **Do not cast to `Any`** in Python or TypeScript to silence type errors — fix the underlying type.
- **Presets use model aliases** (e.g. `gemini-flash-lite`, `gemini-pro`, `deepseek-v3.1-nex-n1`) defined in `llm.py` / `presets.py`; don't hardcode vendor model strings.
- **graphify knowledge graph:** for cross-module "how does X relate to Y" questions, prefer `graphify query "..."` / `graphify path "A" "B"` over grep. Run `graphify update .` after significant code edits (AST-only, no API cost).

## Entry points

| Purpose | Command |
|--------|---------|
| Run everything | `python start_all.py` |
| Backend only | `uvicorn asgi:app --reload --port 8003` |
| Frontend only | `cd ui-next && npm run dev` |
| CLI reasoning | `python main.py --problem "..." [--preset ...]` |
| Tests | `python -m pytest tests/ -v` |
| Lint | `ruff check src/reasoner/` |
