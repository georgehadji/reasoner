# Fifth Whole-Repo Audit: Remediation Plan

**Date:** 2026-10-29
**Status:** Draft. Not yet reviewed by a second agent.
**Source:** the read-only `/ponytail-audit` run on 2026-10-29 against `docs/audit4-plan`
(`f1fa2261`). That audit reported 20 numbered findings and named 3 smaller ones it left out. This
plan covers all 23. Four read-only sub-agents each read one area: money, security,
runtime/persistence, and lean/tests/frontend. The main session re-read the code for every item
marked **R** below.

**Supersedes:** nothing. Audit 4 (`audit-remediation-4-2026-10-22.md`) is a draft and is not yet
built. Its 17 items are not repeated here. Section 3 says where the two plans touch the same code.
**Branch target:** one branch per PR below, each cut from `main`. Section 3 gives the order.

### Architectural constraints

Every item keeps the Dependency Rule (CLAUDE.md §1).

- **Layering.** `.importlinter` contract 1 puts `core` above `domain`, and `domain` above `utils`.
  - `domain/` imports nothing from `core/`.
  - `infrastructure/` imports nothing from `application/`.
  - A port that both an application service and an infrastructure adapter need goes in
    **`core/ports/`**.
  - Wiring that needs both an infrastructure concrete and an application object happens at a
    composition root: `api/__init__.py`, `main.py` or `headless.py`. The model-registry port
    (`set_model_registry_port()`) is the pattern to copy.
- **Contract 2** (`application -> infrastructure`) was at 50 declared exceptions on 2026-10-22.
  Re-measure with `scripts/count_importlinter_exceptions.py --contract 2` when you cut each branch.
  No PR adds an `ignore_imports` line. BIL-28 should remove one.
- **Ratchets.** Re-measure silent-failure, bandit, vulture, mypy and ruff at branch time. None may
  get worse. A PR that improves one lowers its `--max` in the same PR. Every new `except` block
  logs through `degraded()` or re-raises.
- **Tests first.** Every item starts with a test that fails on `main` for the reason given in the
  register. The PR body quotes that failure.

---

## 0. Findings register

**Check column:**

- **R:** re-read in the main session.
- **A:** reported by a sub-agent from its own code reading, and not re-read in the main session.
  The first step of that item's PR re-reads it.

**Severity:** M = must fix, S = should fix, N = nice to have. The audit number is in brackets.

### Run admission and billing doors

| ID | Sev | Check | Where | Failure case |
|----|-----|-------|-------|--------------|
| SEC-18 [3] | M | R | `api/mcp/tools.py:L61-163`, `L214-282` | `reasoner_run` and `reasoner_followup` never call `check_preset_access`, and they have no per-user rate limit. A FREE key runs `debate-premium` over MCP, while the same preset returns 403 over HTTP. Only `reasoner_gate` (`L306-318`) has a bucket. |
| SEC-19 [4] | M | R | `domain/api_keys.py:L42-46`; `api/dependencies.py:L338-354`; every route that calls `admit_run` | `DEFAULT_SCOPES` is `{read, preset:read, history:read}`. `require_key_scope` guards uploads, deletes, keys and billing, but not one route that starts a run. A default read-only key calls `POST /api/agent/run` and spends credits. |
| BIL-26 [2] | M | R/A | `api/__init__.py:L745-781` (`/api/search`); `api/routes/images.py:L199-224`; `api/routes/gate.py:L29-39` | These routes call paid providers without reserving credits. A 0-credit account runs smart search (an LLM call plus several search calls) up to the 1000-per-hour rate limit. `preview_only` calls `enhance_image_prompt` before any credit check. Authenticated `/api/gate` runs HyperGate's five LLM calls for free. With `ENABLE_LEGACY_API_KEY=true`, image generation with `user is None` skips both the reservation and the anonymous trial cap. |
| BIL-27 [7] | S | R | `api/mcp/tools.py:L240-256` | `reserve_or_402` runs at `L246`, and `FollowupRequest(...)` is built after it at `L250`. A blank or blocked question raises after the hold, and nothing releases it. `_run_and_bill` fixed the same bug (BIL-7); the follow-up tool was missed. |

### Runtime

| ID | Sev | Check | Where | Failure case |
|----|-----|-------|-------|--------------|
| RUN-10 [1] | M | R | `api/__init__.py:L837-867`; `infrastructure/redis/run_state.py:L211-221`, `L288-294`; `api/execution/pipeline.py:L293-305` | `/api/stop` checks `_run_store.is_active` and `get_owner`, which read only this worker's memory. `request_cancel` writes the Valkey `cancelled_runs` set, but no code reads it while a run is in flight: `is_cancelled` has no caller. With 8 workers, about 7 in 8 Stops return `not found`. The run keeps billing until the absolute timeout. Also, `ACTIVE_SET` has one TTL for the whole set (`L220`, 300 s), so on an otherwise quiet worker a run older than 5 minutes drops out of it. |
| RUN-11 [9] | S | R | `api/streaming.py:L274-306` | Past `MAX_COLLECTED_EVENTS=200` the collector stops appending, but `done` still triggers `_save_cache`. A long Article run saves without its last frames, and replay then ends with no `done`. |
| RUN-12 [10] | S | R | `api/cache.py:L88-124`; `api/schemas.py:L134` | The key hashes `attachments` but not `file_ids`. The same question about contract 2 replays the cached answer about contract 1. There is no age limit, so a `web_search` answer replays for months. |

### Money

| ID | Sev | Check | Where | Failure case |
|----|-----|-------|-------|--------------|
| BIL-28 [8] | S | R | `domain/spend_limits.py:L87-93`; `domain/credits.py:L30-36`; `infrastructure/llm/spend_tracker.py`; `application/services/spend_limit_service.py:L318-332`; `infrastructure/llm/executor.py:L770-775` | PRO is granted 25,000 credits ($25) but the monthly cap is $8.00, so a PRO user is blocked after about 8,000 credits. The counter also lives per worker and resets on restart. The module documents that half as an MVP trade-off, but the cap contradicting the grant is not documented. |
| BIL-29 [11] | S | A | `infrastructure/billing/stripe_adapter.py:L86-105`; `application/services/billing_service.py:L103-161`; `domain/credits.py:L45-67` | There is no handler for `charge.refunded`, `charge.dispute.*` or PayPal `PAYMENT.SALE.REFUNDED`. After a chargeback the subscription stays active, and the user keeps the tier and the granted credits. |
| BIL-30 [20b] | N | A | `api/dependencies.py:L800-863`; `api/run_observability.py:L81` | Quota is checked read-only at admission and only incremented at settle. Ten parallel runs at 19/20 all pass the check. Credits still limit the damage. |

