# 04 — Implementation Instructions (for executor LLM)

Consume tasks in order. Conventions for this repo:
- Backend tests: `python -m pytest tests/ -v -m "not slow and not integration and not searxng"` (Windows; PYTHONPATH may need `src`).
- Frontend checks: `cd ui-next && npx tsc --noEmit && npm run build`.
- All LLM-response parsing must go through `parsing.extract_json()`; all user text through `sanitize_for_prompt()`. Do not change these invariants.
- One task = one commit, message format `fix: <summary> (<FINDING-ID>)`.
- **Never weaken an existing security check to make a test pass.**

---

## TASK A1 — Secret hygiene (SEC-01R, SEC-13)
**Objective:** Remove weak/dev-grade security config; document production requirements.
**Files Likely Affected:** `.env` (local, not committed), `.env.example`.
**Required Changes:**
1. In `.env.example`, replace the `CSRF_SECRET` line area with:
   ```
   # REQUIRED in production. Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
   CSRF_SECRET=
   # MUST be true in production (validated at startup)
   CSRF_ENFORCE_BACKEND=false
   ```
2. Tell the user (do not do it yourself) to: rotate provider API keys as a precaution and set a random `CSRF_SECRET` in their local `.env`.
**Acceptance Criteria:** `.env.example` contains no secrets and carries the generation instructions.
**Regression Tests:** none (docs-only).
**Do Not Change:** the actual `.env` file contents (user-owned), any settings parsing logic in this task.
**Risk Notes:** none.

## TASK A2 — Dockerfile port (XS-10)
**Objective:** Align EXPOSE with default `SERVER_PORT=8003` (`src/reasoner/core/settings.py:96`).
**Files:** `Dockerfile` (line ~50).
**Required Changes:** `EXPOSE 8000` → `EXPOSE 8003`.
**Acceptance Criteria:** `docker build .` succeeds; grep shows no other hardcoded 8000 for the backend (check `docker-compose.yml`, `docker-entrypoint.sh`, `Caddyfile*` — if they map 8000, align them too and say so in the commit body).
**Do Not Change:** SERVER_PORT default.
**Risk Notes:** if any deployment script assumes 8000, it must be updated in the same commit.

