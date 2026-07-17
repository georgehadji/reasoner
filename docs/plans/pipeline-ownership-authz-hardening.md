# Plan: Pipeline Ownership Authorization Hardening

**Status:** Draft
**Author:** (agent-drafted)
**Date:** 2026-07-17
**Scope:** Replace the JSON-file pipeline-ownership store with the event-store DB,
close the fail-open authorization gap, fix the mis-targeted WebSocket authz test,
repair GDPR erasure, and remove the dead half-migration.

---

## 1. Problem statement

Pipeline ownership — who is allowed to read/stop/resume a pipeline run — is
persisted in a JSON file (`src/reasoner/domain/history/pipeline_owners.json`)
via `reasoner.domain.pipeline_owner`. This has three linked defects, one of
which is a live authorization vulnerability.

### 1.1 Fail-open authorization (HIGH — security)

`_get_pipeline_owner()` swallows **every** exception and returns `None`
(`domain/pipeline_owner.py:22-26`): missing file, corrupt JSON, partial write,
permission error — all read as "no owner".

Every consumer treats `owner is None` as **allow**:

- `api/routes/pipelines.py:29` — `_check_pipeline_ownership` → `return True`
  ("legacy pipelines without an owner are world-accessible"). Gates
  `GET /api/pipelines/{id}`, stop, resume-stream, and status (lines 84, 111,
  138, 211).
- `api/routes/pipelines.py:70` — list-pipelines filter admits `owner in
  (None, user_id_str)`.
- `infrastructure/websocket/manager.py:434,488` — `owner is not None and owner
  != user_id` → a `None` owner authorizes the subscription.

Consequence: if the JSON file is lost or corrupted (guaranteed on any ephemeral
container without a mounted volume — the file is written to the source tree
under `domain/history/`), **every pipeline becomes world-readable and
world-controllable**. This is fail-open on an auth path.

### 1.2 GDPR erasure silently no-ops (HIGH — compliance)

`event_store.list_aggregate_ids_for_user()` (`event_store.py:622-637`) also
scans the JSON file and returns `[]` on any error. It is the first step of
`data_eraser.py:47` (right-to-erasure). A missing/corrupt file ⇒ erasure
reports success while deleting nothing. Same root cause as 1.1.

### 1.3 Dead half-migration (MEDIUM — correctness/clarity)

A `pipeline_owners` SQL table is already created in
`event_store_connection.py:90-95` (`pipeline_id PK, user_id, run_id,
created_at`) but is **never read or written** — grep for INSERT/SELECT against
it returns nothing. The migration to the DB was started and abandoned; the JSON
path is still the source of truth. This is the intended destination for the fix.

### 1.4 Mis-targeted WebSocket authz test (HIGH — test integrity)

`tests/test_websocket_authz.py` patches `reasoner.api.history._get_pipeline_owner`
(lines 39, 65), but `manager.py:432,486` imports from
`reasoner.pipeline_owner`. The patch targets a module the code under test never
calls, so:

- `test_dynamic_subscribe_ownership_enforced` **FAILS today** (verified): the
  mock never applies, the real lookup returns `None`, fail-open authorizes, no
  error is sent.
- `test_dynamic_subscribe_same_user_allowed` **passes vacuously**: `owner=None`
  → allowed, so it would pass even if authz were entirely removed.

The one test that should have caught 1.1 is wired to the wrong module.

### 1.5 Runtime state was tracked in git (LOW — already fixed)

`pipeline_owners.json` was committed and churned on every run. Untracked +
gitignored in `b1d6254`. Listed here for completeness; no further action.

---

## 2. Architectural constraints

Per `CLAUDE.md` and the existing layout, the fix must respect:

1. **Dependency rule** — `API → Application → Infrastructure → Core → Domain`,
   dependencies point inward. Ownership persistence is I/O ⇒ it belongs in
   **Infrastructure**, behind a **port** defined in **Application** (or Core),
   consumed by API/Infra via that port.
2. **Port pattern** — mirror `application/ports/billing_deadletter_port.py`: a
   `Protocol` in `application/ports/`, a concrete adapter in
   `infrastructure/persistence/`, wired through the existing DI/singleton
   accessors (`api.get_architecture_components()` /
   `api/dependencies.py` factory style).
3. **Event store is the system of record** — `PipelineAggregate` is
   event-sourced; the `pipeline_owners` table lives in the same SQLite DB
   (`event_store_connection.py`). Ownership should be persisted there, in the
   same connection/pool, so it shares the DB's durability and is covered by the
   same GDPR delete path.
4. **import-linter** — an Infra→Application-ports edge is already an accepted
   pattern (`websocket.manager -> application.ports.auth_port`,
   `.importlinter:36`). New Infra→port edges follow precedent; adding the
   adapter needs **no** new exceptions if the port lives where the linter
   already tolerates it. Verify with `PYTHONPATH=src lint-imports --no-cache`.
