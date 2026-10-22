# Fourth Whole-Repo Audit: Remediation Plan

**Date:** 2026-10-22
**Status:** Draft for review. Revised the same day after an independent review; section 8 lists
what that review changed.
**Source:** the read-only `/ponytail-audit` run on 2026-10-22 against `main` (`d1c94d7f`). Every
finding was re-read for this plan, and two came out larger than the audit report said:

- **PER-13** (the Postgres pools) is a whole-process connection budget problem, not only a pool
  that is sized by whichever call comes first.
- **DAT-16** (the upload hash index) also leaks data: erasing a user leaves their content hashes in
  the index.

**Supersedes:** nothing. Audit 3 (`audit-remediation-3-2026-10-21.md`) is fully merged. Its
section 7 gaps are not repeated here: the `GuardedValkey` rate limiter, the direct-vendor price
table, the 45 over-budget preset pairs, the Supabase CSP check and `docker build`.
**Branch target:** one branch per PR below, each cut from `main`. Section 3 gives the order.

### Architectural constraints

No item changes the Dependency Rule (CLAUDE.md §1).

- **Layering.** `.importlinter` contract 1 orders the layers so that `core` sits **above**
  `domain`, and `domain` sits above `utils`. Two rules follow from that order:
  - **`domain/` imports nothing from `core/`.** The only domain-to-core edges are declared
    exceptions for `preset_core.py`.
  - **`infrastructure/` imports nothing from `application/`.** Every
    `infrastructure -> application.ports` edge, `billing_deadletter_repo` included, is a declared
    exception. A new port that both an application service and an infrastructure adapter need
    therefore goes in **`core/ports/`**, as `CreditRepository` does.
  - Contract 2 is at **50** declared exceptions (measured 2026-10-22 with
    `scripts/count_importlinter_exceptions.py --contract 2`).
  - No PR adds an `ignore_imports` line to either contract.
- **Ratchets.** These scripts must not get worse, and any PR that improves one lowers its `--max`
  in the same PR, as #165 did:
  - silent-failure 98;
  - bandit 93;
  - vulture 372;
  - mypy 423;
  - ruff 2162.

  Every new `except` block logs through `degraded()` or re-raises.
- **Tests first.** Every item starts with a test that fails on `main` for the reason given in the
  register. The PR body quotes that failure.

---

## 0. Findings register

**Check column:**

- **R:** re-read in the main session for this plan.
- **V:** also confirmed by the independent reviewer.
- **X:** reproduced by running code.

**Severity:**

- **M:** must fix.
- **S:** should fix.
- **N:** nice to have.

### Money

| ID | Sev | Check | Where | Failure case |
|----|-----|-------|-------|--------------|
| BIL-22 | M | R | `application/services/run_metering.py:L249-286` | The true-up makes two ledger writes, each in its own `try`, and a failed write is only logged. If the release fails and the charge succeeds, the user pays the hold and the actual cost. If the release succeeds and the charge fails, the run is free. |
| BIL-23 | M | R | `run_metering.py:L147-214`, no sweeper anywhere | A worker that dies mid-run never reaches `metered()`'s `finally`. Gunicorn timeouts and OOM kills both do this. The `:reserve` row then has no `:release` row, ever. Nothing scans for such rows: `api/cron.py` only runs Neuro maintenance. |
| BIL-24 | M | R | `run_metering.py:L189-197`, `L225`; `api/dependencies.py:L733-739` | The `metered()` docstring says "a ledger outage is reconciled later". Nothing reconciles it. A settlement that fails, or hits `fail_after`/`move_on_after`, is logged and dropped. `reserve_or_402` also lets a run through unreserved when the ledger is down; if the ledger is still down when the run ends, that run is free. |
| BIL-25 | M | RV | `infrastructure/billing/webhooks.py:L226-240`, `L328-330` | An unset `STRIPE_WEBHOOK_SECRET` or `PAYPAL_WEBHOOK_ID` returns 200 `"misconfigured"`. A mistyped Stripe secret fails every signature check, and that also returns 200. The provider counts both as delivered and never retries, so upgrades and cancellations are lost. `core/settings.py:L639-647` checks other secrets in production but not these two. |

### Data rights

