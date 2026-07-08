# ARCHITECTURAL REAPER V7 — DEEP AUDIT REPORT
## System: Reasoner v2.2 | Audience: Tech Lead | Date: 2026-07-08

---

## EXECUTIVE SUMMARY

### Top 5 Critical Findings (P0)

| # | Finding | Blast Radius |
|---|---------|-------------|
| **1** | **8 P0s total — Ship Decision: NOT READY** | See below |
| **2** | **Stripe/PayPal webhook failures silently swallowed** — billing events lost with 200 OK; paying users stuck on FREE tier | Billing → Revenue → User trust |
| **3** | **Account deletion is broken** — frontend never calls backend; audit trail violates FK; GDPR non-compliance | Auth → Data → Legal |
| **4** | **Dead letter queue has zero replay/alerting** — 313 real events permanently lost including pipeline completions | EventBus → Audit trail → Analytics |
| **5** | **httpx connection pool leak** — `ResilientReasoning`/`ResilientEmbedding` wrappers never call `aclose()`; file-descriptor exhaustion over time | Neuro → All LLM/embedding calls → Process crash |

### Single Point of Failure
**OpenRouter** — 85% of 130+ models route exclusively through it. Fallback covers only Anthropic → OpenAI → Google. If OpenRouter is down, Qwen, Mistral, Perplexity, NVIDIA, and dozens of other providers become completely unreachable despite having direct API keys configured.

### First 3AM Alert Prediction
**Stripe webhook processing failure** — a checkout.session.completed event fails due to missing `reasoner_user_id` metadata, returns HTTP 200 to Stripe, never alerts, charging a customer who stays on FREE tier. Discovered days later via support ticket.

### One Change → Maximum Reliability
**Deploy Prometheus + Alertmanager with the 5 alert rules already written in `docs/monitoring/alerts-reference.yml`.** This single change would surface P0-level failures (webhook errors, pool exhaustion, dead-letter accumulation, memory pressure, error rate spikes) that currently go completely undetected.

---

## SEVERITY SUMMARY

| Part | P0 | P1 | P2 | P3 | Confidence Avg |
|------|----|----|----|-----|---------------|
| 1. Temporal Compatibility | 0 | 2 | 2 | 0 | HIGH |
| 2. Design Decisions | 0 | 2 | 3 | 1 | HIGH |
| 3. Observability & Cost | 1 | 3 | 1 | 0 | HIGH |
| 4. Human Factors | 0 | 0 | 2 | 2 | HIGH |
| 5. Security | 2 | 3 | 3 | 0 | HIGH |
| 6. Data Management | 1 | 3 | 1 | 0 | HIGH |
| 7. Failure Handling | 2 | 2 | 2 | 0 | HIGH |
| 8. Concurrency & State | 1 | 1 | 2 | 0 | HIGH |
| 9. Dependencies | 0 | 1 | 3 | 0 | HIGH |
| 10. Performance | 1 | 2 | 1 | 0 | HIGH |
| **TOTAL** | **8** | **19** | **20** | **3** | **HIGH** |

---

## INPUT DECLARATION

| Evidence | Available | Details |
|----------|-----------|---------|
| Source code | ✅ Full | `src/reasoner/` (backend), `ui-next/src/` (frontend), `tests/` |
| Architecture diagrams | ✅ | `ARCHITECTURE_MINDMAP.md`, `docs/`, `graphify-out/` |
| CI/CD config | ✅ | `.github/workflows/self-healing-ci.yml` |
| Dependency manifests | ✅ | `requirements.txt`, `ui-next/package.json` |
| Logs / metrics | ⚠️ Partial | `logs/` directory, `api/metrics.py`, but no live production logs |
| README / docs | ✅ | `AGENTS.md`, `CLAUDE.md`, `REASONIX.md`, `docs/` |
| Docker / deployment | ✅ | `Dockerfile`, `docker-compose.yml`, `Caddyfile`, `nginx.conf` |
| Interview with developer | ❌ | [ΔΕΔΟΜΕΝΟ ΕΛΛΙΠΕΣ] — no developer interview available |
| Live runtime data | ❌ | [ΔΕΔΟΜΕΝΟ ΕΛΛΙΠΕΣ] — no production metrics, crash dumps, or live logs |

---

## PRE-ANALYSIS: ΜΕΤΑ-ΕΛΕΓΧΟΙ

### 1. Ανάστροφη αιτιότητα (Reverse causality)
The project's `_ensure_fresh_preset_service()` deletes and reimports modules on the first pipeline run. This could be the *cause* of subtle bugs (stale imports, broken references) rather than a symptom of bad module design. Similarly, the known architectural violations (domain importing infrastructure) may be effects of rapid iteration, not root design flaws.