5. **`--resume` / backward-compat** — keep `domain.pipeline_owner` and the
   `reasoner.pipeline_owner` shim importable during migration; do not break the
   `dict[str,Any]`-style tolerant access elsewhere.

---

## 3. Design

### 3.1 Port — `application/ports/pipeline_ownership_port.py`

```python
class PipelineOwnershipPort(Protocol):
    async def get_owner(self, pipeline_id: str) -> str | None: ...
    async def set_owner(self, pipeline_id: str, user_id: str | None, run_id: str) -> None: ...
    async def list_pipeline_ids_for_user(self, user_id: str) -> list[str]: ...
```

Notes:
- `user_id` stays `str | None` — anonymous/unauthenticated runs legitimately
  have no owner, and that must remain distinguishable from "lookup failed"
  (see 3.3).
- Async, to match the event-store adapter and the existing
  `list_aggregate_ids_for_user` async signature.

### 3.2 Adapter — `infrastructure/persistence/pipeline_ownership_repo.py`

Backed by the **existing `pipeline_owners` table** (already in the schema),
using the event-store connection/pool:

- `set_owner` → `INSERT ... ON CONFLICT(pipeline_id) DO UPDATE`. Anonymous run:
  store a sentinel (e.g. `user_id IS NULL` — but the current table has
  `user_id TEXT NOT NULL`; **migration needed**, see 3.5).
- `get_owner` → `SELECT user_id WHERE pipeline_id = ?`. Distinguish three
  outcomes: row-with-user, row-with-null (anonymous), no-row.
- `list_pipeline_ids_for_user` → `SELECT pipeline_id WHERE user_id = ?`.
- Reuse `_run_in_executor` / async pattern already in `event_store.py`.

### 3.3 Fail-closed semantics (the core security fix)

Separate "not found" from "lookup error". Ownership decisions become:

| DB result            | `_check_pipeline_ownership` | Rationale                          |
|----------------------|-----------------------------|------------------------------------|
| row, user matches    | allow                       | owner                              |
| row, user differs    | deny                        | not owner                          |
| row, `user_id` null  | allow (anonymous/legacy)    | explicitly unowned run             |
| **no row**           | **deny** (non-admin)        | unknown pipeline ⇒ fail closed     |
| **DB/lookup error**  | **deny** (raise/500)        | never fail open on infra error     |

- Admin scope still bypasses (`Scope.ADMIN`).
- The adapter must **raise** on DB errors, not swallow to `None`. Route layer
  maps the raised error to 500 (already does — `pipelines.py:73-75`), which is
  fail-closed.
- **Behavior change to flag:** truly pre-existing "legacy" runs with no row
  will now be denied for non-owners. Mitigation options, pick per product call:
  (a) one-time backfill from the JSON file into the table (3.5); (b) treat
  no-row as allow **only** for pipelines created before a cutoff timestamp.
  Recommendation: (a) backfill, then fail-closed cleanly.

### 3.4 Wiring

- Add a singleton factory (mirror `api/dependencies.py::_get_subscription_repo`
  added in `9d29bea`, and `_reset_*` for tests).
- `api/execution/pipeline.py:67` `_save_pipeline_owner(run_id, user_id)` →
  `await ownership.set_owner(run_id, user_id, run_id)`.
- `api/routes/pipelines.py` `_check_pipeline_ownership` + list filter → port.
- `infrastructure/websocket/manager.py:432,486` → port (import from
  `application.ports`, following the existing `auth_port` precedent).
- `event_store.list_aggregate_ids_for_user` → delegate to the port /
  table `SELECT`, so GDPR erasure reads the same source. Keep the method
  signature (called by `data_eraser.py:47`).

### 3.5 Data migration / backfill

- **Schema:** relax `pipeline_owners.user_id` to nullable (anonymous runs).
  SQLite can't `ALTER COLUMN`; add an idempotent migration that recreates the
  table if the NOT NULL constraint is present, or gate new writes to always
  provide a value and treat empty string as anonymous. Prefer nullable via
  table rebuild in the connection bootstrap (it already does
  `CREATE TABLE IF NOT EXISTS`).
- **Backfill:** one-shot importer that reads the JSON (if present) and upserts
  rows, so existing local/prod ownership survives cutover. Run once at startup
  behind a guard, or a `scripts/` migration.

### 3.6 Retire the JSON path

- Keep `domain/pipeline_owner.py` as a thin **deprecated** shim delegating to
  the port for one release, or delete after call sites move and the backfill
  runs. Keep `reasoner.pipeline_owner` re-export shim until external refs are
  gone.
- Remove the `_MAX_PIPELINE_OWNERS` file-eviction hack (the DB doesn't need it;
  if unbounded growth matters, prune via the GDPR delete path or a TTL job).

---

## 4. Test plan

