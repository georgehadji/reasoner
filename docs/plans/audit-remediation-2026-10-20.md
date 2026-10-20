# Whole-Repo Audit — Remediation Plan

**Date:** 2026-10-20
**Status:** Draft for review
**Source:** the read-only audit run on 2026-10-20 (four slices: auth/billing, persistence/concurrency,
pipeline/LLM core, sandbox/SSRF/uploads/frontend proxy). The 20 ranked findings and the ~20 smaller ones
listed under "left out" are all covered here.
**Branch target:** one branch per PR below, each cut from `main` (not from the stacked
`fix/method-flow-*` branches).
**Related:** [`method-flow-gap-remediation-2026-10-18.md`](method-flow-gap-remediation-2026-10-18.md)
(independent; no overlap except `core/constants_limits.py`).

Nothing here changes the Dependency Rule (CLAUDE.md §1). `domain/` and `core/` stay a
dependency-free functional core. `application/` talks to infrastructure only through `core/ports` or
`application/ports`, and `.importlinter` contract 2 must not gain an exception. New
infrastructure code implements an existing port wherever one exists (`CreditRepository`,
`BillingPort`, `BillingDeadLetterPort`, `FileSearchPort`, `CircuitBreakerPort`, `CodeExecutorPort`).

---

## 0. Findings register

**Evidence** is where to look first. **Check** says who confirmed it:

- **R:** re-read or reproduced in the main session.
- **A:** traced end to end by an audit agent, not re-read.
- **P:** plausible; one link is untraced, and the row names it.

Every item's first task is to turn the failure case into a failing test. That also confirms the A
and P items before code changes.

### Security and money (exploitable now)

| ID | Finding | Sev | Check | Evidence |
|----|---------|-----|-------|----------|
| SEC-1 | PayPal webhook "verification" accepts any non-empty `paypal-transmission-sig`. A verification exception is logged and processing continues. A forged `ACTIVATED` grants ENTERPRISE. A missing `plan_id` maps to PRO when `PAYPAL_PRO_PLAN_ID` is unset. A forged `CANCELLED` downgrades victims. | Critical | R | `infrastructure/billing/paypal_adapter.py:152,204-213`, `infrastructure/billing/webhooks.py:251-260` |
| SEC-2 | API-key scopes are attached to `User` but never enforced. Only `admin` is ever checked, so a `read` key can run, mint keys, erase data, delete the account and open checkout. CSRF is skipped for keys. `Scope` itself lives in `infrastructure/auth_legacy.py`. | Critical | R | `api/dependencies.py:167-194`, `api/auth_deps.py:51-78,169`, `api/routes/{account_keys,gdpr,agent}.py`, `api/saas_router.py:183-189`, `api/billing_router.py:27-64` |
| BIL-1 | Caller-chosen `client_run_id` is the ledger `reference_id`. The Redis duplicate guard expires after 3600s, and after that `record()` returns the old rows. Reserve, settle and release all no-op, so the run is free. | Critical | R | `api/routes/agent.py:162-170`, `api/__init__.py:~704`, `api/mcp/tools.py:~99`, `credit_repo_postgres.py:141-148` |
| SEC-3 | Scraper SSRF. The client sets `follow_redirects=True` and only the first URL is checked. The blocklist misses `0.0.0.0/8`, `::/128` and non-loopback `::ffff:0:0/96`. DNS is resolved separately from the connect, so rebinding works. Responses are read whole and DNS runs sync on the loop. `_download_image_url` has the same redirect gap. | Critical | R (redirect, list), A (the agent ran the bypass IPs) | `infrastructure/scraper.py:25-47,146-172`, `security/url_validator.py:13-100`, `infrastructure/llm/image_generation.py:238-246` |
| SEC-4 | `PrismFileSearch` reads `UPLOAD_DIR/{file_id}.vectors.json` with no owner check and no id format check. That allows a cross-tenant read on legacy plaintext sidecars. Encrypted sidecars return `[]`, so the feature is dead for new uploads. `RunRequest.file_ids` is a bare `list[str]`. | High | R | `infrastructure/prism/file_search.py:48-80`, `api/schemas.py:129,228`, `documents/vector_store.py:200-210` |
| SEC-5 | No request-body cap exists anywhere (uvicorn, Caddy or middleware). The anonymous `/api/provenance/inspect` takes an unbounded `image` string. Docx/PDF extraction is sync, so `wait_for` cannot interrupt it, and there is no zip-bomb check. | High | A | `api/routes/provenance.py:39-65`, `api/routes/uploads.py:39-48`, `infrastructure/uploader.py:143-172,282-324,495-500` |

### Run lifecycle and spend leaks

| ID | Finding | Sev | Check | Evidence |
|----|---------|-----|-------|----------|
| RUN-1 | A client disconnect or the 600s absolute timeout does not cancel `run_task`. `asyncio.wait` does not cancel what it waits on, and `run_stream` has no `finally` that cancels its task. Orphaned runs keep billing, or block on a full queue. | Critical | R | `api/execution/pipeline.py:262-283`, `api/streaming.py:145-190` |
| RUN-2 | With Redis healthy, `RunStateManager.add` and `request_cancel` each build a throwaway `RunStateStore()`, so the cancel event is never set. `/api/stop` reads the fallback, which raises in production. | Critical | R | `infrastructure/redis/run_state.py:99-111,178-187,225-234` |
| BIL-2 | Three billed paths skip cost accounting. (a) Cascade calls, both successes and failed attempts. (b) The direct-vendor fallback, which is on by default and returns no usage. (c) DIRECT/WEB_SEARCH `done` frames, which carry no `total_cost_usd` and run before `check_run_allowed`. | Critical | A | `infrastructure/llm/executor.py:290-366,499-544`, `infrastructure/llm/router.py:55-102,579-624`, `api/execution/direct.py:152-161`, `api/execution/pipeline.py:375-381` |
| RUN-3 | Circuit-breaker HALF_OPEN slots leak when the call is cancelled, and HALF_OPEN has no timeout. Three cancelled probes wedge a model for the whole process. In Redis mode they wedge it for every worker. | High | A (two agents independently) | `infrastructure/llm/router.py:135-207,640-702`, `infrastructure/circuit_breaker.py:113-150,240-288`, `redis/scripts/circuit_breaker.lua:54-60` |
| RUN-4 | The router mutates the shared provider's `extra_body` around a network await. The guard is a counting semaphore of 30, not a mutex, so concurrent runs see each other's reasoning effort, and a wrong value can stick for the process lifetime. The `last_*` usage counters have the same race (P: it needs a suspension point). | High | A | `infrastructure/llm/router.py:138-166,189-213,657-675`, `providers/openai_compat.py:129,236-241,317-340` |

### Billing correctness

| ID | Finding | Sev | Check | Evidence |
|----|---------|-----|-------|----------|
| BIL-3 | Two wrong amounts. (a) A cached SSE replay re-sends the original `total_cost_usd`, and `metered()` bills it again. (b) Direct-provider ids such as `deepseek-v4-flash` price at the `_default` rate ($1/$5 per M), because the executor estimates with `domain.pricing`, not `pricing_resolver.get_pricing`. | High | A | `api/streaming.py:288-293`, `application/services/run_metering.py:103-157`, `infrastructure/llm/executor.py:504-510`, `infrastructure/llm/registry.py:597-610` |
| BIL-4 | The webhook claim row is written before processing and stays after a failure. The handler returns 200, so provider retries are deduplicated away. Nothing replays `failed_webhook_events`, and no JWT user can pass `_require_admin`. A stale `customer.subscription.updated` can overwrite `deleted`. | High | A | `infrastructure/billing/webhooks.py:127-147,184,213-217,263,290-293`, `application/ports/billing_deadletter_port.py`, `infrastructure/auth/supabase_adapter.py:74-82`, `api/routes/admin.py:28-31` |
| BIL-5 | Credit enforcement fails open on any exception, and settlement failures are only logged. Likely schema triggers: no migration creates `users.display_name`, and the credit and api-key tables exist only in raw `migrations/007_*.sql`, outside the alembic chain. | High | A (code), P (production schema state unknown) | `api/dependencies.py:88-118,549-557,631-636`, `application/services/run_metering.py:207-214`, `migrations/alembic/versions/df9629e72f17_baseline.py`, `migrations/007_credits_and_api_keys.sql` |
| BIL-6 | `ensure_monthly_allowance` runs only from `GET /api/credits`, keyed `monthly:YYYY-MM` with no tier. An upgrade mid-month grants nothing, and accounts used only through the API never get credits. No purchase or invoice grant exists. | Medium | A | `api/routes/credits.py:55`, `application/services/credit_service.py:33-36,82-96`, `credit_repo_postgres.py:208` |
| BIL-7 | MCP `reasoner_run` reserves credits before `RunRequest` validation and before `register_run`, so a raise loses the reservation. `reasoner_gate` makes five LLM calls with no credit or rate gate. | Medium | A | `api/mcp/tools.py:99-112,270-288` |
| BIL-8 | Account deletion cancels only one `status='active'` subscription (`LIMIT 1`) and ignores cancel errors. It then cascades away the local row, while the provider keeps charging. | Medium | A | `api/saas_router.py:202-243` |
| BIL-9 | Some spend escapes the caps. The quality-gate retry loop does not re-check `_spend_cap_exceeded`, and HyperGate and subagent calls bypass the executor's estimate and cap. | Medium | A | `application/flows/runner.py:143,165-228`, `subagents/base.py:167-175`, `hypergate/` |

