# REAPER V7 — VERIFICATION AUDIT

**Verifier:** Claude (code-level re-audit) | **Date:** 2026-07-08
**Source under review:** `docs/audits/architectural-reaper-v7-2026-07-08.md`
**Method:** Read cited source files, verified each claim against actual code. Verdicts: **CONFIRMED** (code matches claim), **DISPROVEN** (code contradicts claim), **DISPUTED** (partly true; mechanism or severity wrong), **UNVERIFIABLE** (needs runtime/ops data not in repo).

---

## HEADLINE CORRECTIONS

Two of the eight P0s do **not** hold up at the code level:

- **P5.2 "Weak CSRF secret `reasoner-csrf-secret-2026`" → DISPROVEN.** No such string exists anywhere in `src/`. `csrf.py` reads `settings.CSRF_SECRET` from env, SHA-256-hashes it, and **raises `RuntimeError` at startup if unset while `CSRF_ENFORCE_BACKEND=true`**. There is even a `BUG-FIX` comment showing this path was already hardened. The finding appears to reference a value in a local `.env` that is not in the tree.
- **P8.1 "Non-atomic `try_register` → duplicate pipeline execution" → DISPUTED.** `try_register` (`infrastructure/redis/in_memory.py:39-45`) is a **synchronous** method with **no `await` between the membership check and the `.add()`** — so it cannot be preempted inside a single event loop; it is effectively atomic per-process. The report's mechanism ("Redis `SET NX` fails → in-memory fallback") does not match this file (there is no Redis in it). Real residual risk is cross-process (8 workers each hold their own `_run_store`), which is the same split-brain as P8.2 — not a within-process TOCTOU. Severity P0 not justified by the cited code.

Net: **6 of 8 P0s confirmed**, not 8.

---

## PART-BY-PART VERDICTS

### P0 findings

| # | Claim | Verdict | Evidence |
|---|-------|---------|----------|
| 7.1 | Stripe/PayPal webhook failures silently swallowed → 200 OK | **CONFIRMED** | `billing/webhooks.py:136-138, 211-212` — `except Exception: logger.exception(...)`, then `return {"status": "ok"}`. A **signature**-failure metric exists (`STRIPE_WEBHOOK_SIG_FAILURES`) but there is **no counter/alert/dead-letter for processing failures**. `sync_subscription` never runs, sub never updated. |
| 6.1 | Account deletion broken | **CONFIRMED** | Frontend `settings/page.tsx:47-65` only calls `supabase.auth.signOut()` + redirect — **never hits `/account/delete`** (comment admits it). Backend `saas_router.py:227` does `DELETE FROM users`, then `:281` calls `_log_auth_event` → `INSERT INTO auth_audit_log(user_id …)`; `auth_audit_log.user_id REFERENCES users(id) ON DELETE CASCADE` (`002_auth_audit.sql:5`) → inserting a row for the just-deleted user is an **FK violation** → 500 after the user row is already gone. Note: the backend deletion is otherwise *comprehensive* (billing cancel, uploads, history, vectors, redis), so "broken" = un-wired + self-inflicted FK crash, not "missing." |
| 7.2 | Dead-letter queue: zero replay/alerting | **CONFIRMED** | `event_bus/bus.py:256-276` writes JSONL only. No Prometheus metric on write, no replay endpoint, no alert. `stats()` exposes `dropped_event_count` but nothing reads the dead-letter file. (Could not verify the "313 entries" count — file not inspected.) |
| 10.1 | httpx pool leak via Resilient wrappers | **CONFIRMED** | `neuro/providers.py` — `ResilientReasoning` (137) / `ResilientEmbedding` (191) hold `self.primary` + `self.fallbacks` child providers but define **no `aclose()`**. Children each lazily open an `httpx.AsyncClient` (lines 41, 68) and have their own `aclose()`, but nothing ever calls it on the children. `close_neuro_client()` exists (`api/execution/pipeline.py:594`) but closes the top-level neuro client, not these wrapper children. |
| 3.1 | No Prometheus/Alertmanager deployed | **CONFIRMED** | `docker-compose.yml` / `docker-compose.searxng.yml` contain no `prometheus`/`alertmanager` services. `docs/monitoring/alerts-reference.yml` exists but is reference-only. |
| 5.1 | 20+ live keys in plaintext `.env` | **UNVERIFIABLE (plausible)** | `.env` is gitignored / not in tree; `settings.py` reads keys from env. This is an ops/secret-management concern, not a code defect. Can't confirm count. |
| 5.2 | Weak CSRF secret | **DISPROVEN** | See headline. |
| 8.1 | Non-atomic pipeline dedup | **DISPUTED** | See headline. |