| ID | Sev | Check | Where | Failure case |
|----|-----|-------|-------|--------------|
| DAT-14 | M | RV | `infrastructure/persistence/user_data_pg.py:L44-46`, `L67-78` | Each table is exported with `LIMIT 1000`, newest first. A run writes about three ledger rows (reserve, release, charge), so a user with about 330 runs gets a partial ledger. Nothing in the export says it is partial. |
| DAT-15 | M | RV | `api/execution/pipeline.py:L330-349`, `history_files.py:L33` | An anonymous run saves its problem text under `history/anon/`. No route can read it, and no erasure request can name it. |
| DAT-16 | S | RV | `infrastructure/uploader.py:L37-62`, `L376-378`; `user_data_local.py:L69-76` | (a) `UploadsStore.erase` deletes the files but not the user's `{sha256: file_id}` map in `.upload_hash_index.json`, so a user's ID and content hashes survive their erasure. (b) Every upload loads and rewrites the whole cross-tenant index under one file lock. |

### Scale and persistence

| ID | Sev | Check | Where | Failure case |
|----|-----|-------|-------|--------------|
| PER-13 | S | RV | `quota_repo_postgres.py:L25-48`; `saas_router.py:L68,L179`; `api/user_data.py:L31-35`; the class-level pools in `credit_repo_postgres.py`, `api_key_repo_postgres.py`, `subscription_repo.py`, `upload_usage_repo.py`; `webhooks.py:L113`; `dependencies.py:L99` | (a) The quota pool is sized by its first caller. If export, delete or erase runs first after a restart, the pool is capped at 2 connections for that process's lifetime. (b) With `DB_POOL_SIZE=50` (`settings.py:L387`), the credit, quota and API-key pools can each grow to 50. Two workers can then open 300 or more connections, against a Postgres default `max_connections` of 100. |
| PER-14 | S | R | `history_files.py:L92-106`, `L160-173`; `scripts/migrate_history_layout.py:L31-52` | The migration writes `.layout-v2` only when `skipped == 0`. One unreadable flat file keeps the flat layout on. Every history list then parses every flat file, and every erase counts that file as failed, so no receipt is ever "completed". |

### Output integrity

| ID | Sev | Check | Where | Failure case |
|----|-----|-------|-------|--------------|
| OUT-1 | S | XV | `domain/watermark/spans.py:L17`; `tests/unit/test_watermark_properties.py:L83-93` | `_FENCED_CODE_RE = r"```.*?```"` matches the first two triple-backtick runs. With `prefix="```"` (also `"````"` and `" ```"`), it matches an empty span and leaves the real fence content unprotected, so the scrubber rewrites code. The test fails locally because `.hypothesis/examples` replays the failing example. CI has no database, so it stays green. |

### Security

| ID | Sev | Check | Where | Failure case |
|----|-----|-------|-------|--------------|
| SEC-17 | S | RV | `api/saas_router.py:L41-47` | `_check_strict_rate_limit` parses the first `X-Forwarded-For` value itself instead of calling the trusted-proxy-aware `api/client_ip.get_client_ip`. The branch is unreachable today, because both routes resolve a user first. A future route without auth would inherit a limit that a client resets by changing the header. |

### Lean

| ID | Sev | Check | Where | What |
|----|-----|-------|-------|------|
| LEAN-9 | N | RV | `api/auth_deps.py:L22-35`, `L42-47`, `L105` | `_get_rate_limiter_instance_auth_deps` has no production caller; only `tests/test_api_auth_deps.py` imports it. `require_api_key` calls `get_auth_manager()` while its siblings use the cached wrapper. |
| LEAN-10 | N | RV | `src/reasoner/pricing.py` | A shim with no importer. It is one of 23 root shims. |
| LEAN-11 | N | RV | `src/reasoner/graphify-out/` (304 files), `ui-next/graphify-out/cache/` (151 files) | 455 generated files are tracked, although `.gitignore:L82` already ignores `graphify-out/`. |
| LEAN-12 | N | RV | `history/` (77 tracked: 74 `*.json`, plus `CONTEXT.md`, `method`, `preset`) | Dev-run output, tracked in git. `.gitignore:L81` ignores `src/reasoner/history/`, not the root `history/`. |
| LEAN-13 | N | R | repo root | About 60 reports, plans and one-off scripts at the top level, for example `19tests.md`, `plan_tmp.md`, `todo.md`, `check_keys.py`, `push_to_github.py`, and a 2 MB PDF. |

---

## 1. Design principles applied