### Persistence and event sourcing

| ID | Finding | Sev | Check | Evidence |
|----|---------|-----|-------|----------|
| PER-1 | `get_event_store()` builds `PostgreSQLEventStore` but never calls `initialize()`. `_pool` stays `None`, and every save fails after three retries. The partitioned `events` table declares `event_id UUID UNIQUE` without the partition key, which Postgres rejects. Compaction uses a second, separately initialized store. | Critical (prod) | R | `infrastructure/persistence/event_store.py:851-864`, `postgres_store.py:112-165,249-279,316,1042-1055`, `api/__init__.py:241-245` |
| PER-2 | Several writers emit `version=1` for the same aggregate, and the SQLite schema dropped `UNIQUE(aggregate_id, version)`. `PipelineAggregate.apply` raises on the second v1, so `GET /api/pipelines/{id}` returns 500 and resume is refused. | High | A (the comment at `event_store.py:88`, "version always 1", agrees) | `application/handlers/handlers.py:134-161,285-295,416-423`, `api/execution/sse_observer.py:80-110`, `core/aggregates/pipeline.py:52-73` |
| PER-3 | `LLM_GENERATION_COMPLETED` persists full prompts and responses. First-turn runs use aggregate `"unknown"`, which erasure never reaches. Pruning needs snapshots that are never written, so the table grows forever. The GDPR route builds the SQLite `EventStore()` directly, so it can report `completed` while Postgres data remains. `clear_memory_cache()` wipes every tenant's cache. | High | A | `infrastructure/llm/executor.py:241-256`, `application/event_bus/bus.py:441-453`, `event_store.py:674-711,767-785`, `api/routes/gdpr.py:31`, `application/services/data_eraser.py:54-60,133-134` |
| PER-4 | Postgres `_update_aggregate` overwrites `current_version` and `status` unconditionally, so a late event can flip a completed run back to `running`. The SQLite version uses `MAX`. | Medium | A | `postgres_store.py:393-413` vs `event_store.py:300-307` |
| PER-5 | `get_handler_registry()` keeps whatever its first caller passed. If a worker's first request is `POST /api/run`, that worker's registry has `event_store=None` for its whole lifetime. | Medium | A | `application/handlers/handlers.py:575-618`, `api/streaming.py:80,107`, `api/__init__.py:411-446` |
| PER-6 | Four smaller issues. `PostgresQuotaRepository.check_and_increment` does its first insert with no `ON CONFLICT`. Ownership stays in a local SQLite file under the Postgres backend. `list_aggregate_ids_for_user` leaks a repo and connection per call. The quota check and increment race. | Low | A | `quota_repo_postgres.py:95`, `pipeline_ownership_repo.py:159-183`, `event_store.py:664-672`, `quota_service.py:33-90` |

### Data fidelity

| ID | Finding | Sev | Check | Evidence |
|----|---------|-----|-------|----------|
| DAT-1 | `extract_json` strips `[n]` and everything after `Sources:`/`Citations:` from the raw text *before* parsing. Reproduced: `{"selected": [2], …}` becomes `{'selected': ''}`, and `{"analysis":"cite Sources: Smith", …}` becomes `{}`. | High | R | `core/parsing.py:31-60,157-158` |
| DAT-2 | The SSE path rebuilds `RunRequest` from a narrow command. `attachments`, `file_ids`, `enhance_prompt`, `force_pipeline`, `no_cache`, `web_search` and `expert` all revert to defaults. Nothing calls `ReasonerPipeline._build_attachment_context`. | High | A | `api/streaming.py:82-94`, `api/execution/pipeline.py:42-52,125-129,179`, `application/pipeline.py:142` |
| DAT-3 | The token cache key uses `user_prompt[:500]` with no tenant. `no_cache` never reaches the cache, truncated or failed outputs are cached, and the semantic path ignores the TTL. Store and lookup use different role lists. | Medium | A | `infrastructure/llm/executor.py:190-221,546-560`, `infrastructure/token_cache.py:134-230` |
| DAT-4 | Neuro recall is always empty: chunks without `schema_version` are dropped, and `ContextChunk.to_dict` never emits that field. Anonymous runs share the `default` tenant, which `/api/neuro/recall` can read back. | Medium | A (dead recall), P (anonymous read: proxy path untraced) | `application/orchestrator.py:432,536`, `neuro/server.py:179,366-427`, `neuro/cache.py:36-38` |
| DAT-5 | `sanitize_for_prompt` rejects benign text, because `system\s*:` and `assistant\s*:` match inside words. Reproduced: `"file system: ext4"` is blocked. | Medium | R | `core/sanitization.py:41-42` |
| DAT-6 | The `PhaseMonitor` LLM judge calls `ProviderRouter.complete`, which does not exist. The `AttributeError` is swallowed, so every rule miss forces a full premium retry. | Medium | A | `quality/monitor.py:176-178,218` |
| DAT-7 | Prism `_action_scrape` reads `s.get("text")`, but `scrape_url` returns `content`, so snippets are always empty. | Low | A | `application/flows/search_phases.py:~380`, `infrastructure/scraper.py:146-205` |

### Resilience and operations

| ID | Finding | Sev | Check | Evidence |
|----|---------|-----|-------|----------|
| OPS-1 | One Redis error sets `_redis_available=False` forever, and `fail_closed` (the default) then denies every request. The Lua script counts rejected calls and sets no EXPIRE. The limiter reads `REDIS_URL` while the startup probe reads `VALKEY_URL`. | High | R (latch), A (Lua, URL) | `infrastructure/rate_limiter.py:82-170`, `redis/scripts/rate_limit.lua:33-69`, `core/settings.py:194` |
| OPS-2 | Event bus `stop()` clears `_running` before `drain()`, so queued events are dropped. The single consumer runs exponential retries in-worker, so a subscriber outage stalls the queue. | Medium | R (stop), P (stall) | `application/event_bus/bus.py:151-267` |
| OPS-3 | Supabase JWT validation is a sync HTTPS call inside `async def authenticate`. It is not cached and runs twice on agent routes. | Medium | A | `infrastructure/auth/supabase_adapter.py:50`, `api/dependencies.py:210-293` |
| OPS-4 | Several per-run maps never shrink. WS `_replay_buffers` is created before the subscriber check, and `LangfuseSubscriber._active_spans` is never popped. A sync `flush()` runs on the loop. `TaggedMemory(HISTORY_DIR)` re-reads every `*.jsonl` on each run. | Medium | A | `infrastructure/websocket/manager.py:156-232`, `infrastructure/observability/langfuse_subscriber.py:80-190`, `api/execution/pipeline.py:321-334`, `core/memory.py:19-48` |
| OPS-5 | The sandbox worker's `communicate()` buffers unbounded output. There is no in-container `timeout` and no concurrency cap, and a crashed worker leaves its container running. This only applies with `EXEC_SANDBOX_ENABLED=true`. | Medium | A (mechanism), P (throughput) | `infrastructure/execution/sandbox_worker/docker_runner.py:60-190`, `sandbox_worker/app.py` |
| OPS-6 | `/api/stocks` and `/api/weather` are anonymous and have no rate limit, and `/api/widget/execute` is guarded only by CSRF. All three run blocking yfinance or yahooquery calls on the loop. | Medium | A | `api/routes/legacy_widgets.py:30-41`, `infrastructure/widgets/stocks.py:84-101`, `api/routes/widgets.py:93-121` |
| OPS-7 | The runtime image has no `libmagic1`, so uploads fail closed, and the obvious workaround disables MIME checks. `MIME_TYPE_MAP` rejects `.md`. The upload response leaks the server path. There is no per-user byte quota. | Medium | A (Dockerfile), P (exact libmagic output) | `Dockerfile:24-27`, `infrastructure/uploader.py:110-127,398-436,558` |
| OPS-8 | Three Next-proxy gaps, which matter only in dev and non-Caddy setups. `neuro/sessions` forwards no `Authorization`. The cookie-CSRF rule in `proxy.ts` blocks the bearer-only and webhook routes. The leftmost `X-Forwarded-For` is trusted. | Low | P (Caddy bypasses these routes in prod) | `ui-next/src/app/api/neuro/sessions/route.ts`, `ui-next/src/proxy.ts:25-39`, `ui-next/src/lib/security-server.ts:728-734` |