### 2. Επιβεβαιωτική προκατάληψη (Confirmation bias)
Actively looked for evidence that security controls *don't* work (CSRF bypass vectors, rate limiter bypasses in multi-worker mode), not just confirmed they exist. Searched for missing validation paths.

### 3. Άγνοια άγνοιας (Unknown unknowns)
- Cannot observe production traffic patterns — real-world load may surface concurrency bugs invisible in code review
- Third-party LLM provider behavior at scale is opaque
- Actual Redis/Postgres performance under load unknown
- SearXNG reliability in production unknown

### 4. Survivorship bias
Bugs that haven't manifested yet: the `QueryTimer` ImportError handler in `api/__init__.py` suggests SSE streaming has already degraded gracefully — but what other silently-swallowed errors exist? The `try/except ImportError` pattern is used elsewhere — what's being silently skipped?

### 5. Blast Radius Map
```
OpenRouter API ──────────┐ [P9.4: 85% models SPOF]
Anthropic/OpenAI/Google ─┤ [P1.3: no fallback timeouts]
                         ↓
                   ProviderRouter ──→ PipelineOrchestrator ──→ SSE Stream ──→ Next.js ──→ User
                         │                    │                      │
                         │              [P2.2: no disconnect detect]  │
                         │              [P2.1: no idempotency]       │
                         ↓                    ↓                      ↓
                   CircuitBreaker        EventBus ──────────→ Neuro LTM [P10.1: conn leak]
                   [P8.2: multi-worker]     │                 [P10.2: unbounded dict]
                         │              [P7.2: dead letter]
                         │              [P7.1: non-critical drop]
                         ↓                    ↓
                   RateLimiter          EventStore (SQLite)
                   [P8.2: split-brain]     │
                         │              [P7.2: no replay]
                   Redis (optional) ────┤
                   [P8.1: non-atomic]    │
                         │              ↓
                   Stripe/PayPal ──→ Billing [P7.1: silent webhook loss]
                   Supabase ───────→ Auth [P6.1: broken account deletion]
                   SearXNG ────────→ Search [P2.4: silent empty results]
                   Postgres ───────→ DB [P6.4: migration atomicity]
                                      [P7.4: pool exhaustion]
                                      [P1.1: timezone mismatch]
```

---

## PART 1: TEMPORAL COMPATIBILITY

| # | Finding | Location | Failure Scenario | Severity | Confidence |
|---|---------|----------|-----------------|----------|------------|
| 1.1 | PostgreSQL `NOW()` vs Python `datetime.now(timezone.utc)` — timezone mismatch in quota month boundaries | `api/cron.py:17-19`, `quota_repo_postgres.py:117,127`, `quota_service.py:52-54` | Non-UTC PostgreSQL server causes quota resets at wrong wall-clock time; users prematurely blocked or granted extra month | **P1** | HIGH |
| 1.2 | PayPal `httpx.AsyncClient()` created without timeout — indefinite hang | `infrastructure/billing/paypal_adapter.py:39,76,196` | PayPal API unresponsive → async task blocks indefinitely, exhausts worker pool, cascades to full API outage | **P1** | HIGH |
| 1.3 | DirectProvider fallback SDK clients without explicit timeout | `infrastructure/llm/providers/direct.py:35,75,115` | During fallback from OpenRouter, SDK calls hang beyond pipeline timeout, immune to `asyncio.wait_for` | **P2** | MEDIUM |
| 1.4 | Month-boundary auto-reset non-atomic — lost increments at rollover | `application/services/quota_service.py:49-57` | Three concurrent requests at month rollover can interleave reset+increment, silently losing usage counts | **P2** | MEDIUM |

---

## PART 2: DESIGN DECISIONS

| # | Operation | Decision | Documented | Risk if Violated | Severity | Confidence |
|---|-----------|----------|------------|-----------------|----------|------------|
| 2.1 | `POST /api/run-followup` idempotency | No idempotency check — unlike `/api/run` which atomically registers `client_run_id` | No | Duplicate LLM calls, double-billing, duplicate pipeline state | **P1** | HIGH |
| 2.2 | SSE client disconnect mid-stream | Producer task continues running after disconnect; only wall-clock timeout stops it | No | Wasted LLM tokens/cost for abandoned runs; resource theft in multi-tenant | **P1** | HIGH |
| 2.3 | EventBus non-critical event delivery | `put_nowait()` silently drops on queue full with only log warning; no dead-letter replay | Partially | Lost persistence events, Langfuse telemetry, audit gaps | **P2** | HIGH |
| 2.4 | SearXNG failure → silent empty results | Returns `[]` with no Perplexity→Tavily→Brave chain; no degraded-signal notification | No | Silent accuracy degradation; users get lower-quality answers without knowing | **P2** | HIGH |
| 2.5 | No database-level rate limiting | Gateway-level RL exists but zero DB connection-throttling or query-rate cap | No | One abusive client saturates DB pool, starving all other requests | **P2** | MEDIUM |
| 2.6 | In-memory rate limiter in multi-worker | Documented per-process state problem; `RATE_LIMITER_MODE` defaults to `memory` with production crash guard | Yes | Misconfiguration causes either crash (denial of service) or bypassable limits | **P3** | MEDIUM |