| Module | Paradigm or pattern | Where it is used |
|--------|---------------------|------------------|
| `domain/credits.py` | Pure functions as the single source of truth | Reference naming: `reservation_reference`, `release_reference`, `RESERVE_SUFFIX`. Both the metering code and the sweeper SQL take the suffix from here, so the two cannot drift apart. |
| `core/ports/settlement_outbox.py` | Port in `core`, so neither side needs an exception | `SettlementOutbox` Protocol plus the `PendingSettlementCall` value type. |
| `application/services/run_metering.py` | Decorator over the existing `SettlementSink` Protocol | `ResilientSettlementSink` adds a per-attempt deadline, one retry and an outbox fallback to `release` and `settle`. The Protocol does not change, so the existing test fakes and patch points keep working. |
| `infrastructure/persistence/settlement_outbox_files.py` | Durable outbox, one file per pending call | It needs neither Postgres (the failure being covered) nor Valkey, whose persistence and eviction settings are unknown. It writes with `utils.atomic_file`. The file name is the idempotency key. |
| `application/services/credit_reconciler.py` | Idempotent reconciler, run by the existing admin cron | It drains the outbox, then sweeps orphaned holds. Every ledger write is idempotent per `(user_id, reference_id)`. |
| `core/settings.py` | Fail fast at startup | The existing production block gets the webhook secrets. |
| Postgres pools | Fix the sizing bug, make the budget explicit; defer the merge | A shared pool would merge failure domains (section 2, PR 4). |
| `infrastructure/uploader.py` | Per-owner sharding, matching `history_files.py` | One small hash file per owner. |
| `domain/watermark/spans.py` | A pure regex fix, plus pinned `@example`s | |

Rejected options:

- **A Postgres outbox table.** It fails during a Postgres outage, the one case it is for.
- **A Valkey outbox.** `GuardedValkey` has no hash methods, and nothing guarantees persistence or
  `noeviction`.
- **`record_batch` and a `true_up` Protocol method.** Proposed in the first draft; the review
  rejected it. It breaks four test fakes and the call-sequence assertions in
  `tests/test_audit2_money_leaks.py`. A batch inside one aborted transaction cannot reuse
  `record()`'s `UniqueViolationError` re-select either. `release` and `settle` are already
  idempotent per reference, so replaying both converges without it.
- **A background `asyncio` loop per worker.** Every worker would run it. Periodic work here goes
  through the admin cron routes (`api/routes/admin.py:L105`).
- **Streaming NDJSON for the export.** It changes the response contract.

---

## 2. Work packages

### PR 1: `fix/audit4-settlement` (BIL-22, BIL-23, BIL-24)

#### Shared design

- **`domain/credits.py`.** Add the pure naming functions, with no imports from `core`:
  - `RESERVE_SUFFIX = ":reserve"` and `RELEASE_SUFFIX = ":release"`;
  - `reservation_reference(run_ref)` and `release_reference(run_ref)`.

  `run_metering.py:L260`, `L312` and `api/routes/images.py:L80` switch to them.
- **`core/constants_limits.py`.** Add these constants:
  - `ORPHANED_RESERVATION_AFTER_SECONDS = max(2 * (PIPELINE_ABSOLUTE_TIMEOUT_SECONDS +
    SETTLE_TIMEOUT_SECONDS), 1800.0)`. The 30-minute floor matters because `streaming.py:L148`
    treats a timeout of 0 as unbounded.
  - `RESERVATION_SWEEP_LOOKBACK_DAYS = 7`.
  - `SETTLE_ATTEMPT_TIMEOUT_SECONDS = 3.0`.
  - `SETTLE_TIMEOUT_SECONDS` rises from 15.0 to **20.0**.

  The time budget then works out as follows:
  - One call is at most 3 s, then 0.5 s of backoff, then 3 s, then at most 1 s to write the
    outbox: 7.5 s.
  - `_true_up` makes two calls, so 15 s in the worst case.
  - That stays below the outer 20 s backstop in `metered()` and `release_unstarted`. The outer
    deadline therefore never cuts off the outbox write.
  - `pool.acquire(timeout=10.0)` (`credit_repo_postgres.py:L163`) is cut off by the per-attempt
    deadline.
- **`core/ports/settlement_outbox.py`:**
  - `PendingSettlementCall(method: Literal["release", "settle"], kwargs: Mapping[str, Any],
    reference_id: str, failed_at: datetime)`.
  - `SettlementOutbox` is a Protocol with three methods: `put(call)`,
    `take(limit) -> list[PendingSettlementCall]` and `ack(reference_id)`.
  - Each item is one sink call, so image releases (`images.py:L79`) are covered with no special
    shape.