### Persistence and scale

| ID | Sev | Check | Where | Failure case |
|----|-----|-------|-------|--------------|
| PER-15 [5] | M | R | `infrastructure/persistence/postgres_store.py:L988-1018`; `event_store.py:L757-816`; `application/event_bus/bus.py:L492-516` | `prune_events_before` only deletes events that a snapshot covers. Production never builds `SnapshotManager` or calls `create_snapshot`, so the join matches 0 rows. `persist_all_events` stores every bus event, every LLM call included, at version 0. None of it is ever deleted. |
| PER-16 [13] | S | R | `api/routes/pipelines.py:L85-121` | The route takes `limit` rows from all users' pipelines, then drops the ones the caller does not own, with one ownership lookup per row. A user with 3 runs among 10,000 gets an empty page, and `total` is the filtered page length. |
| PER-17 [14] | S | A | `neuro/server.py:L251-307`; `neuro/cache.py:L49-186` | Each worker loads a tenant's `L1Cache.bundles` and `L2Index.entries` once. `L2.add` re-reads the file under its lock, but `search` does not, and L1 never re-reads. Turn 2 is learned on worker A. Turn 3 then runs on worker B and misses turn 2. |
| PER-18 [15] | S | R | `neuro/server.py:L710`; `neuro/sessions.py:L269-303` | `search_hot` opens and parses every hot JSONL file synchronously, on the event loop, on every recall. A heavy tenant has tens of MB, and every stream on that worker stalls while it runs. |
| PER-19 [20a] | N | R | `api/__init__.py:L239-247`; `application/services/compaction_service.py:L89-124` | Every worker runs the 03:00 compaction loop and issues the same DELETE batches. Today they delete nothing (PER-15). Once PER-15 is fixed they will compete. |
| PER-20 [left out] | N | R | `api/cache.py:L164-198` | `_prune_disk_cache` globs and stats up to 1000 files on the event loop after every save. Another worker can delete a file between the glob and its `stat()`, which raises `FileNotFoundError` out of `_save_cache`. |

### Edge hardening

| ID | Sev | Check | Where | Failure case |
|----|-----|-------|-------|--------------|
| SEC-20 [12] | S | R | `api/client_ip.py:L34-53`; `core/settings.py:L573` | When `TRUSTED_PROXIES` is set, the function walks `X-Forwarded-For` but never checks that the direct peer is a trusted proxy. A caller that reaches the app without the proxy sets a random header and gets a fresh rate-limit bucket and a fresh anonymous trial cap each time. Matching is exact-string, so a CIDR in `TRUSTED_PROXIES` silently never matches. |
| SEC-21 [16] | S | R | `api/routes/feedback.py:L23-48` | `POST /api/feedback` has no rate limit, `context` is an unbounded dict, and `rating` is any string up to 10 characters. A script can fill the table. |
| SEC-22 [left out] | N | R/A | `api/dependencies.py:L314`; `api/__init__.py:L781`; `infrastructure/uploader.py:L548-551`; `api/routes/admin.py:L179`, `L214` | Raw exception text goes back to callers, for example `"Authentication failed: {exc}"` in a 401 body and `"Search unavailable: {exc}"` in a 503. |

### UI

| ID | Sev | Check | Where | Failure case |
|----|-----|-------|-------|--------------|
| UI-13 [6] | M | R | `ui-next/src/lib/db.ts:L31-58`; `app/settings/page.tsx:L65`; `app/providers.tsx:L24`, `L41` | Every helper opens a new IndexedDB connection through `getDB()`, and none is ever closed. `deleteDB` waits until every open connection closes, so `await deleteHistory()` never resolves. Account deletion then spins forever. On sign-out the previous user's history stays readable until the tab closes, which brings back the UI-5 leak. |
| UI-14 [18] | S | R | `ui-next/src/stores/app-store.migrate.test.ts:L3-13`; `app-store.ts:L232-244` | The test checks an inline copy of `migrate`, and the copy already lacks `autoMethodAlways`. Breaking the real `migrate` fails no test. |
| UI-15 [left out] | N | R | `ui-next/src/lib/db.ts:L120-146` | Paging uses the non-unique `timestamp` index with an exclusive bound on the last key. Two rows with the same timestamp that straddle a page boundary lose the second row. |

### Lean and gates

| ID | Sev | Check | Where | What |
|----|-----|-------|-------|------|
| LEAN-14 [17] | S | R | `infrastructure/widgets_legacy.py` (582 lines), `src/reasoner/widgets.py` (shim), `api/routes/legacy_widgets.py` | Calculator, weather, stocks and discover exist twice. The UI calls the legacy paths (`ui-next/src/lib/config.ts:L218-220`). The two calculators use different safety checks: a hand-written AST whitelist, and `asteval`. |
| LEAN-15 [20c] | N | A | `ui-next/package.json:L29` | `rehype-highlight` is never imported. |
| OPS-10 [19] | S | R | `.github/workflows/test.yml:L333-341`; `scripts/ci-local.sh:L66` | The vulture ratchet still has `continue-on-error: true`. Its own comment says it should block from 2026-10-03. |

---

## 1. Design principles applied