---

## PART 3: OBSERVABILITY & COST

| # | Pillar | Current State | Gap | Impact | Severity | Confidence |
|---|--------|--------------|-----|--------|----------|------------|
| 3.1 | Alerting | 5 Prometheus alert rules in `docs/monitoring/alerts-reference.yml` (reference-only) | No Prometheus/Alertmanager deployed; no notification routing; cron has no heartbeat | All production incidents undetected until user reports | **P0** | HIGH |
| 3.2 | Logs | `StructuredLogger._log()` uses synchronous `print()` + stdlib `logging` | No `asyncio.to_thread` wrapping; blocks event loop on every log call | Degraded SSE streaming responsiveness under load | **P1** | HIGH |
| 3.3 | Cost | `CostTrackingState` tracks per-phase cost; `query_log` persists | No cost spike alerting; no per-user spend cap; no anomaly detection | Runaway pipeline silently burns hundreds of dollars | **P1** | HIGH |
| 3.4 | Tracing | Sentry + Langfuse use independent trace IDs; SSE events lack `correlation_id` | No W3C/OTel bridge; frontend cannot correlate to backend traces | Manual cross-system stitching for every incident | **P1** | HIGH |
| 3.5 | Metrics | 22 Prometheus technical metrics; `PHASE_DURATION` histogram defined | `PHASE_DURATION` never `.observe()`d; zero business KPIs (revenue, retention, conversion) | No per-phase latency SLOs; blind on product health | **P2** | HIGH |

---

## PART 4: HUMAN FACTORS

| # | Area | Gap | Impact | Severity | Confidence |
|---|------|-----|--------|----------|------------|
| 4.1 | Error Messages | `str(e)` leaked in public health endpoint, billing, SSE streams, pipeline responses — bypasses `_safe_json_response()` | Credentials exposure (DB URL in asyncpg errors), infrastructure topology leak | **P2** | HIGH |
| 4.2 | Documentation | 4 overlapping knowledge-base files with version drift (v2.1/v2.2 vs v2.3); REASONIX.md claims "no pyproject.toml" but it exists | Maintenance burden, contradictory version info, stale warnings mislead debugging | **P3** | HIGH |
| 4.3 | ADRs | Zero Architecture Decision Records — `docs/decisions/` contains only a bug RCA and constants file | Design rationale for hexagonal DDD+CQRS, HyperGate, cross-lab routing undocumented | **P3** | HIGH |
| 4.4 | Knowledge Concentration | Bus factor = 1 on core pipeline (SSE streaming, HyperGate, 31 prompt modules); no onboarding guide; time-to-first-commit ~2-4 weeks | Project blocked if lead developer leaves | **P2** | HIGH |

---

## PART 5: SECURITY

| # | Finding | STRIDE | Attack Vector | Current Control | Gap | Severity | Confidence |
|---|---------|--------|--------------|----------------|-----|----------|------------|
| 5.1 | Real API keys in `.env` — 20+ live keys in plaintext | Info Disclosure | Container compromise, backup leak, screenshot exposes all credentials | `.gitignore` excludes `.env` | No secret manager; no key rotation; Supabase `SERVICE_ROLE_KEY` exposed | **P0** | HIGH |
| 5.2 | Weak CSRF secret — `reasoner-csrf-secret-2026` | Tampering | Attacker discovers guessable secret → forges valid CSRF tokens | HMAC-signed with `compare_digest` | Secret is human-readable string, not `secrets.token_urlsafe(32)` | **P0** | HIGH |
| 5.3 | Admin API key empty — admin endpoints dead code | Elevation of Privilege | No legitimate admin access; `Scope.ADMIN` never assigned by any auth adapter | `compare_digest` guard | Admin endpoints effectively non-functional | **P1** | HIGH |
| 5.4 | Legacy pipelines without owner are world-accessible (IDOR) | Info Disclosure | User A reads/resumes/deletes User B's legacy pipelines | Ownership check with `owner is None` fallback | `pipeline_owners.json` cap of 50K → oldest entries evicted, reverting to ownerless | **P1** | HIGH |
| 5.5 | Default PostgreSQL credentials in `.env.example` | Elevation of Privilege | `postgres:postgres` well-known defaults | Docker Compose TLS | Empty password in actual `.env` | **P1** | HIGH |
| 5.6 | Timing side-channel in API key auth | Info Disclosure | OrderedDict LRU `get` timing varies with dict size | Admin key uses `compare_digest` | Primary stored-key lookup not constant-time | **P2** | MEDIUM |
| 5.7 | Error message discrimination in auth | Info Disclosure | Four distinct error messages enable key enumeration | `require_auth` wraps generically | `require_api_key` returns raw "Invalid API key" | **P2** | MEDIUM |
| 5.8 | Mass assignment — 13/16 Pydantic models lack `extra="forbid"` | Tampering | Unknown fields silently accepted; `ExecuteWidgetRequest.params` is unvalidated `dict[str, Any]` | 3 models explicitly forbid | 13 models allow extra; no validation on widget params | **P2** | HIGH |