1. **Fix `tests/test_websocket_authz.py` first (RED):** repoint the patch to
   `reasoner.infrastructure.websocket.manager._get_pipeline_owner` (or the port
   accessor the code actually calls). Confirm
   `test_dynamic_subscribe_ownership_enforced` now genuinely exercises the deny
   path. Add a case asserting **no-row ⇒ deny** (would fail today under
   fail-open) and **lookup-error ⇒ deny**.
2. **Port/adapter unit tests** (new
   `tests/test_pipeline_ownership_repo.py`): get/set/list, upsert idempotency,
   null/anonymous owner, and the three-way `get_owner` outcomes. Mirror
   `tests/test_saas_cached_subscription.py` structure.
3. **Route authz tests** (extend/one new file): owner allow, non-owner 403/deny,
   admin bypass, no-row deny, DB-error → 500 (fail closed) for status/stop/
   resume/list.
4. **GDPR erasure test:** `list_pipeline_ids_for_user` returns the user's rows;
   erasure deletes them; a lookup error propagates (does not silently report
   success). Guards `data_eraser.py`.
5. **Backfill test:** JSON with mixed owned/null entries imports into the table
   with correct mapping; idempotent on re-run.
6. Run subset per `reasoner-testing`: `PYTHONPATH=src pytest
   tests/test_websocket_authz.py tests/test_pipeline_ownership_repo.py
   tests/test_pipelines_authz.py -q` (note repo's `addopts` uses xdist; clear
   with `-o addopts=""` for single-file focus).

---

## 5. Execution order (phased, each independently shippable)

- **Phase 0 — test-truth fix (tiny, ship alone):** repoint the WebSocket authz
  patch so the existing suite actually tests authz; watch it fail, confirming
  1.1/1.4. This alone converts a vacuous test into a real regression signal.
- **Phase 1 — port + adapter + backfill + schema:** add
  `PipelineOwnershipPort`, the DB adapter on the existing table, nullable
  `user_id`, and the JSON→DB backfill. No call-site changes yet; adapter unit
  tests green.
- **Phase 2 — cut over consumers, fail-closed:** move
  `pipeline.py`, `routes/pipelines.py`, `websocket/manager.py`, and
  `event_store.list_aggregate_ids_for_user` to the port; flip no-row/error to
  **deny**. Land the fixed authz tests + GDPR test.
- **Phase 3 — retire JSON:** delete/deprecate `domain.pipeline_owner` file I/O,
  drop `_MAX_PIPELINE_OWNERS`, remove the now-unused JSON scan in
  `event_store.py`. Confirm no remaining importers of the shim.
- **Gates per phase:** `PYTHONPATH=src lint-imports --no-cache` →
  `1 kept, 0 broken`; targeted pytest green; `pytest -m "not slow and not
  integration"` for the touched areas.

---

## 6. Risk register

| Risk | Mitigation |
|------|------------|
| Fail-closed denies legitimate pre-existing runs | Backfill from JSON before cutover (3.5); optional cutoff-timestamp grace |
| SQLite lacks `ALTER COLUMN` for nullable user_id | Idempotent table rebuild in connection bootstrap; or empty-string sentinel |
| WebSocket path is sync-import today; port is async | `manager.py` handlers are already async; call `await port.get_owner()` |
| import-linter regression | Port lives in `application/ports`; Infra→ports edge already whitelisted (`.importlinter:36`) — verify, don't assume |
| Concurrent writers to same pipeline_id | `ON CONFLICT DO UPDATE` upsert is idempotent; last-writer-wins is acceptable for ownership |
| Backward-compat `--resume` / external shim importers | Keep `reasoner.pipeline_owner` re-export until Phase 3; grep for external refs first |

---

## 7. Out of scope / deferred

- The pytest `_HAS_API_KEY` guard weakness and CI `OPENROUTER_API_KEY`
  invalidity (separate CI/secrets issue; live integration tests 401 instead of
  skipping). Tracked separately.
- The pre-existing import-linter billing edges (already whitelisted on the
  tasktype branch).
- Broader event-store snapshot/aggregate table concerns noted in
  `event_store_connection.py` comments.

---

## 8. Concrete file touch-list

- **New:** `application/ports/pipeline_ownership_port.py`,
  `infrastructure/persistence/pipeline_ownership_repo.py`,
  `tests/test_pipeline_ownership_repo.py`, `tests/test_pipelines_authz.py`,
  backfill (in adapter bootstrap or `scripts/`).
- **Edit:** `api/dependencies.py` (factory + `_reset`),
  `api/execution/pipeline.py:67`, `api/streaming.py:49` (import),
  `api/routes/pipelines.py:22-31,70`,
  `infrastructure/websocket/manager.py:432-434,486-488`,
  `infrastructure/persistence/event_store.py:622-637`,
  `infrastructure/persistence/event_store_connection.py:90` (nullable user_id),
  `tests/test_websocket_authz.py:39,65` (patch target).
- **Deprecate/remove (Phase 3):** `domain/pipeline_owner.py` file I/O,
  `_MAX_PIPELINE_OWNERS`.