### Lean (dead or broken code; the agents grepped the whole tree)

| ID | Item | Evidence |
|----|------|----------|
| LEAN-1 | `SnapshotManager`, `SnapshotStrategy`, `ReadModelProjection` and `setup_read_model_projections`: only exports and one test use them. PER-3 decides whether snapshots stay; delete only after that. | `infrastructure/persistence/snapshots.py` |
| LEAN-2 | `valkey/state_adapter.py`, `memory_state_adapter.py` and `core/ports/distributed_state_port.py` have no importers. If RUN-2 needs a distributed-flag port, reuse this one instead. | — |
| LEAN-3 | `SubprocessExecutor` cannot run multi-line code: the dedent puts the code at column 16. Its AST guard is bypassable, and the container path replaced it. | `infrastructure/execution/subprocess_executor.py:78-88`, `services.py:61-67` |
| LEAN-4 | `StopPipelineCommandHandler` has no route, and its `version=0` event would break replay. | `application/handlers/handlers.py:317-342` |
| LEAN-5 | Tracked `src/reasoner/.upload_hash_index.json` is dead; the live copy is the gitignored one under `infrastructure/`. | — |

---

## 1. Design principles applied

| Module | Paradigm / pattern | Applied to | Why |
|--------|-------------------|------------|-----|
| `domain/` | **Pure policy functions over value objects** (Specification style: `allows(granted, required) -> bool`) | `ScopePolicy` (SEC-2), `LedgerReference` (BIL-1), `allowance_delta` (BIL-6) | Rules that decide money and access get exhaustive tests without mocks, and sit where the Dependency Rule wants them. `Scope` leaves `infrastructure/auth_legacy.py`, where a domain concept does not belong. |
| `security/` | **Pure predicate** `is_public_address(ip)` built on `ipaddress.is_global` | SEC-3 | One rule in place of a hand-kept list, so it is correct by construction for mapped and NAT64 forms. |
| `core/aggregates`, event store | **The aggregate is the single writer**, plus **optimistic concurrency** (`expected_version`, `UNIQUE(aggregate_id, version)`) | PER-2, PER-4 | Event sourcing only works if one writer owns the sequence. Today five emitters guess the version. |
| `core/parsing` | **Chain of Responsibility, strict first**: exact parse → fenced block → balanced span → cleaned text | DAT-1 | Cleaning is a fallback for malformed text. It must never pre-filter valid JSON. |
| `application/` run driver | **Structured concurrency** (`try/finally` cancel) | RUN-1 | No child task may outlive the request scope that started it. |
| `application/` cost | **Single choke point**: one `account_call_cost()` that every billed path calls | BIL-2, BIL-3, BIL-9 | Three paths drifted because each re-implemented the cost logic. One function cannot drift from itself. |
| `application/` billing | **Unit of Work** + **Transactional Outbox** | BIL-4 (the claim commits with the effect), BIL-5 (unsettled costs) | The idempotency marker and the side effect commit or roll back together, and failures are stored durably and replayed. |
| `application/handlers` | **Command + handler** (the existing CQRS registry) | BIL-4 replay | Uses the mechanism the codebase already has; no new one. |
| `api/` | **Guard dependency** (FastAPI `Depends`) | SEC-2 `require_scope`, BIL-7, OPS-6 | One reusable guard per concern, declared on the route where review can see it. |
| `api/` | **Pure ASGI middleware** that wraps `receive`, not `BaseHTTPMiddleware` | SEC-5 body cap | It must count streamed bytes, including chunked bodies with no `Content-Length`, before the app reads them. |
| `infrastructure/llm` | **Immutable per-call parameters**: `extra_body` passed into `complete()`. Fallback: **Prototype** (`copy.copy` per call) | RUN-4 | A shared adapter must hold no per-call state. |
| `infrastructure/` circuit breaker | **Explicit state machine** + **scoped acquisition** (`async with breaker.slot():`) | RUN-3 | The slot is released on every exit path, including cancellation, and HALF_OPEN gets a timeout edge. |
| `infrastructure/` rate limiter, run state | **Cooldown re-probe** around the dependency (the house pattern in `RunStateManager._should_try_redis`) | OPS-1, RUN-2 | Reuse the existing recovery logic instead of a one-way latch. |
| `infrastructure/` HTTP fetch | **Adapter**: a custom `httpx` transport that resolves, validates and connects to the pinned IP. Redirects are followed manually. | SEC-3 | The check and the connect must use the same address, or the check is decorative. |
| `infrastructure/` sandbox, widgets | **Bulkhead** (bounded semaphore) + **bounded reader** | OPS-5, OPS-6 | No tenant can exhaust a shared pool. |
| Blocking libraries | **Offload**: `asyncio.to_thread`, or a subprocess when the work must be killable | SEC-5, OPS-3, OPS-4, OPS-6 | `wait_for` cannot interrupt sync code. Killable work must run in a separate process. |
| Every fallback | **Visible degradation** via `core.degrade.degraded()` | BIL-5, OPS-1, DAT-6 | The repo already treats silent fallbacks as defects. New ones use the existing helper. |

---

## 2. Work packages

There are eight PRs. PR 1 is a hotfix and goes first. PRs 4–7 are independent after PR 1; §3 lists
the files they share. Each item lists the design, the changes, the **test that must fail before the
fix**, and the risk.

### PR 1 — `fix/audit-sec-hotfix`: exploitable now (SEC-1, SEC-2, BIL-1, SEC-3)

These are small diffs with the highest risk, so they ship before anything else.

> **As implemented (2026-10-20).** Where the build departed from the design below:
>
> - **SEC-1** follows the Stripe handler's house pattern:
>   - An unset `PAYPAL_WEBHOOK_ID` returns `{"status": "misconfigured"}` and ignores the event.
>   - A failed verification returns 200 and is not processed.
>   - A verification *error* returns 503, so PayPal retries.
>
>   There is no boot check; the Stripe path has none either.
> - **SEC-2** reuses the scope vocabulary already in `domain/api_keys.py`: `ASSIGNABLE_SCOPES` and
>   `DEFAULT_SCOPES`. It adds `key_allows()`, `KEY_MANAGE_SCOPE` and `ACCOUNT_DELETE_SCOPE` there
>   instead of moving the legacy `Scope` enum. The guard is `api/dependencies.require_key_scope`,
>   which returns the user, so each route swaps it in for `get_current_user`.
>
>   Running pipelines stays allowed with `read`, because the legacy `Scope.READ` documents it as
>   "run pipelines, view history" and the default key exists for the agent endpoints. Q2 decides
>   whether to tighten this. Guarded routes:
>   - `key:manage`: key create/revoke. No key can hold it.
>   - `account:delete`: account delete. No key can hold it.
>   - `history:delete`: data erase, history delete, pipeline delete.
>   - `write`: upload, upload delete, checkout, portal.
> - **BIL-1** is `domain/credits.run_reference()`, used at all five call sites (run and follow-up,
>   HTTP, agent and MCP).
> - **SEC-3** puts the pure policy and the async pinning resolver in `security/url_validator.py`,
>   and the fetch loop in `infrastructure/safe_fetch.py`. The sync `is_safe_url` stays for input
>   validation in `api/routes/context.py`.