---

## PART 6: DATA MANAGEMENT

| # | Area | Current Behavior | Risk | Severity | Confidence |
|---|------|-----------------|------|----------|------------|
| 6.1 | Cascading Deletes | Account deletion: audit FK violation on `auth_audit_log`, `pipeline_owners.json` never cleaned (wrong key), frontend only calls `supabase.auth.signOut()` — never calls backend | GDPR non-compliance; user believes account deleted but all DB rows survive; audit trail broken | **P0** | HIGH |
| 6.2 | Soft vs Hard Deletes | Entire system uses physical `DELETE FROM` — zero `is_deleted`/`deleted_at` fields; GDPR erasure skips neuro sessions (comment-only stub) | Accidental deletion permanent; no undo/grace period; erasure receipt misleading | **P1** | HIGH |
| 6.3 | Data Retention | Neuro `archive_hot_sessions()`/`archive_warm_to_cold()` implement tiered lifecycle but are **never called** — zero callers in entire codebase | Disk exhaustion from unbounded user conversation storage; GDPR storage limitation violation | **P1** | HIGH |
| 6.4 | Migration Safety | DDL statements auto-commit individually in PostgreSQL; `20260501` migration has 4 auto-committed statements without explicit transaction | Mid-migration failure leaves DB in inconsistent state Alembic cannot auto-recover; CI runs `alembic check \|\| true` | **P1** | HIGH |
| 6.5 | Cascading Deletes | Stripe/PayPal cancel failure during deletion → billing continues; webhook re-upsert blocked by FK cascade | User charged after "deleting" account; no dead-letter, no alert, no recovery | **P2** | HIGH |

---

## PART 7: FAILURE HANDLING

| # | Scenario | Trigger | Detection | Behavior | Worst-Case Impact | Mitigation | Severity | Confidence |
|---|---------|---------|-----------|----------|-----------------|-----------|----------|------------|
| 7.1 | Stripe/PayPal webhook silently swallowed | Exception in `BillingService.handle_webhook()` | `logger.exception()` only; no metric; no alert | HTTP 200 returned; Stripe marks delivered; subscription never updated | Paying customer stuck on FREE tier; cancellation not processed; financial reconciliation impossible | Add Prometheus counter + dead-letter + PagerDuty alert | **P0** | HIGH |
| 7.2 | Dead letter queue has zero replay/alerting | Any persistent handler failure after 4 retries | No Prometheus metric; no alert; no dashboard | Event permanently lost in JSONL file (313 real entries already, incl. pipeline completions) | Audit trail gaps; incomplete analytics; disk growth from unbounded file | Add `dead_letter_count` gauge + admin replay endpoint + periodic background replay | **P0** | HIGH |
| 7.3 | Event bus retries lack jitter | Multiple handlers fail simultaneously (e.g., DB down) | None — deterministic schedule | All handlers retry at 1s, 2s, 4s, 8s in lockstep | Thundering herd on recovery; prolonged outage | Add `random.uniform(0, 1.0)` jitter — one-line fix | **P1** | HIGH |
| 7.4 | DB connection pool exhaustion | All 20 connections in use; `acquire()` blocks indefinitely | `PoolTimeoutError` from asyncpg; no app-level circuit breaker | All DB-dependent endpoints hang → 500 | Complete application outage | Add pool utilization gauge + circuit breaker + `timeout` on `acquire()` | **P1** | HIGH |
| 7.5 | Memory exhaustion no alerting | Process approaches 4096 MB limit | `MemoryLimitMiddleware` returns 503; no metric exported | All requests get 503 until K8s health probe restarts pod | Silent outage extended by orchestrator probe delays | Export `reasoner_memory_usage_mb` Prometheus gauge + alerts | **P2** | HIGH |
| 7.6 | No email notification infrastructure | Subscription payment fails, password changed, quota exceeded | None — no email library, SMTP config, or template system | Users receive no proactive notifications | Eroded trust; increased support burden; Stripe sends only its own emails | Integrate transactional email (Resend/Postmark/SES) + EventBus subscriber | **P2** | HIGH |