- **`core/ports/credit_repository.py`.** Add
  `list_open_reservations(*, suffix_reserve, suffix_release, older_than, newer_than, limit)`.
  Implement it in Postgres and in memory. The Postgres query:

  ```sql
  SELECT ... FROM credit_ledger r
  WHERE r.reference_id LIKE '%' || $1
    AND r.created_at < $3 AND r.created_at > $4
    AND NOT EXISTS (SELECT 1 FROM credit_ledger x
                    WHERE x.user_id = r.user_id
                      AND x.reference_id = left(r.reference_id, -length($1)) || $2)
  ORDER BY r.created_at LIMIT $5
  ```

  The suffixes are bound parameters taken from `domain/credits.py`.
  - Image holds (`image:<uuid>`) do not end in `:reserve`, so the sweeper never sees them. That
    is deliberate: on success an image hold *is* the charge, and no release row is written.
  - A crashed image request therefore keeps its hold as the charge. This is a documented
    residual: the estimate is small, and generation is capped at
    `IMAGE_GEN_COMPLETION_TIMEOUT_SECONDS=90`.
- **Migration `20261022_000300_open_reservation_index`.** `down_revision` is `20261021_000200`.
  - `upgrade` runs `CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_credit_ledger_open_reserve ON
    credit_ledger (created_at) WHERE reference_id LIKE '%:reserve'` inside
    `op.get_context().autocommit_block()`. A plain `CREATE INDEX` blocks ledger writes while it
    builds.
  - `downgrade` runs `DROP INDEX CONCURRENTLY IF EXISTS`.
  - `tests/integration/test_alembic_schema_contract.py` asserts that the index exists.

#### BIL-22 and BIL-24: retry, then outbox, then replay

- **`ResilientSettlementSink(inner, outbox)`** in `run_metering.py`:
  - It forwards `reserve` unchanged, so a reserve failure still reaches `reserve_or_402`.
  - It runs `release` and `settle` with the per-attempt deadline and one retry.
  - After the second failure it writes a `PendingSettlementCall` to the outbox, under
    `anyio.move_on_after(1.0)`, and calls `degraded("run_metering.unsettled", ...)`. It returns
    normally, which keeps `metered()`'s never-raise contract.
  - `_true_up` keeps calling `release`, then `settle`, so the call order the tests assert stays
    the same.
- **Why this closes BIL-22.** The two calls stay separate. Each one either succeeds or ends up in
  the outbox, and replaying an item re-runs the same idempotent call. "Paid twice" and "paid
  nothing" are therefore temporary states until the next reconcile, not permanent ones.
- **The quota increment must not repeat on replay.**
  - `CreditSink.settle` calls `quota.increment` (`run_observability.py:L81`), and
    `check_and_increment` (`quota_repo_postgres.py:L80`) has no idempotency key.
  - Add `was_existing: bool = field(default=False, compare=False)` to `CreditLedgerEntry`. Both
    repositories set it when `record` returns an existing row, on the pre-check path and on the
    `UniqueViolationError` path.
  - `CreditSink.settle` increments only when `charge_usd` returned an entry with
    `was_existing=False`.
  - The residual is an undercount, never an overcount. It happens only when an attempt committed
    on the server but timed out on the client before the increment ran.
- **One factory, `settlement_sink()`, in `api/run_observability.py`.**
  - It returns `ResilientSettlementSink(CreditSink(), file_outbox())`, and it looks up
    `CreditSink` at call time, so tests that patch it keep working.
  - All ten construction sites switch to it:
    - `dependencies.py:L718`;
    - `mcp/tools.py:L148`, `L270`;
    - `routes/agent.py:L142`;
    - `routes/context.py:L194`;
    - `routes/pipelines.py:L261`;
    - `run_admission.py:L178`;
    - `api/__init__.py:L594`, `L650`;
    - `routes/images.py:L47`, `L79`.
  - A new architecture test, `tests/architecture/test_settlement_sink_factory.py`, fails when
    `CreditSink()` appears outside `run_observability.py`. That catches the eleventh site.
- **`infrastructure/persistence/settlement_outbox_files.py`:**
  - The directory is `settings.SETTLEMENT_OUTBOX_DIR`. It defaults to `settle_outbox/` next to
    `EVENT_STORE_DB_PATH`, which deployments already mount, and it must be on the shared volume.
  - `put` writes `<sha256(reference_id)>.json` with `atomic_write_text`. A repeat `put`
    overwrites.
  - `take` lists the oldest files first, and `ack` unlinks.
  - A crash between `take` and `ack` replays the item, which the ledger absorbs.
- **`reserve_or_402`'s fail-open branch** (decision Q2): kept. Add a counter,
  `reasoner_reservation_skipped_total`, so an outage is visible. The unreserved run's `settle`
  now ends up in the outbox if the ledger is still down.