| Module | Paradigm or pattern | Where it is used |
|--------|---------------------|------------------|
| `api/run_admission.py` | **One admission sequence per door** (Template Method in function form), the BIL-10 lesson | `admit_run` gains the key-scope step (SEC-19). A sibling, `admit_flat_charge`, covers the routes that call paid providers but run no pipeline (BIL-26). Image generation moves onto it, so `_reserve_image_credits` and `_release_image_credits` go away. |
| `api/mcp/tools.py` | The same template for the transport that has no `Request` | `_admit_mcp_caller` runs scope, rate limit, quota, credits and preset tier. It is shared by `reasoner_run`, `reasoner_followup` and `reasoner_gate`. |
| `domain/api_keys.py` | Pure value rules | `RUN_SCOPE` and the `key_allows` implications stay pure functions. |
| `infrastructure/redis/run_state.py` | Shared state behind the existing facade, with per-key TTLs and a heartbeat | Per-run Valkey keys replace the set-wide TTL. A polling watcher maps a remote cancel flag onto the local `asyncio.Event`. |
| `core/ports/spend_counter.py` | Port in `core`, adapters in `infrastructure`, injected at the composition roots | `SpendCounter` Protocol; a Valkey adapter (`INCRBYFLOAT`) and an in-memory adapter. |
| `application/services/spend_limit_service.py` | Functional core | `check_run_allowed` takes `spent_usd` as an argument instead of reading a counter. Its async callers read the port. |
| `domain/spend_limits.py`, `domain/credits.py` | One source of truth | The monthly USD cap is derived from the tier's credit allowance, so the two cannot disagree again. `clawback_credits()` is a pure function. |
| `application/services/billing_service.py` | Strategy table, as `PAYPAL_HANDLERS` already does | `STRIPE_HANDLERS` replaces the `if` chain and gains refund and dispute entries. |
| `api/cache.py` | Specification (one predicate), plus an envelope value | `is_replayable(events)` gates both save and replay. Entries are stored as `{saved_at, max_age, events}`. |
| `infrastructure/persistence/*_store.py` | Retention by row class, not by a join that cannot match | Version-0 audit rows have their own retention rule, separate from replayable rows. |
| `api/routes/pipelines.py` | Query in the store, not filtering in the adapter | `list_pipelines(aggregate_ids=...)` plus `count_pipelines(...)`. |
| `neuro/cache.py` | Cache-aside with a version stamp (file or directory `mtime_ns`) | `refresh_if_changed()` on L1 and L2. |
| `api/client_ip.py` | Value object parsed once | `TrustedProxies` built on `ipaddress` networks, so CIDRs work. |
| Periodic jobs | External cron hitting admin routes, the audit-4 rule | Compaction leaves the per-worker lifespan loop. |
| Legacy widget routes | Adapter over the registry, pinned by characterization tests | The routes keep their paths and response shapes. The second engine is deleted. |
| `ui-next/src/lib/db.ts` | One cached connection per owner that yields to version changes | A `blocking` handler closes it. Paging uses a `[timestamp, id]` cursor. |

Rejected options:

- **A Valkey pub/sub channel for Stop.** Each worker would need a dedicated subscriber connection
  and a reconnect loop. One `EXISTS` per running run per second costs less and has nothing to
  reconnect.
- **A new route `Depends` per run route for the key scope.** Seven routes would each need it, and
  the next route would forget it, exactly as BIL-10 happened. The scope check goes inside
  `admit_run` and `admit_flat_charge` instead. An architecture test pins that every billed route
  goes through one of them.
- **A Valkey lock around the compaction loop.** It keeps per-worker periodic work, which audit 4
  rejected. The existing admin route plus a cron is simpler.
- **Writing snapshots to unlock event pruning (PER-15).** `application/handlers/handlers.py:L324`
  and `L456` rebuild aggregates from full history with `load_from_history`, not from snapshots.
  Deleting versioned events would break status and resume for old runs. See Q6.
- **Making `check_run_allowed` async.** It would change two production call sites and twelve test
  call sites. Passing `spent_usd` in keeps the function pure, and the tests stay synchronous.

---

## 2. Work packages

### PR 1: `fix/audit5-run-admission` (SEC-18, SEC-19, BIL-26, BIL-27)

#### SEC-19: a `run` scope, enforced at admission (decision Q1)

- **`domain/api_keys.py`:**
  - Add `RUN_SCOPE = "run"`.
  - Add it to `ASSIGNABLE_SCOPES` and to `DEFAULT_SCOPES`. Default keys keep working, and a key
    minted without it is truly read-only.
  - `key_allows` is unchanged: `write` implies only `read`.
- **`api/run_admission.py`.** Add the step `_require_run_scope(request, user)` near the top of
  `admit_run`, after `require_auth_if_legacy_disabled`:
  - It raises 403 `"API key lacks the 'run' scope"` when `request.state.auth_method == "api_key"`
    and `not key_allows(user.scopes, RUN_SCOPE)`.
  - Session and JWT callers pass, matching `require_key_scope`.
  - This covers `/api/run` and `/api/run-followup` (`api/__init__.py:L689`, `L727`),
    `agent.py:L161`, `L193`, `context.py:L189` and the resume stream (`pipelines.py:L242`), with
    no route edits.
- **Migration `<ts>_api_key_run_scope`.** It backfills existing keys so none of them breaks:
  - `upgrade`: `UPDATE api_keys SET scopes = array_append(scopes, 'run') WHERE NOT ('run' = ANY(scopes))`.
    The column is `TEXT[] NOT NULL` (`20261021_000000_credits_keys_and_event_constraints.py:L91`).
  - `downgrade`: `array_remove(scopes, 'run')`.
  - `down_revision` is the head at build time: `20261022_000300` if audit-4 PR 1 has landed,
    otherwise `20261021_000200`. Run `alembic heads` to check.
  - `tests/integration/test_alembic_schema_contract.py` stays green.
- **UI.** Grep `ui-next/src` for where keys are minted. If scopes are offered there, list `run`.

#### SEC-18 and BIL-27: one MCP admission helper

- **`api/mcp/context.py`.** `resolve_caller(ctx, *, scope: str | None = None)`:
  - When the token `looks_like_api_key` and `scope` is given and `not key_allows(user.scopes, scope)`,
    it raises `McpAuthError("API key lacks the '<scope>' scope")`.
- **`api/mcp/tools.py`.** Add `_admit_mcp_caller(ctx, *, preset) -> tuple[User, str]`:
  1. `resolve_caller(ctx, scope=RUN_SCOPE)`;
  2. resolve the tier;
  3. the per-user rate limit, moved out of `reasoner_gate` (`L310-318`) unchanged and still
     failing closed;
  4. `check_quota`, then `require_credits`;
  5. `check_preset_access(preset, user, None)` from `api/dependencies.py:L866`.

  Its callers are `_run_and_bill` (replacing `L98-101`), `reasoner_followup` (replacing `L240-243`)
  and `reasoner_gate` (steps 1–3 only, with no scope check, since the gate runs nothing billed by
  the pipeline; BIL-26 bills it separately).
- **`reasoner_followup` order** becomes the HTTP order: build `FollowupRequest` first, then reserve.
  Wrap everything from the reserve up to the start of the stream in `try/except BaseException`,
  and release through `release_unstarted`, as `_run_and_bill` does at `L115-128`.
