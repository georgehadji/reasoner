# 05 — Architecture Review

## Architectural Strengths

1. **Real layering, not aspirational.** Domain (`pipeline_state.py`, `preset_core.py`) has no outward dependencies; Core defines ports (`core/ports/`); Infrastructure implements them; API/Application sit on top. The two known violations (streaming bypassing CQRS; `flows/__init__` importing `api.serializers`) are *documented* in CLAUDE.md with a feature flag — honest architecture governance.
2. **Cross-lab model routing as a first-class concern.** The whitelist/registry/router split (`infrastructure/llm/registry.py`, `router.py`) with fallback-to-different-ecosystem rules is implemented in code, not just described. Fallback events are buffered and surfaced into state (`orchestrator.py:94-106, 222-225`).
3. **Resilience patterns are pervasive.** Circuit breakers per provider, cascading model fallback with quality checks (`executor.py:206-285`), retry-with-classification in the workflow runner (`flows/runner.py:131-139`), Redis circuit breaker with in-memory fallback, Postgres store with retry + breaker.
4. **Event sourcing with snapshots and compaction** (`core/aggregates/`, `persistence/snapshots.py`, nightly compaction service) gives replayability and `--resume`; the dict-with-`.get()` method-state convention keeps old state files loadable.
5. **Security defense-in-depth exists at every boundary:** sanitization with prompt-injection regexes, HMAC CSRF with constant-time compare, token-bucket rate limiting with fail-closed Redis mode, security headers middleware, IP anonymization, scoped auth. Second-pass verification confirmed the auth comparisons use `secrets.compare_digest` and the calculator endpoint uses a safe AST evaluator — the foundations are stronger than a first glance suggests.
6. **Self-aware tooling:** self-healing CI, living docs via post-commit hooks, regression tests named after fixed bugs (~70 of them) — evidence of a learning loop.

## Architectural Weaknesses

1. **The app factory is a god-module.** `api/__init__.py` (789 lines) performs logging config, Sentry init, lifespan orchestration with ~20 inline imports, middleware ordering, startup probes, and route mounting. Startup cannot be tested in isolation; any new infrastructure dependency lands here. (TD-04)
2. **Silent degradation is the house style.** Prompt enhancement, translation, SearXNG search, Redis run-state, WS broadcast, dead-letter logging — all fail quietly (BC-05/06/12, XS-05/09, INF-08, BC-01). The system *stays up*, which is good, but neither operators nor `state.errors` learn that quality or capability degraded. There is no metrics layer at all; observability is unstructured logs.
3. **The SSE contract has no single source of truth.** Backend emits shapes in `streaming.py`/`serializers.py`; frontend hand-maintains `types.ts`. Drift is already observable (`phase_warning` unhandled, `reason` untyped, followup history schema narrower than payload — XS-01/03/06). Every new event type will repeat this.
4. **Event bus is the least mature core component.** Fire-and-forget tasks, no backpressure timeout for critical events, snapshot races on the handler list, drain that doesn't wait for in-flight handlers (BC-01/02/03/10). It sits under every pipeline run.
5. **Monolith files at the hot spots.** `preset_registry.py` (1987 lines: registry + tier enforcement + pricing + routing), `pipeline_state.py` (1616: state + cost + serialization), `streaming.py` (941: five distinct stream generators), `serializers.py` (1083). These are exactly the files that change most often.
6. **30 backward-compat shims** at `src/reasoner/` root blur the import surface; tests and new code still import through them, so the "real" module graph is hidden from tooling.
7. **PipelineState is a ~60-field mutable bag shared by all phases.** Today phases run sequentially so unsynchronized mutation works (BC-04 latent), but the design gives no guardrail if anyone parallelizes phases — and Phase 2 already runs LLM calls in parallel.

## Scaling Risks

- **Horizontal scaling is currently unsafe.** Memory rate limiter multiplies limits per worker (guard bypassable, SEC-10); run-state cancellation silently localizes per worker when Redis blips (XS-04/INF-08); upload dedup index and history are local JSON files. Multi-instance deployment needs: Redis mandatory + shared object storage + the startup probes from Phase B.
- **SQLite event store** is single-writer with a process lock; fine for one node, a wall for several. The Postgres store exists — the migration path should be exercised before scale demands it.
- **In-process caches** (token cache with index bloat INF-06, circuit-breaker registries with FIFO-not-LRU eviction INF-09) degrade over long uptimes.

## Maintainability Risks

- Root workspace clutter (~69 untracked artifacts, tracked `legacy/`/`Humanizer/`) raises onboarding cost and hides real changes in `git status`.
- Critical-path test gaps (streaming 0 unit tests, router 1, CSRF 1) make the planned refactors of exactly those files risky — tests must precede splits (sequenced in the plan: E before F).
- Self-healing CI generates tests that are uploaded but never executed (TD-05) — automation that produces unverified artifacts is negative-value over time.
- Frontend coverage threshold is 50% with ~16 test files for ~200 components and a single E2E spec.

## Recommended Future Direction

1. **Make degradation loud before making anything faster.** A minimal metrics module (counters: redis_fallbacks, ws_broadcast_failures, dead_letters, enhancement_failures) + the WARNING logs from Phase D changes the operational posture more than any refactor.
2. **Contract-first SSE.** Define the event schema once (Pydantic models already exist piecemeal in `schemas.py`) and generate `types.ts` from it in CI; fail the build on drift. This permanently retires the XS-01/03/06 class of bugs.
3. **Test-then-split.** Land E1 (streaming tests) → split `streaming.py` by stream type; land router tests → simplify the fallback-candidate logic (INF-07); extract lifespan from the app factory with a `LifecycleManager` whose phases are individually testable.
4. **Decide the multi-worker story explicitly.** Either document "single-worker product" and delete the multi-worker code paths, or make Redis + Postgres the hard requirement above 1 worker (Phase B does the latter). The half-supported middle is where the silent bugs live.
5. **Retire the shims on a schedule.** `warnings.warn(DeprecationWarning)` now, codemod imports next quarter, delete after.
6. **Keep PipelineState honest.** Either freeze the sequential-phases invariant in a comment + assertion in the runner, or introduce a narrow mutation API (single accumulate method for costs/tokens — BC-09) so future parallelization has one place to add locking.