---

## PART 8: CONCURRENCY & DISTRIBUTED STATE

| # | Finding | Location | Failure Scenario | Severity | Confidence |
|---|---------|----------|-----------------|----------|------------|
| 8.1 | Non-atomic `try_register` — duplicate pipeline execution under Redis failure | `infrastructure/redis/in_memory.py:39-45` | Redis `SET NX` fails → in-memory fallback does `if run_id not in self._runs` + `self._runs[run_id] = now` — two non-atomic ops; concurrent runs create duplicate pipelines | **P0** | HIGH |
| 8.2 | Per-worker in-memory state split-brain with 8 workers | `docker-compose.yml:67` (8 workers), `.env.example:137` (`RATE_LIMITER_MODE=memory`), `settings.py:125` (`RATE_LIMITER_MODE` defaults to `"redis"`) | `.env.example` and `settings.py` default to different modes; multi-worker with in-memory limiter → per-worker isolated rate buckets, customer bypasses by hitting different workers | **P1** | HIGH |
| 8.3 | Quota check–increment TOCTOU gap | `application/services/quota_service.py:33-77` | Two requests hit `check()` simultaneously with 1 remaining quota slot → both pass → both execute pipelines → second `increment()` sees 0 and rejects, but tokens already spent | **P2** | HIGH |
| 8.4 | Production Caddyfile orphaned | `docker-compose.yml:29` mounts dev `Caddyfile`; `Caddyfile.prod` exists but never referenced | Production deployments lack HSTS, CSP, X-Frame-Options, Let's Encrypt auto-HTTPS; dev Caddyfile has bare `:80` listener | **P2** | HIGH |

---

## PART 9: DEPENDENCIES & SUPPLY CHAIN

| # | Dependency | Version | License | CVE | Maintenance | Blast Radius | Severity | Confidence |
|---|-----------|---------|---------|-----|------------|-------------|----------|------------|
| 9.1 | `simpleeval` | 0.9.13 | **None** (proprietary by default) | N/A | Active | All deployments — direct dependency in MIT project | **P1** | HIGH |
| 9.2 | npm registry | — | — | `npm audit` broken (404 from npmmirror.com) | N/A | Every `npm ci`/`npm install` — no CVE scanning; single registry point of failure | **P2** | HIGH |
| 9.3 | `requirements.lock` | — | — | 3 missing deps, 1 unmet npm dep, 5 extraneous npm deps | N/A | Reproducible builds broken; Docker builds resolve untested versions | **P2** | HIGH |
| 9.4 | OpenRouter | — | — | 85% of 130+ models route exclusively through it | Active | If OpenRouter down → Qwen, Mistral, Perplexity, NVIDIA, Nous, Tencent, ByteDance, Morph all unreachable | **P2** | HIGH |

---

## PART 10: HIDDEN PERFORMANCE ISSUES

| # | Problem | Location | Mechanism | Impact | Severity | Confidence |
|---|---------|----------|-----------|--------|----------|------------|
| 10.1 | httpx connection pool leak via Resilient wrappers | `neuro/providers.py:137,191` | `ResilientReasoning`/`ResilientEmbedding` hold child providers but have no `aclose()` — children's `httpx.AsyncClient` never closed | File-descriptor exhaustion; port exhaustion; remote API rate-limiting from stale connections | **P0** | HIGH |
| 10.2 | Unbounded `TenantManager` dict — permanent memory leak | `neuro/server.py:126-151` | Every new `agent_id` permanently allocates `L1Cache` + `L2Index` + `SessionManager` — no eviction, TTL, or cap | Monotonic memory growth; OOM under multi-tenant workload | **P1** | HIGH |
| 10.3 | `TokenAwareCache._problem_index` zombie entry leak | `infrastructure/token_cache.py:259-265` | Overwriting cache key appends to index without removing old entry; eviction only removes first occurrence | Index grows with dead references; inflates memory; slows eviction | **P1** | HIGH |
| 10.4 | Synchronous `print()` in `StructuredLogger` | `core/logging_utils.py:254` | `print(entry.to_json(), file=sys.stdout)` blocks event loop on every log call | Increased P99 latency under load; event-loop starvation with slow log consumer | **P2** | MEDIUM |