#### SEC-1 — Real PayPal webhook verification

- **Design:** verification is an adapter capability (on the `BillingPort` side). The handler
  treats anything other than a positive answer as a rejection (fail closed).
- **Changes:**
  - `paypal_adapter.verify_webhook_signature`: POST to `/v1/notifications/verify-webhook-signature`
    with:
    - `auth_algo`, `cert_url`, `transmission_id`, `transmission_sig` and `transmission_time`;
    - `webhook_id`, from a new setting `PAYPAL_WEBHOOK_ID` that is required when PayPal is enabled;
    - the parsed event.

    Return `verification_status == "SUCCESS"`.
  - `webhooks.handle_paypal_webhook`: return 400 on `False` **or on an exception**, and do not
    claim or process the event. Today it logs and continues.
  - `paypal_adapter.py:152`: compare plan ids only when the setting is non-empty. An unknown or
    missing `plan_id` means no tier change, not PRO.
  - Boot check: if PayPal is enabled and `PAYPAL_WEBHOOK_ID` is empty, fail at startup in
    production, mirroring the Stripe-secret check.
- **Tests:** new `tests/test_paypal_webhook_verification.py`, with the HTTP call mocked through
  `httpx.MockTransport`:
  - A forged header returns 400 with no subscription write.
  - A verifier that raises returns 400.
  - `SUCCESS` is processed.
  - A missing `plan_id` with an unset env var gives no tier.
- **Risk:** real deliveries fail until the webhook id is configured. Add it to `DEPLOY.md` and to
  the env reference under `docs/` (see Q1).

#### SEC-2 — Enforce API-key scopes

- **Design:**
  - Move `Scope` to a new `domain/auth_scopes.py` with a pure
    `ScopePolicy.allows(granted: frozenset[str], required: str) -> bool`. Implied scopes live in
    one table: `write ⊇ read`, `admin ⊇ *`.
  - `infrastructure/auth_legacy.py` and the `reasoner.auth` shim re-export `Scope`, so current
    imports keep working.
  - Add one guard factory in `api/auth_deps.py`: `require_scope(name)`. It does nothing for
    session/JWT auth, where scopes don't apply. It returns 403 when
    `request.state.auth_method == "api_key"` and the policy denies.
- **Route → scope table.** It goes in the PR description and is also the test's parameter list.
  - **`write`:** run, agent run, MCP run, upload, checkout, portal.
  - **`keys:manage`:** create and revoke keys. This is a new scope and is never in the defaults.
  - **`history:delete`:** data erase.
  - **`account:delete`:** account delete. This is a new scope and is never in the defaults.
  - Read routes keep `read` and `history:read`.
  - A key can only mint scopes it already holds (`requested ⊆ granted`, checked in
    `account_keys.py`).
- **Changes:**
  - Add `Depends(require_scope(...))` on every mutating route.
  - Correct the false comment at `dependencies.py:170`.
- **Tests:**
  - A table-driven test over the route table: a `read` key gets 403 on each mutating route, and a
    key with the right scope gets 2xx.
  - A pure unit test of `ScopePolicy`.
  - An escalation test: a key that tries to mint a broader key gets 403.
- **Risk:** keys holding only the defaults will start getting 403 on writes. Ship it with a release
  note, and decide in Q2 whether to migrate existing keys.

#### BIL-1 — Server-owned ledger references

- **Design:**
  - A domain value object, `LedgerReference.for_run(client_run_id: str | None)`, returns
    `f"{client_run_id or 'run'}:{uuid4().hex}"`. The `:reserve` and `:release` references derive
    from it.
  - The client id stays the duplicate-submit key in Redis. The ledger key is never chosen by the
    caller.
- **Changes:** use it at the three call sites (`api/routes/agent.py`, `api/__init__.py`,
  `api/mcp/tools.py`), and pass the returned reference into `metered()` the way `reference_id` is
  passed today.
- **Tests:**
  - Two runs with the same `client_run_id`, with the Redis key cleared between them to simulate
    TTL expiry: both are charged.
  - A pure test that references are unique and keep the client prefix, for support lookups.
- **Risk:** support tooling that searches the ledger by bare `client_run_id` has to switch to a
  prefix match.

#### SEC-3 — SSRF-safe fetching

- **Design:**
  - **Pure policy** in `security/url_validator.py`: `is_public_address(ip) -> bool`. It unwraps
    `ipv4_mapped`, 6to4 and NAT64 (`64:ff9b::/96`), then requires `ip.is_global` and not
    `is_multicast`. This replaces the hand list, so `0.0.0.0`, `::`, `::ffff:10.0.0.1` and
    `::ffff:169.254.169.254` are covered by construction.
  - **Infrastructure adapter:** `SafeAsyncTransport(httpx.AsyncHTTPTransport)`. It resolves with
    `loop.getaddrinfo` (async), rejects any non-public address, and connects to the validated IP,
    keeping the original `Host` and SNI.
  - **Redirects are off.** A helper, `safe_get(url, max_hops=3, max_bytes=2_000_000)`, follows
    `Location` headers by hand and re-validates each hop. It streams the body (`client.stream`) and
    aborts at `max_bytes`.
- **Changes:**
  - `scraper._get_scraper_client` uses the new transport with `follow_redirects=False`, and
    `scrape_url` calls `safe_get`.
  - `image_generation._download_image_url` uses `safe_get` too.
  - Delete `_BLOCKED_NETWORKS` once the policy test covers every range it lists.
- **Tests:** new `tests/test_url_safety.py`:
  - Parametrized over every bypass address from the audit, plus the currently blocked ones.
  - A redirect to `169.254.169.254` is refused at hop 2.
  - A body over the cap is cut off.
  - A rebinding resolver that answers public, then private: the connection uses the validated IP.
- **Risk:** some legitimate sites redirect more than three times. Make `max_hops` and `max_bytes`
  named constants in `core/constants_limits.py`.

### PR 2 — `fix/audit-run-lifecycle`: stop the spend leaks (RUN-1, RUN-2, RUN-3, RUN-4, BIL-2)

#### RUN-1 — A run never outlives its request

- **Design:** structured concurrency in the driver.
  - `api/execution/pipeline.py:_run_phases` wraps the `asyncio.wait` in `try/finally`. The
    `finally` cancels `run_task` and `cancel_watch` if they are not done, then awaits them under
    `contextlib.suppress(asyncio.CancelledError)`.
  - `api/streaming.run_stream` gets the same treatment: `try/finally: task.cancel()` around the
    consume loop, then an await under suppression.
  - **Why not `TaskGroup`:** a `TaskGroup` cancels siblings only when one raises, and the cancel
    watcher finishing is not an exception. An explicit `finally` keeps today's "stopped by user"
    behaviour with the least change.
  - Once the consumer is gone, `stream.emit` becomes a no-op: a `closed` flag set in the `finally`.
    This removes the case where an orphan blocks forever on `queue.put`.
- **Tests:** new `tests/test_run_cancellation.py`, using a fake runner that sleeps and counts LLM
  calls:
  - Close the SSE generator mid-run. Within one tick, the runner task is cancelled and the call
    count stops.
  - Repeat with the absolute timeout forced to 0.1s.
- **Risk:** a phase that swallows `CancelledError` would keep running. In this PR, grep
  `application/flows` for `except BaseException` and `except asyncio.CancelledError` without a
  re-raise.

#### RUN-2 — One run-state store per process; Redis is the cross-worker flag

- **Design:**
  - `RunStateManager` owns a single process-local `RunStateStore`, created in `__init__`. It holds
    the `asyncio.Event` objects.
  - Redis holds only active-run membership and a `cancel:{run_id}` flag.
  - `add` always registers the run locally, and in Redis too when Redis is available.
  - `request_cancel` sets the Redis flag, and sets the local event when the run is local.
  - The pipeline's cancel watcher polls `is_cancelled(run_id)` once per second while the run lives
    (a cheap `EXISTS`). A Stop sent to another worker then reaches the owning one.
  - `is_active` checks Redis first, then the local store.
  - The production `RuntimeError` on fallback stays, but fires only when Redis is really
    unavailable.
