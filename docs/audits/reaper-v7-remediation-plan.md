# REAPER V7 — REMEDIATION PLAN

**Author:** Claude | **Date:** 2026-07-08
**Basis:** `docs/audits/reaper-v7-verification-2026-07-08.md` (verified findings only)
**Scope:** Fix every *confirmed* and *disputed-but-real* finding, respecting Hexagonal DDD + CQRS + Event Sourcing layering. Disproven items (5.2) excluded. Unverifiable items (5.1, counts) handled as ops tasks.

## Guiding constraints (do not violate)

- **Dependency rule:** `domain → application → core ports → infrastructure → api`. Fixes add adapters behind existing ports (`BillingPort`, `LLMPort`, `SearchServicePort`), never new domain→infra imports.
- **Metrics** go through the existing `reasoner/metrics.py` Prometheus registry (22 metrics already live). Reuse it — no parallel metric system.
- **Events** flow through `application/event_bus/bus.py`; new async work (email, replay) becomes **EventBus subscribers**, not inline calls in request handlers.
- **State-changing HTTP** stays behind `require_csrf` + auth scopes; admin actions require `Scope.ADMIN`.
- **No secrets in code.** Everything via `core/settings.py` (pydantic-settings) + env.
- **Every fix ships with a pytest** under `tests/` using the project's existing markers and `ProviderRouter` mocking patterns (`skill: reasoner-testing`).

---

## PHASE 0 — DEPLOY-BLOCKING (P0). Target: 1 sprint

### 0.1 — Webhook processing failures are silent (7.1) — CONFIRMED

**Root cause:** `infrastructure/billing/webhooks.py:130-153, 205-224` — on `BillingService.handle_webhook` exception, only `logger.exception`, then `return {"status":"ok"}`. Stripe/PayPal mark the event delivered; subscription never syncs. No metric, no dead-letter.

**Architecture-aware fix:**
1. Add Prometheus counters in `metrics.py`:
   `WEBHOOK_PROCESSING_FAILURES = Counter("reasoner_webhook_processing_failures_total", "...", ["provider", "event_type"])`.
2. On the `except` branch (both handlers): `WEBHOOK_PROCESSING_FAILURES.labels(provider, event_type).inc()` **and** persist the raw event to a durable **billing dead-letter** so it can be replayed. Reuse the EventBus dead-letter path conceptually, but billing events must survive process restart → write to a Postgres table `failed_webhook_events(id, provider, event_type, payload JSONB, error, created_at, replayed_at NULL)` via a new `BillingDeadLetterRepository` (infra, behind a port).
3. Keep returning HTTP 200 (correct — prevents Stripe retry storms) **but only after** the failure is durably recorded.
4. Emit a domain event `WebhookProcessingFailed` on the bus so an alert subscriber (Phase 0.5) and future email subscriber can react.

**Files:** `metrics.py`, `infrastructure/billing/webhooks.py`, new `application/ports/billing_deadletter_port.py`, new `infrastructure/persistence/billing_deadletter_repo.py`, migration `add_failed_webhook_events`.
**Tests:** extend `tests/test_saas_stripe_webhooks.py` — force `handle_webhook` to raise, assert counter incremented + row persisted + still 200.
**Effort:** 3 days.

### 0.2 — Account deletion un-wired + FK-crashes (6.1) — CONFIRMED

**Two independent bugs:**

**(a) FK violation.** `saas_router.py:227` `DELETE FROM users` runs *before* `:281` `_log_auth_event` INSERT into `auth_audit_log` (FK → `users(id) ON DELETE CASCADE`). Insert for a deleted user violates FK → 500 after the user is already gone (partial, non-atomic deletion).

Fix — make the whole deletion one transaction and order it correctly:
```python
async with pool.acquire() as conn:
    async with conn.transaction():
        await _log_auth_event_conn(conn, user.id, "account_delete", ip, ua)  # BEFORE delete
        await conn.execute("DELETE FROM users WHERE id = $1", str(user.id))    # CASCADE cleans audit + subs + quotas
```
Because the FK is `ON DELETE CASCADE`, the audit row logged *before* delete is itself cascaded away — which defeats the audit. So: write the audit row to a **separate append-only table with no FK** (`account_deletion_log(user_id, deleted_at, ip, ua)`), or set that one FK to `ON DELETE SET NULL`. Prefer the dedicated no-FK deletion-log table (audit of deletions must outlive the user — GDPR accountability). External side-effects (Stripe cancel, uploads, vectors, redis) happen **after** the DB transaction commits, each already best-effort.