**Tests first:** `tests/test_audit4_settlement.py`:

- `test_hung_settle_lands_in_outbox`: the inner `settle` sleeps forever. The outbox holds one item
  within about 7.5 s, and the stream completes. This is the outage case the first draft missed.
- `test_settle_retries_then_succeeds`.
- `test_release_unstarted_failure_lands_in_outbox`.
- `test_replay_does_not_double_increment_quota`: settle, then replay the same call; the quota is
  incremented once.
- The existing fakes in `tests/test_run_metering.py`, `test_audit2_money_leaks.py`,
  `test_audit2_run_identity.py` and `test_images_metering.py` must pass unchanged. That proves
  the Protocol is untouched.

#### BIL-23: reconciler and cron route

- **`application/services/credit_reconciler.py`:** `reconcile(sink, credit_repo, outbox, *, now,
  lookback_days, batch=200) -> ReconcileReport`.
  - **Step 1:** drain the outbox through the *inner* sink. The reconciler must not write back to
    the outbox it is draining.
  - **Step 2:** `list_open_reservations(...)`, then a release under `release_reference(...)` with
    the description `"Orphaned reservation released"` (decision Q1).
  - The loop continues past a failing row. Starvation needs 200 permanently failing rows, and those
    would show up in the `errors` counter.
- **`POST /api/admin/cron/credit-reconcile?lookback_days=7`** in `api/routes/admin.py` calls
  `api/cron.py::run_credit_reconciliation()`, built like `neuro-maintenance`.
  - The first run after deploy passes a larger `lookback_days`, so holds older than 7 days are
    recovered once.
- **Metrics.** `REASONER_CRON_HEARTBEAT_TIMESTAMP` (`infrastructure/metrics.py:L227`) is one
  unlabelled gauge that the Neuro job also sets, so it cannot show this job ran. Add:
  - `reasoner_credit_reconcile_last_success_timestamp`;
  - `reasoner_credit_reconcile_total{outcome="settled|released|error"}`;
  - `reasoner_settlement_outbox_depth`.
- Two workers running the reconciler at once is safe: the ledger is idempotent, and the balance
  row lock serialises the writes.

**Tests first:**

- `test_orphaned_reservation_is_released_once`: a row 35 minutes old gets one release. A second
  run adds nothing.
- `test_live_reservation_is_not_swept`.
- `test_image_hold_is_not_swept`.
- `test_threshold_has_floor_when_timeout_is_zero`.
- `test_outbox_drained_through_inner_sink`.

### PR 2: `fix/audit4-webhook-config` (BIL-25)

- **`core/settings.py`.** Add these checks next to the production block (`L639-647`):

  ```python
  if settings.ENVIRONMENT == "production":
      if settings.STRIPE_SECRET_KEY and not os.getenv("STRIPE_WEBHOOK_SECRET"):
          raise RuntimeError("STRIPE_WEBHOOK_SECRET must be set when Stripe is configured in production.")
      if os.getenv("PAYPAL_CLIENT_ID") and not os.getenv("PAYPAL_WEBHOOK_ID"):
          raise RuntimeError("PAYPAL_WEBHOOK_ID must be set when PayPal is configured in production.")
  ```

- **Missing secret** (`webhooks.py:L238-240`, `L328-330`): return 503 with `Retry-After: 300`, so
  the provider retries for up to about three days. Once the secret is set, the backlog drains.
- **Bad Stripe signature** (`L232-236`): return 400. Stripe then shows the failure and retries it.
  An invalid JSON payload (`L229-231`) keeps its 200, since a retry cannot fix a malformed body.
  PayPal is unchanged, because its verification failure already raises for a retry.
- **Runbook step, shipped in this PR:** set both secrets before deploying.
  `docker-compose.yml:L95` (`ENVIRONMENT=production`) already passes both Stripe variables.

**Tests first:** update `tests/test_saas_stripe_webhooks.py` and
`tests/test_paypal_webhook_verification.py`.

- Missing secret: expect 503. Bad signature: expect 400.
- New `tests/test_settings_production_webhooks.py`: reload settings with `ENVIRONMENT=production`,
  `STRIPE_SECRET_KEY` set and no webhook secret, and expect `RuntimeError`.

### PR 3: `fix/audit4-data-rights` (DAT-14, DAT-15, DAT-16)

#### DAT-14: complete export (decision Q3)

- **`PgUserDataStore.export`** reads keyset batches of 1000, ordered by `(order_by, id)`, until a
  batch comes back short. `id` is the UUID primary key on `query_log` and `credit_ledger`.
  `subscriptions` keeps a single read.
