# 03 — Implementation Plan

Ordered to minimize regression risk: configuration-only changes first, then isolated one-file bug fixes, then behavior-affecting reliability changes, then tests, then refactors. Every task is minimal, incremental, testable, and reversible. Detailed executor instructions are in `04_IMPLEMENTATION_INSTRUCTIONS.md`.

Legend — Complexity: S (<1h) / M (half-day) / L (1–2 days). Regression risk: Low/Med/High.

---

## Phase A — Quick Wins: configuration & hygiene (no code-path behavior change)

| # | Task | Findings | Complexity | Risk | Validation | Rollback |
|---|------|----------|-----------|------|------------|----------|
| A1 | Rotate provider keys (precaution); replace `CSRF_SECRET` with `secrets.token_urlsafe(32)`; add prod-values comment block to `.env.example` | SEC-01R, SEC-13 | S | Low | App boots; CSRF round-trip works | Restore previous values |
| A2 | Dockerfile `EXPOSE 8000` → `EXPOSE 8003` | XS-10 | S | Low | `docker build` succeeds | Revert line |
| A3 | Remove stale `LOG_LEVEL` from `.env.example` **or** wire it: read in `core/settings.py`, apply in logging init | XS-11 | S | Low | Set `LOG_LEVEL=DEBUG`, observe verbosity | Revert |
| A4 | `.gitignore` additions: `test_async*.py`, `result_*.json`, `tmp*/`, `.tmp_*/`, `cache/`, `cookies.txt`, `nul`, `server_*.log`, `pytest_full_output*.txt` | TD-01 | S | Low | `git status` shrinks | Revert .gitignore |
| A5 | Delete dead root artifacts (untracked only, after user confirmation for `Vane-master/` 36 MB): tmp dirs, `test_async*.py` ×15, `result_*.json`, `cookies.txt`, `nul` | TD-01 | S | Low | Test suite still green | N/A (untracked deletions; confirm before deleting anything ambiguous) |

**Rationale:** zero interaction with runtime logic; clears noise so later diffs are reviewable.

## Phase B — Safety guards (config-validation code, fail-fast at startup)

| # | Task | Findings | Complexity | Risk | Validation | Rollback |
|---|------|----------|-----------|------|------------|----------|
| B1 | Rate limiter: raise on `UVICORN_WORKERS>1 && RATE_LIMITER_MODE=="memory"` regardless of `ENVIRONMENT` | SEC-10 | S | Low | Unit test of guard; dev single-worker unaffected | Revert condition |
| B2 | Force `CSRF_ENFORCE_BACKEND=true` when `ENVIRONMENT=production` (settings validator) | SEC-03 | S | Low | Settings unit test | Revert validator |
| B3 | Startup probe: when `UVICORN_WORKERS>1`, verify run-state Redis reachable or fail | XS-04, INF-08 | M | Med (can block startup — intended) | Integration test with Redis down | Feature-flag the probe |
| B4 | Production startup: validate `APP_URL` set/valid; WARNING if `TRUSTED_PROXIES` empty | SEC-09, SEC-11 | S | Low | Settings tests | Revert |
| B5 | SearXNG: compose `healthcheck` + startup probe warning when research enabled | XS-05 | S | Low | compose up with/without SearXNG | Remove healthcheck |

**Dependencies:** none between tasks; B3 after B1 (same file region).

## Phase C — Verified bug fixes (surgical, one file each)

| # | Task | Findings | Complexity | Risk | Validation | Rollback |
|---|------|----------|-----------|------|------------|----------|
| C1 | FE: functional updater in `useConversationHistory.loadMore` | FE-01 | S | Low | New unit test: paginate twice, no dupes/loss | Revert hook |
| C2 | FE: inactivity watchdog in `readSSEStream` (60s default, configurable) | FE-04 | M | Med (timeout tuning) | Unit test with stalled mock stream | Make timeout opt-in |
| C3 | FE: AbortController for `handleResume`; abort on conversation switch | FE-11 | S | Low | Manual: resume → switch → no cross-events | Revert |
| C4 | FE: add `case 'phase_warning'` handler; add `reason?: string` to `PhaseEvent` | XS-01, XS-03 | S | Low | Type-check + UI shows warning on degraded response | Revert |
| C5 | BE: retain dead-letter task refs + done-callback in event bus | BC-01 | S | Low | Unit test: queue-full path logs dead letter | Revert |
| C6 | BE: log + `state.errors.append` in enhancement and translation catch blocks | BC-05, BC-06, BC-12 | S | Low | Unit test: failing enhancer recorded in errors | Revert |
| C7 | BE: parameterize event-store SET clause and error-store retention DELETE | INF-01, INF-02 | S | Low | Existing store tests + new param test | Revert (old code worked) |
| C8 | BE: WS `send_to_connection` — re-check state under lock, delete dead code 227-230; while in file, trace NEW-01 call graph | INF-03, NEW-01 | M | Med | WS integration test; disconnect mid-send | Revert |
| C9 | FE: CSRF cookie `httpOnly: true` (client already consumes token from JSON body) | SEC-02 | S | Med (verify no code reads cookie) | Grep client for cookie reads; CSRF e2e round-trip | Revert flag |
| C10 | BE: remove WS query-param token branch | SEC-07 | S | Med (breaks any client using `?token=`) | Search frontend for `?token=` usage first | Revert |
| C11 | FE: `skipHtml` on ReactMarkdown; throw on failed CSRF refresh | SEC-15, FE-07 | S | Low | Markdown snapshot tests | Revert |