**(b) Frontend never calls backend.** `ui-next/src/app/settings/page.tsx:47-65` only `supabase.auth.signOut()`. Wire it:
```ts
await apiClient.post('/api/account/delete');   // CSRF + auth token attached by api-client
await supabase.auth.signOut();
logout(); router.push('/?deleted=true');
```
Surface real backend errors instead of the generic message.

**Files:** `api/saas_router.py`, new migration (deletion-log table / FK change), `ui-next/src/app/settings/page.tsx`, `ui-next/src/lib/api-client.ts` (confirm CSRF header).
**Tests:** backend integration test asserting single-transaction delete + no FK error + deletion-log row survives; `tests/` for cascade coverage. Frontend: Playwright asserting `POST /api/account/delete` fires.
**Effort:** 1 week (BE + FE + migration).

### 0.3 — Dead-letter queue: no replay, no alerting (7.2) — CONFIRMED

**Root cause:** `event_bus/bus.py:256-276` appends JSONL; nothing observes or replays it.

**Architecture-aware fix:**
1. **Metric:** add `DEAD_LETTER_EVENTS = Counter("reasoner_dead_letter_events_total", "...", ["event_type","critical"])`; increment inside `_log_to_dead_letter`. Also expose current file line-count as a gauge scraped lazily.
2. **Replay:** new admin-scoped route `POST /api/admin/dead-letter/replay` (requires `Scope.ADMIN`) → `EventBusReplayService` (application layer) that reads the JSONL, re-publishes each event through `bus.publish`, and on success moves the line to a `.replayed` sidecar (idempotent, at-least-once). Add `GET /api/admin/dead-letter` for inspection with pagination.
3. **Bounded growth:** rotate the JSONL (size cap + timestamped archive) so it can't grow without bound.
4. **Optional background drain:** a periodic task (see 1.7 scheduler) that retries replay for non-critical events.

**Files:** `metrics.py`, `event_bus/bus.py`, new `application/services/deadletter_replay_service.py`, new `api/routes/admin_deadletter.py`, route mount in `api/__init__.py`.
**Tests:** publish → force handler failure → assert dead-letter written + counter; call replay → assert re-published + sidecar moved.
**Effort:** 2 days.

### 0.4 — httpx connection leak via Resilient wrappers (10.1) — CONFIRMED

**Root cause:** `neuro/providers.py:137,191` — `ResilientReasoning`/`ResilientEmbedding` own `self.primary` + `self.fallbacks` (each lazily opens `httpx.AsyncClient`) but expose no `aclose()`; children are never closed.