- **There is no silent cap.** A per-table ceiling of 1,000,000 rows stays only as an OOM guard.
  Hitting it raises, so the all-or-nothing `UserDataExporter` fails loudly with "export
  incomplete", and the case is handled by hand. A labelled partial export is still a partial
  subject-access answer.
- The test goes in the existing `tests/integration/test_user_data_pg.py`.

**Tests first:** `test_export_returns_every_ledger_row`. Seed 2,500 ledger rows and expect 2,500
back; it fails today with 1,000.

#### DAT-15: no anonymous history

- `_record_history` returns early when `user_id is None`.
- `HistoryFileRepository._save` raises `ValueError` for owner `None`.
- **Runbook step, shipped in this PR:** delete `history/anon/` (decision Q5).

**Tests first:** `test_anonymous_run_writes_no_history`.

#### DAT-16: per-owner hash index

- **Hash file location.** Use `UPLOAD_DIR / ".hash_index" / f"{owner_key(user_id)}.json"`.
  `owner_key` is imported from `history_files.py`; infrastructure-to-infrastructure is legal. The
  first draft moved it to `utils/`, but that would break `scripts/migrate_history_layout.py:L30`
  and two test files.
- **Read and write paths.** `_record_hash` and the lookup at `L376-378` touch only that owner's
  file.
- **Erase.** `UploadsStore.erase` calls a new `uploader.forget_hashes(user_id)`.
- **Old global index.** Delete it once, behind a `.hash_index/.v2` marker. Losing the index is
  already covered by `test_usage_survives_losing_the_hash_index`.

**Tests first:**

- `test_erase_removes_upload_hashes`.
- `test_hash_index_is_per_owner`.
- Update `tests/test_audit2_storage.py:L55`.

### PR 4: `fix/audit4-pg-pool-budget` (PER-13, decision Q6)

The smallest complete fix. It needs no shared pool.

- **(a) First-caller sizing.**
  - Remove `pool_size=2` from `saas_router.py:L68`, `L179` and `api/user_data.py:L35`.
  - Make `PostgresQuotaRepository` size its class pool from settings, never from the first
    instance's argument. The class-level pool already makes the argument meaningless after the
    first call.
- **(b) Explicit budget.**
  - Add `SAAS_DB_POOL_SIZE` (default 10). The credit, quota, API-key, subscription and
    upload-usage pools use it. The callers are:
    - `dependencies.py:L517`, `L556`, `L581`;
    - `billing_router.py:L51`, `L111`;
    - `billing_service.py:L88`;
    - `stripe_adapter.py:L263`;
    - `spend_limit_service.py:L378`;
    - `upload_usage_repo.py:L150`.
  - `DB_POOL_SIZE` (50) keeps meaning the event store pool (`event_store.py:L869`), so its
    throughput does not change silently.
  - The runbook states the rule, shipped in this PR:
    `workers × (5 × SAAS_DB_POOL_SIZE + 3 + 5 + DB_POOL_SIZE + 2) ≤ max_connections − 10`. The
    3 is the webhook pool, the 5 the provision pool, and the 2 the health pool.
- **Deferred: one shared pool.** It is the cleaner end state, but the review found four costs:
  - It merges failure domains, so a settlement storm would starve auth, quota and webhook
    lookups.
  - Its tests must be rewritten: `test_saas_preset_tier_enforcement.py:L601-736` and
    `test_audit2_billing_pg.py:L49-50` exercise the subscription pool internals.
  - It needs shutdown hooks in `main.py:L364` and `headless.py:L263` as well as `api/__init__.py`.
  - It must keep `webhooks._get_webhook_pool`'s "no `DATABASE_URL`" path and its DDL-on-create,
    and terminate stale loop-bound pools.

  Revisit it only if the budget in (b) proves too coarse.

**Tests first:** `test_quota_pool_not_sized_by_first_caller`. Call the export path first, then a
quota check, and assert `max_size == SAAS_DB_POOL_SIZE`. It fails today with 2.

### PR 5: `fix/audit4-small-correctness` (PER-14, OUT-1, SEC-17)

- **PER-14.**
  - `migrate_history_layout.py` renames every file it cannot attribute to
    `<name>.corrupt-<ts>`: unreadable files (`OSError`), unparsable files (`ValueError`), and JSON
    that is not a dict (the `AttributeError` case). That suffix falls outside the `*.json` glob.
  - It writes the marker when every remaining `*.json` file has moved.
  - Only a rename that itself fails still blocks the marker, and the script prints it.

  **Test first:** `test_unreadable_file_does_not_block_marker`, with three cases: corrupt, a list
  instead of a dict, and unreadable.
