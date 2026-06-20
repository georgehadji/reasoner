# 06 — Testing Gaps

Current state (verified): ~207 backend test files with a 60% coverage hard gate (80% warn) in CI; pytest marks exclude `slow`/`integration`/`searxng` from CI runs; frontend has ~16 vitest files for ~200 components with a 50% threshold and exactly one Playwright spec (`ui-next/e2e/checkout.spec.ts`); self-healing CI generates tests it never executes (`.github/workflows/self-healing-ci.yml:141-150`).

Ordered by risk.

---

## 1. Missing Unit Tests — Backend (highest risk)

### TG-01 — `api/streaming.py` (941 lines, ZERO direct unit tests) — HIGH
The single most-used code path (every chat request) has no dedicated test file; only ~11 incidental mentions across other tests.
Add `tests/test_api_streaming.py`:
- SSE generator closes cleanly when the pipeline raises mid-stream (error event emitted, generator terminates).
- Cached replay (`run_stream_cached`) emits the same event sequence as a live run, including the `connecting` event (currently a known gap, XS-07 — write the test to pin desired behavior).
- Follow-up streams do not share state across concurrent invocations.
- `phase_warning` emitted on DegradedLLMResponse (pins XS-01 backend side).
- Client-disconnect path triggers run-store cleanup (`streaming.py:815-821`).

### TG-02 — `infrastructure/llm/router.py` — HIGH
Only `test_provider_router_degradation.py` exists. Add:
- Primary selected when healthy; fallback chain order on failure; fallback never selects same model as failed primary (pins INF-07 logic).
- Cross-lab fallback preference (the routing philosophy is untested).
- Behavior when explicit fallback == primary model (the `next(..., None)` → None edge in `router.py:123-138`).

### TG-05 — CSRF (`api/csrf.py`, security boundary, one regression test) — HIGH
Add `tests/test_csrf_comprehensive.py`:
- Malformed tokens (wrong segment count, non-hex, truncated signature) rejected.
- Expiry boundaries: exactly max-age, ±1s.
- Frontend-format vs backend-format token cross-verification (both formats are accepted; only the clock-jump case is tested today).
- Tampered payload with valid-length signature rejected.

### TG-03 — HyperGate sub-agents (integration-only coverage) — MEDIUM
`tests/test_hypergate.py` exercises the gate end-to-end only. Add unit tests per sub-agent:
- ComplexityEstimator: empty, one-word, code-heavy, very long prompts.
- LanguageDetector: mixed-language, code snippets, RTL.
- TieBreaker: determinism for identical inputs; documented precedence on ties.
- Fast-path regex ordering in `hyperagent.py` (short-prompt → writing → realtime → factual) — pin the order.

### TG-04 — Persistence stores — MEDIUM
`auth_store.py`, `feedback_store.py`, `telemetry_store.py`, `cached_quota_repo.py`, `subscription_repo.py` lack dedicated tests (only event_store/postgres_store/quota_repo_postgres covered). Priorities:
- auth_store: revocation takes effect immediately; concurrent revoke+authenticate.
- telemetry_store: non-JSON-serializable `fallback_events` (pins INF-10 fix).
- feedback_store: write durability/error path.

### TG-06 — Rate limiter Redis-fallback quota invariant — MEDIUM
Three concurrency/edge test files exist; missing: Redis dies mid-window → in-memory fallback still enforces per-minute limit (no quota reset on failover); `fail_closed` mode actually denies.

### TG-07 — App assembly (`api/__init__.py`) — MEDIUM
- Startup raises when workers>1 + memory limiter regardless of ENVIRONMENT (pins B1).
- Production settings validation (CSRF enforce, APP_URL) (pins B2/B4).
- Middleware ordering: CSRF/auth evaluated before CORS short-circuits.
- Lifespan failure in one init step produces a clear startup error (not a half-initialized app).