- `tests/test_mcp_tools.py` still pins the tool list, which is unchanged.

#### BIL-26: `admit_flat_charge` for paid calls that run no pipeline (decision Q2)

- **`api/run_admission.py`:**

  ```python
  @dataclass(frozen=True)
  class FlatCharge:
      user_id: str | None
      reference_id: str          # "<kind>:<uuid4>", never ending in ":reserve"
      credits: int

  async def admit_flat_charge(request, *, user, cost_usd, kind) -> FlatCharge: ...
  async def refund_flat_charge(charge: FlatCharge) -> None: ...
  ```

  - Steps, in order: `require_auth_if_legacy_disabled`, then `_require_run_scope`.
  - For `user is None`: `enforce_anonymous_trial_cap(get_client_ip(request), cost_usd)`, and no
    hold.
  - Otherwise reserve `cost_usd` through the sink. With audit-4 PR 1 merged that is
    `settlement_sink()`; before then it is `CreditSink()`. The `402` mapping moves here from
    `images.py:L53-65`.
  - The hold **is** the charge, exactly like today's `image:` hold. Its reference does not end in
    `:reserve`, so audit 4's orphan sweeper never releases it.
  - `refund_flat_charge` releases under `f"{reference_id}:release"`. Callers use it only when the
    provider call fails.
  - The ledger-outage fail-open branch (`images.py:L68-70`) is kept, and gets the counter that
    audit 4 adds for `reserve_or_402`.
- **Routes:**
  - `/api/search`: `kind="search"` or `"smart-search"`, with the matching cost constant. Refund on
    an exception.
  - `/api/generate-image` with `preview_only`: `kind="image-preview"`.
  - `/api/generate-image` itself: move `L216-224` onto `admit_flat_charge(kind="image")`. That
    also closes the `user is None` gap, because the helper calls the trial cap. Delete
    `_reserve_image_credits` and `_release_image_credits`.
  - `/api/gate`: one `admit_flat_charge(kind="gate", cost_usd=GATE_ESTIMATED_COST_USD)` for
    everyone. It replaces the anonymous-only branch at `gate.py:L37-38`.
- **`core/constants_limits.py`.** Add `SEARCH_ESTIMATED_COST_USD`,
  `SMART_SEARCH_ESTIMATED_COST_USD` and `IMAGE_PREVIEW_ESTIMATED_COST_USD`, next to
  `GATE_ESTIMATED_COST_USD`. Their values are decision Q2.
- **Architecture test** `tests/architecture/test_billed_routes_admitted.py`: an AST scan of
  `api/` that fails when a module calls `smart_search`, `SearchService.search`,
  `enhance_image_prompt`, `generate_images` or `decide_route` from a route function that does not
  also call `admit_run`, `admit_flat_charge` or `_admit_mcp_caller`.

**Tests first:** `tests/test_audit5_admission.py`:

- `test_read_only_key_cannot_start_run`: a key with `{read}` gets 403 from `/api/agent/run`. A key
  with `{read, run}` passes.
- `test_session_caller_needs_no_run_scope`.
- `test_mcp_run_enforces_preset_tier`: a FREE user and `debate-premium` raise. This fails today.
- `test_mcp_run_is_rate_limited`.
- `test_mcp_followup_rejected_question_releases_hold`: `question="   "` leaves the ledger balance
  unchanged. This fails today.
- `test_search_reserves_credits` and `test_zero_balance_search_is_402`.
- `test_image_preview_is_charged`.
- `test_authenticated_gate_is_charged`.
- `test_legacy_anonymous_image_hits_trial_cap`.
- Migration: `tests/integration/test_api_key_run_scope_backfill.py` against `reasoner-pg-test`
  (:55499).

### PR 2: `fix/audit5-cross-worker-stop` (RUN-10)

- **`core/constants_limits.py`.** Add:
  - `RUN_STATE_TTL_SECONDS = max(PIPELINE_ABSOLUTE_TIMEOUT_SECONDS + 120, 600)`. The floor covers
    a timeout of 0, which `streaming.py` treats as unbounded.
  - `RUN_STATE_HEARTBEAT_SECONDS = 30.0`.
  - `REMOTE_CANCEL_POLL_SECONDS = 1.0`.
- **`infrastructure/redis/run_state.py`.** Store per-run keys, each with its own TTL:
  - `run:active:<id>`, whose value is the owner id or `""`, with `EX RUN_STATE_TTL_SECONDS`;
  - `run:cancel:<id>`, with `EX RUN_STATE_TTL_SECONDS`;
  - `ACTIVE_SET` becomes a sorted set, with each member's expiry time as its score. `add` runs
    `ZADD`. `active_runs_anywhere()` runs `ZREMRANGEBYSCORE -inf now`, then `ZRANGE`. The
    whole-set `EXPIRE` at `L220-221` goes away, and that is what dropped long runs.
  - New async methods:
    - `is_active_anywhere(run_id)`: local first, then `EXISTS run:active:<id>`;
    - `get_owner_anywhere(run_id)`;
    - `heartbeat(run_id)`, which re-sets both key TTLs and the score;
    - `watch_remote_cancel(run_id)`: every `REMOTE_CANCEL_POLL_SECONDS` it checks
      `run:cancel:<id>`. On a hit it sets the local event and returns. Every
      `RUN_STATE_HEARTBEAT_SECONDS` it heartbeats.
  - `is_cancelled` and `_cancel_redis` move to the per-run key. `pop_cancelled` and its Lua script
    keep working on the new key.
  - With Valkey unavailable, everything stays local, as today (dev and single worker).
- **`api/__init__.py` `/api/stop`.** Use `await _run_store.is_active_anywhere(run_id)` and
  `await _run_store.get_owner_anywhere(run_id)`. The global stop uses `active_runs_anywhere()`.
- **`api/execution/pipeline.py:_run_phases`.** Add a third task,
  `remote_watch = asyncio.ensure_future(_run_store.watch_remote_cancel(run_id))`. Its completion
  sets `cancel_event`, so the existing `cancel_watch` branch fires unchanged. The `finally` block
  cancels and gathers it with the other two tasks.
- **WebSocket stop** (`infrastructure/websocket/manager.py:L577`) already calls `request_cancel`,
  so it works once the watcher exists.

