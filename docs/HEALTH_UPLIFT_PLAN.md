# Reasoner Health Uplift Plan — 6/10 → 9+/10

**Created:** 2026-06-12
**Baseline:** Forensic audit in `audit/01–06` (six reports, second-pass verified). Current overall health: **6/10**.
**Goal:** ≥ 9/10, measured against the dimension rubric below — not vibes. Every dimension has objective exit criteria; the program is done when all gates pass, not when the work "feels" done.
**Prime directive:** Respect the existing architecture (Hexagonal DDD + CQRS + Event Sourcing + ports/adapters). This is a hardening and consolidation program, **not** a rewrite. Strangler-pattern splits along existing seams only; no framework migrations; no speculative abstractions (YAGNI); every change minimal, testable, reversible.

---

## 1. Scoring Rubric — where the 3 points come from

| Dimension | Weight | Today | Target | Gap drivers (audit IDs) |
|---|---|---|---|---|
| D1 Security posture | 20% | 6 | 9 | SEC-01R/02/03/07/10/12/13/17, CSP |
| D2 Reliability & failure visibility | 20% | 5 | 9 | INF-04/08, BC-01/03/05/06/12, XS-04/05/09 |
| D3 Correctness (verified bugs) | 15% | 6 | 10 | FE-01/04/11, XS-01/03, INF-03, BC-19 |
| D4 Test coverage & CI rigor | 15% | 5 | 9 | TG-01…TG-10, TD-05, frontend 50% threshold |
| D5 Contract integrity (BE↔FE) | 10% | 5 | 9 | XS-01/02/03/06, no SSE source of truth |
| D6 Maintainability & code health | 10% | 5 | 9 | TD-01…TD-04, monoliths, 30 shims |
| D7 Deployment & operability | 10% | 6 | 9 | SEC-10, XS-04/10/11, multi-worker story |

Weighted today: ~5.6 (rounded to 6). Weighted at targets: **9.15**.

**Scoring is re-run at each milestone** (Section 7) by re-executing the verification commands in each dimension's exit criteria. A dimension scores its target only when *every* exit criterion passes.

---

## 2. Architectural Ground Rules (apply to every task)

1. **Dependency rule is law.** Domain → nothing; Application → Domain/Core; Infrastructure implements Core ports; API → Application. Any new module lands in the layer its dependencies allow. New cross-layer needs go through a Core port, never a direct import.
2. **The two documented violations stay documented, not multiplied.** `CQRS_BYPASS_STREAMING` and `flows/__init__ → api.serializers` are tracked exceptions. Workstream W6 removes the second; the first is re-evaluated (not silently extended) after streaming is modularized.
3. **State invariants preserved:** method-state via `dict.get()` (resume compatibility); all LLM JSON through `parsing.extract_json()`; all user text through `sanitize_for_prompt()`; cross-lab fallback routing semantics unchanged.
4. **Immutability bias:** new code returns new objects; existing mutation hot-spots get a single narrow mutation API rather than scattered writes (see W2.4).
5. **Fail loud, degrade gracefully:** every fallback path must (a) keep serving, (b) log WARNING once per cooldown, (c) increment a counter, (d) where user-relevant, append to `state.errors`. Silence is a defect.
6. **File budget:** no new file > 800 lines; functions < 50 lines; splits happen along existing concern boundaries already identified in `audit/05`.
7. **One task = one conventional commit** referencing the finding/task ID; feature branches; revert = rollback.

---

## 3. Workstreams

### W1 — Security Hardening → D1: 9/10
*Builds on audit Phases A/B/C (tasks A1, B1, B2, B4, C9, C10, C11, D4, D7).*

