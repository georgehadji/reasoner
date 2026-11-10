# Audit remediation 6 — 2026-11-10

Source: the ponytail audit of 2026-11-10 (11 findings). This plan fixes all 11 inside
Reasoner's architecture: hexagonal inner ring, ports in `core/ports` or `application/ports`,
adapters in `infrastructure/`, one admission sequence for billed runs, expand-only migrations.

Finding numbers below match the audit report. Labels: VERIFIED = read in code this session;
INFERENCE = follows from code but not executed; UNKNOWN = not checked.

## Ground rules (apply to every phase)

- **Layering.** `.importlinter` contract 2 (`application -> infrastructure`) only falls. No phase
  may add an exception. New behaviour reaches adapters through a port. New ports go in
  `core/ports/` (if `domain` types only) or `application/ports/` (existing pattern for
  billing, quota, ownership). Adapters live in `infrastructure/persistence/` or `infrastructure/valkey/`.
- **No behaviour change by accident.** Each phase is one PR, one concern, with a test that fails
  before the change and passes after. Name the test in the PR.
- **Money paths are idempotent.** Every ledger write keeps its `reference_id` idempotency key.
  Nothing may widen the window where a retried write double-charges or double-refunds.
- **Migrations are expand-only** (see `20261029_000300_api_key_run_scope.py`). `down_revision` is
  the current Alembic head; confirm with `alembic heads` before writing. Revision ids follow
  `YYYYMMDD_NNNNNN`.