## TASK A3 — LOG_LEVEL wiring (XS-11)
**Objective:** Make the documented `LOG_LEVEL` env var real.
**Files:** `src/reasoner/core/settings.py`, the logging-init site (search for `logging.basicConfig` or logger configuration in `src/reasoner/api/__init__.py` / `logging_utils.py`).
**Required Changes:** Add `LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")` to settings (match the file's existing style — it uses pydantic-settings; follow neighboring field definitions). Apply it where logging is initialized.
**Acceptance Criteria:** Running with `LOG_LEVEL=DEBUG` emits debug logs; default unchanged (INFO).
**Regression Tests:** small settings unit test asserting default and override.
**Do Not Change:** existing log formats/filters (`SafeLoggingFilter`).
**Risk Notes:** none.

## TASK A4/A5 — Workspace cleanup (TD-01)
**Objective:** Stop tracked noise growth; remove dead artifacts.
**Files:** `.gitignore`; deletions at repo root.
**Required Changes:**
1. Append to `.gitignore`: `test_async*.py`, `result_*.json`, `tmp*/`, `.tmp_*/`, `cache/`, `cookies.txt`, `nul`, `server_*.log`, `ui_*.log`, `pytest_full_output*.txt`, `tmp_import_log.txt`.
2. Delete (untracked only): `test_async*.py` (15 files), `result_*.json` (5), `cookies.txt`, `nul`, `tmpkk6lsxts/`, `tmpzlzsurxw/`, `tmpztzw00bg/`, `.tmp_base/`, `.tmp_base2/`, `.tmp_pytest/`.
3. **ASK THE USER before deleting:** `Vane-master/` (36 MB), `Humanizer/`, `legacy/` (the latter two are git-tracked), `-p/`.
**Acceptance Criteria:** `git status` output dramatically smaller; full test suite still green.
**Do Not Change:** anything under `src/`, `tests/`, `ui-next/`, `.claude/`, `graphify-out/` (rebuilt by hooks), `docs/`.
**Risk Notes:** deletion is irreversible for untracked files — verify each against the list above; skip anything not listed.

## TASK B1 — Rate-limiter multi-worker guard (SEC-10)
**Objective:** The memory-mode/multi-worker RuntimeError must fire in every environment.
**Files:** `src/reasoner/api/__init__.py` (lines ~91-106).
**Required Changes:** Remove the `if settings.ENVIRONMENT != "development":` gate around the `raise RuntimeError(...)`; keep the message. Single-worker memory mode stays allowed.
**Acceptance Criteria:** unit test: settings with `UVICORN_WORKERS=2, RATE_LIMITER_MODE="memory", ENVIRONMENT="development"` → app factory raises.
**Regression Tests:** existing app-startup tests must pass (they run single-worker).
**Do Not Change:** the Redis startup probe just below.
**Risk Notes:** any dev who genuinely runs 2 workers locally must switch to Redis — intended.

## TASK B2 — CSRF enforcement in production (SEC-03)
**Objective:** `CSRF_ENFORCE_BACKEND` cannot be false when `ENVIRONMENT=production`.
**Files:** `src/reasoner/core/settings.py` (near the existing CSRF validation at ~lines 219-224).
**Required Changes:** Extend validation: if `ENVIRONMENT == "production"` and not `CSRF_ENFORCE_BACKEND`, raise RuntimeError with a clear message. Keep the existing "secret required when enforcing" check.
**Acceptance Criteria:** settings test for the new combination; CI (which uses `CSRF_ENFORCE_BACKEND=false` and non-production env) unaffected.
**Do Not Change:** the CI behavior documented in CLAUDE.md (`CSRF_ENFORCE_BACKEND=false` in CI envs).

## TASK B3 — Run-state Redis startup validation (XS-04)
**Objective:** Multi-worker deployments must fail fast if run-state Redis is unreachable.
**Files:** `src/reasoner/api/__init__.py` (lifespan/startup probe region, ~116-127), `src/reasoner/infrastructure/redis/run_state.py` (you may add a small `async def ping()` helper).
**Required Changes:** In startup, when `settings.UVICORN_WORKERS > 1`, attempt a run-state Redis operation; on failure raise RuntimeError naming the consequence ("cancellation will not propagate across workers").
**Acceptance Criteria:** integration-style test (mark `integration`) with Redis URL pointing nowhere and workers=2 → startup fails; workers=1 → starts with in-memory fallback as today.
**Do Not Change:** the in-memory fallback behavior for single-worker.
**Risk Notes:** blocks startup by design; gate behind `RUN_STATE_REQUIRE_REDIS` env default `true` only when workers>1.

## TASK B4 — Production config validation (SEC-09, SEC-11)
**Files:** `src/reasoner/api/__init__.py` (~220-224) or `core/settings.py`.
**Required Changes:** In production: raise if `APP_URL` unset/not http(s); log resulting CORS origins at INFO. Log WARNING if `TRUSTED_PROXIES` empty in production.
**Acceptance Criteria:** settings tests for both branches.

## TASK B5 — SearXNG health (XS-05)
**Files:** `docker-compose.yml` (searxng service, ~130-148), `src/reasoner/api/__init__.py` startup.
**Required Changes:** Add compose healthcheck (`curl -f http://localhost:8080/` — verify the container's internal port first by reading the service definition; do not assume 8888 which is the host mapping). Add startup probe: GET `settings.SEARXNG_URL` with 3s timeout; on failure log WARNING ("web search will return empty results") — warn, don't fail.
**Acceptance Criteria:** stack boots with SearXNG stopped, warning logged once.
**Do Not Change:** `search_service.py` exception-to-empty-list behavior in this task (that is request-path resilience; the gap is observability).

## TASK C1 — Pagination stale closure (FE-01)
**Files:** `ui-next/src/hooks/useConversationHistory.ts` (lines ~35-49).
**Required Changes:** Replace `setHistory([...history, ...next.items])` with `setHistory(prev => [...prev, ...next.items])`; remove `history` from the `useCallback` dependency array.
**Acceptance Criteria:** `npx tsc --noEmit` clean; add a vitest test: two sequential `loadMore` calls with mocked pages produce concatenated, duplicate-free history.
**Do Not Change:** the `setPage` functional update (already correct).

## TASK C2 — SSE inactivity watchdog (FE-04)
**Files:** `ui-next/src/lib/sse-reader.ts`.
**Required Changes:** Add optional `timeoutMs = 60000` parameter. Before each `reader.read()`, (re)arm a timer that calls `reader.cancel(new Error('SSE inactivity timeout'))`; clear it after each read. Ensure the error surfaces to callers so `usePipelineStream` sets its error state (check how read errors currently propagate — they should reject the `readSSEStream` promise).
**Acceptance Criteria:** vitest with a mock ReadableStream that never resolves → promise rejects ~timeout; normal streams unaffected.
**Do Not Change:** SSE frame parsing/buffering logic.
**Risk Notes:** long synthesis phases can legitimately pause; backend sends keepalive flushes (`SSE_FLUSH_INTERVAL`) — confirm keepalives arrive as readable bytes (they do; they're comment/empty events) so 60s is safe.

## TASK C3 — Resume abort signal (FE-11)
**Files:** `ui-next/src/app/chat/page.tsx` (handleResume, ~892-966).
**Required Changes:** Create an `AbortController` per resume; pass `signal` as third arg to `readSSEStream`; store the controller in a ref; abort it when a different conversation is selected, on a new submit, and on unmount (mirror the cleanup pattern in `usePipelineStream.ts:30-36`).
**Acceptance Criteria:** type-check clean; manual flow: resume pipeline → switch conversation → no further message updates in the old/new conversation.

## TASK C4 — SSE contract: phase_warning + reason (XS-01, XS-03)
**Files:** `ui-next/src/lib/types.ts` (PhaseEvent, ~27-34), `ui-next/src/app/chat/page.tsx` (onEvent switch, ~511-645).
**Required Changes:** Add `reason?: string` and ensure `warning?: string` is in `PhaseEvent`. Add `case 'phase_warning':` that surfaces `ev.warning` to the user — follow the existing pattern used by `phase_retry` for updating the message (e.g., set a status/notice on the assistant message rather than inventing new UI).
**Acceptance Criteria:** tsc clean; simulate event in a unit test or via mocked stream → warning visible in message state.
**Do Not Change:** backend emit shape (`src/reasoner/api/streaming.py:200-207, 648`).

## TASK C5 — Event-bus task retention (BC-01)
**Files:** `src/reasoner/application/event_bus/bus.py` (line ~206).
**Required Changes:** Add `self._pending_tasks: set[asyncio.Task] = set()` in `__init__`. Replace bare `asyncio.create_task(self._log_to_dead_letter(...))` with create → add to set → `task.add_done_callback(self._pending_tasks.discard)`. In `drain()`/shutdown, `await asyncio.gather(*self._pending_tasks, return_exceptions=True)` with the existing timeout.
**Acceptance Criteria:** new unit test: fill queue to trigger dead-letter path, drain, assert dead-letter file written and no pending tasks.
**Do Not Change:** worker-task creation at line ~114 (already correct).

## TASK C6 — Surface silent pipeline failures (BC-05, BC-06, BC-12)
**Files:** `src/reasoner/application/pipeline.py` (lines ~289-316 enhancement; ~395-396 and ~414-415 translation).
**Required Changes:** In each `except` block, before the fallback assignment: `self._log("<TAG>", f"...: {exc}", state)` and `state.errors.append(f"...: {exc}")`. Tags: `PROMPT-ENHANCE`, `CROSS-LANG`. Keep fallback behavior identical.
**Acceptance Criteria:** unit tests with a raising enhancer/translator: pipeline completes, `state.errors` contains the entry, `enhanced_problem == problem`.
**Do Not Change:** the fallback-to-original semantics (degradation should still be graceful).

## TASK C7 — Parameterize SQL (INF-01, INF-02)
**Files:** `src/reasoner/infrastructure/persistence/event_store.py` (~275-281), `error_store.py` (~153-160).
**Required Changes:**
1. event_store: replace `{', '.join(updates)}` with a static, fully-written `SET col1 = ?, col2 = ?, ...` clause for the fixed field set, binding values positionally. If fields are conditional, build the clause from a hardcoded whitelist mapping only.
2. error_store: `conn.execute("DELETE FROM errors WHERE datetime(timestamp) < datetime('now', ?)", (f"-{days} days",))` — keep `_safe_int` bounds check.
**Acceptance Criteria:** existing store tests green (`tests/test_error_store_sql_safety.py` etc.); add a test asserting retention works with parameterized form.
**Do Not Change:** schema, retention semantics, `_safe_int`.

## TASK C8 — WS manager race + dead code (INF-03, NEW-01)
**Files:** `src/reasoner/infrastructure/websocket/manager.py` (~216-243; check ~112-118).
**Required Changes:** Delete the no-op dead code at lines ~227-230. Restructure `send_to_connection` so the connection-state check and the retrieval of the per-connection send lock happen atomically under `self._lock`, with the actual `send` outside the global lock but inside the per-connection lock. **First**, trace whether `connect()` (~112-118) calls `send_to_connection` while holding `self._lock` (NEW-01): if yes, move that send outside the lock block; if no, note "NEW-01 refuted" in the commit body.
**Acceptance Criteria:** WS tests green; add test: disconnect during send → no exception escapes, failure logged.
**Risk Notes:** most delicate change in Phase C; keep diff minimal, no API changes.

## TASK C9 — httpOnly CSRF cookie (SEC-02)
**Files:** `ui-next/src/app/api/csrf/route.ts` (line 10).
**Required Changes:** **Pre-check first:** grep `ui-next/src` for any code reading the CSRF cookie via `document.cookie` (e.g. in `security-client.ts`). If the client obtains the token only from the JSON body (`{ token }`), flip `httpOnly: false` → `true`. If anything reads the cookie, refactor that reader to use the body/`getToken()` path first, then flip.
**Acceptance Criteria:** CSRF round-trip e2e: fetch `/api/csrf`, POST with `X-CSRF-Token` header → 200; POST without header → 403 (when enforcement on).
**Risk Notes:** breaks any cookie-reading client code — hence the mandatory pre-check.

## TASK C10 — Remove WS query-param token (SEC-07)
**Files:** `src/reasoner/api/routes/websocket.py` (lines ~17-22).
**Required Changes:** **Pre-check:** grep `ui-next/src` for `?token=` / `token=` in WebSocket URL construction. If found, migrate that client to header auth first (note: browsers can't set WS headers — if the frontend relies on query param for browser WS, instead keep the param but switch to a short-lived one-time ticket, and say so in the commit; do NOT silently break the UI). If no client uses it, delete the query-param branch.
**Acceptance Criteria:** WS connection tests pass with header auth.
**Risk Notes:** browser WebSocket API limitation is the reason query tokens exist in many apps — verify before removing.

## TASK C11 — Markdown skipHtml + CSRF refresh error (SEC-15, FE-07)
**Files:** `ui-next/src/components/chat/MarkdownRenderer.tsx`; `ui-next/src/lib/security-client.ts` (~48-62).
**Required Changes:** Add `skipHtml` to the `ReactMarkdown` element (verify no feature depends on inline HTML rendering — check existing snapshots/components for raw HTML usage). In security-client: when CSRF refresh returns null after a CSRF-403, `throw new Error('CSRF token refresh failed — please reload the page')` instead of falling through.
**Acceptance Criteria:** markdown render tests; manual: messages render normally.

## TASK D1 — Event bus hardening (BC-03, BC-07, BC-10)
**Files:** `src/reasoner/application/event_bus/bus.py`.
**Required Changes (three independent commits):**
1. Critical-event put: `asyncio.wait_for(self._task_queue.put(...), timeout=2.0)`; on timeout, log ERROR and dead-letter via the retained-task pattern from C5.
2. `_safe_execute`: do not retry exceptions that are clearly non-transient; classify via the existing `classify_error`/`is_retryable` helpers in `application/flows` if importable without layering violation, else a local tuple of retryable exception types (TimeoutError, ConnectionError).
3. Track in-flight handler tasks in a set; `drain()` gathers them with the existing timeout.
**Acceptance Criteria:** event-bus test suite green; new tests: slow handler doesn't block pipeline >2s; non-retryable error not retried; drain waits for in-flight.
**Do Not Change:** public subscribe/publish API.

## TASK D2 — Redis fallback observability (INF-08)
**Files:** `src/reasoner/infrastructure/redis/run_state.py` (~112-150).
**Required Changes:** Every `except _RedisUnavailable: pass` gets `logger.warning("Run-state Redis unavailable — falling back to in-memory (operation=%s)", op_name)` rate-limited (e.g., once per cooldown window using the existing 5s cooldown state) plus an incrementing module-level counter exposed via a `stats()` function.
**Acceptance Criteria:** test with Redis down: warning emitted once per cooldown, counter increments.

## TASK D3 — Snapshot boundary validation (INF-04)
**Files:** `src/reasoner/infrastructure/persistence/snapshots.py` (~197-240).
**Required Changes:** After loading a snapshot at version V, verify the event store contains an event at version V for that aggregate (or that V==0/initial). If absent, treat snapshot as invalid: log ERROR and fall back to full replay from version 0 rather than raising, unless full replay is impossible (then raise `EventStoreCorruptionError`).
**Acceptance Criteria:** new test: snapshot at V with event V pruned → full replay path taken, correct state; existing snapshot tests green.
**Risk Notes:** flag-gate with `SNAPSHOT_STRICT_BOUNDARY` default true; document in commit.

## TASK D4 — Datetime + header hygiene (XS-02, SEC-12)
**Files:** `src/reasoner/api/sse_utils.py` (~23-26), `src/reasoner/api/error_handler.py` (~193-194).
**Required Changes:** In the SSE `json_serializer`: `if isinstance(obj, datetime): obj = obj if obj.tzinfo else obj.replace(tzinfo=timezone.utc); return obj.isoformat()`. In error handler: filter headers through a `_sanitize_headers` helper redacting `{authorization, cookie, x-api-key, x-csrf-token, x-admin-key}` (case-insensitive).
**Acceptance Criteria:** unit tests for both helpers.

## TASK D5 — Store robustness (INF-05, INF-06, INF-10)
**Files:** `event_store.py`, `token_cache.py`, `telemetry_store.py` under `src/reasoner/infrastructure/`.
**Required Changes (independent commits):** `BEGIN IMMEDIATE` before write transactions in the SQLite event store; prune `_problem_index` entries whose lists become empty on eviction; `json.dumps(..., default=str)` for telemetry `fallback_events` and `phase_results`.
**Acceptance Criteria:** store/cache test suites green; new eviction test asserts index has no stale keys.

## TASK D6 — Widget resilience (FE-09)
**Files:** `ui-next/src/components/widgets/WidgetRenderer.tsx`.
**Required Changes:** Null/shape-check `widget.result` before use; wrap rendering in try/catch (or a small per-widget ErrorBoundary component) returning the existing "Unknown widget" styled div with an error message.
**Acceptance Criteria:** render test: `result: null` calculator widget → fallback div, no crash.

## TASK D7 — Route hardening (SEC-17, XS-06, XS-13)
**Files:** `src/reasoner/api/routes/admin.py`, `src/reasoner/api/schemas.py`.
**Required Changes:** Add the same `check_rate_limit` dependency used by `routes/uploads.py:23` to the compaction route. Widen `FollowupRequest.history` to `list[dict[str, Any]]`; add field validators for `preset` (known preset or empty) and `conversation_id` (length/charset) mirroring `RunRequest` patterns at schemas.py:58-133.
**Acceptance Criteria:** route tests; follow-up request with attachment-bearing history validates.
**Do Not Change:** `build_followup_context` call shape (`streaming.py:839-840`) unless adding attachment extraction — that is optional scope; if done, keep it additive.

## TASKS E1–E5 — Tests
Follow `06_TESTING_GAPS.md` specs exactly. Place backend tests under `tests/`, frontend under existing vitest layout. For E5, add a CI job in `.github/workflows/test.yml` running `-m integration` separately (allowed to be non-blocking initially), and in `self-healing-ci.yml` add `pytest healing/generated_tests/ -v || true` immediately after generation, upgrading to blocking once stable.

---

### Global "Do Not Change" list
- `parsing.extract_json` / `sanitize_for_prompt` contracts.
- `PipelineState` method-state `.get()` access convention (resume compatibility).
- Preset registry contents and model whitelist.
- The CQRS streaming bypass (`CQRS_BYPASS_STREAMING`) — documented intentional.
- Backward-compat shims at `src/reasoner/` root (Phase F only, with deprecation warnings first).