| # | Action | Practice applied |
|---|--------|------------------|
| W1.1 | Rotate all provider keys; random `CSRF_SECRET` (`secrets.token_urlsafe(32)`); `.env.example` documents prod-required values with generation commands | Secret hygiene; least-privilege keys |
| W1.2 | Settings-level production validators: `CSRF_ENFORCE_BACKEND` forced true, `APP_URL` required/valid, memory-rate-limiter + multi-worker rejected in **all** environments, `TRUSTED_PROXIES` warning | Fail-fast configuration; 12-factor |
| W1.3 | `httpOnly: true` CSRF cookie (token already delivered in JSON body — pre-check client cookie reads first) | Defense-in-depth vs XSS |
| W1.4 | WS auth: replace query-param token with short-lived one-time ticket endpoint (browser WS cannot set headers — do **not** just delete the param; mint ticket via authenticated POST, accept ticket once, expire in 30s) | Token non-exposure without breaking browser clients |
| W1.5 | Redact `authorization/cookie/x-api-key/x-csrf-token/x-admin-key` in error logging; rate-limit admin compaction route | Log hygiene; uniform endpoint protection |
| W1.6 | Nonce-based CSP replacing `'unsafe-inline'` (backend middleware generates nonce; Next.js consumes). Land last in W1 — coordinated change | CSP as real XSS mitigation |
| W1.7 | Add `gitleaks` (or `detect-secrets`) as pre-commit hook + CI job; add `pip-audit` + `npm audit --audit-level=high` to CI | Shift-left secret/dependency scanning |
| W1.8 | `skipHtml` on ReactMarkdown; widget payload validation (FE-09) | Output encoding at the render boundary |

**Exit criteria (D1 = 9):** all SEC findings in `audit/02` closed or explicitly risk-accepted in an ADR; gitleaks + pip-audit + npm audit green in CI; CSP has no `unsafe-inline` for scripts; CSRF e2e round-trip test passes with enforcement on; a fresh secret-scan of the repo and of `.env.example` finds nothing.

### W2 — Reliability & Failure Visibility → D2: 9/10
*Builds on audit Phases C5/C6/D1–D5; adds the metrics layer the audit identified as the root cause of the "silent degradation" theme.*

| # | Action | Practice applied |
|---|--------|------------------|
| W2.1 | **Minimal metrics module** `core/metrics.py`: process-local counters + gauges behind a tiny port (`MetricsPort`) so Infrastructure can later swap in Prometheus without touching callers. Counters: `redis_runstate_fallbacks`, `ws_broadcast_failures`, `dead_letter_writes`, `enhancement_failures`, `translation_failures`, `search_empty_fallbacks`, `rate_limiter_fallbacks`, `llm_cascade_fallbacks` | Hexagonal: metrics as a port; observability-first |
| W2.2 | Event bus hardening: retained dead-letter tasks (BC-01), 2s backpressure timeout for critical events (BC-03), fail-fast on non-transient errors (BC-07), in-flight tracking in `drain()` (BC-10), lock around subscription mutation (BC-02) | Structured concurrency; bounded queues |
| W2.3 | Loud fallbacks: Redis run-state WARNING+counter per transition (INF-08); SearXNG startup probe + compose healthcheck (XS-05); `state.errors` appends in enhancement/translation catches (BC-05/06/12) | Fail loud, degrade gracefully |
| W2.4 | `PipelineState.record_llm_usage(role, cost, tokens)` — single mutation method consolidating `total_cost_usd`/`phase_costs`/token accumulation (BC-09); runner asserts sequential-phase invariant (BC-04) | Narrow mutation API; explicit invariants |
| W2.5 | Snapshot boundary validation with full-replay fallback (INF-04); `BEGIN IMMEDIATE` SQLite writes (INF-05); telemetry `default=str` (INF-10); token-cache index pruning (INF-06); true-LRU or documented-FIFO registry eviction (INF-09) | Data-integrity-first persistence |
| W2.6 | WS manager: state check atomically under lock, dead code removed, NEW-01 call-graph resolved (INF-03) | TOCTOU elimination |
| W2.7 | `/health` reports component status: event store, Redis (rate-limit + run-state), Postgres, SearXNG, with `degraded` vs `down` semantics | Deep health checks |

**Exit criteria (D2 = 9):** zero bare `except: pass` on infrastructure fallback paths (`grep` gate in CI); every fallback has a counter and a test asserting it increments; `/health` exercised in an integration test with each optional dep down; chaos test "Redis dies mid-run" passes (run completes, fallback counted, warning logged once per cooldown).

### W3 — Verified Bug Elimination → D3: 10/10
*Exactly audit Phase C — all second-pass-verified bugs.*

FE-01 functional updater; FE-04 SSE inactivity watchdog (60s, keepalive-aware); FE-11 resume AbortController; XS-01 `phase_warning` handler; XS-03 `reason` typed; FE-05 explicit IndexedDB transactions; FE-07 CSRF-refresh failure surfaces; FE-03 blob-URL lifecycle cleanup; BC-19 debate-rebuttal guard; XS-07 `connecting` on cached replay; XS-02 UTC-coercing serializer.

**Each fix ships with the regression test that would have caught it** (test-first where feasible: write the failing test, then the fix — RED/GREEN).