### Additional Notable Issues (Not in Top 4 for Part 10)

| # | Problem | Location | Severity |
|---|---|---|---|
| 10.5 | Per-run pool close defeats shared httpx pool — `close_neuro_client()` after every pipeline run | `api/execution/pipeline.py:592-597` | P2 |
| 10.6 | `GET /api/uploads` has no pagination — returns all user files | `api/routes/uploads.py:75-81` | P2 |
| 10.7 | `GET /api/pipelines` has no `limit` upper bound — client can request `limit=999999` | `api/routes/pipelines.py:51` | P3 |
| 10.8 | `_list_history` reads all JSON files into memory before slicing | `api/history.py:34-47` | P2 |
| 10.9 | Triple JSON serialization per phase — for SSE, WebSocket, and event store | `api/execution/pipeline.py:440-490` + `api/sse_utils.py:28` | P3 |
| 10.10 | `GET /api/history/tagged` filters in-memory after full retrieval | `api/routes/history.py:46-48` | P3 |

---

## SHIP DECISION: **NOT READY**

**Rationale:** 8 P0 findings exist — including billing webhook loss, broken account deletion, dead-letter events permanently lost, production alerting completely absent, CSRF secret guessable, API keys in plaintext, duplicate pipeline execution under Redis failure, and httpx connection pool leak causing process crashes.

---

## PRIORITIZED ACTION LIST

| Priority | Action | Owner | ETA | Blocks Deploy | Blast Radius |
|----------|--------|-------|-----|---------------|-------------|
| **P0-1** | Deploy Prometheus + Alertmanager with `alerts-reference.yml` rules | DevOps | 1 week | **Yes** | All subsystems |
| **P0-2** | Fix Stripe/PayPal webhook: add dead-letter write + Prometheus counter + PagerDuty alert on failure | Backend | 3 days | **Yes** | Billing → Revenue |
| **P0-3** | Fix account deletion: wire frontend to backend, fix FK audit violation, add neuro session clearing | Backend + Frontend | 1 week | **Yes** | Auth → Data → Legal |
| **P0-4** | Add dead-letter replay endpoint + `dead_letter_count` Prometheus gauge | Backend | 2 days | **Yes** | EventBus → Audit |
| **P0-5** | Rotate CSRF secret to `secrets.token_urlsafe(32)`; audit all `.env` keys | DevOps | 1 day | **Yes** | All state-changing endpoints |
| **P0-6** | Add `aclose()` to `ResilientReasoning`/`ResilientEmbedding`; add connection pool metrics | Backend | 2 days | **Yes** | Neuro → All LLM calls |
| **P0-7** | Make `InMemoryRunStateStore.try_register()` atomic (add `threading.Lock`) | Backend | 1 day | **Yes** | Pipeline deduplication |
| **P1-1** | Add idempotency to `POST /api/run-followup` via `client_run_id` | Backend | 2 days | No | Pipeline runs |
| **P1-2** | Add client-disconnect detection to SSE `run_task()` | Backend | 3 days | No | LLM cost |
| **P1-3** | Add `asyncio.to_thread()` wrapping to `StructuredLogger._log()` | Backend | 1 day | No | Event loop latency |
| **P1-4** | Fix PostgreSQL `NOW()` → `NOW() AT TIME ZONE 'UTC'` in all quota queries | Backend | 1 day | No | Billing accuracy |
| **P1-5** | Add `timeout=httpx.Timeout(30.0)` to all PayPal `AsyncClient()` calls | Backend | 1 hour | No | Billing availability |
| **P1-6** | Add soft-delete infrastructure (`is_deleted`/`deleted_at`) to user/pipeline models | Backend | 1 week | No | Data recovery |
| **P1-7** | Schedule `archive_hot_sessions()`/`archive_warm_to_cold()` as cron tasks | Backend | 2 days | No | Disk usage / GDPR |
| **P1-8** | Add `simpleeval` license or replace with `asteval` (BSD) | Backend | 1 day | No | Legal |
| **P1-9** | Add explicit timeouts to DirectProvider SDK clients (Anthropic, OpenAI, Google) | Backend | 2 hours | No | Pipeline timeout reliability |
| **P1-10** | Add cost anomaly detection + per-user spend caps | Backend | 3 days | No | Cost control |
| **P1-11** | Implement W3C TraceContext propagation across Sentry/Langfuse/SSE | Backend | 3 days | No | Incident debugging |
| **P1-12** | Wire `Caddyfile.prod` into docker-compose or create `docker-compose.prod.yml` | DevOps | 1 day | No | Production security headers |
| **P1-13** | Fix migration atomicity — wrap multi-statement DDL in explicit transactions | Backend | 2 days | No | DB consistency |
| **P2-1** | Add jitter to EventBus retry backoff | Backend | 30 min | No | Recovery time |
| **P2-2** | Add `extra="forbid"` to all 13 Pydantic API models | Backend | 2 hours | No | Input validation |
| **P2-3** | Wrap generic error messages in auth endpoints (unify `require_auth`/`require_api_key` wrapping) | Backend | 1 hour | No | Info disclosure |
| **P2-4** | Switch npm registry from npmmirror.com to npmjs.org | Frontend | 30 min | No | CVE scanning + build reliability |
| **P2-5** | Sync `requirements.lock` and `node_modules`; add CI check for lock freshness | DevOps | 2 days | No | Reproducible builds |
| **P2-6** | Observe `PHASE_DURATION` histogram in phase lifecycle | Backend | 1 hour | No | Phase latency SLOs |
| **P2-7** | Add pagination bounds to all list endpoints | Backend | 1 day | No | Resource exhaustion |
| **P2-8** | Add SearXNG fallback to Perplexity/Tavily/Brave chain on failure | Backend | 2 days | No | Search reliability |
| **P2-9** | Fix `TokenAwareCache._problem_index` zombie entry leak | Backend | 2 hours | No | Memory |
| **P2-10** | Add DB pool utilization gauge + `timeout` on `acquire()` calls | Backend | 1 day | No | DB resilience |
| **P2-11** | Integrate transactional email provider (Resend/Postmark/SES) | Backend | 1 week | No | User communication |
| **P3-1** | Consolidate 4 knowledge-base files (CLAUDE.md, AGENTS.md, knowledge.md, README.md) | Docs | 1 week | No | Maintenance burden |
| **P3-2** | Write ADRs for key architectural decisions (Hexagonal DDD, HyperGate, cross-lab routing, Neuro) | Docs | 1 week | No | Design rationale preservation |
| **P3-3** | Fix REASONIX.md stale claim about pyproject.toml | Docs | 10 min | No | Developer confusion |