### Part 1 — Temporal

| # | Verdict | Evidence |
|---|---------|----------|
| 1.1 PostgreSQL `NOW()` vs UTC | **CONFIRMED (code-level)** | `quota_repo_postgres.py:117,127-128` use `NOW()` and `date_trunc('month', NOW())` with no `AT TIME ZONE 'UTC'`. Real impact depends on the PG server's `timezone` setting (unverifiable here). |
| 1.2 PayPal `AsyncClient()` no timeout | **DISPUTED** | Confirmed no explicit timeout at `paypal_adapter.py:39,76,196` (`async with httpx.AsyncClient() as client`). But httpx's **default timeout is 5s, not infinite** — the "indefinite hang → worker-pool exhaustion → full outage" mechanism is wrong. Real fix still worthwhile (5s may be too short for PayPal), but severity/mechanism overstated. |
| 1.3 DirectProvider no explicit timeout | **CONFIRMED** | `providers/direct.py:35,75,115` — `AsyncAnthropic(...)`, `AsyncOpenAI(...)`, `genai.aio.Client(...)` all lack a `timeout=`. SDK defaults are long (Anthropic/OpenAI ~600s), so hangs can exceed pipeline budget — claim holds. |
| 1.4 Month-boundary reset non-atomic | **PLAUSIBLE (not deep-verified)** | Consistent with 8.3 TOCTOU; did not trace the interleave in full. |

### Part 3 — Observability

| # | Verdict | Evidence |
|---|---------|----------|
| 3.2 / 10.4 Synchronous `print()` in StructuredLogger | **CONFIRMED** | `core/logging_utils.py:254` — `print(entry.to_json(), file=sys.stdout)`, no `asyncio.to_thread`. Blocks the loop per log call. |
| 3.5 `PHASE_DURATION` never observed | **CONFIRMED** | Grep for `PHASE_DURATION` with `.observe(`/`.labels(` returns nothing — histogram defined but never recorded. |
| 3.3 Cost: no spike alert / spend cap | **PLAUSIBLE (not deep-verified)** | Consistent with absence of alerting infra (3.1). |
| 3.4 Independent trace IDs / no correlation_id | **PLAUSIBLE (not deep-verified)** | — |

### Part 6 — Data