**Exit criteria (D3 = 10):** every active CRITICAL/HIGH correctness finding in `audit/02` closed with a named regression test; `audit/02` register updated with closure commit hashes; no new HIGH correctness findings in the M3 re-audit (Section 7).

### W4 — Testing & CI Rigor → D4: 9/10
*Audit Phase E + `audit/06` in full, plus ratchets.*

| # | Action | Practice applied |
|---|--------|------------------|
| W4.1 | `tests/test_api_streaming.py` — the 941-line hot path gets first-class tests (error mid-stream, cache replay parity, concurrent followup isolation, disconnect cleanup, `phase_warning` emission) | Test the riskiest code first |
| W4.2 | Router suite: fallback order, cross-lab preference, same-model edge (INF-07) | Pin the routing philosophy in tests |
| W4.3 | CSRF comprehensive suite (formats, boundaries, tamper, cross-format) | Security boundaries get exhaustive tests |
| W4.4 | HyperGate sub-agent unit tests incl. fast-path regex ordering | Determinism pinned |
| W4.5 | Persistence: auth_store revocation/concurrency, telemetry serialization, feedback durability | AAA pattern, isolation |
| W4.6 | Frontend: hook tests for `useConversationHistory`/`usePipelineStream`/`readSSEStream`; component tests for `WidgetRenderer`/`MarkdownRenderer`/onEvent reducer; raise vitest threshold 50→70 (ratchet +5/sprint, never down) | Coverage ratchet, not big-bang |
| W4.7 | E2E (Playwright): core chat flow, stream-interruption, conversation-switch-during-stream/resume, CSRF round-trip. Deterministic waits only; flaky tests quarantined within 24h or deleted | Few, reliable E2E > many flaky |
| W4.8 | CI restructure: (a) integration job with Redis/Postgres services running `-m integration` (non-blocking 2 sprints, then blocking); (b) self-healing generated tests executed post-generation (`pytest healing/generated_tests/`), non-blocking → blocking; (c) backend coverage gate ratchet 60→70→75 (fail) as suites land; (d) `npx tsc --noEmit` + `npm run build` as PR gates if not already | CI is the contract; ratchets prevent regression |
| W4.9 | **Fix `.gitignore` ignoring `tests/` and `test*.py`** — new test files are currently invisible to git. Remove both lines; audit for orphaned untracked tests and add them | Eliminate silent test loss |

**Exit criteria (D4 = 9):** backend coverage ≥ 75% enforced (80% warn); frontend ≥ 70% enforced; integration job blocking and green; zero quarantined-forever tests; streaming/router/CSRF/HyperGate each have dedicated suites; `.gitignore` no longer ignores tests.

### W5 — Contract Integrity (BE↔FE) → D5: 9/10
*Root-cause fix for the XS-01/03/06 class, per `audit/05` recommendation #2.*

| # | Action |
|---|--------|
| W5.1 | Define every SSE event as a Pydantic model in `api/schemas.py` (many exist piecemeal); a discriminated union `SSEEvent` becomes the single backend source of truth. Emitters in `streaming.py`/`serializers.py` construct models, not ad-hoc dicts (incremental: one event type per commit) |
| W5.2 | Generate `ui-next/src/lib/types.generated.ts` from the Pydantic union (script in `scripts/`, e.g. via `pydantic-to-typescript` or a small JSON-schema→TS step); hand-written `types.ts` re-exports from it during migration |
| W5.3 | CI drift gate: regenerate + `git diff --exit-code` fails the build on contract drift |
| W5.4 | Contract conformance test: mocked full pipeline run captures every emitted `type`; assert set ⊆ frontend handled-or-explicitly-ignored set (explicit `IGNORED_EVENTS` list in frontend so ignoring is a decision, not an accident) |
| W5.5 | Close current drift: `FollowupRequest.history` widened + validators (XS-06/13); datetime policy = tz-aware UTC ISO-8601 everywhere (XS-02), documented in the schema module docstring |

**Exit criteria (D5 = 9):** generated types in use; drift gate active; conformance test green; zero unhandled-and-unlisted event types.

### W6 — Maintainability & Code Health → D6: 9/10
*Audit Phase F, strictly test-then-split (refactor only what W4 has protected).*