- **Postgres-dependent tests** run against the local container `reasoner-pg-test` on `:55499`
  (never `:55432`, that is the user's).
- **Living docs.** After each phase run `python scripts/check_skill_maps.py`; if it reports a
  stale map, run `/update-maps` for that folder. Update `AGENTS.md` only if a rule changes
  (phase 5 and 6 do).
- **`ui-next/` is gated.** Phase 8 touches server-only files under `ui-next/src/`. Check whether
  `spec/.gate-enabled` exists; the hook needs `spec/art-direction.md` and `ui-next/src/styles/tokens.css`
  non-empty. Do not work around the hook.
- **Gate commands before each PR:** `python -m pytest tests/ -m "not slow and not integration" -n auto --dist loadscope`,
  `lint-imports`, `ruff check src tests`, and for `ui-next`: `cd ui-next && npx tsc --noEmit && npx vitest run`.

## Decisions (D1, D2, D3 approved 2026-11-10: all three recommendations accepted)

| # | Question | Recommendation | Why |
|---|----------|----------------|-----|
| D1 | Finding 4: hard quota or soft quota? | **Hard.** Claim the slot at admission, give it back if the run does not complete. | Matches how credits already work (reserve, then true-up). Soft quota means a free user can exceed the plan by running in parallel. |
| D2 | Finding 5: where do unsettled-run records go when the database is the thing that is down? | **Valkey list plus a structured ERROR log.** | Postgres cannot record "Postgres was down". Valkey is already a dependency (idempotency, anonymous cap, webhook dedup). |
| D3 | Finding 3: what if duplicate subscription rows already exist in production? | **Migration refuses and lists them.** A separate dedupe script does the deletion, run by a person. | A migration that silently deletes billing rows is irreversible. |

If D1 is answered "soft", phase 6 shrinks to a documentation change (see phase 6).

## Phase order and why

Small and independent first, shared-interface changes last.

| Phase | Findings | Depends on |
|-------|----------|------------|
| 1. Backend hygiene | 7, 8 (backend half), 9, 10 | none |
| 2. Subscription uniqueness | 3 | none |
| 3. Pipeline list per owner | 2 | none |
| 4. Auth failure is not anonymous | 6 | none |
| 5. Atomic settlement and fail-open record | 1, 5 | none, but phase 6 and 7 build on its `RunContext`/sink changes |
| 6. Quota claimed at admission | 4 | phase 5 |
| 7. Anonymous cap accounting | 11 | phase 5 |
| 8. Next.js proxy error helper | 8 (front half) | none |

Phases 1 to 4 and 8 can run as parallel sessions in separate worktrees (they touch disjoint files).
Phases 5, 6, 7 touch `run_metering.py`, `run_admission.py`, `run_observability.py` and must go in order.

---

## Phase 1 — Backend hygiene (findings 7, 8 backend, 9, 10)

**Finding 7: dead `invoice.payment_succeeded` branch.** VERIFIED: `StripeBillingAdapter.sync_subscription`
returns a placeholder with no `stripe_subscription_id` for that event, so the branch in
`BillingService._apply_webhook` never acts.

- Delete the branch at `application/services/billing_service.py:140-149`.
- Leave the event unhandled: it falls through to `logger.debug("Unhandled event type")`. Renewal and
  past_due-to-active are carried by `customer.subscription.updated`, which `sync_subscription`
  already handles by re-reading live state (BIL-15).
- Test: extend `tests/test_saas_stripe_webhooks.py` with a case that sends `invoice.payment_succeeded`
  and asserts no repository write happens.

**Finding 8 (backend half): error text leaked to callers.**

- `api/dependencies.py:315`: replace `f"Authentication failed: {exc}"` with the fixed text
  `"Authentication failed"`; keep `logger.warning(..., exc_info=True)` for the detail.
- `api/billing_router.py:87`: replace `f"Checkout creation failed: {exc}"` with a fixed message and
  status 502 (the upstream provider failed). Keep the `ValueError` to 400 branch: those messages
  are written by us and safe.
- Test: `tests/test_billing_audit_fixes.py` and the auth dependency tests assert the response body
  does not contain the exception text.

**Finding 9: `provider` unchecked.**

- Add `BillingProvider(str, Enum)` with `STRIPE`/`PAYPAL` to `domain/saas.py` next to `SubscriptionTier`.
- `billing_router.create_checkout`: type the parameter `provider: BillingProvider = BillingProvider.STRIPE`.
  FastAPI then returns 422 for any other value. Use `.value` in the URLs and drop the
  `provider.lower()` comparison.
- The Next.js proxy `ui-next/src/app/api/billing/checkout/route.ts:31-50` forwards the value as a query
  param; it needs no change if the UI only sends `stripe` or `paypal`. Confirm with a grep of the pricing page.
- Test: 422 for `provider=x&checkout=y`; 200 path unchanged for both valid values.

**Finding 10: `/api/events/stats` visible to every user.** VERIFIED in `api/routes/pipelines.py:63`.
VERIFIED: nothing in `ui-next/src` or `sdk/` calls it.

- Reuse the admin check already in the same file (`Scope.ADMIN.value in user.scopes`). Extract it once
  as a small dependency `require_admin_scope` in `api/dependencies.py` (the file already holds
  `require_key_scope`, `require_tier`) and use it for this route. `_check_pipeline_ownership` and
  `list_pipelines` can adopt the same helper later; not in this PR.
- Test: non-admin gets 403, admin gets 200 (extend `tests/test_pipelines_authz.py`).

---

## Phase 2 — Subscription uniqueness (finding 3)

VERIFIED: no unique constraint on `subscriptions.stripe_sub_id` or `paypal_sub_id`; `upsert_subscription`
selects, then inserts.

1. **Pre-check script** `scripts/check_duplicate_subscriptions.py`: lists provider ids that appear on
   more than one row. Run against production first. Output goes to the PR description.
2. **Migration** `migrations/alembic/versions/20261110_000400_subscription_provider_ids_unique.py`:
   - First statement: a `DO $$ ... $$` block that raises with the duplicate ids if any exist (D3).
   - Then `CREATE UNIQUE INDEX IF NOT EXISTS uq_subscriptions_stripe_sub_id ON subscriptions(stripe_sub_id) WHERE stripe_sub_id IS NOT NULL`
     and the same for `paypal_sub_id`. Use `CONCURRENTLY` inside `op.get_context().autocommit_block()`.
   - Downgrade drops both indexes.
3. **Adapter** `infrastructure/persistence/subscription_repo.py::upsert_subscription`: keep the existing
   SELECT (it also handles the user-id fallback, BIL-14), but make the INSERT
   `INSERT ... ON CONFLICT (stripe_sub_id) WHERE stripe_sub_id IS NOT NULL DO UPDATE SET ...` (branch on
   which provider id is set, since one statement allows one conflict target). The DO UPDATE keeps the
   monotonic guard `last_event_at <= $event_at` so the BIL-15 ordering rule is unchanged. Return value
   keeps its meaning: True when a row was written, False when the guard skipped it.
4. **Tests.** `tests/test_saas_stripe_webhooks.py` already mocks the repo; add a live test against
   `reasoner-pg-test` that fires two `upsert_subscription` calls with the same `stripe_subscription_id`
   through `asyncio.gather` and asserts exactly one row. Mark it `integration`.
5. **Rollout order.** Deploy the migration first (indexes only, code tolerant), then the adapter change.
   The adapter change is safe without the index too, so order cannot break production.

---

## Phase 3 — Pipeline list per owner (finding 2)

VERIFIED: `event_store.list_pipelines` has no owner filter; the route pages the global list then filters per
row (`api/routes/pipelines.py:84-120`). Ownership lives in SQLite (`pipeline_owners`, shares the event-store
database file); aggregates may live in SQLite (`EventStore`) or Postgres (`PostgresEventStore`). A SQL join is
therefore not portable, so the owner filter goes through ids.

1. **Port.** `PipelineOwnershipPort.list_pipeline_ids_for_user` already exists
   (`application/ports/pipeline_ownership_port.py:74`). Use it as is.
2. **Event store.** Add an optional `aggregate_ids: Sequence[str] | None = None` argument to
   `list_pipelines` in both `infrastructure/persistence/event_store.py` and `postgres_store.py`, and a
   matching `count_pipelines(status, aggregate_ids)`.
   - SQLite: `AND aggregate_id IN (SELECT value FROM json_each(?))`, one JSON parameter, so no variable limit.
   - Postgres: `AND aggregate_id = ANY($n::text[])`.
   - `aggregate_ids=[]` returns `[]` without a query.
3. **Route.** For a non-admin caller: fetch ids from the ownership repo (fail closed on error, as today),
   then call `list_pipelines(limit, offset, status, aggregate_ids=ids)` and `count_pipelines(...)` for
   `total`. Admins keep the global path. This removes the per-row `get_owner` loop (one SQLite read
   instead of up to 500).
4. **Sibling.** `application/handlers/handlers.py:484` (`GetHistoryQueryHandler`) lists pipelines with no owner
   filter and returns problem text. UNKNOWN whether anything reaches it. First grep for callers of
   `GetHistoryQuery`: if unreachable, delete the handler; if reachable, give it the same `owner_id` filter.
5. **Tests.** `tests/test_pipelines_authz.py`: three users, 60 pipelines, user B owns 3. Assert B's page with
   `limit=50` returns exactly 3, `total == 3`, offset pages correctly, and a user with none gets `[]`.
   Add one case per store type (SQLite always; Postgres under `integration`).

---

## Phase 4 — A failed login must not become an anonymous run (finding 6)

VERIFIED: `get_optional_user` swallows every exception and returns `None`
(`api/dependencies.py:318-336`). With `ENABLE_LEGACY_API_KEY=true` a revoked key, an expired token or a
database error then runs anonymously with no reservation and no billing.

Why not just make `get_optional_user` strict: it also serves `health`, `gate`, `/auth/me/optional` and the neuro
owner lookup, where a stale token must still fall back to anonymous. The single chokepoint for billed runs is
`admit_run`, so the refusal goes there (consistent with the "one admission sequence" rule).

1. In `get_optional_user`, when credentials were sent and resolution fails, record the outcome on
   `request.state.auth_failure`: `"rejected"` for an `HTTPException` (bad or revoked credential), `"unavailable"`
   for any other exception (infrastructure). Still return `None` so non-billed routes behave as before.
2. In `run_admission.admit_run`, before `require_auth_if_legacy_disabled(user)`: if `user is None` and
   `request.state.auth_failure` is set, raise 401 (`rejected`) or 503 with `Retry-After` (`unavailable`).
   Credentials never sent means no `auth_failure`, so true anonymous callers are unchanged.
3. MCP: `api/mcp/tools.py` has its own `resolve_caller` and `_run_and_bill`. Confirm `resolve_caller`
   raises `McpAuthError` on a bad credential rather than degrading to anonymous; add a test either way.
4. Tests: `tests/test_pipelines_authz.py` or a new `tests/test_admission_auth_failure.py`: with
   `ENABLE_LEGACY_API_KEY=true`, (a) revoked rsn_ key gives 401, (b) `_ensure_user_in_db` raising gives 503,
   (c) no header still runs anonymously.

---

## Phase 5 — Atomic settlement and a record when settlement is skipped (findings 1, 5)

VERIFIED: `run_metering._true_up` calls `sink.release` then `sink.settle` as two ledger writes; a failure of the
second leaves a free run, logged only. `require_credits`, `reserve_or_402` fail open on ledger errors with no
metric.

### 5a. One transaction for release plus charge (finding 1)

1. **Port.** Add to `core/ports/credit_repository.py::CreditRepository`:
   `record_batch(user_id, writes: Sequence[LedgerWrite]) -> list[CreditLedgerEntry]` where `LedgerWrite` is a small
   frozen dataclass in `domain/credits.py` (`delta, reason, reference_id, description, allow_overdraft`).
   Contract: one transaction, one balance-row lock, each write keeps its own idempotency key and returns the
   original entry on replay.
2. **Adapters.** `PostgresCreditRepository`: factor the body of `_record_locked` so the lock and balance update
   run once for the whole batch (one `SELECT ... FOR UPDATE`, entries inserted in order, balance computed
   cumulatively). `InMemoryCreditRepository`: loop under its lock.
3. **Service.** `CreditService.true_up_run(user_id, reserved_credits, cost_usd, reference_id, preset)` builds the
   refund (`ref:release`, reason `REFUND`) and the charge (`ref`, reason `PIPELINE_RUN`, overdraft allowed)
   and calls `record_batch`. Same two ledger rows, same keys, so the statement history and replays are
   unchanged. If the cost rounds to zero credits only the refund is written.
4. **Sink.** Add `true_up(...)` to `SettlementSink` (`run_metering.py`) and `CreditSink`
   (`api/run_observability.py`); `CreditSink.true_up` also calls `quota.increment` after the batch, as `settle` does.
   `_true_up` calls `sink.true_up` once. Keep `release` (used by `release_unstarted`) and `settle` (used by the
   no-reservation fallback).
5. **Outcome.** The two-write gap is gone: either both rows land or neither. If neither lands the reservation stays
   debited (the user pays the estimate, which is safe) and the run is recorded under 5b.
6. **Tests.** `tests/test_run_metering.py`: fake sink whose `true_up` raises, assert no partial write.
   `tests/test_credits.py`: live Postgres test where the charge insert is made to fail mid-batch and the refund row
   is not present (transaction rollback). Concurrency: two `true_up` with the same `reference_id` produce one pair.

### 5b. Record what could not be settled (finding 5)

1. **Metric.** In `reasoner/metrics.py`, beside the existing quota-check-failure counter, add
   `REASONER_CREDIT_FAILOPEN_TOTAL{path}` with `path` in `require_credits`, `reserve`, `settle`. Increment at the three
   places that fail open or fail to settle. Add an alert rule next to `QuotaExceededSpike` in
   `docs/monitoring/alerts.yml`.
2. **Port.** `application/ports/unsettled_run_port.py`: `UnsettledRunPort.record(user_id, reference_id, cost_usd, reserved_credits, preset, error)`.
   Adapter in `infrastructure/valkey/` pushing a JSON line to a list `unsettled_runs` (D2), plus a structured
   `logger.error` with the same fields as the fallback when Valkey is also down.
3. **Wire it.** `run_metering._settle` and the `settle_timeout` branch call the port after logging. They still never raise.
4. **Replay.** Extend `application/services/deadletter_replay_service.py` (existing replay pattern for webhooks)
   with a `replay_unsettled_runs(limit)` that calls `CreditService.charge_usd` with the stored `reference_id`
   (idempotent) and removes the entry on success. Expose it through the existing admin replay route in
   `api/routes/admin.py`.
5. **GDPR.** The list holds `user_id`. Add the key to `application/services/data_eraser.py` scope or give the entries a TTL
   (30 days) and document it in `docs/` privacy notes. Recommendation: TTL.
6. **Docstring fix.** `run_metering.metered` says "reconciled later"; after this phase that is true. Keep the sentence.
7. **Tests.** Fake port asserts `record` is called when `sink.settle` raises and when the 15 s timeout fires; replay
   test asserts a second replay is a no-op.

---

## Phase 6 — Quota claimed at admission (finding 4, decision D1)

VERIFIED: `QuotaService.check` runs when the run starts; `CreditSink.settle` calls `increment` at the end and ignores
a "denied" result. Five parallel runs at 19/20 all start.

If D1 = soft: replace this phase with a docstring on `QuotaService` and a line in `docs/` stating quota is advisory
and credits are the hard cap. Skip the rest.

If D1 = hard (recommended):

1. **Port.** `application/ports/quota_repository.py`: add `release_slot(user_id)` (decrement `used_queries`, floor at 0).
   `PostgresQuotaRepository` implements it with one `UPDATE ... SET used_queries = GREATEST(used_queries - 1, 0)`.
   `CachedQuotaRepository` forwards and invalidates its cache entry (it does the same for `reset_monthly`).
2. **Admission.** In `admit_run`, after the credit reservation succeeds and only for an authenticated caller on a
   finite tier, call `QuotaService.increment` (already atomic, `check_and_increment` under `FOR UPDATE`). Denied means
   429 and the reservation is released through the existing `except BaseException` block. Store `quota_claimed=True`
   on `Admission` and `RunContext`.
3. **Metering.** `metered`'s `finally`: if the run did not complete and `ctx.quota_claimed`, call `release_slot`
   inside the existing shielded scope. `release_unstarted` does the same. Completed runs keep the slot.
4. **Sink.** Remove `quota.increment` from `CreditSink.settle` and `true_up` when `ctx.quota_claimed` (pass a flag),
   so a run is never counted twice. Keep the increment for callers that did not claim (see MCP below).
5. **MCP and agent routes.** `api/mcp/tools.py::_run_and_bill` has its own sequence. Apply the same claim and release
   there, or route it through a shared helper in `application/services/` (preferred: one function used by both,
   per the module docstring's warning about copy/paste). Check `api/routes/agent.py` the same way.
6. **Tests.** Update `tests/test_quota_increment_is_wired.py` (it asserts the old wiring). New: 5 concurrent admissions at
   19/20 give 1 admitted and 4 refused with 429; failed run frees its slot; completed run keeps it.
7. **Docs.** `AGENTS.md`: one line stating quota is claimed at admission and released on non-completion.

---

## Phase 7 — Anonymous cap accounting (finding 11)

VERIFIED: `enforce_anonymous_trial_cap` does `INCRBY` then `EXPIRE` before the run, and a refusal later in
`admit_run` does not give the credits back. INFERENCE (extra, same code): `INCRBY` and `EXPIRE` are two calls; if the
process dies between them the key has no TTL, so that address is blocked past midnight once it exceeds the cap.

1. **Atomic increment with TTL.** Replace the two calls with `pipeline(transaction=True)` (`INCRBY` then `EXPIRE ... NX`
   where the server supports it, otherwise `SET key 0 EX ttl NX` followed by `INCRBY`). Keep fail-open on Valkey errors.
2. **Refund.** Add `refund_anonymous_trial(client_ip, estimated_cost_usd)` (`DECRBY`, floor handled by the cap check)
   in the same module. Have `enforce_anonymous_trial_cap` return the credits it counted.
3. **Use it.** `admit_run`: keep `(ip, credits)` and call the refund in the existing `except BaseException` block (409 for a
   duplicate `client_run_id`, 503 for the idempotency store, ownership conflict). Add `anon_cap` to `Admission`; the
   unstarted-stream path in `MeteredSSEResponse` refunds it through `release_unstarted`.
4. **Decision kept.** A run that starts and then fails keeps its count: provider spend was incurred (same policy as
   `metered`, 2026-09-03).
5. **Tests.** Extend the anonymous-trial tests: a 409 and a dropped-before-first-frame request leave the counter unchanged;
   a simulated crash between `INCRBY` and `EXPIRE` (pipeline mock) cannot leave a TTL-less key.

---

## Phase 8 — Next.js proxy error helper (finding 8, front half)

VERIFIED: 10 route files in `ui-next/src/app/api/` return `detail: msg` on a connection error, which includes internal
host and error text.

1. Add `proxyErrorResponse(err, label, upstreamUrl)` to `ui-next/src/lib/security-server.ts`. Behaviour: `ValidationError` gives 400
   with its message (as today); connection errors give 504 `{ error: 'Backend unreachable' }`; everything else 502
   `{ error: 'Proxy error' }`. Log the real message server-side only.
2. Replace the duplicated catch block in the 10 routes (`grep -l "detail: msg" ui-next/src/app/api`), starting with `run`,
   `upload`, `run-followup`. This also removes about 20 duplicated lines per route.
3. Check the front end does not read `detail` from those responses: grep `ui-next/src` for `.detail` handling of 502/504.
4. Tests: `ui-next/src/lib/security-server.edge-cases.test.ts` gets cases for each branch and asserts the response body has
   no hostname or error text.
5. Not visual, so the art-direction pipeline does not apply; respect the write-gate hook if armed.

---

## Verification summary

| Finding | Proof it is fixed |
|---------|-------------------|
| 1 | transaction-rollback test; no partial ledger rows |
| 2 | 60-pipeline, 3-owner pagination test on SQLite and Postgres |
| 3 | concurrent upsert gives one row; migration refuses on duplicates |
| 4 | 5 concurrent admissions at 19/20: 1 admitted |
| 5 | metric increments; unsettled record written; replay idempotent |
| 6 | revoked key gives 401, DB error gives 503, no header still anonymous |
| 7 | `invoice.payment_succeeded` is a no-op; branch deleted |
| 8 | no exception text in responses (backend and 10 proxy routes) |
| 9 | 422 for any provider other than stripe or paypal |
| 10 | non-admin gets 403 on `/api/events/stats` |
| 11 | 409 and dropped streams leave the anonymous counter unchanged; no TTL-less key |

## Not covered by this plan

Anything outside the 11 findings. The audit did not read `phases/`, `hypergate/`, `neuro/`, the LLM router and executor,
the uploader, the websocket layer, the CSRF implementation or most of the 419 test files; a second audit pass over those
may add findings.