- **OUT-1.**
  - `_FENCED_CODE_RE = re.compile(r"(`{3,}|~{3,}).*?(?:\1|\Z)", re.DOTALL)`. An opening run of N
    closes only on N or more, and an unclosed fence runs to the end of the text, as in
    CommonMark.
  - Pin these examples: `@example(prefix="```", suffix="")`, `@example(prefix="````",
    suffix="")` and `@example(prefix=" ```", suffix="")`.
  - Add an explicit test in `tests/unit/test_watermark_spans.py`. With this change, an unclosed
    fence exempts the rest of the text from normalization.

  **Test first:** the `@example`s, added before the regex change.
- **SEC-17.** Replace the hand-rolled parse with `get_client_ip(request)`.

  **Test first:** with no user, a spoofed `X-Forwarded-For` from an untrusted peer is keyed by the
  peer address.

### PR 6: `chore/audit4-lean` (LEAN-9 to LEAN-13)

It holds no behaviour change.

- **LEAN-9.** Delete `_get_rate_limiter_instance_auth_deps` and its test. Give `require_api_key`
  the same accessor its siblings use; if `get_auth_manager()` is already cached, delete the
  wrapper instead. Lower the vulture `--max`.
- **LEAN-10.** Delete `src/reasoner/pricing.py` and fix the comment at
  `test_regression_BUG002_pricing.py:L12`.
  - Run the same importer grep over the other 22 shims: `src/`, `tests/`, `scripts/`, the root
    `*.py` files, `pyproject.toml`, `.github/` and `ui-next/`.
  - Keep `server_check.py`, which `start_all.py` runs as a script, and keep `models.py` and
    `pipeline.py` while anything imports them.
  - Update `map-reasoner-root`.
- **LEAN-11.** `git rm -r --cached src/reasoner/graphify-out ui-next/graphify-out`.
- **LEAN-12.** Add `/history/*.json`, `/history/method` and `/history/preset` to `.gitignore`,
  after checking that the last two are runtime output. Then `git rm --cached` them and keep
  `history/CONTEXT.md` tracked.
- **LEAN-13** (decision Q4). Move documents to `docs/archive/`, and delete unreferenced one-off
  scripts.
  - Before each move, grep `README.md`, `CLAUDE.md`, `AGENTS.md`, `CONTEXT.md`, `docs/` and
    `.github/`.
  - Keep `Caddyfile*`, `DEPLOY.md`, `docker-entrypoint.sh`, `mcp_server.py`, `ENCRYPTION.md` and
    `SAAS.md` unless the grep shows they are dead.

---

## 3. Order and parallelism

```
PR 1 settlement ─┐
PR 2 webhooks    ├─ independent, any order
PR 3 data rights ┤
PR 5 small fixes ┘
      PR 4 pool budget  (after PR 1, PR 2, PR 5: shares dependencies.py, settings.py, saas_router.py)
            PR 6 lean   (last)
```

Estimated size:

| PR | Size |
|----|------|
| PR 1 | about 250 lines of code plus 250 of tests, smaller than the first draft |
| PR 2 | about 40 plus 60 |
| PR 3 | about 110 plus 120 |
| PR 4 | about 40 plus 40 |
| PR 5 | about 40 plus 70 |
| PR 6 | removes about 600 tracked files and about 40 lines |

## 4. Deploy steps (each ships in its PR's runbook section)

Each PR appends its own steps to `docs/DEPLOY_AUDIT_2_3.md`, under a new "Audit 4" heading. The
first draft put them all in PR 6, which would have been too late.

| PR | Step |
|----|------|
| PR 2 | Set `STRIPE_WEBHOOK_SECRET` and `PAYPAL_WEBHOOK_ID` wherever those providers are configured. Without them the build refuses to start in production. |
| PR 1 | Run `alembic upgrade head`, which applies `20261022_000300` (built concurrently). |
| PR 1 | Put `SETTLEMENT_OUTBOX_DIR` on the shared volume. |
| PR 1 | Schedule `POST /api/admin/cron/credit-reconcile` every 10 minutes. Run it once by hand with `lookback_days=90`. |
| PR 1 | Alert on `reasoner_credit_reconcile_last_success_timestamp` going stale, on `reasoner_settlement_outbox_depth > 0` for more than 30 minutes, and on a steady non-zero `released` count, which means runs are dying mid-flight. |
| PR 3 | Delete `history/anon/`. |
| PR 4 | Check the connection budget formula against Postgres `max_connections`. |
| PR 5 | Re-run `scripts/migrate_history_layout.py --apply`. |

## 5. Decisions needed

| # | Question | Recommendation |
|---|----------|----------------|
| Q1 | An orphaned hold, from a run that died with unknown spend: release it in full, or keep it as the charge? | **Release in full.** The spend is unknown, the crash is ours, and the 2026-09-03 policy bills *actual* spend. |
| Q2 | When the ledger is down at reservation: keep letting runs through unreserved, or return 503? | **Keep fail-open.** The settlement now lands in the outbox, and overdraft blocks the next run. |
| Q3 | Export size? | **Batched, complete reads.** A 1M-row guard fails loudly; there is no silent cap. |
| Q4 | Root clutter: archive or delete? | **Archive documents, delete unreferenced scripts.** |
| Q5 | Existing `history/anon/` data? | **Delete it on deploy.** |
| Q6 | Postgres pools: an explicit budget now, or one shared pool? | **Budget now** (PR 4 as written). Defer the shared pool. |

## 6. Verification for every PR

- The new failing test is quoted in the PR body, then shown passing.
- `python -m pytest tests/ -m "not slow and not integration" -n auto --dist loadscope` passes.
- The live-PG tests run against `reasoner-pg-test` (:55499) for PR 1, PR 3 and PR 4.
- `lint-imports` passes in CI, with no new `ignore_imports`.
- CI is green on the exact head SHA before `gh pr merge --merge --match-head-commit`.
- Ratchet limits are lowered where the PR improved them, and map skills are updated as
  `scripts/check_skill_maps.py` reports.

## 7. Not covered

- Nothing in this plan was run under load.
- These parts are still unread: `ui-next/`, most of `application/flows` and `phases/`, HyperGate,
  Neuro internals, provider routing, the Stripe and PayPal adapters in detail, the SDK, and
  migrations before `20261021_000200`.
- Unused Python dependencies were not checked.
- The residuals named above are accepted, not fixed:
  - a crashed image request keeps its hold as the charge;
  - a client-side timeout after a server-side commit undercounts quota by one;
  - a settlement fails silently only when the ledger *and* the shared volume both fail.

## 8. Changes after independent review (2026-10-22)

A separate agent checked the first draft against the code. Its findings that held up, and how
the plan changed:

| # | Finding | Change |
|---|---------|--------|
| 1 | The outbox write sat inside the 15 s outer deadline, so a hung `pool.acquire(timeout=10)` would cancel it, and the outage case would never reach the outbox. | Added the per-attempt deadline and the budget arithmetic, and raised `SETTLE_TIMEOUT_SECONDS` to 20. `release_unstarted` is covered. |
| 2 | Two layering errors: `domain -> core` and `infrastructure -> application.ports`. | The constants moved to `core/constants_limits.py`, and the port moved to `core/ports/`. |
| 3 | Replay would double-increment quota. | Added `was_existing` on the ledger entry. |
| 4 | `record_batch` and a `true_up` method would break four test fakes and the sequence assertions. | Dropped. The Protocol stays the same, and convergence comes from replaying the idempotent calls. |
| 5 | Image holds are invisible to the sweeper, and the outbox had no shape for a release. | The outbox item is now one generic sink call. Image holds are excluded on purpose, as a documented residual. |
| 6 | The shared cron heartbeat gauge cannot show the reconciler ran. | Added dedicated metrics. |
| 7 | Smaller defects. | The migration uses `CONCURRENTLY` and has a downgrade. The orphan threshold has a floor, the SQL suffix is a parameter, and the lookback has a backfill path. Ten call sites are listed, not eight, plus a guard test. |
| 8 | PER-13 had missed callers, test churn, shutdown hooks and a merged failure domain. | PR 4 became a budget fix, and the shared pool is deferred (Q6). |
| 9 | PR ordering. | PR 4 now waits for PRs 1, 2 and 5. The `owner_key` move is dropped. Runbook steps ship with their own PRs. |
| 10 | PER-14 also needs `OSError` and non-dict files handled. | Both are handled. |
| 11 | OUT-1 needed more pinned examples and an explicit test for an unclosed fence. | Added both. |
| 12 | DAT-14's ceiling was still a partial answer. | It now fails loudly. |
| 13 | The Valkey outbox's durability was unknown. | It is a file outbox on the shared volume instead. |
| 14 | LEAN-12's counts and `.gitignore` claim were wrong. | Corrected. |