**Tests first:** `tests/test_audit5_cross_worker_stop.py`. Use two `RunStateManager` instances,
each with its own local store, sharing one Valkey fake.

- `test_stop_on_other_worker_cancels_run`: the run is registered on A, the stop goes to B, and A's
  cancel event is set within 2 poll intervals. This fails today.
- `test_stop_route_finds_run_on_other_worker`: `/api/stop` on B returns `stop requested`, not
  `not found`.
- `test_owner_enforced_across_workers`: another user's stop on B gets 403.
- `test_long_run_stays_active_past_old_set_ttl`: with time frozen past 300 s and heartbeats
  running, `is_active_anywhere` is still true.
- `test_crashed_run_expires`: with no heartbeat, the run is gone after `RUN_STATE_TTL_SECONDS`.

### PR 3: `fix/audit5-billing-ledger` (BIL-28, BIL-29, BIL-30)

This PR goes after audit-4 PR 1, which changes `CreditSink.settle` and the quota increment.

#### BIL-28: a shared spend counter, and caps derived from the allowance (decision Q3)

- **`core/ports/spend_counter.py`.** A `SpendCounter` Protocol with two methods:
  - `async def get(self, subject: str, period: str) -> float`;
  - `async def add(self, subject: str, period: str, usd: float) -> float`.

  Module-level `set_spend_counter_port()` and `spend_counter()` follow the model-registry-port
  shape.
- **Adapters:**
  - `infrastructure/valkey/spend_counter.py`: `INCRBYFLOAT spend:<subject>:<YYYY-MM>`, then
    `EXPIRE` of 40 days on the first write of a period.
  - `infrastructure/llm/spend_tracker.py` becomes the in-memory adapter. Its existing functions
    stay as the implementation, so `tests/unit/test_spend_limits.py` keeps passing.
  - On a Valkey error the adapter degrades to the in-memory one through `degraded()`. That is
    today's behaviour, now visible.
- **Injection.** `api/__init__.py`, `main.py` and `headless.py` each call
  `set_spend_counter_port(...)`, next to `set_model_registry_port()`.
- **`spend_limit_service.check_run_allowed(preset_id, tier, billing_subject=None, *, spent_usd=0.0)`.**
  It stays pure. The import at `L319` goes away; if it is a declared contract-2 exception, delete
  that line and lower the count.
  - The two async callers (`api/execution/pipeline.py:L400`, `routes/context.py:L123`) first run
    `spent = await spend_counter().get(user_id, current_period())`.
- **`executor.py:L770-775`** uses `await spend_counter().add(...)`.
- **`domain/spend_limits.py`.** Derive `monthly_usd` for each paid tier as
  `credits_to_usd(TIER_MONTHLY_CREDITS[tier]) * MONTHLY_CAP_HEADROOM`, with
  `MONTHLY_CAP_HEADROOM = 1.2`. `domain -> domain` is legal. FREE keeps its explicit $0.50 for
  anonymous callers (Q3). Add a test that pins `monthly_usd >= allowance` for every paid tier.

#### BIL-29: refunds and disputes (decision Q4)

- **`domain/credits.py`:**
  - Add `CreditReason.CLAWBACK = "clawback"`. It is not in `_CREDIT_REASONS`, so it removes
    credits.
  - Add `def clawback_credits(balance: int, granted_this_period: int) -> int: return max(0, min(balance, granted_this_period))`.
    It never pushes a balance below zero, and it never takes back more than this period's grant.
- **`application/services/credit_service.py`.** Add
  `claw_back(user_id, *, reference_id, period_key)`. It reads the period's `MONTHLY_GRANT` total
  from the ledger, then records one `CLAWBACK` entry. That entry is idempotent per
  `clawback:<provider-object-id>`.
- **`infrastructure/billing/stripe_adapter.py`.** `sync_subscription` maps `charge.refunded`,
  `charge.dispute.created` and `charge.dispute.closed` to the user's subscription through the
  charge's `customer`, using the subscription repo's lookup by `stripe_customer_id`. It returns
  the subscription, not the placeholder at `L99-105`.
- **`application/services/billing_service.py`.** Replace the Stripe `if` chain (`L119-161`) with
  `STRIPE_HANDLERS: dict[str, Handler]`, the same shape as `PAYPAL_HANDLERS`. Add:
  - `charge.refunded`: only when `amount_refunded == amount` (a full refund), set the status to
    `cancelled`, `sync_quota_for_subscription`, then `claw_back`.
  - `charge.dispute.created`: set the status to `past_due`.
  - `charge.dispute.closed`: when `status == "lost"`, cancel and `claw_back`. When `won`, set the
    status back to `active`.
  - PayPal `PAYMENT.SALE.REFUNDED` and `PAYMENT.SALE.REVERSED`: the same as a full Stripe refund.
    Before writing that handler, read the PayPal adapter to confirm how it maps a sale to its
    subscription.
  - Every write keeps the `event_at` ordering guard (BIL-15).
- **Runbook.** Enable these event types on the Stripe and PayPal webhook endpoints.

#### BIL-30: hold quota at admission (decision Q5)

- **`application/ports/quota_repository.py`.** Add `release(user_id) -> None`. Postgres implements
  it as a single `UPDATE` that sets `used_queries = GREATEST(used_queries - 1, 0)` on the user's
  quota row. The in-memory repo mirrors it.
- **Admission.** `admit_run` and `_admit_mcp_caller` call `check_and_increment` instead of the
  read-only `check_quota`. `RunContext` gains `quota_held: bool = False`.
- **`run_metering.metered(..., quota_hold: QuotaHold | None = None)`.** The new parameter is
  keyword-only and defaults to `None`, so every existing fake still fits. `QuotaHold` is a
  one-method Protocol in `run_metering.py`.
  - `_finalize` calls `quota_hold.release(user_id)` when `ctx.quota_held` and `cost_usd == 0`.
  - `release_unstarted` does the same.
- **`run_observability.CreditSink.settle`.** Remove the increment at `L81`. If audit-4 PR 1 added
  a `was_existing` guard around that increment, remove the guard with it.

**Tests first:** `tests/test_audit5_billing_ledger.py`:

- `test_spend_counter_shared_across_instances`: two app instances share one Valkey fake.
- `test_pro_cap_not_below_allowance`.
- `test_check_run_allowed_is_pure`.
- `test_full_refund_cancels_and_claws_back_unspent_grant`.
- `test_partial_refund_changes_nothing`.
- `test_dispute_lost_claws_back`, `test_dispute_won_restores_active`.
- `test_clawback_is_idempotent_on_replay`.
- `test_parallel_runs_cannot_exceed_quota`: ten concurrent admissions at 19/20 give one success
  and nine 429s. This fails today.
- `test_zero_cost_run_returns_quota`.
- The existing fakes in `tests/test_run_metering.py` and `tests/test_audit2_money_leaks.py` pass
  unchanged.

### PR 4: `fix/audit5-event-retention` (PER-15, PER-16, PER-19)

#### PER-15: retention for audit rows (decision Q6)

- **Both stores' `prune_events_before`** (`postgres_store.py:L988`, `event_store.py:L757`) delete
  in two classes per batch:
  1. **Audit rows**, the new class: `version = 0 AND created_at < cutoff`. `get_events` reads only
     `version > 0` (`bus.py:L503-508`), so replay is unaffected. These rows are the bulk: one per
     bus event, every LLM call included.
  2. **Snapshot-covered rows**: the existing query, unchanged.

  Postgres keeps the CTE-with-`LIMIT` form for the partitioned table. `count_eligible_events`
  counts both classes.
- **Read-path check, first step of this PR.** Grep `src/` for readers of version-0 rows: admin
  stats, the export in `user_data_*`, the trace and debug routes. Each reader gets the retention
  window written into its docstring, and any that needs older rows is listed in the PR body.
  Shipping without this check would repeat the CLAUDE.md "verified" mistake.
- **Versioned rows** (`version > 0`) still grow by a few rows per run. That is a documented
  residual (Q6).

#### PER-16: filter by owner in the store

- `EventStore.list_pipelines(limit, offset, status, aggregate_ids: Sequence[str] | None = None)`
  and a new `count_pipelines(status, aggregate_ids)`, in both stores:
  - Postgres: `AND aggregate_id = ANY($n::text[])`.
  - SQLite: `AND aggregate_id IN (SELECT value FROM json_each(?))`. One bound parameter, so the
    SQLite variable limit cannot bite.
- **`routes/pipelines.py:L94-121`.** For non-admins:
  `ids = await repo.list_pipeline_ids_for_user(user_id)` (`pipeline_ownership_repo.py:L103`,
  already on the port), then one store call, then `total = await count_pipelines(...)`. The
  per-row ownership loop goes away. It still fails closed: a failed id lookup raises 503 instead of
  returning an empty list that looks like the real answer.

#### PER-19: compaction leaves the workers

- Delete the lifespan task (`api/__init__.py:L239-247` and its shutdown cancel), and delete
  `run_nightly_compaction_loop` (`compaction_service.py:L89-124`).
- Schedule the existing `POST /api/admin/compaction/run` (`routes/admin.py:L34`) from the same
  external cron as `neuro-maintenance`.
- Add the metric `reasoner_compaction_last_success_timestamp`, set by that route.
- `COMPACTION_RUN_HOUR_UTC` becomes unused. Delete it from `core/settings.py` and from
  `docs/ENVIRONMENT.md`.

**Tests first:**

- `test_audit_rows_pruned_without_snapshot`: seed version-0 rows older than retention; they are
  deleted. This fails today with 0.
- `test_versioned_rows_kept_without_snapshot`.
- `test_replay_unaffected_by_audit_prune`.
- `test_pipeline_list_paginates_per_owner`: 3 owned runs among 500 foreign ones return 3, with
  `total=3`. This fails today.
- `test_no_compaction_task_in_lifespan`.
- Postgres variants run against `reasoner-pg-test`.

### PR 5: `fix/audit5-run-cache` (RUN-11, RUN-12, PER-20)

- **`api/cache.py`:**
  - `def is_replayable(events: list[dict]) -> bool`: true only when the last event is `done`,
    `done.errors` is empty, and no `phase_complete` carries `error` or `errors`.
  - `_save_cache` returns without writing when it is false.
  - `run_stream_cached` (`streaming.py:L255-272`) calls the same predicate instead of its own
    copy.
- **`api/streaming.py`.** `RUN_CACHE_MAX_EVENTS` moves to `core/constants_limits.py`. Once the
  stream reaches it, the collector sets `truncated = True`, stops appending, and skips
  `_save_cache`. The cap rises from 200 to 2000, so that typical Article and Writing runs still
  cache; the value is in Q7.
- **Cache key v8** (`cache.py:L107-123`). Add `"file_ids": sorted(req.file_ids)`. The version bump
  makes every v7 entry, which lacked file ids, unreachable.
- **Envelope.** Store `{"saved_at": time.time(), "max_age": N, "events": [...]}` on disk and in the
  memory cache:
  - `N` is `settings.RUN_CACHE_WEB_MAX_AGE_SECONDS` when the request had `web_search` or
    `smart_search`, otherwise `settings.RUN_CACHE_MAX_AGE_SECONDS`.
  - `_load_cache` treats an expired entry, or one that is not an envelope, as a miss and unlinks
    it.
  - Both settings go into `docs/ENVIRONMENT.md`.
- **PER-20.** `_prune_disk_cache` and the temp-file cleanup run through `asyncio.to_thread`. Each
  `stat()` sits in its own `try`, and `FileNotFoundError` skips that file. Pruning also drops
  expired envelopes.

**Tests first:** `tests/test_audit5_run_cache.py`:

- `test_truncated_stream_not_cached`: 2,500 events then `done`; nothing is saved. This fails today.
- `test_replay_requires_done`.
- `test_file_ids_change_cache_key`: this fails today.
- `test_expired_entry_is_a_miss`.
- `test_web_search_entry_uses_short_ttl`.
- `test_prune_tolerates_concurrent_delete`.

### PR 6: `fix/audit5-neuro-freshness` (PER-17, PER-18)

- **`neuro/cache.py`:**
  - `L2Index` keeps `_loaded_mtime_ns`, set in `_load` and after its own `_merge_and_write`.
    `refresh_if_changed()` stats `index.json` and re-runs `_read()` when the value differs.
  - `L1Cache` does the same with the directory's `st_mtime_ns`. Adding or removing a bundle file
    changes the directory's mtime on NTFS and on local POSIX file systems. The bundle id is a
    content digest, so a same-name overwrite carries the same content.
