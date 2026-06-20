# Reasoner — Reasonix knowledge base

## Stack
- **Backend:** Python 3.12+ / FastAPI 0.115 / Pydantic v2 / uvicorn
- **Frontend:** Next.js 16 / React 19 / TypeScript 5 / Tailwind CSS v4 / Zustand v5
- **Key deps:** OpenRouter (primary LLM), httpx, anthropic/openai/google-genai SDKs, stripe, SWR, idb v8, framer-motion

## Layout
- `src/reasoner/` — Python backend: `api/` (FastAPI+SSE), `application/` (CQRS), `pipeline.py` (orchestrator), `phases/` (19 prompt modules), `hypergate/` (5 sub-agent pre-router), `domain/` (preset registry), `infrastructure/` (LLM providers, persistence), `neuro/` (memory), `core/` (settings, constants), `healing/`
- `ui-next/src/` — Next.js App Router: `app/` (pages + API proxy routes), `components/`, `hooks/` (SSE streaming), `stores/` (Zustand), `lib/` (types, api-client, security)
- `tests/` — pytest suite (~190 files, conftest.py at root)

## Commands
- **Backend dev:** `uvicorn asgi:app --reload --host 0.0.0.0 --port 8003`
- **Frontend dev:** `cd ui-next && npm run dev`
- **All servers:** `python start_all.py`
- **Tests (Python):** `pytest tests/`
- **Tests (frontend):** `cd ui-next && npm test` (vitest), `npm run test:e2e` (Playwright)
- **Lint:** `ruff check src/` (Python), `cd ui-next && npm run lint` (TS)
- **Typecheck:** `mypy src/`

## Conventions
- Commits use Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:` prefixes
- Tailwind CSS v4: no `tailwind.config.ts` — config in `globals.css` via `@import "tailwindcss"`
- Python tests: `test_*.py` in `tests/`, named after module under test
- API proxy: Next.js routes at `ui-next/src/app/api/*/route.ts` validate+forward to `http://127.0.0.1:8003` (from `API_BASE_URL` in `ui-next/.env.local`)
- Frontend SSE: `usePipelineStream` hook wraps `fetchWithCsrf` + `readSSEStream`
- Rate limiter: `RATE_LIMITER_MODE=memory` in dev `.env`; switch to `redis` for multi-worker

## Watch out for
- **No pyproject.toml** — Python deps in `requirements.txt` only. Ruff/pytest config has no central file (ruff uses defaults, pytest uses `tests/conftest.py`).
- **`_ensure_fresh_preset_service()`** in `api/streaming.py` deletes+reimports modules on first pipeline run — can break inline interpreters. Affects any code path importing presets mid-request.
- **`QueryTimer` is undefined** in `api/__init__.py: _run_stream_with_metrics` — `try/except ImportError` was added so SSE streaming degrades gracefully; don't reintroduce hard import.
- **First SSE event yields AFTER preflight** — if orchestrator.preflight() hangs (HyperGate LLM calls or neuro recall), user sees empty spinner with no phase_start event.
- **Two layer ratelimit** — Next.js proxy (`ui-next/src/lib/security-server.ts`, 10 req/min per IP) AND backend (`rate_limiter.py`, 10000/min with burst 50). Both must be tuned together.