---

## UNCERTAINTY REGISTER

### Top 3 Claims Most Likely to Be Wrong
1. **P10.1 httpx connection leak severity** — May already be mitigated if `ReasoningProvider.aclose()` is called somewhere I missed; needs runtime validation with `lsof` on a long-running process.
2. **P2.2 SSE disconnect waste** — The actual cost impact depends on how often users disconnect mid-pipeline; without production metrics, this could be negligible or massive.
3. **P8.3 Quota TOCTOU** — The window is extremely narrow (microseconds) and requires ≥3 concurrent requests at month boundary; may never occur in practice at current scale.

### Requires Runtime Validation (Static Analysis Insufficient)
- Actual memory growth rate of `TenantManager` under multi-tenant load
- Real-world frequency of SSE client disconnects
- PostgreSQL timezone setting in production deployment
- npm registry npmmirror.com availability from CI environment

### Requires Additional Context to Assess
- [ΔΕΔΟΜΕΝΟ ΕΛΛΙΠΕΣ] Production traffic patterns — concurrency level, user count, pipeline frequency
- [ΔΕΔΟΜΕΝΟ ΕΛΛΙΠΕΣ] Deployment environment — K8s? Bare metal? Cloud provider?
- [ΔΕΔΟΜΕΝΟ ΕΛΛΙΠΕΣ] Existing monitoring infrastructure — is there any external monitoring not in the repo?
- [ΔΕΔΟΜΕΝΟ ΕΛΛΙΠΕΣ] Developer interview — are there known-but-undocumented issues?

### [ΕΙΚΑΣΙΑ] Items Needing Confirmation
- DirectProvider SDK internal timeout defaults (assumed 60-600s but not verified against SDK source)
- Whether `Caddyfile.prod` is deployed via external automation not visible in the repo
- Whether the `.env` with real keys is a development-only copy or matches production

---

## WHAT IS WORKING WELL

Despite the findings, several areas show strong engineering:

- **Circuit breaker**: Excellent implementation with in-memory + Redis backends, atomic Lua scripts, half-open probing, Prometheus metrics, and per-worker fallback caching
- **LLM retry**: Exponential backoff with jitter, retryability classification by exception type, dual-layer retry prevention via `single_attempt=True` on fallback paths
- **Webhook idempotency**: Two-phase DB+Redis deduplication with atomic `SET NX` claims and 24-hour TTL
- **Memory limit middleware**: Monitors RSS and rejects requests with HTTP 503 before OOM
- **Event bus backpressure**: Critical events use blocking `put`, non-critical are dropped with logging and dead-letter, bounded concurrency via `Semaphore(200)`
- **SafeLoggingFilter**: Redacts API keys, tokens, passwords, and connection strings from ALL log output
- **22 Prometheus metrics**: Cover queries, latency, quality scores, circuit breakers, rate limiting, cache hit rates, WebSocket connections, and Postgres/Redis pools
- **Hexagonal architecture**: Clean `BillingPort`, `LLMPort`, `SearchServicePort` abstractions enabling provider swaps
- **Cost tracking**: Per-phase breakdown, `query_log` persistence, pre-flight estimates, aggregate scorecard, cache savings counter

---

## JSON SUMMARY

```json
{
  "audit_type": "beyond-the-obvious-v7",
  "system_name": "Reasoner v2.2",
  "audit_date": "2026-07-08",
  "scope": "all",
  "audience": "Tech Lead",
  "input_available": ["source_code", "docs", "ci_cd", "dependency_manifests", "docker_configs", "logs_partial"],
  "total_findings": {
    "P0": 8, "P1": 19, "P2": 20, "P3": 3
  },
  "by_category": {
    "temporal": {"P0": 0, "P1": 2, "P2": 2, "P3": 0, "confidence_avg": "HIGH"},
    "design_decisions": {"P0": 0, "P1": 2, "P2": 3, "P3": 1, "confidence_avg": "HIGH"},
    "observability_cost": {"P0": 1, "P1": 3, "P2": 1, "P3": 0, "confidence_avg": "HIGH"},
    "human_factors": {"P0": 0, "P1": 0, "P2": 2, "P3": 2, "confidence_avg": "HIGH"},
    "security": {"P0": 2, "P1": 3, "P2": 3, "P3": 0, "confidence_avg": "HIGH"},
    "data_management": {"P0": 1, "P1": 3, "P2": 1, "P3": 0, "confidence_avg": "HIGH"},
    "failure_handling": {"P0": 2, "P1": 2, "P2": 2, "P3": 0, "confidence_avg": "HIGH"},
    "concurrency_state": {"P0": 1, "P1": 1, "P2": 2, "P3": 0, "confidence_avg": "HIGH"},
    "dependencies": {"P0": 0, "P1": 1, "P2": 3, "P3": 0, "confidence_avg": "HIGH"},
    "performance": {"P0": 1, "P1": 2, "P2": 1, "P3": 0, "confidence_avg": "HIGH"}
  },
  "ship_decision": "NOT READY",
  "blocking_items": [
    "No production alerting (Prometheus/Alertmanager not deployed)",
    "Stripe/PayPal webhook failures silently swallowed",
    "Account deletion broken (frontend never calls backend, FK audit violation)",
    "Dead letter queue has zero replay or alerting",
    "CSRF secret is guessable plaintext",
    "httpx connection pool leak via Resilient wrappers",
    "Non-atomic pipeline run deduplication",
    "20+ API keys stored in plaintext .env"
  ],
  "top_risk": "Silent billing webhook loss → paying customers stuck on FREE tier with no detection",
  "single_point_of_failure": "OpenRouter (85% of 130+ models unreachable without it)",
  "blast_radius_map": {
    "OpenRouter": ["85% of model routing", "All non-Big-3 LLM providers"],
    "EventBus": ["Event persistence", "Langfuse telemetry", "Dead letter (no replay)"],
    "Postgres": ["Auth", "Quota", "Subscriptions", "Event store", "Webhook idempotency"],
    "Neuro TenantManager": ["L1 cache", "L2 embedding index", "Session manager (all unbounded)"],
    "Stripe webhook handler": ["Billing", "Subscription state", "Revenue"]
  },
  "first_3am_alert_prediction": "Stripe checkout.session.completed webhook fails silently → customer charged but stays on FREE tier → discovered days later via support ticket",
  "uncertainty_register": {
    "likely_wrong": [
      "P10.1 httpx leak severity — may be partially mitigated by GC; needs lsof validation",
      "P2.2 SSE disconnect waste — impact depends on user behavior; no metrics exist",
      "P8.3 Quota TOCTOU — window is microseconds; may never trigger at current scale"
    ],
    "requires_runtime_validation": [
      "TenantManager memory growth rate under multi-tenant load",
      "Real-world SSE client disconnect frequency",
      "PostgreSQL timezone in production deployment",
      "npm npmmirror.com availability from CI"
    ],
    "guesses_needing_confirmation": [
      "DirectProvider SDK internal timeout defaults (not verified against SDK source)",
      "Caddyfile.prod deployment via external automation",
      ".env with real keys is dev-only vs production"
    ]
  }
}
```
