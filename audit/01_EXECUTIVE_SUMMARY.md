# 01 — Executive Summary

**Audit date:** 2026-06-12
**Scope:** Full repository — Python/FastAPI backend (`src/reasoner`, ~380 files), Next.js 16/React 19 frontend (`ui-next`, ~144 TS files), tests (~207 files), CI, deployment config.
**Method:** Six parallel area investigations (backend core, API/security, infrastructure, frontend, cross-system/reliability, testing/tech-debt) followed by an independent second-pass verification that confirmed, refuted, or recalibrated every high-impact claim. All findings cite file:line evidence; refuted findings are recorded in `02_FINDINGS_REGISTER.md`.

---

## Repository Overview

Reasoner is an AI reasoning orchestrator: HyperGate pre-router → 6-phase pipeline (classify, decompose, generate cross-lab perspectives in parallel, critique, stress-test, synthesize) streamed to the UI over SSE. Architecture is hexagonal DDD + CQRS + event sourcing with 131 whitelisted LLM models, 50 presets, SQLite/Postgres event stores, Redis run-state, and a tiered Neuro memory.

The architecture is genuinely sound at the macro level: layering is real (domain has no outward deps), fallback/circuit-breaker patterns are pervasive, security middleware exists (sanitization, CSRF HMAC, rate limiting, headers), and there is a 60% coverage gate in CI. The problems are concentrated in (a) operational/configuration hygiene, (b) async edge cases and silent-failure paths, (c) SSE contract drift between backend and frontend, and (d) accumulated workspace debt.

## Overall Health Score: **6 / 10**

Production-capable for a single-worker, single-operator deployment; **not yet safe for multi-worker or multi-tenant production** without the Tier-1 fixes below.

---

## Top Risks (prioritized)

1. **Secret & security-config hygiene (HIGH).** Local `.env` contains live API keys for ~12 providers plus Supabase, with `CSRF_ENFORCE_BACKEND=false` and a guessable `CSRF_SECRET` (`reasoner-csrf-secret-2026`). The file is correctly gitignored — *not committed* — but keys were trivially readable by any tool/agent operating in the workspace, and the dev config would be catastrophic if promoted to production unchanged. (SEC-01R, SEC-03, SEC-13)
2. **Multi-worker deployment breaks safety assumptions (HIGH).** In-memory rate limiting multiplies limits per worker (guard is bypassable via `ENVIRONMENT=development`), and Redis run-state silently falls back to per-process memory — cancellation issued on worker A never reaches worker B. (SEC-10, XS-04, INF-08)
3. **SSE contract drift and stream fragility (HIGH).** Backend emits `phase_warning` that the frontend never handles; `phase_retry.reason` missing from frontend types; the SSE reader has no inactivity timeout (a dead backend freezes the UI in "running" state); `handleResume` streams cannot be aborted. (XS-01, XS-03, FE-04, FE-11)
4. **Verified frontend pagination bug (HIGH).** Stale-closure in `useConversationHistory.loadMore` corrupts conversation history during pagination. (FE-01)
5. **SQL built by string interpolation (MEDIUM, defense-in-depth).** Event store `ON CONFLICT … SET {', '.join(updates)}` and error store f-string `days` interpolation. Currently fed only by hardcoded/bounds-checked values, so not exploitable today — but a brittle pattern in security-sensitive persistence code. (INF-01, INF-02)
6. **Silent failure modes throughout the pipeline (MEDIUM).** Prompt enhancement, cross-language translation, Redis fallback, SearXNG search, and dead-letter logging all swallow errors without `state.errors` entries, metrics, or warnings. Degradation is invisible to operators and users. (BC-05, BC-06, BC-12, INF-08, XS-05, XS-09)
7. **Critical-path test gaps (HIGH risk exposure).** `api/streaming.py` (941 lines, 0 direct unit tests), `infrastructure/llm/router.py` (one degradation test only), CSRF (one regression test), HyperGate sub-agents (integration-only). (TG-01…TG-10)
8. **Workspace/tech debt (MEDIUM).** ~69 untracked root artifacts plus ~20 tracked legacy files (`legacy/`, `Humanizer/`), 30 backward-compat shims, five 900–2000-line monoliths (`preset_registry.py` 1987, `pipeline_state.py` 1616, `streaming.py` 941, `api/__init__.py` 789). (TD-01…TD-06)

---

## Architectural Assessment (summary — full review in 05)

**Strengths:** real layered architecture with enforced dependency direction; cross-lab model-routing philosophy implemented, not just documented; defense-in-depth security middleware; event-sourced state with snapshots; explicit known-violations documented in CLAUDE.md (CQRS streaming bypass).

**Weaknesses:** app factory (`api/__init__.py`) is a 789-line monolith doing lifespan, wiring, and routing; the event bus has fire-and-forget tasks and no backpressure timeout for critical events; optional infrastructure (Redis, SearXNG) degrades silently rather than loudly; the SSE event contract has no single source of truth shared between backend and frontend; observability is log-only (no metrics/counters on failure paths).

---

## Prioritized Action List

| Tier | Actions | Effort |
|------|---------|--------|
| **T1 — Now (config/safety, near-zero regression risk)** | Rotate live keys as precaution; generate random `CSRF_SECRET`; document prod-required flags; force Redis rate limiter when workers>1 regardless of `ENVIRONMENT`; fix Dockerfile `EXPOSE 8000→8003`; remove WS query-param token | < 1 day |
| **T2 — This week (verified bugs, surgical fixes)** | FE-01 stale closure; FE-04 SSE inactivity timeout; FE-11 resume abort signal; XS-01 `phase_warning` handler; XS-03 type field; BC-01 task retention; BC-05/06/12 error logging; parameterize INF-01/INF-02 SQL | 2–3 days |
| **T3 — This sprint (reliability hardening)** | Startup validation for Redis run-state under multi-worker; SearXNG healthcheck + startup probe; Redis-fallback WARNING logs/counters; WS manager race + dead code; httpOnly CSRF cookie (token already returned in body); skipHtml on markdown | 3–5 days |
| **T4 — Next sprint (tests + debt)** | Streaming/router/CSRF/HyperGate test suites; delete root clutter + .gitignore additions; deprecation warnings on shims | 1 week |
| **T5 — Strategic** | Split `streaming.py`, `api/__init__.py`, `preset_registry.py`; SSE contract codegen/single source of truth; metrics layer | ongoing |

**Refuted during second pass (do not implement):** timing attack in auth (uses `secrets.compare_digest`), RCE in `/api/calculate` (safe AST whitelist evaluator), "conversation switch corrupts streams" as originally framed (new runs do abort prior streams).