**Fix (minimal, matches existing pattern — children already have `aclose`):**
```python
class ResilientReasoning:
    async def aclose(self):
        await self.primary.aclose()
        for fb in self.fallbacks:
            await fb.aclose()
```
Same for `ResilientEmbedding`. Then ensure the owner closes them: trace who constructs these via `create_resilient_*` and call `aclose()` on shutdown. Consolidate with `close_neuro_client()` (`api/execution/pipeline.py:594`, `api/__init__.py:254`) so shutdown closes the wrapper chain, not just the top client. **Do not** close per-run (that's P10.5, the opposite anti-pattern) — close on app shutdown / lifespan exit only; keep the shared pool alive across runs.

**Files:** `neuro/providers.py`, `reasoner/clients.py` (`close_neuro_client`), `api/__init__.py` lifespan.
**Tests:** construct wrapper, call `aclose`, assert `primary._client.is_closed` and each fallback closed.
**Effort:** 2 days (incl. tracing ownership + a leak-regression test that counts open clients).

### 0.5 — No production alerting (3.1) — CONFIRMED

**Root cause:** `docs/monitoring/alerts-reference.yml` is reference-only; no Prometheus/Alertmanager in compose.

**Fix (DevOps, infra-as-code):**
1. Add `prometheus` + `alertmanager` services to a new `docker-compose.observability.yml` (keep base compose lean); scrape the existing `/metrics` endpoint (respect `METRICS_ALLOWED_IPS`).
2. Promote `alerts-reference.yml` → active rules; wire Alertmanager routing (PagerDuty/Slack via env-provided webhook, no secret in file).
3. Alert set must cover the newly-added metrics: webhook failures (0.1), dead-letter rate (0.3), memory (`reasoner_memory_usage_mb` — add per 7.5), DB pool utilization (2.10), error-rate.
4. Add a cron **heartbeat** metric so a silent cron is detectable.

**Files:** new `docker-compose.observability.yml`, `docs/monitoring/prometheus.yml`, `docs/monitoring/alertmanager.yml`, promote alert rules.
**Effort:** 1 week. **This is the single highest-leverage change** — it's what makes every other P0 *detectable*.

### 0.6 — Pipeline dedup across workers (8.1 reclassified → 8.2 class)

Not a within-process TOCTOU (verified). Real gap: 8 workers each hold a private `_run_store`, so `try_register` can't dedup cross-process. Fix belongs with 8.2 (Phase 1.5): back run-registration with the same Redis `SET NX` already used for webhook idempotency (`get_redis().set(key, nx=True, ex=ttl)`), with the in-memory store as per-process fast-path. Add an `asyncio.Lock` around `try_register` for defense-in-depth even though single-loop is currently safe. **Downgrade from P0 to P1.**

---

## PHASE 1 — HIGH (P1). Target: 2 sprints

### 1.1 — PayPal client timeout (1.2, disputed→real) 
httpx default is 5s (not infinite), so no outage — but set explicit, sensible values. `paypal_adapter.py:39,76,196`: `httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))`. **1h.**

### 1.2 — DirectProvider SDK timeouts (1.3) — CONFIRMED
`providers/direct.py:35,75,115`: pass `timeout=` to `AsyncAnthropic`/`AsyncOpenAI`/`genai` clients, sourced from `TIMEOUTS` constants so fallback calls respect the pipeline budget and don't outlive `asyncio.wait_for`. **2h.**

### 1.3 — Postgres `NOW()` → UTC (1.1) — CONFIRMED
`quota_repo_postgres.py:117,127-128`: `NOW()` → `(NOW() AT TIME ZONE 'UTC')` and `date_trunc('month', NOW() AT TIME ZONE 'UTC')`. Audit every quota/cron query. Add a test pinning a non-UTC session `SET TIME ZONE` and asserting month boundary. **1 day.**

### 1.4 — Synchronous `print()` in StructuredLogger (3.2/10.4) — CONFIRMED
`core/logging_utils.py:254`: replace `print(...)` with a non-blocking sink. Prefer a `logging.QueueHandler` + `QueueListener` (stdlib, offloads I/O to a background thread) over ad-hoc `asyncio.to_thread` per call — cleaner and framework-idiomatic. Keep `SafeLoggingFilter`. **1 day.**

### 1.5 — Rate limiter / run-dedup split-brain (8.2 + 0.6) — CONFIRMED mismatch
Reconcile defaults: `settings.py:125` (`redis`) vs `.env.example` (`memory`). In production (`ENV=production` + workers>1) **fail fast** if mode is `memory`. Back `try_register` with Redis `SET NX` (0.6). Add jitter/lock. **2 days.**

### 1.6 — EventBus retry jitter (7.3) — CONFIRMED (one-liner)
`event_bus/bus.py:232`: `wait = min(2 ** attempt, 8) + random.uniform(0, 1.0)`. Prevents thundering herd. **30 min.**

### 1.7 — Neuro lifecycle actually runs (6.3) — CONFIRMED dead code
`neuro/sessions.py:316,389` (`archive_hot_sessions`/`archive_warm_to_cold`) have zero callers. Introduce a scheduler (reuse `api/cron.py` pattern or an EventBus periodic task) that invokes them on a cadence with a Prometheus heartbeat. Also implement the neuro-session-clearing stub referenced in 6.1/6.2 for GDPR erasure. **2 days.**

### 1.8 — TenantManager unbounded (10.2) — CONFIRMED
`neuro/server.py:126`: add LRU + TTL eviction (cap `active_tenants`, evict idle agents, `aclose` their L1/L2/sessions on eviction). Reuse the `_evict_stale_locked` pattern already in `RunStateStore`. **1 day.**

### 1.9 — Cost anomaly / spend caps (3.3) — verify-then-build
`CostTrackingState` tracks per-phase cost. Add a per-user cumulative spend gauge + a preflight cap check in the orchestrator (before Phase 2 fan-out), emitting `SpendCapExceeded` on the bus. **3 days.**

### 1.10 — simpleeval license (9.1) — CONFIRMED present
Confirm `simpleeval` license terms; if unacceptable, swap to `asteval` (BSD) behind the same evaluation call-site (it's isolated — likely PoT / widget eval). Pin in `requirements.lock`. **1 day.**

---

## PHASE 2 — MEDIUM (P2). Target: ongoing

- **2.1 run-followup idempotency (2.1):** apply the same `client_run_id` + Redis `SET NX` registration used by `/api/run` to `/api/run-followup`. *(Verify current handler first.)* **2 days.**
- **2.2 SSE disconnect detection (2.2):** in `api/streaming.py` producer, poll `request.is_disconnected()` / catch `GeneratorExit` to cancel the pipeline task and stop LLM spend. Tie into `RunStateStore.request_cancel`. **3 days.**
- **2.3 `extra="forbid"` on API models (5.8):** add to the 13 `api/schemas.py` models lacking it; validate `ExecuteWidgetRequest.params`. **2h.**
- **2.4 Auth error uniformity (5.7):** route `require_api_key` through the same generic wrapper as `require_auth`; constant-time primary key lookup (5.6). **1h.**
- **2.5 Migration atomicity (6.4, disputed):** low priority — Alembic already wraps in a transaction. If any migration sets autocommit, wrap explicitly; otherwise document that DDL is transactional and close. **Verify then likely no-op.**
- **2.6 `str(e)` leakage (4.1):** route billing/health/SSE/pipeline error bodies through `_safe_json_response()`; never emit raw exception text (DB URLs leak from asyncpg). **1 day.**
- **2.7 PHASE_DURATION observe (3.5):** call `.observe()` in the phase lifecycle wrapper so latency SLOs work. **1h.**
- **2.8 token_cache zombie index (10.3):** `token_cache.py:265` — on overwrite, remove the old key from `_problem_index[old.problem_hash]` before re-appending. **2h.**
- **2.9 DB pool gauge + acquire timeout (7.4):** export pool utilization; add `timeout=` on `acquire()`; app-level circuit breaker reusing `infrastructure/circuit_breaker.py`. **1 day.**
- **2.10 Memory gauge (7.5):** `MemoryLimitMiddleware` already computes RSS — export it as `reasoner_memory_usage_mb`. **1h.**
- **2.11 Pagination bounds (10.6/10.7/10.8/10.10):** cap `limit` on `/api/uploads`, `/api/pipelines`, `/api/history*`; stream/paginate instead of loading all JSON. **1 day.**
- **2.12 SearXNG fallback (2.4):** on empty/failed SearXNG, chain to Perplexity/Tavily and mark the result degraded (do not silently return `[]`). Behind `SearchServicePort`. **2 days.**
- **2.13 Caddyfile.prod (8.4):** create `docker-compose.prod.yml` referencing `Caddyfile.prod` (HSTS/CSP/security headers). **1 day.**
- **2.14 Transactional email (7.6):** integrate Resend/Postmark/SES as an EventBus subscriber reacting to `WebhookProcessingFailed`, `SpendCapExceeded`, payment-failed, password-changed. **1 week.**
- **2.15 npm registry (9.2/9.3):** switch `ui-next` off npmmirror.com to npmjs.org so `npm audit` works; sync `requirements.lock`; add a CI lock-freshness check. **2 days.**

---

## PHASE 3 — LOW (P3). Docs & hardening

- **3.1** Consolidate the 4 overlapping KB files; fix version drift (4.2).
- **3.2** Write ADRs for Hexagonal DDD, HyperGate, cross-lab routing, Neuro (4.3).
- **3.3** Fix REASONIX.md stale `pyproject.toml` claim (10 min).
- **3.4** OpenRouter SPOF (9.4): document, and enable direct-adapter fallbacks for non-Big-3 providers where keys exist, so an OpenRouter outage doesn't strand Qwen/Mistral/Perplexity.

---

## CROSS-CUTTING / SEQUENCING

```
Week 1:  0.5 (alerting infra) ──┐  parallel  0.1 webhook, 0.3 dead-letter, 0.4 httpx
Week 2:  0.2 account deletion (BE+FE+migration)
Week 3:  Phase 1 quick wins (1.1–1.6, 1.8) — mostly hours/days each
Week 4+: 1.7, 1.9, 2.x rolling
```

**Do 0.5 first** — every other P0 fix adds a metric that is only useful once Prometheus/Alertmanager scrape and route it.

## DEFINITION OF DONE (per fix)

- [ ] Root cause fixed at the correct layer (no domain→infra leakage).
- [ ] pytest added, uses existing markers + `ProviderRouter` mocks; suite green.
- [ ] New metric registered in `metrics.py` and covered by an alert rule where relevant.
- [ ] No secret in code; new config via `settings.py` + `.env.example`.
- [ ] `security-reviewer` pass for anything touching auth/billing/deletion.
- [ ] Frontend changes verified via Playwright + preview.
- [ ] import-linter contract still within the 58/65 exception budget.

## ITEMS TO VERIFY BEFORE IMPLEMENTING (not independently confirmed in verification pass)

2.1, 2.2, 2.5, 2.9, 3.3, 4.x, 5.3–5.6, 6.2/6.5, 7.4/7.6, 8.3, 9.3/9.4, 10.5/10.9 — trace the cited code first; none were contradicted, but confirm before writing the fix.