- **Changes:**
  - `infrastructure/redis/run_state.py`, and the watcher in `api/execution/pipeline.py`.
  - Reuse `core/ports/distributed_state_port.py` if its shape fits (LEAN-2). Otherwise keep the
    logic local to infrastructure.
- **Tests:** use `fakeredis` if it is already a dev dependency, otherwise a small in-test fake.
  - `add`, then `request_cancel`: the local event is set.
  - Two managers on one fake Redis: a cancel sent to B is seen by A's watcher.
- **Risk:** one Redis call per second per active run. That is fine at the expected load, and the
  interval is a named constant.

#### RUN-3 — Circuit-breaker slots are scoped

- **Design:**
  - Add `async with breaker.slot():` to `CircuitBreakerPort`. Keep `can_execute` for one release
    as a thin wrapper.
  - The context manager takes the HALF_OPEN slot and always releases it in `__aexit__`. Success
    records a success, an exception records a failure, and `CancelledError` releases without
    recording either.
  - Add a HALF_OPEN → OPEN timeout edge (`half_open_timeout_seconds`) to the Python breaker and to
    both Lua copies (redis and valkey).
- **Changes:** `infrastructure/circuit_breaker.py`, `redis/scripts/circuit_breaker.lua` and its
  valkey twin. The router's `_call_with_circuit` and `_call_with_tools_circuit` each become a single
  `async with`.
- **Tests:** extend `tests/test_bug003_circuit_breaker_half_open.py`:
  - Three cancelled probes leave zero held slots.
  - After the HALF_OPEN timeout, the breaker reopens and probes again later.
- **Risk:** the Lua change reaches every worker at once. Put a script version in the key name so a
  mixed fleet mid-deploy never runs two sets of rules against one key.

#### RUN-4 — No per-call state on shared providers

- **Design:** immutable per-call parameters.
  - `complete()` and `complete_with_retry()` on the provider protocol gain
    `extra_body: dict | None = None`. `finetuned.py` already takes this parameter, so the shape is
    proven.
  - `openai_compat._effective_extra_body` merges the configured `self.extra_body` with the per-call
    value without assigning to `self`.
  - Usage comes back in the call's metadata instead of `self.last_*`.
  - The router stops mutating `provider.extra_body` and passes the value through.
- **Fallback** if the provider surface is too wide for one PR: `p = copy.copy(provider)` per call
  (Prototype). The HTTP client stays shared, the per-call state is private, and usage is read from
  `p`.
- **Changes:** `infrastructure/llm/router.py:138-213,657-675`, `providers/openai_compat.py`,
  `providers/direct.py`, `providers/noop.py`, and the `LLMPort` signature in
  `core/ports/llm_port.py`.
- **Test:** two concurrent calls on one provider instance with different `extra_body`, through a
  fake transport that records request bodies. Each request carries only its own value, and the
  provider's configured value is unchanged afterwards.
- **Risk:** `config_signature(self.extra_body)` feeds the LRU key at `openai_compat.py:146`. It
  stays correct, because the configured value no longer changes.

#### BIL-2 — Every billed call goes through one cost function

- **Design:**
  - Extract the cost block at `executor.py:499-544` into
    `account_call_cost(state, model, usage, *, attempt_failed=False)`. It is the only place cost
    enters state. It does four things:
    1. Take `usage.cost`, or estimate it with `pricing_resolver.get_pricing`.
    2. Add it to `state.total_cost_usd`.
    3. Run `_enforce_spend_caps`.
    4. Call `spend_tracker.record`.
  - The normal path, every cascade attempt (accepted or rejected) and the direct-vendor fallback
    all call it.
- **Changes:**
  - **Cascade:** `executor.py:290-366`.
  - **Direct fallback:** `router._try_direct_fallback` returns the provider's usage. When the vendor
    returns none, it estimates tokens from prompt and response length and flags the result
    `estimated=True`. It also goes through the same semaphore, breaker and timeout as the primary
    path.
  - **DIRECT/WEB_SEARCH:** `direct.py` adds `total_cost_usd=meta.get("cost_usd", 0.0)` to `done`.
    Move `check_run_allowed` ahead of the direct branch (`pipeline.py:375-381`).
- **Tests:**
  - A cascade with one rejected and one accepted attempt: both costs reach `state.total_cost_usd`.
  - A fallback with no vendor usage: the cost is non-zero and flagged as estimated.
  - A DIRECT answer: `extract_run_cost(done)` equals the meta cost.
  - A capped user asking a DIRECT question gets the cap error.
- **Risk:** coding presets will now show higher, correct charges. Note it in the changelog.

### PR 3 — `fix/audit-billing`: correct charges and entitlements (BIL-3 … BIL-9)

This PR depends on PR 2 for `account_call_cost`.

#### BIL-3 — Replays are free; direct models are priced right

- **(a) Cached replays.**
  - `run_stream_cached` rewrites replayed `done` and `phase_complete` frames with
    `total_cost_usd=0` and `cached=true`.
  - `extract_run_cost` returns `0.0` when `cached` is set, so the rule lives in one place.
  - Fix the docstring, and fix `tests/test_run_metering.py:274` so it asserts the real replay end
    to end, not the helper alone.
- **(b) Direct model prices.**
  - `account_call_cost` already uses `pricing_resolver.get_pricing`.
  - Add a stripped-id → `vendor/id` step to the resolver's alias lookup. Derive it from
    `registry.py:597-610`, not a hand-written list.
- **Tests:**
  - A cached replay settles 0.
  - Parametrized over every direct-provider model in the registry: the resolved price is never
    `_default`. This catches the next model someone adds.

#### BIL-4 — Webhooks: claim with the effect, replay failures

- **Design (Unit of Work):**
  - `_db_claim_webhook` and the subscription writes run in one transaction. On an exception it
    rolls back, which removes the claim.
  - The failure is then recorded in `failed_webhook_events` in a separate transaction, and the
    handler returns **500** so the provider retries.
  - For successes, the DB claim stays the dedupe guard.
- **Ordering:**
  - For `customer.subscription.updated`, ignore events whose `created` is older than the stored
    `subscription.updated_at`.
  - Store the provider event timestamp on the row in a new nullable column.
- **Replay:**
  - Add `ReplayFailedWebhooksCommand` and its handler in `application/handlers/`. The handler goes
    `BillingDeadLetterPort.list_failures` → `handle_webhook` → `mark_replayed`.
  - Expose it as `POST /api/admin/billing/dead-letter/replay`, plus a script in `scripts/`.
- **Admin reachability:** `SupabaseAuthAdapter` maps the `app_metadata.role == "admin"` claim (the
  Supabase convention) to `scopes={"admin"}`, so a JWT admin can pass `_require_admin`. The claim
  is configurable through the existing settings.
- **Tests:**
  - If processing raises, there is no claim row, the response is 500 and a failure row exists. The
    retry then succeeds.
  - A stale `updated` that arrives after `deleted` is ignored.
  - The replay handler marks rows as replayed.
- **Risk:** returning 500 means providers retry for up to a few days. That is correct, provided the
  side effects are idempotent too; the upserts already are.

#### BIL-5 — Credits fail closed; unsettled costs are durable

- **Design:**
  - In production, `require_credits` and `reserve_or_402` return **503** on a ledger error.
  - In dev, fail-open stays available behind `CREDITS_FAIL_OPEN=true`. It defaults to false in
    production.
  - Settlement errors go to a `credit_settlement_outbox` table (Transactional Outbox). A periodic
    job retries them, using the lifespan-task pattern that compaction already uses.
  - Every fallback goes through `degraded("credits.settle", …)`.
- **Schema:**
  - Add an alembic revision that creates `users.display_name`, `user_credits`, `credit_ledger`,
    `api_keys` and the outbox, all idempotent (`IF NOT EXISTS`). A database built from alembic
    alone then matches the code.
  - Mark the raw `007_*.sql` as superseded in its header.
  - `_ensure_user_in_db` stops swallowing errors: it logs and re-raises.
- **Tests:**
  - A repo that raises gives 503 in production. With the dev flag on, the run is allowed and a
    degraded warning is logged.
  - A settle failure lands in the outbox, and the retry job drains it.
  - `alembic upgrade head` on an empty Postgres creates every table the repos query. This runs as a
    marked test, or in the CI service container where the lane has one.
- **Blocked by Q3:** confirm the production schema state before shipping fail-closed. Otherwise the
  first deploy turns a silent free-for-all into a hard outage.