- **`neuro/server.py` recall (around `L704-725`).** Add `await asyncio.to_thread(_refresh, tenant)`
  before searching, where `_refresh` calls both methods.
- **PER-18.** `hot_results = await asyncio.to_thread(sessions.search_hot, req.prompt, 3)`.

**Tests first:**

- `test_l2_sees_entry_written_by_other_instance`: two `L2Index` objects on one directory; A adds,
  B searches and finds it. This fails today.
- The same test for `L1Cache`.
- `test_recall_does_not_block_loop`: a slow `search_hot` stub; a concurrent coroutine keeps
  ticking.

### PR 7: `fix/audit5-edge-hardening` (SEC-20, SEC-21, SEC-22)

- **SEC-20, `api/client_ip.py`:**
  - `TrustedProxies.parse(entries)` builds a tuple of `ipaddress.ip_network(e, strict=False)`.
    It is cached on the settings tuple, so it is parsed once.
  - `get_client_ip`:
    1. no proxies configured: return `direct_ip`;
    2. `direct_ip` not trusted: return `direct_ip`, which is the fix;
    3. walk `X-Forwarded-For` from the right, skipping trusted entries;
    4. return the first entry that parses as an IP;
    5. an unparsable entry, or a chain that is all trusted, returns `direct_ip`.
  - **Runbook check, shipped in this PR.** `TRUSTED_PROXIES` must contain the real proxy address,
    for example the Caddy container's network. If it does not, every user shares the proxy's
    bucket. After deploy, check that two clients log different resolved IPs.
- **SEC-21, `api/routes/feedback.py`:**
  - Add `dependencies=[Depends(check_rate_limit)]`.
  - `rating: Literal["up", "down"]`.
  - A `field_validator` rejects `context` whose `json.dumps` length exceeds
    `FEEDBACK_CONTEXT_MAX_BYTES = 8192`, a new constant in `core/constants_limits.py`.
- **SEC-22.** Each of these sites logs the exception, at `info` for auth and `warning` otherwise,
  and returns a fixed message: `dependencies.py:L314` ("Authentication failed"),
  `api/__init__.py:L781` ("Search unavailable"), `uploader.py:L548-551`, and `admin.py:L179` and
  `L214`.

**Tests first:**

- `test_untrusted_peer_cannot_spoof_xff`: this fails today.
- `test_cidr_trusted_proxy`, `test_ipv6_chain`.
- `test_feedback_rejects_bad_rating` and `test_feedback_rejects_oversized_context`.
- `test_feedback_rate_limited`.
- `test_auth_failure_hides_exception_text`.

### PR 8: `fix/audit5-ui-history` (UI-13, UI-14, UI-15, LEAN-15)

- **UI-13, `ui-next/src/lib/db.ts`:**
  - Keep one `Promise<IDBPDatabase<ARADB>>` per owner in module state.
  - In `openDB` options:
    - `blocking() { db.close(); reset(); }`. This also closes the connection in other tabs when
      `deleteDB` runs.
    - `terminated() { reset(); }`.
  - `setHistoryOwner` closes and resets when the owner changes.
  - `deleteHistory(userId)` closes the cached connection first when it belongs to `userId`, then
    calls `deleteDB(name, { blocked() { console.warn(...) } })`.
- **UI-14.** Move `migrate` to `ui-next/src/stores/app-store-migrate.ts` as `migrateAppStore`,
  import it in `app-store.ts`, and import it in the test. Delete the inline copy. Add an assertion
  that `autoMethodAlways` is preserved.
- **UI-15.** `nextCursor` becomes `{ timestamp: string; id: string }`. Resuming opens the index
  cursor at `IDBKeyRange.upperBound(timestamp)`, calls `cursor.continuePrimaryKey(timestamp, id)`,
  and skips that one record when its primary key equals `id`. Update the caller in
  `hooks/useConversationHistory` to the new cursor type.
- **LEAN-15.** `npm uninstall rehype-highlight`. Grep again first.
- **Test infrastructure.** If `fake-indexeddb` is not already in `ui-next/package.json`
  devDependencies, add it there. It is dev-only, and it is the standard way to test `idb` under
  vitest.

**Tests first:**

- `db.test.ts`: `deleteHistory resolves while a connection is open`. This hangs today, so the test
  has a 2 s timeout.
- `db.test.ts`: `paging returns every row when timestamps tie across a page boundary`.
- `app-store.migrate.test.ts` against the real function.
- Verify with `npx tsc --noEmit`, `npx vitest run`, `npx eslint .` and `npm audit`.

### PR 9: `chore/audit5-lean-gates` (LEAN-14, OPS-10)

- **LEAN-14:**
  1. **Pin first.** Add characterization tests that freeze today's response shapes of
     `/api/weather`, `/api/stocks`, `/api/calculate` and `/api/discover`. Run
     `tests/test_security.py`'s calculator cases against the **registry** calculator. If any of
     them fails, fix the registry calculator before deleting anything; its `asteval` setup is what
     remains.
  2. **Adapt.** `api/routes/legacy_widgets.py` keeps its paths and calls the registry through the
     same `ExecuteWidgetCommand` path that `/api/widgets/execute` uses (`routes/widgets.py:L104-120`).
     It maps the result to the pinned shapes.
  3. **Delete.** Remove `infrastructure/widgets_legacy.py` and `src/reasoner/widgets.py`, and the
     `SafeExpressionError` allowlist entry in `tests/architecture/test_layer_boundaries.py:L241`.
     Repoint `test_security_regression.py`, `test_widget_guards.py` and
     `unit/test_widget_and_image_signals.py`.
  4. Update `map-infrastructure` and `map-reasoner-root`.
- **OPS-10:**
  - Run `python scripts/vulture_ratchet.py --max <current>` on Python 3.14, the CI interpreter,
    and record the count.
  - Delete `continue-on-error: true` (`test.yml:L339`), and move the step in `ci-local.sh:L66`
    from `advisory` to `gate`.
  - Lower `--max` by what LEAN-14 removed.
  - Rewrite the step name and comment so they no longer say "ADVISORY".

---

## 3. Order and parallelism