| # | Action | Seam used |
|---|--------|-----------|
| W6.1 | Split `api/streaming.py` (941) → `api/streams/{run,followup,cached,direct,search}.py` + shared `api/streams/common.py` | The five generator functions are already independent |
| W6.2 | Extract lifespan from `api/__init__.py` (789) → `api/lifecycle.py` with a `LifecycleManager` of ordered, individually-testable startup/shutdown steps; `__init__.py` becomes thin factory + mounting (< 300 lines) | Startup steps are already sequential blocks |
| W6.3 | Split `preset_registry.py` (1987): data (preset configs) vs behavior (tier enforcement → `domain/tiering.py`, pricing lookup → `domain/pricing.py`); registry keeps lookup only | Concern boundaries named in audit |
| W6.4 | Split `pipeline_state.py` (1616): state dataclasses vs serialization (`domain/state_serde.py`) vs cost/token accounting (consumes W2.4 API) | Already grouped within the file |
| W6.5 | Shim retirement: `warnings.warn(DeprecationWarning)` in all 30 root shims now; codemod internal imports to real paths (mechanical, one commit per package); delete shims at M5 | Strangler pattern with a deadline |
| W6.6 | Remove the `flows/__init__ → api.serializers` violation: move the needed serialization helper behind a Core port or into Application | Dependency rule restoration |
| W6.7 | Workspace hygiene completion: remove the six admin-locked tmp dirs (elevated prompt); review remaining root scripts (`check_*.py`, `find_*.py`, `patch_*.py`, `build_chunk_07.py`, stray `.md`/`.json`/`.txt` artifacts) → keep in `scripts/`, or delete; resolve TODO(#501/#502) tier-lookup cluster or convert to tracked issues | Clean workspace = reviewable diffs |
| W6.8 | Enforcement: `ruff` (already cached → configured?) + line-budget lint (fail on new files > 800 lines), `mypy` scope expansion beyond `auth_legacy`, pre-commit config (`ruff`, `gitleaks`, `eslint`/`prettier` for ui-next) | Automated style/size enforcement |

**Exit criteria (D6 = 9):** no source file > 1,000 lines (target 800 for new); `api/__init__.py` < 300; shims deleted or warning for one full release; documented violations reduced to one (streaming bypass) with an ADR; pre-commit active; `git status` clean on a fresh clone + bootstrap.

### W7 — Deployment & Operability → D7: 9/10

| # | Action |
|---|--------|
| W7.1 | **Decide the multi-worker story explicitly (ADR-001):** Option A "single-worker product" → enforce `UVICORN_WORKERS=1`, simplify; Option B "multi-worker supported" → Redis + Postgres hard-required above 1 worker (startup probes from audit B1/B3), shared upload storage plan. The audit's recommendation: Option B gates, since the code is 80% there |
| W7.2 | Dockerfile `EXPOSE 8003`; `LOG_LEVEL` wired into settings + logging init; compose healthchecks for all services (SearXNG added) |
| W7.3 | Structured logging: JSON log option for production (`LOG_FORMAT=json`), correlation/run IDs already exist — propagate consistently |
| W7.4 | Graceful-shutdown verification: SIGTERM → in-flight SSE streams get terminal event, event bus drains (uses W2.2), stores flush; integration test |
| W7.5 | `DEPLOY.md` refreshed against reality (ports, required env per environment, multi-worker requirements); generated env-var reference table from `settings.py` so docs can't drift |
| W7.6 | Postgres event-store path exercised in CI (it exists but SQLite dominates) — one integration suite runs against Postgres |

**Exit criteria (D7 = 9):** ADR-001 merged; misconfigured deployments fail at startup with actionable messages (tested); graceful-shutdown test green; deploy docs generated/verified; both store backends CI-tested.

### W8 — Institutionalization (keeps the score ≥ 9)

1. **ADRs** (`docs/adr/NNN-*.md`) for: multi-worker story, CQRS streaming bypass disposition, SSE contract governance, shim retirement, snapshot strictness. Lightweight template; decisions become reviewable artifacts.
2. **PR checklist** (CONTRIBUTING.md): new SSE event ⇒ schema model + handler-or-ignore entry; new fallback ⇒ counter + warning + test; new env var ⇒ settings + `.env.example` + docs table; security-sensitive change ⇒ security review.
3. **Ratchets in CI:** coverage thresholds only move up; file-size budget; contract drift gate; secret scan; dependency audit. The gates are the institution — they outlive attention spans.
4. **Quarterly mini-audit:** re-run the `audit/02` register against the codebase (a half-day with the same parallel-subagent method); update health score in this file's log (Section 8).

---

## 4. Sequencing & Dependencies

```
M1 (week 1):   W1.1-W1.3, W1.5, W1.7-W1.8 │ W7.2 │ W4.9 │ W2.2-W2.3 (loud fallbacks)
M2 (weeks 2-3): W3 (all bug fixes, test-first) │ W1.4 (WS ticket) │ W2.1 (metrics port) │ W4.1-W4.3
M3 (weeks 4-5): W2.4-W2.7 │ W4.4-W4.6, W4.8 │ W5.1-W5.5 │ W7.1 (ADR-001) + W7.3-W7.4
M4 (weeks 6-8): W6.1-W6.4 (test-protected splits) │ W4.7 (E2E) │ W7.5-W7.6 │ W1.6 (CSP nonce)
M5 (weeks 9-10): W6.5-W6.8 (shims, violation, enforcement) │ W8 │ full re-audit & re-score
```

Hard dependencies: W6.1 **after** W4.1 (never refactor untested streaming); W6.3/6.4 after their suites; W5.2 after W5.1; W1.6 after frontend stabilizes (M4); blocking-integration-CI after two green non-blocking sprints.

Parallelizable: W1 ∥ W2 ∥ W3 mostly touch disjoint files — suitable for parallel agents/devs, one finding-ID branch each.

## 5. Risk Register for the Program Itself

| Risk | Mitigation |
|---|---|
| Refactors (W6) introduce regressions | Test-then-split ordering is mandatory; splits are move-only commits (no logic change in the same commit); coverage gates already raised by then |
| Startup-validation changes (W1.2/W7.1) break existing dev setups | Validators keyed on `ENVIRONMENT=production` except the multi-worker/memory-limiter rule (unsafe everywhere); clear error messages name the env var to fix |
| SSE codegen (W5.2) tooling friction on Windows | Keep the generator a plain Python script in `scripts/` with zero exotic deps; commit generated output so the build never depends on generation |
| WS ticket auth (W1.4) breaks clients | Dual-accept (ticket + legacy param) for one release with deprecation warning header, then remove |
| Snapshot strictness (W2.5) rejects existing data | Fallback-to-full-replay default (not hard error); `SNAPSHOT_STRICT_BOUNDARY` flag |
| Program stalls mid-way, leaving half-migrations | Every milestone leaves the repo releasable; shims/dual-accepts have explicit removal milestones written here |

## 6. Effort Estimate

| Milestone | Scope | Estimate |
|---|---|---|
| M1 | Security/config quick wins + loud fallbacks | ~1 dev-week |
| M2 | Bug elimination + critical test suites | ~2 dev-weeks |
| M3 | Reliability hardening + contract governance | ~2 dev-weeks |
| M4 | Refactors + E2E + CSP | ~3 dev-weeks |
| M5 | Debt retirement + institutionalization + re-audit | ~2 dev-weeks |
| **Total** | | **~10 dev-weeks** (highly parallelizable to ~5–6 calendar weeks with agent assistance) |

## 7. Milestone Gates & Re-scoring

At each milestone, run the gate battery; a milestone is complete only when its battery is green:

- **G-test:** `python -m pytest tests/ -v -m "not slow and not searxng"` (integration included from M3) + `cd ui-next && npx tsc --noEmit && npm run build && npx vitest run --coverage`
- **G-sec:** gitleaks scan, `pip-audit`, `npm audit --audit-level=high`, CSRF e2e, grep-gate for `except.*pass` on fallback paths
- **G-contract:** type regeneration diff-clean + conformance test
- **G-ops (M3+):** chaos checks — Redis down, SearXNG down, SIGTERM mid-stream
- **G-score:** re-evaluate Section 1 rubric; update Section 8 log

Expected trajectory: M1 → 6.8 · M2 → 7.6 · M3 → 8.4 · M4 → 8.9 · M5 → **9.2**.

## 8. Score Log

| Date | Event | Score |
|---|---|---|
| 2026-06-12 | Baseline forensic audit (`audit/01–06`) | 6.0 |
| — | M1 gate | — |
| — | M2 gate | — |
| — | M3 gate | — |
| — | M4 gate | — |
| — | M5 gate + full re-audit | target ≥ 9.0 |

---

*Companion documents: `audit/02_FINDINGS_REGISTER.md` (finding details/evidence), `audit/04_IMPLEMENTATION_INSTRUCTIONS.md` (per-task executor instructions for Phases A–E referenced by W1–W4), `audit/05_ARCHITECTURE_REVIEW.md` (rationale for W5–W7 directions).*