#### BIL-6 — Allowance follows the tier, not page loads

- **Design:**
  - A pure domain function, `allowance_delta(tier_allowance, already_granted_this_period) -> int`.
  - Grant keys become `monthly:{period}:{tier}`. An upgrade mid-period grants only the difference
    over what this period already received.
- **Changes:** call `ensure_monthly_allowance` from two new places, and keep the existing GET call:
  - `require_credits`, cached per user per period in-process, so it is not a DB hit per request;
  - the webhook's subscription-apply step.
- **Tests:**
  - Free → Pro mid-month grants the delta exactly once.
  - An account used only through the API gets its allowance on its first run.
  - A downgrade grants nothing.

#### BIL-7 — MCP reserves last; the gate is metered

- **`api/mcp/tools.py`:**
  - Use the same order as the HTTP routes: build `RunRequest` (validation), then call
    `register_run`, then `reserve_or_402`.
  - Wrap everything after the reserve in the same `metered()` context, so a raise releases the
    reservation.
- **`reasoner_gate`:** add the rate-limit guard and either a small fixed credit charge or a per-key
  cap per minute, depending on Q4.
- **Tests:** a validation error leaves the balance unchanged, and the gate returns 429 past its
  limit.

#### BIL-8 — Account deletion never orphans a paid subscription

- **Changes:**
  - Select every subscription whose status is not in `('canceled','incomplete_expired')`, and
    cancel each through `BillingPort.cancel_subscription`.
  - If any cancel fails, abort with 502 **before** `DELETE FROM users`, and record the attempt in
    `account_deletion_log`.
- **Tests:** a cancel failure gives 502 and the user row stays. Subscriptions in both `active` and
  `past_due` are cancelled.

#### BIL-9 — Caps hold everywhere

- **Changes:**
  - In `flows/runner.py`, check `_spend_cap_exceeded` at the top of every quality-gate retry
    attempt, not only at phase start.
  - HyperGate and subagent LLM calls report usage through `account_call_cost`.
  - HyperGate runs before `PipelineState` exists, so it gets a small injected `CostSink` callable
    from the orchestrator. That keeps hypergate free of application imports. Once state is built,
    the orchestrator folds HyperGate's total into it.
- **Tests:** a retry after the cap trips is refused, and HyperGate cost appears in the run total.

### PR 4 — `fix/audit-persistence`: event sourcing that works on Postgres (PER-1 … PER-6)

#### PER-1 — One initialized store per process; valid schema

- **Lifecycle:**
  - The lifespan creates the one event store and calls `await store.initialize()` for Postgres,
    then registers it with `set_event_store(store)`.
  - `get_event_store()` returns the registered instance, and raises a clear error if called before
    startup.
  - The CLI and headless entry points call the same initializer.
  - Compaction and admin reuse this instance. Delete the second `_compaction_store` and the
    `get_postgres_store()` singleton.
- **Schema:**
  - Replace `event_id UUID UNIQUE` with `UNIQUE (event_id, aggregate_type)`, with a matching
    `ON CONFLICT`.
  - Add a `DEFAULT` partition, so a new `aggregate_type` (for example `saas`) cannot break inserts.
  - Ship the DDL as an alembic revision, not only in `_init_schema`.
- **Tests:**
  - A Postgres integration test that initializes the store, saves, reads and runs compaction. It is
    marked and runs where a service container exists.
  - A unit test that calling `get_event_store()` before init raises.

#### PER-2 — The aggregate owns its sequence

- **Design:** split the log into two kinds of stream.
  1. **Aggregate events** (`PIPELINE_*`, `PHASE_*`):
     - Written only by `RunStream.persist`, which already assigns monotonic versions.
     - Saved with `expected_version` (optimistic concurrency).
     - Protected by `UNIQUE(aggregate_id, version)`, restored in both stores.
  2. **Telemetry events** (LLM generation, perspectives, metrics):
     - Written with `aggregate_type='telemetry'`.
     - Never replayed into `PipelineAggregate`.

  The handler drops its direct `PIPELINE_STARTED`/`COMPLETED` writes, and `persist_all_events`
  routes each event by its kind.
- **Migration:** existing rows with duplicate versions are renumbered per aggregate by
  `(timestamp, id)` before the unique index is created. This runs in the same alembic revision.
- **Tests:**
  - A fake streamed run → `get_events` → `PipelineAggregate` replays without error.
  - Two concurrent `save_events` calls with the same `expected_version`: one raises
    `ConcurrencyError`.
  - Resume works on a streamed run.
- **Also:** delete `StopPipelineCommandHandler` (LEAN-4) in this PR, because its `version=0` event
  breaks the new rule.

#### PER-3 — No prompt bodies in the log; erasure reaches everything; bounded growth

- **Retention:**
  - Telemetry events keep model, tokens, cost and latency. They drop `system_prompt`,
    `user_prompt` and `raw_response`.
  - If prompt capture is wanted for debugging, put it behind `EVENT_CAPTURE_PROMPTS=false` (the
    default), encrypted through the existing `CryptoPort`, with a TTL (Q8).
- **Aggregate ids:** bus events use the run id, which exists from run start, never `"unknown"`.
- **Pruning:**
  - Replace "delete what a snapshot covers" with a time-based prune. It removes telemetry streams
    older than `EVENT_TELEMETRY_RETENTION_DAYS`, and finished aggregates past the retention window.
  - Decide here whether snapshots stay. If they don't, LEAN-1 deletes them.
- **GDPR:**
  - `api/routes/gdpr.py` uses `get_event_store()`.
  - `data_eraser` also erases telemetry rows by run id, plus the user's uploads and API keys, as
    `/api/account/delete` already does.
  - Extract the shared part into one `erase_user(user_id)` service that both routes use.
  - Cache eviction becomes per tenant: add `clear_for_tenant(agent_id)` to the cache port.
- **Tests:**
  - A run's telemetry rows contain no prompt text.
  - Erase on the Postgres backend deletes the user's aggregates and telemetry. Its status is
    `completed` only if the deleted counts match.
  - Prune removes telemetry older than the window and keeps fresh rows.

#### PER-4 — Monotonic aggregate row on Postgres

- **Changes:**
  - Set `current_version = GREATEST(aggregates.current_version, EXCLUDED.current_version)`.
  - Pass a `NULL` status for events that carry none, and keep the `COALESCE`.
  - Never overwrite a terminal status (`completed`, `failed`, `cancelled`) with `running`. One
    `CASE` in the upsert does this, mirroring the SQLite logic at `event_store.py:300-307`.
- **Test:** a run completes, then a late phase event arrives. The run stays completed and its
  version does not drop.

#### PER-5 — The handler registry is built at startup

- **Changes:**
  - The lifespan builds the registry once, with the initialized store from PER-1 and the executor.
  - `get_handler_registry()` takes no arguments and returns that instance. Update the callers that
    pass arguments.
  - `get_architecture_components()` stops constructing anything.
- **Test:** a worker whose first request is `POST /api/run` then serves `GET /api/pipelines/{id}`
  correctly.

#### PER-6 — Small persistence fixes

- `quota_repo_postgres.check_and_increment` becomes one atomic statement:
  `INSERT … ON CONFLICT (user_id, period) DO UPDATE … RETURNING`. The check becomes the
  increment's result, which also closes the check-then-increment race.
- **Ownership on Postgres:** add a Postgres `PipelineOwnershipPort` implementation, selected by the
  same backend switch as the event store.
- `list_aggregate_ids_for_user` reuses the store's connection or pool instead of creating a repo
  per call.

### PR 5 — `fix/audit-input-limits`: tenant isolation and resource caps (SEC-4, SEC-5, OPS-5, OPS-6, OPS-7, DAT-4 tenant part)

#### SEC-4 — File search goes through the owning store

- **Changes:**
  - `PrismFileSearch.search_chunks` delegates to
    `DocumentVectorStore.retrieve(query, file_ids, top_k, user_id=...)`, which already checks
    ownership in the file's meta record and decrypts.
  - `FileSearchPort.search_chunks` gains `user_id: str | None`, and the research flow passes
    `state.user_id`.
  - `RunRequest.file_ids` becomes
    `list[Annotated[str, StringConstraints(pattern=r"^[a-f0-9-]{1,36}$")]]` with
    `max_length=20`. The second schema at `schemas.py:228` gets the same constraint.