```
audit-4 PR 1 (settlement) ──► PR 3 billing-ledger   (shares CreditSink.settle, the quota increment, run_metering)
PR 1 run-admission ─────────► PR 3                  (shares admit_run and _admit_mcp_caller)
PR 2 cross-worker stop ─┐
PR 4 event retention    │
PR 5 run cache          ├─ independent of each other and of PR 1
PR 6 neuro freshness    │
PR 7 edge hardening     │
PR 8 UI history         ┘
            PR 9 lean and gates   (last: its vulture --max depends on the others)
```

- PR 1, PR 2 and PR 4 each edit a different block of `api/__init__.py`: the search route, the
  stop route, and the lifespan. Merge them one at a time and rebase in between.
- With audit-4 PR 1 merged, the new reserve sites in PR 1 use `settlement_sink()`, and audit 4's
  guard test, which forbids `CreditSink()` outside `run_observability.py`, covers them. Before
  then they use `CreditSink()`.
- Audit-4 PR 4 (the pool budget) touches `dependencies.py`, and so does PR 3's quota change.
  Whichever lands second rebases.

Estimated size:

| PR | Size |
|----|------|
| PR 1 | about 180 lines of code plus 250 of tests, plus a migration |
| PR 2 | about 120 plus 150 |
| PR 3 | about 220 plus 260 |
| PR 4 | about 90 plus 120 |
| PR 5 | about 80 plus 110 |
| PR 6 | about 30 plus 60 |
| PR 7 | about 60 plus 90 |
| PR 8 | about 70 plus 90 (TypeScript) |
| PR 9 | removes about 600 lines; adds about 80 of characterization tests |

## 4. Deploy steps (each ships in its PR's runbook section)

Append to `docs/DEPLOY_AUDIT_2_3.md` under a new "Audit 5" heading, in the same PR as the change.

| PR | Step |
|----|------|
| PR 1 | Run `alembic upgrade head`, which applies the `run` scope backfill. Announce that new keys can opt out of `run`, and that existing keys are unchanged. |
| PR 2 | Confirm that Valkey is reachable from every worker. Without it, Stop stays per worker, as today. |
| PR 3 | Enable `charge.refunded`, `charge.dispute.created` and `charge.dispute.closed` on the Stripe webhook endpoint, and `PAYMENT.SALE.REFUNDED` and `PAYMENT.SALE.REVERSED` on PayPal. |
| PR 3 | Expect the spend totals to start from zero once they move to Valkey. |
| PR 4 | Schedule `POST /api/admin/compaction/run` daily. Run it once by hand, then check the deleted count and the table size. |
| PR 4 | Alert on `reasoner_compaction_last_success_timestamp` going stale. |
| PR 5 | Set `RUN_CACHE_MAX_AGE_SECONDS` and `RUN_CACHE_WEB_MAX_AGE_SECONDS` if the defaults do not suit. The v8 key turns every existing entry into a miss once. |
| PR 7 | Check `TRUSTED_PROXIES` against the real proxy address before deploy, then confirm that resolved client IPs differ between two clients. |

## 5. Decisions needed

| # | Question | Recommendation |
|---|----------|----------------|
| Q1 | Key scope for starting runs: a new `run` scope, or require the existing `write`? | **A new `run` scope, in `DEFAULT_SCOPES`, backfilled onto every existing key.** No key breaks, and a read-only key becomes possible. Requiring `write` would break every default key used for agent runs today. |
| Q2 | Flat prices for search, smart search, image preview and gate | **[INPUT REQUIRED: per-call fees for Brave, Tavily and Perplexity Sonar on the plans in use.]** The repo has no provider pricing for search APIs. The LLM part (smart-search decomposition, the prompt enhancer, HyperGate) can be priced from the model price table that `estimate_service` already uses. |
| Q3 | Monthly USD cap against the credit allowance | **Derive the cap from the allowance × 1.2 for paid tiers.** Keep FREE at $0.50, because it also bounds anonymous callers. The alternative, lowering the PRO allowance to $8, changes what customers bought. |
| Q4 | Refund and dispute policy | **A full refund or a lost dispute cancels and claws back the unspent part of this period's grant. A partial refund changes nothing and is logged. An open dispute sets `past_due`, and a won dispute restores `active`.** |
| Q5 | Does a failed run use up quota? | **No.** Hold at admission, and give it back when the run settles at zero cost. That matches today's "count only charged runs" behaviour, without the race. |
| Q6 | Event retention | **Prune version-0 audit rows now.** Leave versioned rows until aggregate loading goes through snapshots (`handlers.py:L324`, `L456` use full history today). That would be a separate plan. |
| Q7 | Cache limits | **`RUN_CACHE_MAX_EVENTS=2000`, `RUN_CACHE_MAX_AGE_SECONDS=604800` (7 days), `RUN_CACHE_WEB_MAX_AGE_SECONDS=3600`.** |
| Q8 | Feedback from anonymous users | **Keep it anonymous, now rate-limited and size-capped.** Requiring sign-in would drop landing-page feedback. |

## 6. Verification for every PR

- The new failing test is quoted in the PR body, then shown passing.
- `python -m pytest tests/ -m "not slow and not integration" -n auto --dist loadscope` passes.
- Live-PG tests run against `reasoner-pg-test` (:55499) for PR 1, PR 3 and PR 4.
- `lint-imports` passes, with no new `ignore_imports`. The contract-2 count is re-measured and
  never higher.
- For PR 8: `npx tsc --noEmit`, `npx vitest run`, `npx eslint .` and `npm audit` all pass.
- CI is green on the exact head SHA before `gh pr merge --merge --match-head-commit`.
- Ratchet limits are lowered where a PR improved them. Map skills are updated as
  `scripts/check_skill_maps.py` reports.

## 7. Not covered

- Nothing in this plan was run, and nothing was load-tested.
- Items marked **A** rest on sub-agent reading. Their PRs re-read them first.
- These parts were not read by the audit: the Next.js `src/app/api/**` proxy routes and
  `security-server.ts`, `auth.py`, `auth_legacy.py`, `sanitization.py`, `rate_limiter.py`, CORS
  and CSP setup, the PayPal adapter in detail, most of `postgres_store.py`, the near-copy question
  for `phases/` and `flows/*_phases.py`, and whether search-provider fees reach `total_cost_usd`.
- Accepted residuals:
  - versioned events still grow by a few rows per run (Q6);
  - a partial refund keeps its credits (Q4);
  - Stop needs Valkey to work across workers;
  - on a network file system with coarse mtimes, Neuro can still read a turn late, by up to that
    file system's timestamp granularity.