### Event bus (new, from this audit) — MEDIUM
- Queue-full → dead-letter written (pins BC-01/C5).
- Slow critical handler does not block publisher beyond timeout (pins BC-03/D1).
- drain() waits for in-flight handlers (pins BC-10).

## 2. Missing Unit Tests — Frontend

### TG-09a — Hooks — HIGH (given verified bugs found here)
- `useConversationHistory.loadMore`: two-page pagination, no dup/loss (pins FE-01).
- `usePipelineStream`: new run aborts previous (pins the FE-02 refutation as a regression guard); error state set on stream rejection.
- `readSSEStream`: truncated/multi-frame SSE chunks; inactivity timeout (pins FE-04/C2).

### TG-09b — Components — MEDIUM
- `WidgetRenderer` with `result: null` / wrong shapes (pins FE-09/D6).
- `MarkdownRenderer`: raw-HTML input is not rendered as HTML (pins SEC-15/C11); large-stream snapshot.
- Chat onEvent reducer: `phase_warning`, `phase_retry` with `reason` (pins C4).

## 3. Missing Integration Tests

1. **SSE contract test (backend↔frontend)** — strongest single addition: a backend test that captures every event `type` emitted across a mocked full run, asserted against the literal union in `ui-next/src/lib/types.ts` (checked into a shared fixture). Fails on any future drift (root-cause guard for XS-01/03/06). — HIGH
2. **Multi-worker cancellation** — two app instances + Redis: cancel on instance A stops stream served by B; with Redis down, startup fails (pins XS-04/B3). Mark `integration`. — HIGH
3. **SearXNG-down path** — research preset with SearXNG unreachable: pipeline completes degraded, warning logged (pins XS-05/B5). — MEDIUM
4. **Event-store replay with pruning** — snapshot boundary event pruned → full replay fallback (pins INF-04/D3). — MEDIUM
5. **Resume (`--resume`) with an older state file** lacking newer method-state keys — pins the `.get()` invariant. — MEDIUM

## 4. Missing E2E Tests (Playwright — currently 1 spec)

Priority order:
1. **Core chat flow:** submit → phases stream → synthesis renders → history persists after reload (IndexedDB).
2. **Stream interruption:** kill backend mid-stream → UI shows error within timeout, not frozen "running" (pins FE-04).
3. **Conversation switching during stream and during resume** (pins FE-11/C3).
4. **CSRF round-trip:** expired token → auto-refresh → success; refresh failure → visible error (pins FE-07).
5. **Preset/tier switching** affects the run request payload.

## 5. Missing Observability Checks

1. **No metrics at all** — failure paths log (at best) and count nothing. Minimum counters: redis run-state fallbacks (INF-08), WS broadcast failures (XS-09), dead-letter writes (BC-01), enhancement/translation failures (BC-05/12), rate-limiter fallback engagements. Then assert in tests that the counters increment.
2. **No health surface for optional deps** — `/health` should report SearXNG/Redis/Postgres reachability so operators see degradation (today only startup probes exist, and only for rate-limiter Redis: `api/__init__.py:116-127`).
3. **CI never runs integration-marked tests** (TG-10) — they will bit-rot. Add a separate (initially non-blocking) CI job for `-m integration` with Redis/Postgres services.
4. **Self-healing generated tests are never executed** (TD-05) — add `pytest healing/generated_tests/` after the generation step; non-blocking first, gate later.
5. **Frontend coverage threshold 50%** — raise to 70% after TG-09a/b land; add the SSE-contract fixture check to the frontend CI as well.

## Suggested sequencing

1. TG-01 streaming tests + SSE contract test (protects the most code and the planned refactor).
2. TG-09a hook tests (pin the just-fixed verified bugs).
3. TG-05 CSRF + TG-02 router.
4. Integration job in CI + multi-worker cancellation test.
5. E2E core chat + stream-interruption specs.
6. Observability counters + health surface, with tests.