- **Tests:**
  - Another user's file id returns no chunks.
  - An encrypted sidecar returns chunks. The existing test, which only uses plaintext, gains an
    encrypted case.
  - `../x` gives 422.

#### SEC-5 — Body caps and killable parsers

- **Body cap:** new pure-ASGI `BodySizeLimitMiddleware(app, default_limit, per_path)` in
  `api/middleware.py`.
  - It rejects early on `Content-Length`. Otherwise it wraps `receive`, counts bytes and returns
    413 on overflow.
  - The limits are named constants: 2 MB default for JSON, 520 MB for `/api/upload`.
  - Mount it first in `api/__init__.py`.
- **Field and proxy limits:** add `max_length` on `image` and `reference_images` in the provenance
  routes, and `request_body { max_size 520MB }` in `Caddyfile.prod`.
- **Extraction:**
  - Pre-check zip members before parsing: the total `file_size` must be ≤ 100 MB and the
    compression ratio ≤ 100:1.
  - Run `_extract_docx` and `_extract_pdf` in a subprocess, using a one-worker `ProcessPoolExecutor`
    with `RLIMIT_AS` on Linux, so the 60s timeout can actually kill the parse.
  - Cache the extracted text in the encrypted sidecar, so `get_file_text` stops re-parsing.
- **Tests:**
  - An oversized body gets 413 without the handler running, and a chunked oversized body gets 413
    too.
  - A zip-bomb docx is rejected before parsing.
  - A parser that sleeps past the timeout is killed. This is a subprocess test, skipped on Windows
    where `RLIMIT` is unavailable.

#### OPS-5 — Sandbox bulkhead and bounded output

- **Output:** read stdout and stderr in chunks. Once the total passes `max_output_bytes`, run
  `docker rm -f` and return a truncated result.
- **Timeouts:** prefix the in-container command with `timeout -s KILL {n}`, and add
  `--stop-timeout`.
- **Concurrency:** add `asyncio.Semaphore(SANDBOX_MAX_CONCURRENCY)` in `sandbox_worker/app.py`, and
  return 429 when it is full.
- **Crash cleanup:** label job containers with the worker id. On start, the worker runs
  `docker rm -f` on any labelled containers a crashed predecessor left behind.
- **Tests:** an output flood is truncated and its container is removed. N+1 concurrent requests
  produce one 429. Use the same marker as `integration/test_sandbox_escape.py`.

#### OPS-6 — Widget endpoints are guarded and non-blocking

- **Guards:** add `Depends(check_rate_limit)` to `/api/stocks`, `/api/weather` and
  `/api/widget/execute`. Also require auth, unless the routes are meant to be public (Q5).
- **Blocking calls:** wrap the yfinance and yahooquery calls in `asyncio.to_thread`. The calculator
  gets asteval's `max_time`, or the existing `wait_for(to_thread)` pattern.
- **Tests:** a burst past the limit gets 429. A fake slow fetch does not block a concurrent
  request, checked with a loop-latency assertion.

#### OPS-7 — Uploads work as configured

- **Changes:**
  - In the Dockerfile runtime stage, run
    `apt-get install -y --no-install-recommends libmagic1`.
  - Set `MIME_TYPE_MAP["text/plain"] = {".txt", ".md"}`, and accept `text/markdown`.
  - Drop `"path"` from the upload response.
  - Add a per-user byte quota: a new limit in `core/constants_limits.py`, checked against the
    uploads-by-user index.
- **Tests:**
  - An `.md` upload is accepted.
  - The response has no `path` field.
  - Going over the quota gives 413.
  - The image-scan workflow gains a step that runs `python -c "import magic"` inside the image.

#### DAT-4 (tenant part) — No shared anonymous memory

- **Changes:**
  - Call `tenant_key(None, conversation_id or run_id)`. A run with no owner then gets a temporary
    `a-<run_id>` tenant, or skips the learn step entirely, depending on Q6.
  - `/api/neuro/recall` without an owner returns 401, or reads only that conversation's tenant.
- **Test:** two anonymous runs cannot recall each other's text.

### PR 6 — `fix/audit-data-fidelity`: the pipeline sees and keeps what it should (DAT-1, DAT-2, DAT-3, DAT-4 recall, DAT-5, DAT-6, DAT-7)

#### DAT-1 — Parse strict first

- **Design:** `extract_json_any` becomes a chain where the first success wins:
  1. `safe_json_loads(text)` on the raw text.
  2. The first fenced code block.
  3. The first balanced `{…}` or `[…]` span.
  4. Only then the cleaned text. The citation and artifact strippers run only here, and only on
     text *outside* string literals.
- **Tests:**
  - The three reproductions from the audit become regression cases. The existing stripper tests
    stay.
  - A Hypothesis property test (Hypothesis is already in the repo): for any valid JSON object `o`,
    `extract_json(json.dumps(o)) == o`.
- **Risk:** some outputs that only parsed because the stripping removed trailing junk will now
  reach a later step of the chain. Run the recorded fixtures under `tests/` before merging.

#### DAT-2 — The request reaches the pipeline intact

- **Changes:**
  - In `run_stream`, store `RunPipelineCommand.metadata["request"] = req.model_dump()`.
  - `_request_from_command` rebuilds it with `RunRequest.model_validate(...)`, and falls back to
    the narrow fields for old callers. The validated request becomes the single source of truth.
  - Wire `_build_attachment_context` into `_seed_state`, its one intended caller.
  - `no_cache` flows into the executor (see DAT-3), and `force_pipeline` skips HyperGate's DIRECT
    outcome.
- **Test:** a table over every `RunRequest` field. Each field reaches `state` with the same value
  through `run_stream` as through a headless run. It includes an attachments case.

#### DAT-3 — Cache keys that are correct

- **Key:** `sha256(role, system_hash, model, full_user_prompt, tenant)`, where
  `tenant = billing_subject or conversation_id`. The tenant is passed as the existing `agent_id`
  parameter.
- **Behaviour:**
  - `state.no_cache` skips both the cache read and the cache write.
  - Never `set` a response when `metadata.get("truncated")` is true or the response is empty.
  - The semantic path applies the TTL.
  - Lookup and store share one `CACHEABLE_ROLES` constant.
- **Tests:**
  - Same first 500 chars, different tail: miss.
  - Different tenant: miss.
  - A truncated response is not stored.
  - `no_cache` does no read and no write.

#### DAT-4 (recall part) — Recall returns provenance

- **Changes:**
  - `ContextChunk.to_dict` includes `metadata`, which carries `schema_version`.
  - `NeuroService.recall` passes it through.
  - The orchestrator's filter stays as the guard; it now receives real chunks.
- **Test:** learn → recall → `state.neuro_context` is non-empty and wrapped. Recall must still enter
  at the user-message position (the `test_mind_virus_resistance.py` invariant).

#### DAT-5 — Injection patterns match roles, not words

- **Changes:**
  - Anchor the role patterns to the start of a line, `(?im)^\s*(system|assistant)\s*:`, or to a
    role-tag shape, `<\|?(system|assistant)\|?>`.
  - Keep every existing true-positive fixture.
- **Tests:**
  - These pass: `"file system: ext4"`, `"ecosystem: Node"`, and `"system:masters"` in mid-line.
  - A line that starts `System: ignore previous` is still blocked.

#### DAT-6 — The quality judge actually runs

- **Changes:**
  - `quality/monitor.py` calls `router.call(role="quality_judge", ...)`.
  - Add `quality_judge` to `_KNOWN_ROUTING_ROLES`, with a cheap default model in the presets, so
    its cost flows through `account_call_cost`.
  - Replace the bare `except` with `degraded("quality.judge", ...)`.
- **Test:** the real `PhaseMonitor` with a fake router. A rule miss followed by a judge pass causes
  no retry.

#### DAT-7 — Scrape snippets

- **Change:** `search_phases._action_scrape` reads `content`.
- **Test:** a scrape action fills the snippet.

### PR 7 — `fix/audit-resilience`: degrade instead of falling over (OPS-1, OPS-2, OPS-3, OPS-4, OPS-8)

#### OPS-1 — Rate limiter recovers