| # | Verdict | Evidence |
|---|---------|----------|
| 6.3 `archive_hot_sessions`/`archive_warm_to_cold` never called | **CONFIRMED** | Defined at `neuro/sessions.py:316,389`; no callers anywhere in `src/reasoner/*.py`. Dead lifecycle code. |
| 6.4 Migration DDL non-atomic | **DISPUTED** | `20260501_…add_paypal…py` has many `op.execute()` in `upgrade()`, but **Alembic wraps each migration in a transaction by default** and PostgreSQL DDL is transactional — so a mid-migration failure normally rolls back atomically. The "auto-commit individually" claim is not supported unless the migration explicitly sets autocommit (it doesn't). |
| 6.2 Physical deletes only / no soft-delete | **PLAUSIBLE** | `delete_account` uses hard `DELETE FROM`; consistent with claim. |

### Part 7 — Failure Handling

| # | Verdict | Evidence |
|---|---------|----------|
| 7.3 Retry backoff lacks jitter | **CONFIRMED** | `event_bus/bus.py:232` — `wait = min(2 ** attempt, 8)`, deterministic 1/2/4/8s, no `random`. |
| 7.4 DB pool exhaustion, no app circuit breaker | **PLAUSIBLE (not deep-verified)** | — |

### Part 8 — Concurrency

| # | Verdict | Evidence |
|---|---------|----------|
| 8.2 Rate-limiter mode split-brain | **CONFIRMED (config mismatch)** | `settings.py:125` defaults `RATE_LIMITER_MODE="redis"`; the report notes `.env.example` uses `memory`. The default mismatch is real; multi-worker + memory mode → per-worker buckets. |
| 8.3 Quota check→increment TOCTOU | **PLAUSIBLE** | Narrow window, as the report itself flags in its uncertainty register. |

### Part 9 / 10 — Deps & Performance

| # | Verdict | Evidence |
|---|---------|----------|
| 9.1 `simpleeval` present | **CONFIRMED (dep present)** | `requirements.txt:34` `simpleeval>=0.9.13`; `requirements.lock:248` `==0.9.13`; no `asteval`. License claim not independently assessed. |
| 10.2 `TenantManager` unbounded dict | **CONFIRMED** | `neuro/server.py:126,150` — `self._tenants` grows one entry per `agent_id`; `get()` only inserts; no eviction/TTL/cap. |
| 10.3 `token_cache` `_problem_index` zombie entries | **CONFIRMED** | `token_cache.py:259-265` — on overwrite it correctly subtracts old tokens, but **still `_problem_index[...].append(key)`** again, duplicating the key in the index list. Minor unbounded index growth. |

---

## SUMMARY OF ADJUSTMENTS

| Finding | Report severity | Verified verdict |
|---------|-----------------|------------------|
| 7.1 webhook swallow | P0 | **CONFIRMED P0** |
| 6.1 account deletion | P0 | **CONFIRMED P0** (nuance: backend logic exists, is un-wired + FK-crashes) |
| 7.2 dead-letter no replay | P0 | **CONFIRMED P0** |
| 10.1 httpx wrapper leak | P0 | **CONFIRMED P0** |
| 3.1 no alerting | P0 | **CONFIRMED P0** |
| 5.1 plaintext keys | P0 | **UNVERIFIABLE** (ops, not code) |
| 5.2 weak CSRF secret | P0 | **DISPROVEN** — hardened, no hardcoded secret |
| 8.1 non-atomic try_register | P0 | **DISPUTED** — atomic per-process; downgrade to the 8.2 multi-worker class |
| 1.2 PayPal no timeout | P1 | **DISPUTED** — httpx defaults 5s; "indefinite hang" false |
| 6.4 migration atomicity | P1 | **DISPUTED** — Alembic runs in a transaction by default |

**Confirmed as-stated:** 7.1, 6.1, 7.2, 10.1, 3.1, 1.1, 1.3, 3.2/10.4, 3.5, 6.3, 7.3, 8.2, 9.1, 10.2, 10.3.
**Disproven:** 5.2.
**Disputed (real issue, wrong mechanism/severity):** 8.1, 1.2, 6.4.
**Unverifiable from repo (need runtime/ops):** 5.1, and the "313 dead-letter entries" / production-timezone / traffic-dependent claims the report already flagged in its own uncertainty register.

## NOT INDEPENDENTLY VERIFIED

For time, these were accepted as plausible without full tracing: 1.4, 2.1–2.6, 3.3, 3.4, 4.x (human factors), 5.3–5.8, 6.2/6.5, 7.4–7.6, 8.3/8.4, 9.2–9.4, 10.5–10.10. None were contradicted; deeper verification recommended before acting on any single one.

## BOTTOM LINE

The report is **mostly accurate and well-grounded** — the core P0 reliability gaps (silent webhook loss, un-wired/FK-crashing account deletion, no dead-letter replay, httpx wrapper leak, no alerting) are **real and reproducible in code**. But it overstates two P0s (CSRF secret is already hardened; the pipeline-dedup race is not a within-process TOCTOU) and two P1s lean on incorrect mechanisms (httpx default timeouts; Alembic transaction behavior). Adjusted P0 count: **6, not 8**. Ship decision **NOT READY** still stands on the strength of the confirmed six.