**Order within C:** C1–C6 independent and parallelizable; C7 isolated; C8 last (most delicate); C9/C10 require the noted pre-checks.

## Phase D — Reliability hardening

| # | Task | Findings | Complexity | Risk | Validation | Rollback |
|---|------|----------|-----------|------|------------|----------|
| D1 | Event bus: backpressure timeout for critical events; fail-fast retry classification; in-flight task tracking for `drain()` | BC-03, BC-07, BC-10 | M | Med | Event-bus unit tests incl. slow-handler simulation | Revert per-change |
| D2 | Redis run-state: WARNING on every fallback transition + counter | INF-08 | S | Low | Test with Redis stopped: log appears | Revert |
| D3 | Snapshot load: validate event exists at snapshot version | INF-04 | M | Med (could reject previously "working" replays — intended) | New corruption-detection test | Flag-gate strictness |
| D4 | UTC-coerce naive datetimes in SSE `json_serializer`; redact sensitive headers in error logging | XS-02, SEC-12 | S | Low | Serializer + redaction unit tests | Revert |
| D5 | `BEGIN IMMEDIATE` for SQLite write transactions; token-cache index pruning on evict; `json.dumps(..., default=str)` in telemetry | INF-05, INF-06, INF-10 | M | Med | Store test suite green; long-run cache test | Revert per-change |
| D6 | Widget rendering: validate `widget.result`, per-widget error fallback | FE-09 | S | Low | Render test with malformed widget | Revert |
| D7 | Rate-limit dependency on admin compaction route; widen `FollowupRequest.history` schema + validators | SEC-17, XS-06, XS-13 | S | Low | Route tests | Revert |

## Phase E — Test coverage (see 06 for full specs)

| # | Task | Findings | Complexity | Risk |
|---|------|----------|-----------|------|
| E1 | `tests/test_api_streaming.py` — SSE generator unit tests | TG-01 | L | Low |
| E2 | Router model-selection/fallback tests | TG-02 | M | Low |
| E3 | CSRF comprehensive suite | TG-05 | M | Low |
| E4 | HyperGate sub-agent unit tests | TG-03 | M | Low |
| E5 | CI: separate integration-test job; execute self-healing generated tests | TG-10, TD-05 | M | Low |

## Phase F — Strategic improvements (separate efforts; not quick wins)

1. **Split `api/streaming.py`** (941 lines, 5 stream types) into run/followup/cache/direct/search modules — do **after** E1 lands so the refactor is test-protected.
2. **Extract lifespan** from `api/__init__.py` (789 lines) into `api/lifecycle.py`.
3. **Split `preset_registry.py`** (1987 lines) and **`pipeline_state.py`** (1616 lines) along existing concern boundaries.
4. **SSE contract single source of truth** — generate `PhaseEvent` TS types from backend schema (or a shared JSON-schema) to end drift (root cause behind XS-01/03/06).
5. **Deprecation warnings on the 30 root shims**, then staged removal.
6. **Metrics layer** (counters for WS broadcast failures, Redis fallbacks, dead-letter writes) — root-cause fix for the "silent degradation" theme.
7. **Nonce-based CSP** (SEC-06) — coordinate backend middleware + Next.js; not a surgical change.

---

### Cross-cutting rollback strategy
Each task is a single small commit on a feature branch with conventional-commit message referencing the finding ID (e.g. `fix: retain dead-letter task refs (BC-01)`). Rollback = revert the single commit. Phases B/D changes that can alter startup or replay behavior (B3, D3) should be flag-gated for one release before becoming defaults.

### Validation gate per phase
Run after each phase: `python -m pytest tests/ -v -m "not slow and not integration and not searxng"` and `cd ui-next && npx tsc --noEmit && npm run build`. Phase C9/C10 additionally require a manual CSRF/WS round-trip check against a running stack.