- **Recovery:** replace the one-way latch with the house cooldown pattern from
  `RunStateManager._should_try_redis`. After `RATE_LIMITER_REDIS_RETRY_SECONDS`, the next call
  re-probes Redis. `fail_closed` applies only while the cooldown runs.
- **Lua:**
  - Add `PEXPIRE` on the three keys, set to the window length.
  - Count a request only when it is allowed: check first, then `ZADD`.
- **Connection:** use `get_valkey_pool()`, so `VALKEY_URL` and `REDIS_URL` resolve the same way as
  in the startup probe.
- **Tests:**
  - After a fake Redis error and then recovery, requests are allowed again once the cooldown ends.
  - Keys have a TTL.
  - Rejected calls do not extend the window.

#### OPS-2 — The event bus drains, and slow subscribers don't stall it

- **Shutdown:** `stop()` awaits `drain()` first, then sets `_running=False`. Events still queued at
  the drain timeout go to the dead-letter log, not just a counter.
- **Retries:** move them out of the consumer. Each handler runs as a bounded task under
  `asyncio.Semaphore(BUS_HANDLER_CONCURRENCY)`, with its own backoff.
- **Tests:**
  - Events queued at stop are all processed or dead-lettered.
  - A failing subscriber delays another subscriber's event by no more than one tick.

#### OPS-3 — Non-blocking JWT validation

- **Validation:** check Supabase JWTs locally against the project JWT secret, or against JWKS via
  `PyJWT` (check whether it is already a dependency before adding it). The fallback is
  `asyncio.to_thread(self._client.auth.get_user, token)`.
- **Cache:** a TTL cache keyed by `sha256(token)`, capped at the token's `exp`.
- **Double authentication:** on agent routes, `check_rate_limit` reuses the user already resolved
  in `request.state`.
- **Tests:** a fake blocking client does not stall a concurrent request. A request now
  authenticates once instead of twice.

#### OPS-4 — Bounded in-memory structures

- **WS manager:** create `_replay_buffers[pid]` only when at least one subscriber exists, and
  expire it after `WS_REPLAY_TTL`.
- **Langfuse:** pop `_active_spans` entries on complete and on fail, and call `flush` through
  `asyncio.to_thread`.
- **History:** `_tag_history` builds `TaggedMemory` once per process and appends incrementally
  instead of re-reading every JSONL file per run. Add size-based rotation for `HISTORY_DIR`.
- **Tests:** after 1,000 SSE-only runs, `_replay_buffers` is still empty and the span map is empty.

#### OPS-8 — Next proxy parity (dev and non-Caddy deployments)

- **Changes:**
  - `neuro/sessions/route.ts` forwards `Authorization` and adds `rateLimit`, matching
    `neuro/recall`.
  - `proxy.ts` exempts the bearer-only and webhook paths from the cookie-CSRF rule.
  - `security-server.ts` takes the client IP from the rightmost trusted hop, mirroring the
    backend's `client_ip.py`.
- **Checks:** run `npx tsc --noEmit` and the Playwright suite.
- **Design gate:** not involved. This touches only `ui-next/src/app/api/**` and `lib/**`, with no
  styling, so the studio rules in CLAUDE.md don't apply.

### PR 8 — `chore/audit-lean`: delete dead code (LEAN-1 … LEAN-5)

This lands last, after PR 4 decides on snapshots (LEAN-1) and PR 2 on the distributed-state port
(LEAN-2).

- Delete each item along with its exports, its `CONTEXT.md` lines and its map-skill entries.
  `scripts/check_skill_maps.py` reports which map entries are stale.
- Re-run `scripts/update_mindmap_meta.py` and commit the new counts. That gate failed PR #130 for
  exactly this reason.
- For LEAN-3, also delete the `EXEC_SANDBOX_MODE=subprocess` branch at `services.py:61-67` and its
  settings. The container executor then becomes the only `CodeExecutorPort` implementation.

---

## 3. Sequencing

```
PR1 (hotfix) ──► PR2 (lifecycle + cost choke point) ──► PR3 (billing)
      │
      ├──► PR4 (persistence) ──┐
      ├──► PR5 (limits)        ├──► PR8 (lean)
      ├──► PR6 (fidelity)      │
      └──► PR7 (resilience) ───┘
```

- **PR 1 goes alone and first.** Each of its items is small and can be reverted on its own. Split
  it into four PRs if review time is the bottleneck.
- **PR 2 lands before PR 3**, because PR 3 needs `account_call_cost`.
- **PRs 4–7 run in parallel after PR 1.** Coordinate on these shared files:
  - `api/dependencies.py`: PR 1 (scopes), PR 3 (fail-closed, allowance), PR 7 (auth dedupe). Land
    PR 1 first, then rebase the others.
  - `api/__init__.py`: PR 4 (lifespan store and registry), PR 5 (middleware mount).
  - `infrastructure/llm/executor.py`: PR 2 (cost), PR 4 (telemetry payload), PR 6 (cache key).
    PR 2 goes first.
  - `infrastructure/redis/*`: PR 2 (run state, breaker Lua), PR 7 (rate-limit Lua).
- **Rollout flags with safe defaults** (all declared in `core/settings.py`):
  - `CREDITS_FAIL_OPEN` (PR 3): false in production.
  - `EVENT_CAPTURE_PROMPTS` (PR 4): false.
  - `PAYPAL_WEBHOOK_ID` (PR 1): required when PayPal is on.
  - SEC-2, SEC-3 and BIL-1 get no flag. They must not be possible to switch off.

## 4. Cross-cutting checks for every PR

1. **Failing test first.** Commit the test that reproduces the finding, then the fix, so the
   history proves the finding (CLAUDE.md §8, "Verification Before Done").
2. `lint-imports` must report 2 contracts kept and 0 broken. **Contract 2's exception count must
   not rise.**
3. `ruff check src/`: when the count drops, lower `--max` in `.github/workflows/test.yml` to the
   new count. Never raise it.
4. `python scripts/update_mindmap_meta.py`: commit its diff whenever test or source files are added
   or removed (`generated-docs-drift`).
5. `pytest -n auto --dist loadscope -m "not slow and not integration"` must be green. PRs 4 and 6
   also run `tests/test_mind_virus_resistance.py` explicitly.
6. Every new fallback goes through `core.degrade.degraded()`. Never a bare
   `except Exception: pass`.
7. New state fields have defaults and are read with `.get()`, for `--resume` compatibility.
8. New env vars go into the env reference under `docs/` and into `DEPLOY.md`.
9. Windows dev note: a test venv where `python-magic` loads Git's MSYS libmagic crashes on import.
   Use the short-path venv without `python-magic`. CI on Linux is unaffected.

## 5. Out of scope

- **Areas the audit did not read.** A follow-up audit should cover these before calling them clean:
  - most `ui-next/` components;
  - the 24 method flows beyond the shared runner;
  - `phases/` prompt text;
  - `domain/` preset routing;
  - `hypergate/sub_agents/*`;
  - watermark internals;
  - `documents/` chunking;
  - `migrations/` beyond `001` and `007`.
- **The per-worker `spend_tracker`:** a documented MVP tradeoff. The credit ledger is the durable
  limit.
- **The anonymous trial cap keyed per IPv6 address:** a policy question (Q7), not a defect fix.
- **Performance work** beyond the items that block the event loop.

## 6. Open questions

| # | Question | Blocks |
|---|----------|--------|
| Q1 | Is PayPal live in production? If so, `PAYPAL_WEBHOOK_ID` must be configured before PR 1 deploys. | SEC-1 |
| Q2 | Should a migration grant `write` to existing keys created as "full access" in the UI, or must users mint new ones? | SEC-2 rollout |
| Q3 | Was the production database built from alembic, from the raw `migrations/*.sql`, or by hand? Fail-closed credits must not ship until this is known. | BIL-5 |
| Q4 | `reasoner_gate`: credits per call, or only a per-key rate limit? | BIL-7 |
| Q5 | Are `/api/stocks` and `/api/weather` meant to be public (landing-page widgets) or for signed-in users only? | OPS-6 |
| Q6 | Anonymous runs: no Neuro learning at all, or a temporary per-conversation tenant? | DAT-4 |
| Q7 | Anonymous trial: key on the IPv6 /64 instead of the full address? | out of scope |
| Q8 | Prompt capture for debugging: is any retention required (support, abuse review)? If so, what TTL? | PER-3 |
