# Autonomous Defect-Hunt Protocol V7 — T2: Persistence & Event Sourcing

**Date:** 2026-09-01
**Worktree:** `E:\Documents\Vibe-Coding\Reasoner\.worktrees\defect-hunt` (branch `chore/backend-defect-hunt-plan`)
**Tier:** T2 — Persistence & Event Sourcing (threat-model rank #2: a corrupt event stream silently poisons every future replay)
**Audit budget:** 12 candidates. **budget_spent = 12.**
**Runtime:** Python 3.12.10, pytest, real temp SQLite. No PostgreSQL server available locally — Postgres-only mechanisms are marked `[UNK]` and were never faked green.

Assertion tags: `[VF]` verified fact · `[HYP]` hypothesis · `[UNK]` insufficient evidence · `[FALSE]` contradicted.

---

## PHASE 1 — Defect-surface map

### Regions

| ID | Region (file:function) | Defect classes present | Entry reachability | Blast radius | Invariant density |
|----|------------------------|------------------------|--------------------|--------------|-------------------|
| R1 | `infrastructure/persistence/snapshots.py` :: `SnapshotStrategy.create_snapshot` / `load_snapshot` / `_deserialize_state` | 1 (corruption), 3 (serialization) | **EXPORTED-API-ONLY** — re-exported from `persistence/__init__.py:18-19,33-34`; no production caller found anywhere in `src/` | MODULE | HIGH (serializer/deserializer must be an inverse pair) |
| R2 | `snapshots.py` :: `SnapshotManager.load_aggregate_with_snapshot` | 1 (replay divergence, off-by-one) | EXPORTED-API-ONLY (same) | SYSTEM (it is the resume path) | HIGH (snapshot-replay equivalence) |
| R3 | `infrastructure/persistence/event_store.py` :: `save_events` | 2 (resource/error path), 1 (partial write) | **REACHABLE** from `asgi:app` via `api/execution/pipeline.py:260` → `api/sse_utils.py:70`, and from `application/event_bus/bus.py:450` (`persist_all_events`, subscribed at `bus.py:466`) | EXTERNALLY-VISIBLE | HIGH (append-only log durability; documented `Raises: sqlite3.Error`) |
| R4 | `event_store.py` :: `_update_aggregate` | 1 (lost update), 4 (concurrency) | REACHABLE (same path as R3, on every event) | EXTERNALLY-VISIBLE (`get_aggregate_state`, `list_pipelines` serve it to the API) | MEDIUM (`current_version` = aggregate head) |
| R5 | `event_store.py` :: `get_events` / `get_events_since` | 1 (version filter semantics) | REACHABLE | SYSTEM | HIGH (`from_version` is EXCLUSIVE, `WHERE version > ?`) |
| R6 | `event_store.py` :: `prune_events_before` / `count_eligible_events` | 1 (compaction gaps) | REACHABLE via `compaction_service.py` and `api/routes/admin.py` | SYSTEM | HIGH (never create a version gap) |
| R7 | `event_store.py` :: `list_aggregate_ids_for_user`, `close`, `reset_event_store`, `get_event_store` | 2 (lifecycle) | REACHABLE — GDPR erasure `application/services/data_eraser.py:49`; shutdown `api/__init__.py:280` | MODULE | MEDIUM |
| R8 | `infrastructure/persistence/event_store_connection.py` :: whole class | 2 (lifecycle), 1 (schema drift vs `EventStore._init_db`) | REACHABLE (constructed by every `EventStore`) | MODULE | MEDIUM |
| R9 | `core/aggregates/pipeline.py` :: `Aggregate.apply`, `load_from_history`, `PipelineAggregate.from_dict` | 1 (replay), 3 (type) | REACHABLE via R2 | SYSTEM | HIGH (strict `version == self.version + 1`) |
| R10 | `core/events/domain_events.py` :: `make_event`, `EVENT_CLASSES`, `ALL_EVENT_TYPES` | 3 (serialization fidelity) | REACHABLE everywhere | SYSTEM | MEDIUM |
| R11 | `infrastructure/persistence/error_store.py` :: `_safe_int`, `_query_sync`, `_stats_sync`, `_prune_old` | 5 (trust boundary — **prior known SQL-injection regression**) | REACHABLE via admin error routes | EXTERNALLY-VISIBLE | HIGH |
| R12 | `infrastructure/persistence/postgres_store.py` :: schema, `save_events`, `_update_aggregate`, `close`, pool selection | 1, 2, 3, 4 | REACHABLE **only when `EVENT_STORE_BACKEND=postgres`** | EXTERNALLY-VISIBLE | HIGH |
| R13 | `infrastructure/persistence/cached_quota_repo.py`, `cached_subscription_repo.py` | 3 (type drift across the cache boundary) | REACHABLE via `api/dependencies.py:409-412` | MODULE | MEDIUM |
| R14 | `pipeline_ownership_repo.py`, `auth_store.py`, `billing_deadletter_repo.py`, `credit_repo_memory.py` | 2, 3, 4 | REACHABLE | MODULE | MEDIUM |
| R15 | `telemetry_store.py`, `feedback_store.py`, `api_key_repo_*.py`, `credit_repo_postgres.py`, `quota_repo_postgres.py`, `subscription_repo.py` | 1, 2, 3, 4 | REACHABLE | MODULE / EXTERNALLY-VISIBLE | MEDIUM |

### Hunt queue (likelihood × blast_radius × reachability)

R2 → R1 → R4 → R3 → R12 → R11 → R7 → R13 → R14 → R5/R6 → R9/R10 → R15

R1/R2 lead despite EXPORTED-API-ONLY reachability because `CLAUDE.md` §"Architecture Style" asserts *"`PipelineAggregate` provides event-sourced replay (verified working: snapshot + full-history replay both exercised, `infrastructure/persistence/snapshots.py`)"* — a documented guarantee that, if false, misleads every future change to the resume path.

### Assertions about the map itself

- **M1 [VF]** `SnapshotManager` and `SnapshotStrategy` have **no caller anywhere in `src/`**. A `Grep` for `SnapshotManager|load_aggregate_with_snapshot|SnapshotStrategy|_deserialize_state|load_snapshot` across `**/*.py` in the worktree returns only `snapshots.py` itself and the `persistence/__init__.py` re-export. They are exported public API, not wired into the pipeline.
- **M2 [VF]** No test in `tests/` exercises `SnapshotManager.load_aggregate_with_snapshot`, `SnapshotStrategy.create_snapshot` or `SnapshotStrategy.load_snapshot`. Of the 13 test files matching `snapshot`, every one uses `EventStore.save_snapshot`/`get_snapshot` directly (e.g. `tests/unit/test_compaction_sqlite.py:45`, `tests/test_event_store_concurrency.py:69`). The `CLAUDE.md` claim that snapshot replay is "verified working … exercised" is **[FALSE]** as of this commit.
- **M3 [VF]** `get_events`' `from_version` is **exclusive** on both backends: `event_store.py:349-353` `WHERE aggregate_id = ? AND version > ?`, `postgres_store.py:424-428` `WHERE aggregate_id = $1 AND version > $2`. The two backends agree with each other; any off-by-one is therefore in a caller, not in a store.
- **M4 [VF]** There are **two independent writers to the same `aggregate_id`** in the live HTTP path: the request coroutine (`api/execution/pipeline.py:260,415,455,604,665,684` → `_persist_event`) and the event-bus worker (`bus.py:466` subscribes `persist_all_events` to *all* events → `bus.py:450`). Concurrency on a single aggregate is therefore a supported, reachable condition, not a test-only artefact.
- **M5 [VF]** `EventStore` carries **two divergent schema definitions**: the live one in `event_store_connection.py:65-126` (used by `__init__`) and a dead legacy copy in `event_store.py:63-130` (`_init_db`, never called). The dead copy still carries the comment `-- UNIQUE(aggregate_id, version) removed: version always 1, see GH-###`, which is **[FALSE]** for the live code — `api/execution/pipeline.py:75,261` increments a per-run `event_version` counter, so versions are 1..N.

---

## PHASE 2 — Suspicion generation

Twelve candidates, in tested order. Every one is grounded in code read in full.

### D1 — snapshot serialize/deserialize are not an inverse pair
Under **any** load of a snapshot this class itself wrote, the code at `snapshots.py:133` (`_deserialize_state(snapshot_data)`, defined at `:137-139` as `PipelineStateData(**data)`) violates the **serializer/deserializer inverse-pair property** — `create_snapshot` (`:91-95`) persists a wrapper `{'state', 'version', 'timestamp'}` while `PipelineStateData` (`core/aggregates/pipeline.py:116-137`) declares none of those three names — producing `TypeError` and an unrecoverable snapshot.
Class 3 · Reachability EXPORTED-API-ONLY · Severity **HIGH** (crash on the resume path) · Prior **HIGH** · Innocence path: some other writer supplies a flat state, or the branch is never entered because `get_snapshot` returns `None`.

### D2 — off-by-one on an exclusive version filter
When a snapshot exists and events follow it, `snapshots.py:211-213` (`from_version=version + 1`) violates **snapshot-replay equivalence** (`replay(snapshot@v) + events(v,∞) == replay(events[0,∞))`) because `get_events` is already exclusive (M3), silently dropping event `v+1` — which the gap guard at `:220-227` then reports as `EventStoreCorruptionError` on a healthy store.
Class 1 · EXPORTED-API-ONLY · Severity **HIGH** (silent event loss, converted to a false corruption alarm) · Prior **HIGH** · Innocence path: the gap guard is intended to be the real behaviour; or `get_events` is inclusive.

### D3 — a snapshot at the aggregate head reported as "not found"
When a snapshot is the newest thing for an aggregate, `snapshots.py:215-216` (`if not events: return None`) violates the **totality of aggregate lookup** — `load_aggregate_with_snapshot` returns `None` ("no such aggregate") for an aggregate that demonstrably exists. Phase-based snapshotting fires on `PipelineCompleted` (`:74-76`), so this is the *normal* terminal state of every finished run.
Class 1 · EXPORTED-API-ONLY · Severity **MEDIUM-HIGH** (silent wrong result) · Prior **MED** · Innocence path: `None` may deliberately mean "nothing new to replay".

### D4 — `conn` used in the handler before it is bound
When `self._get_connection()` raises, `event_store.py:143-181` violates the method's own **documented exception contract** (`Raises: sqlite3.Error … OSError`): all three `except` arms call `conn.rollback()`, so the handler raises `UnboundLocalError` and destroys the original cause.
Class 2 · REACHABLE (disk full, locked DB, unwritable path) · Severity **MEDIUM** (diagnosability destroyed on the durability path) · Prior **HIGH** · Innocence path: `_get_connection` may be total.

### D5 — per-call ownership repository never closed
On every GDPR erasure, `event_store.py:646-654` constructs a `PipelineOwnershipRepository` (which builds its own `EventStoreConnection`, `pipeline_ownership_repo.py:43`) and never calls its `close()`, potentially violating **resource-lifecycle symmetry** (one `sqlite3.Connection` + one `ThreadPoolExecutor` worker leaked per call).
Class 2 · REACHABLE (`data_eraser.py:49`) · Severity **MEDIUM** · Prior **MED** · Innocence path: CPython refcounting closes the connection on `__del__`, and `ThreadPoolExecutor` workers exit when the executor is collected.

### D6 — `UsageQuota.tier` changes type across the cache boundary
On a Redis cache hit, `cached_quota_repo.py:39-46` (`tier=data["tier"]`) violates the **declared field type** — `UsageQuota.tier: SubscriptionTier` (`domain/saas.py:64`) — returning a plain `str` where the cache-miss path returns the enum, so `quota.tier.value` (the same file's own write path, `:57`) raises `AttributeError`.
Class 3 · REACHABLE (`api/dependencies.py:409-412`) · Severity **MEDIUM** · Prior **HIGH** (the sibling `cached_subscription_repo.py:63` does `SubscriptionTier(data["tier"])` correctly) · Innocence path: `SubscriptionTier` is a `str`-Enum, so equality and JSON still work.

### D7 — async `close()` invoked without `await`
When `EVENT_STORE_BACKEND=postgres`, `event_store.py:849-854` (`reset_event_store`, `_event_store.close()`) violates **resource-lifecycle symmetry**: `PostgreSQLEventStore.close` is a coroutine function (`postgres_store.py:1013`), so the bare call builds a coroutine that is never awaited and the asyncpg pool is never closed.
Class 2 · REACHABLE (test teardown; the same shape at `api/__init__.py:280` on FastAPI shutdown) · Severity **MEDIUM** · Prior **HIGH** · Innocence path: on SQLite `close()` is synchronous and correct.

### D8 — `saas` aggregate_type has no partition
If a `USER_REGISTERED`/`USER_LOGGED_IN` event ever reaches the Postgres store, `event_store.py:247-251` / `postgres_store.py:359-362` return `"saas"`, violating **total coverage of the LIST partition key**: `postgres_store.py:168-176` declares partitions for `pipeline`/`widget`/`memory`/`generic` only, with no `DEFAULT`, so PostgreSQL raises and the surrounding `conn.transaction()` (`:280`) rolls back **the entire batch**.
Class 1 · Reachability **DEAD** (see innocence) · Severity **HIGH if reached** · Prior **LOW** · Innocence path: no emitter of those two event types exists anywhere in `src/`.

### D9 — `aggregates.current_version` is assigned, not maximised
Under concurrent appends to one aggregate, `event_store.py:288` (`updates.append("current_version = ?")`) violates the **monotonic aggregate-head invariant**: the last batch to win the store lock overwrites `current_version` with its own version, which need not be the highest. `get_aggregate_state()['version']` and `list_pipelines()['version']` then serve a stale head to the API.
Class 1 + 4 · REACHABLE (M4) · Severity **MEDIUM** (silent wrong result, externally visible) · Prior **MED** · Innocence path: production writers may be strictly serial and ascending.

### D10 — ErrorStore SQL construction (prior known regression)
`error_store.py:173,238,274,279,285,298` interpolate day/hour windows into SQL via f-string, potentially violating the **trust boundary** (SQLite datetime modifiers cannot be parameter-bound).
Class 5 · REACHABLE via admin error routes · Severity **CRITICAL if real** · Prior **MED** (a regression here was found before) · Innocence path: `_safe_int` (`:149-164`).

### D11 — `_read_pool` dereferenced without a `None` guard
Constructed with `use_read_replica=True, read_replica_url=None`, `postgres_store.py:551,595,788,846` (`self._read_pool if self.use_read_replica else self._pool`) would violate **pool-selection totality** and raise `AttributeError` on `None.acquire`.
Class 2/3 · Reachability ? · Severity MEDIUM · Prior **MED** (line 421 has the `is not None` guard the other four lack) · Innocence path: no construction site passes `use_read_replica=True`.

### D12 — compaction runs two DELETEs with no transaction
`postgres_store.py:958-991` executes the events DELETE and the aggregates DELETE with no `async with conn.transaction():`, violating **compaction atomicity** — contrast `delete_aggregate:893-894`, which wraps its deletes correctly.
Class 2 + 1 · REACHABLE (`compaction_service.py`, `api/routes/admin.py`) · Severity MEDIUM · Prior MED · Innocence path: each statement is individually atomic in autocommit and the second is idempotent cleanup the next nightly run repeats.

---

## PHASE 3 — Proof-of-defect

All triggers ran against a **real temp SQLite database**. Nothing about the store, the connection, or the snapshot strategy was mocked. Only `get_valkey_pool` (a network transport, not the mechanism under test) was faked, for D6.

### D1 — FIRED
```
D1 raw snapshot row keys: ['state', 'timestamp', 'version'] version: 5
D1 FIRED: TypeError PipelineStateData.__init__() got an unexpected keyword argument 'state'
```
**Innocence attempt:** searched for any other writer that could make the wrapper shape correct. `create_snapshot` is the only writer that `load_snapshot` can pair with; `EventStore.save_snapshot` is a lower-level primitive that takes whatever it is given. No guard, no upstream validation, no unreachable branch. → **NO-DEFENSE-FOUND**.
**Verdict: CONFIRMED [VF]** (reachability qualified — exported API, no production caller).

### D2 — FIRED
```
D2 events with from_version=3 -> [4, 5]
D2 events with from_version=4 (what the code passes) -> [5]
D2 FIRED: EventStoreCorruptionError Event gap detected for aggregate agg-offbyone:
          expected versions [4], got [5]
```
The snapshot used here was written *flat* via `save_snapshot`, deliberately isolating D2 from D1.
**Innocence attempt:** if `get_events` were inclusive, `version + 1` would be right. M3 shows it is exclusive on both backends. If the gap guard were meant to fire, `expected_versions` would start at `version + 2` — it starts at `version + 1` (`:221`), so the guard and the call disagree with each other. → **NO-DEFENSE-FOUND**.
**Verdict: CONFIRMED [VF]**.

### D3 — FIRED
```
D3 load_aggregate_with_snapshot -> None
D3 events actually in store: 5
```
Five events and a valid snapshot at v5; the loader reports the aggregate as absent.
**Innocence attempt:** `None` could mean "nothing new". But the method's contract is `-> PipelineAggregate | None` used as a lookup, and the no-snapshot branch (`:243-251`) uses `None` for genuine absence — the two branches would then mean different things by the same value. → **NO-DEFENSE-FOUND**.
**Verdict: CONFIRMED [VF]**.

### D4 — FIRED
```
D4 raised: UnboundLocalError cannot access local variable 'conn' where it is not associated with a value
```
(injected `sqlite3.OperationalError("disk I/O error")` from `_get_connection`).
**Innocence attempt:** `_get_connection` calls `sqlite3.connect` and four `PRAGMA` statements (`event_store_connection.py:39-49`), every one of which can raise `sqlite3.OperationalError` on a locked, full or unwritable database. Not total. → **NO-DEFENSE-FOUND**.
**Verdict: CONFIRMED [VF]**.

### D5 — DID-NOT-FIRE
```
D5 threads before=1 after=2 new=['event_store_0']
D5 event_store threads still alive after store.close(): []
```
Five successive `list_aggregate_ids_for_user` calls produced **one** transient worker thread, not five, and none survived.
**Innocence attempt (successful):** CPython refcounting closes each orphaned `sqlite3.Connection` in `__del__`, and `concurrent.futures.ThreadPoolExecutor` workers hold only a weakref to their executor and exit once it is collected. Both resources are reclaimed.
**Verdict: CLEARED — CODE-INNOCENT.** Recorded as a portability note (a non-refcounting runtime would leak), **not** a defect.

### D6 — FIRED
```
D6 db-path tier type: SubscriptionTier | cache-path tier type: str
D6 FIRED: rebuilt.tier.value -> AttributeError 'str' object has no attribute 'value'
```
**Innocence attempt:** `SubscriptionTier(str, Enum)` makes `==` and JSON round-trips work, so no *current* consumer breaks (a `Grep` for `.tier.value` finds no `UsageQuota` consumer outside this file). But the declared type is violated regardless, and the sibling `cached_subscription_repo.py:63` performs the identical conversion correctly — the asymmetry is an omission, not a design choice. → **NO-DEFENSE-FOUND** for the type contract; consequence today is latent.
**Verdict: CONFIRMED [VF]**, severity MEDIUM.

### D7 — FIRED
```
D7 PostgreSQLEventStore.close is coroutine fn: True
D7 warnings on reset_event_store(): ["coroutine 'PostgreSQLEventStore.close' was never awaited"]
```
**Innocence attempt:** correct on the SQLite backend only. `get_event_store` (`event_store.py:838-843`) genuinely returns a `PostgreSQLEventStore` when configured for Postgres, so the call site is polymorphic over a sync and an async `close`. → **NO-DEFENSE-FOUND**.
**Verdict: CONFIRMED [VF]** — but see Phase 5, `[REQUIRES HUMAN REVIEW]`.

### D8 — DID-NOT-FIRE (unreachable)
`Grep` for `USER_REGISTERED|USER_LOGGED_IN` across the worktree finds them **declared** (`domain_events.py:58-59`), **mapped** (`:472-473`), and **classified** (`event_store.py:248-249`, `postgres_store.py:360`) — and emitted nowhere. `Grep` for `PARTITION OF events` confirms `postgres_store.py:169-175` covers `pipeline`/`widget`/`memory`/`generic` and the alembic baseline `migrations/alembic/versions/df9629e72f17_baseline.py:132-144` covers only `pipeline`/`widget`/`memory`.
**Innocence attempt (successful on reachability):** the branch is dead — no publisher exists.
**Verdict: INDETERMINATE.** Latent, correctly identified, not currently firing. Not fixed (a partition change is a migration, i.e. cross-boundary). See Residual Risk.

### D9 — FIRED, STATISTICAL
```
A serial-then-older current_version = 1   (max event version = 5)
B concurrent-shuffled: current_version != max in 51/60 trials
C after completed:      {... 'version': 9, 'status': 'completed' ...}
C after late STARTED:   {... 'version': 1, 'status': 'running'  ...}
```
**STATISTICAL(rate = 51/60 = 85% of shuffled concurrent trials).**
**Innocence attempt:** the production HTTP path *is* serial and ascending (`api/execution/pipeline.py:75` `event_version = 1`, incremented after each awaited `_persist_event`). But M4 shows a **second** writer — the event-bus worker (`bus.py:466` → `:450`) — appends to the same `aggregate_id` from an independent task with independently assigned versions, and `tests/test_event_store_concurrency.py:35-60` blesses concurrent same-aggregate appends as supported behaviour. No documented invariant forbids the trigger. → **NO-DEFENSE-FOUND** for the version regression.
**Verdict: CONFIRMED [VF] STATISTICAL(0.85)** for the `current_version` regression.
The **status** regression shown in probe C (`completed` → `running`) is a *separate* mechanism in the same function and requires a `PipelineStarted` delivered after a `PipelineCompleted`, which the production emitter cannot produce. → recorded **INDETERMINATE**, not fixed.

### D10 — DID-NOT-FIRE
**Innocence attempt (successful):** `error_store.py:149-164` `_safe_int` calls `int(value)` — which raises `ValueError`/`TypeError` on any non-numeric payload such as `"7; DROP TABLE errors"` — and clamps to `[floor, ceiling]`. It gates **every** interpolation site: `:173` (`_prune_old`), `:238` (`_query_sync`, `hours`), `:270` (`_stats_sync`, `days`, coerced once and reused at `:274,279,285,298`). The only non-gated interpolations are the hard-coded `'-1 hours'`/`'-24 hours'` literals at `:290,294`. All user-controllable filters (`level`, `source`, `path`, `user_id`, `limit`, `offset`) are parameter-bound.
**Verdict: CLEARED — CODE-INNOCENT.** The previously reported SQL-injection regression is **fixed in the current tree**. `tests/test_error_store_sql_safety.py` exists and passes.

### D11 — DID-NOT-FIRE (unreachable)
**Innocence attempt (successful):** `PostgreSQLEventStore.__init__` (`postgres_store.py:83-90`) defaults `use_read_replica=False`, and **no construction site anywhere passes it True** — `event_store.py:840-843`, `api/__init__.py:243` and `get_postgres_store` all omit it. The dangerous branch is unreachable under current wiring.
**Verdict: CLEARED (unreachable).** The inconsistency between `:421` (guarded) and `:551/595/788/846` (unguarded) is recorded as a latent hazard.

### D12 — INDETERMINATE `[UNK]`
No PostgreSQL server is available in this environment. Writing an executable trigger would require mocking the asyncpg connection — i.e. mocking away the very transaction semantics under test — which the protocol forbids. The code reading is not in dispute (`postgres_store.py:958-991` has no `conn.transaction()`; `delete_aggregate:893-894` does), but *fired* cannot be asserted.
**Verdict: INDETERMINATE `[UNK]` — needs a live PostgreSQL to validate.** Not fixed.

---

## PHASE 4 — Triage inventory

| Candidate | Trigger | Innocence | Evidence basis | Status |
|-----------|---------|-----------|----------------|--------|
| D2 `snapshots.py:211-213` off-by-one on exclusive `from_version` | FIRED | NO-DEFENSE-FOUND | VERIFIED DEFECT | **CONFIRMED** |
| D1 `snapshots.py:133/137-139` wrapper/state asymmetry | FIRED | NO-DEFENSE-FOUND | VERIFIED DEFECT | **CONFIRMED** |
| D3 `snapshots.py:215-216` head snapshot → `None` | FIRED | NO-DEFENSE-FOUND | VERIFIED DEFECT | **CONFIRMED** |
| D9 `event_store.py:288` `current_version` not maximised | STATISTICAL(51/60) | NO-DEFENSE-FOUND | VERIFIED DEFECT | **CONFIRMED** |
| D4 `event_store.py:143-181` `conn` unbound in handler | FIRED | NO-DEFENSE-FOUND | VERIFIED DEFECT | **CONFIRMED** |
| D6 `cached_quota_repo.py:39-46` enum→str drift | FIRED | NO-DEFENSE-FOUND (consequence latent) | VERIFIED DEFECT | **CONFIRMED** |
| D7 `event_store.py:853` async `close()` unawaited | FIRED | NO-DEFENSE-FOUND | VERIFIED DEFECT | **CONFIRMED** (escalated) |
| D8 `postgres_store.py:168-176` no `saas` partition | DID-NOT-FIRE (no emitter) | CODE-INNOCENT *by unreachability only* | SUSPECTED | INDETERMINATE |
| D9b `event_store.py:303-305` terminal status regression | FIRED under out-of-order input | caller cannot produce that order | SUSPECTED | INDETERMINATE |
| D12 `postgres_store.py:958-991` untransacted compaction | not executable here | — | UNKNOWN | INDETERMINATE `[UNK]` |
| D5 `event_store.py:646-654` per-call repo not closed | DID-NOT-FIRE | CODE-INNOCENT | FALSE (innocent) | **CLEARED** |
| D10 `error_store.py` SQL interpolation | DID-NOT-FIRE | CODE-INNOCENT (`_safe_int`) | FALSE (innocent) | **CLEARED** |
| D11 `postgres_store.py:551/595/788/846` `_read_pool` | DID-NOT-FIRE | CODE-INNOCENT (unreachable) | FALSE (innocent) | **CLEARED** |

### Verified defects ranked (severity × reachability × blast_radius)

1. **D2** — HIGH · EXPORTED-API-ONLY · SYSTEM. Silent event loss on replay, surfaced as a false corruption alarm.
2. **D1** — HIGH · EXPORTED-API-ONLY · MODULE. Snapshot restore cannot succeed at all.
3. **D3** — MEDIUM-HIGH · EXPORTED-API-ONLY · SYSTEM. Completed runs reported as missing.
4. **D9** — MEDIUM · REACHABLE · EXTERNALLY-VISIBLE. Wrong `version` served by `get_aggregate_state`/`list_pipelines`.
5. **D4** — MEDIUM · REACHABLE · EXTERNALLY-VISIBLE. Root-cause destruction on the durability error path.
6. **D6** — MEDIUM · REACHABLE · MODULE. Type contract violated across the cache boundary.
7. **D7** — MEDIUM · REACHABLE (Postgres only) · MODULE. Pool leak at shutdown. → escalated.

D1/D2/D3 rank above the reachable defects because they compose: fixing any one alone still leaves the resume path broken, and `CLAUDE.md` currently documents that path as verified.

---

## PHASE 5 — Fix design

Five fixes applied across three files. D2 and D3 live in the same function and were **merged deliberately** (see interaction analysis). D7 is escalated, not applied.

### FIX-1 (D1) — `snapshots.py :: SnapshotStrategy.load_snapshot`

```diff
--- a/src/reasoner/infrastructure/persistence/snapshots.py
+++ b/src/reasoner/infrastructure/persistence/snapshots.py
@@ -130,6 +130,11 @@ class SnapshotStrategy:
         version, snapshot_data = result
 
-        # Deserialize state
-        state = self._deserialize_state(snapshot_data)
+        # create_snapshot() persists a WRAPPER: {'state': ..., 'version': ...,
+        # 'timestamp': ...}. _deserialize_state splats its argument straight
+        # into PipelineStateData, which has none of those three field names --
+        # so passing the wrapper raised TypeError on every snapshot that this
+        # class itself wrote. Unwrap here; the fallback keeps a flat state
+        # written directly through EventStore.save_snapshot working too.
+        state = self._deserialize_state(snapshot_data.get("state", snapshot_data))
 
         return version, state
```

**Causal justification.** The verified mechanism is *`create_snapshot` writes `{'state', 'version', 'timestamp'}`; `_deserialize_state` splats that dict into a dataclass declaring none of those names*. This breaks it by unwrapping at the single consumption point, restoring the inverse-pair property. No lower-side-effect fix exists: the alternative — making `create_snapshot` write flat — would silently invalidate every snapshot already on disk, whereas the `.get(..., snapshot_data)` fallback keeps both shapes readable.
**Risk.** Scope: 1 function, 1 statement. Side effects: none — `PipelineStateData` has no field named `state`, so the fallback is unambiguous. Regression risk: LOW. Reversibility: trivial (revert one line).

### FIX-2 (D2 + D3, merged) — `snapshots.py :: SnapshotManager.load_aggregate_with_snapshot`

```diff
@@ -208,12 +213,13 @@ class SnapshotManager:
             version, state = snapshot_result
 
-            # Load events since snapshot (exclude the version already in snapshot)
+            # Load events since snapshot. get_events' from_version is
+            # EXCLUSIVE (`WHERE version > ?`), so `version` already excludes
+            # the snapshotted version; passing `version + 1` skipped the first
+            # event after the snapshot, which the gap guard below then reported
+            # as store corruption on every otherwise-healthy load.
             events = await self.event_store.get_events(
-                aggregate_id, from_version=version + 1
+                aggregate_id, from_version=version
             )
 
-            if not events:
-                return None
-
             # Guard against event gaps left by incorrect compaction.
@@ -227,5 +233,8 @@ class SnapshotManager:
-            # Rebuild aggregate
+            # Rebuild aggregate. An empty `events` is the normal terminal case
+            # (snapshot taken on PipelineCompleted, nothing after it) -- it
+            # means "the snapshot IS the state", not "no such aggregate".
+            # Returning None here reported completed runs as missing.
             aggregate = PipelineAggregate(aggregate_id=aggregate_id)
```

**Fix interaction — why merged.** D3's fix *changes D2's reachability*: with the early `return None` in place, the gap guard is never evaluated for a head snapshot; with it removed, an empty `events` list must be proven safe against the guard. It is: `expected_versions = list(range(version+1, version+1+0)) == []` equals `actual_versions == []`, so the guard passes, and the `for` loop applies nothing. Fixing them separately would have left a window where an empty tail hit an unproven guard. They also sit in the same function, so the ≤1-function constraint requires a single fix.
**Causal justification.** The verified mechanism is *an exclusive filter fed an inclusive-style argument*. Passing `version` (not `version + 1`) makes the call agree with both `get_events`' `WHERE version > ?` and the guard's own `range(version + 1, …)`. The `return None` removal breaks the second mechanism — *"no events after the snapshot" conflated with "no aggregate"* — by letting the snapshot state stand on its own, which is the entire point of compaction. No lower-side-effect fix exists: changing `get_events` to be inclusive would break `prune_events_before`, `get_events_since` and the Postgres backend simultaneously.
**Risk.** Scope: 1 function, 3 edits. Side effects: `load_aggregate_with_snapshot` now returns a non-`None` aggregate in a case that previously returned `None` — no in-repo caller exists to regress (M1). Regression risk: LOW. Reversibility: trivial.

### FIX-3 (D4) — `event_store.py :: save_events`

```diff
@@ -142,7 +142,10 @@ class EventStore:
         def _save_events_sync():
+            # Acquired OUTSIDE the try: every except branch below calls
+            # conn.rollback(), so a failure to open the connection raised
+            # UnboundLocalError from the handler and destroyed the real
+            # sqlite3.Error this method documents itself as raising.
+            conn = self._get_connection()
             try:
-                conn = self._get_connection()
-
                 for event in events:
```

**Causal justification.** The verified mechanism is *the handler dereferences a name the failing statement never bound*. Hoisting the acquisition above the `try` means a connection failure propagates as itself and no handler ever sees an unbound `conn`. No lower-side-effect fix exists: wrapping each `rollback()` in its own guard would be three edits and would still swallow the cause.
**Risk.** Scope: 1 function, 2 lines moved. Side effects: a `_get_connection` failure no longer attempts a DLQ write — correct, since there is no connection to write to. Regression risk: LOW. Reversibility: trivial.

### FIX-4 (D9) — `event_store.py :: _update_aggregate`

```diff
@@ -286,5 +289,11 @@ class EventStore:
-        updates.append("current_version = ?")
+        # MAX(), not plain assignment: two writers append to the same
+        # aggregate concurrently (the request coroutine's _persist_event and
+        # the event bus' persist_all_events subscriber), so the last INSERT to
+        # win the lock is not the one carrying the highest version. Assigning
+        # unconditionally let current_version regress below the aggregate's
+        # true head, which get_aggregate_state()/list_pipelines() then report.
+        updates.append("current_version = MAX(current_version, ?)")
         values.append(event.version)
```

**Causal justification.** The verified mechanism is *last-writer-wins on a value that must be a running maximum*. `MAX(current_version, ?)` makes the `ON CONFLICT … DO UPDATE` arm monotonic, so commit order stops mattering. No lower-side-effect fix exists within the constraint: serialising writers would require an application-level change across two modules, and adding a `WHERE current_version < excluded.current_version` clause would suppress the `updated_at`/`status` updates that share the same statement.
**Risk.** Scope: 1 function, 1 SQL fragment. Side effects: the INSERT arm is untouched, so the first event still seeds `current_version` with its own version (covered by a boundary test). Regression risk: LOW — `MAX(a, b)` in SQLite's scalar form is total over the two integers, and `current_version` is `NOT NULL DEFAULT 0`. Reversibility: trivial.

### FIX-5 (D6) — `cached_quota_repo.py :: get_quota`

```diff
-from reasoner.domain.saas import QuotaResult, UsageQuota
+from reasoner.domain.saas import QuotaResult, SubscriptionTier, UsageQuota
@@ -39,5 +39,11 @@ class CachedQuotaRepository(QuotaRepository):
                 return UsageQuota(
                     user_id=UUID(data["user_id"]),
-                    tier=data["tier"],
+                    # SubscriptionTier(...), not the raw str: [...]
+                    tier=SubscriptionTier(data["tier"]),
```

**Causal justification.** The verified mechanism is *the enum is serialized via `.value` but rebuilt as a bare `str`*. Passing it back through the enum constructor restores the declared type, exactly as the sibling `cached_subscription_repo._deserialize` (`:63`) already does. No lower-side-effect fix exists — this *is* the inverse of `.tier.value`.
**Risk.** Scope: 1 function + 1 import. Side effects: a corrupt/unknown cached tier now raises `ValueError` inside `get_quota`'s existing `try`, which degrades to a database read — verified by a no-regression test. Regression risk: LOW. Reversibility: trivial.

### D7 — `[REQUIRES HUMAN REVIEW: cross-boundary mechanism]`

**Not applied.** `reset_event_store` is synchronous and cannot await. Every in-constraint patch either masks the symptom (calling `coro.close()` silences the warning without closing the pool — forbidden: it does not break the mechanism causally) or reaches outside this tier (`api/__init__.py:280`, the FastAPI shutdown hook, is T-API's file). The correct fix spans a boundary. Larger diff for human review:

```diff
--- a/src/reasoner/infrastructure/persistence/event_store.py
+++ b/src/reasoner/infrastructure/persistence/event_store.py
@@
+async def aclose_event_store() -> None:
+    """Close the global event store, awaiting an async backend's close().
+
+    PostgreSQLEventStore.close is a coroutine function; the synchronous
+    reset_event_store() below could only ever build and discard the
+    coroutine, so the asyncpg pool was never released.
+    """
+    global _event_store
+    if _event_store is not None:
+        result = _event_store.close()
+        if inspect.isawaitable(result):
+            await result
+    _event_store = None
+
+
 def reset_event_store() -> None:
-    """Reset global event store (for testing)."""
+    """Reset global event store (SQLite/testing only).
+
+    Raises on an async backend rather than silently leaking its pool --
+    use `await aclose_event_store()` there.
+    """
     global _event_store
     if _event_store:
-        _event_store.close()
+        if inspect.iscoroutinefunction(_event_store.close):
+            raise RuntimeError(
+                "Event store backend has an async close(); "
+                "await aclose_event_store() instead."
+            )
+        _event_store.close()
     _event_store = None
--- a/src/reasoner/api/__init__.py          # T-API's file — not edited here
@@
-        if _event_store and hasattr(_event_store, 'close'):
-            try:
-                _event_store.close()
+        try:
+            from reasoner.infrastructure.persistence.event_store import (
+                aclose_event_store,
+            )
+            await aclose_event_store()
         except Exception as exc:
```

Reviewer must confirm no other caller of `reset_event_store` runs against a Postgres backend, and coordinate the `api/__init__.py` half with the API-tier owner.

---

## PHASE 6 — Self-review (RAR)

Six attack vectors per fix: boundary · invalid input · state · regression · concurrency · new-defect introduction.

### FIX-1 (D1)
- **Boundary** — snapshot dict is `{}`: `{}.get("state", {})` → `PipelineStateData()` (all defaults). Snapshot absent: short-circuited at `:127-128` before reaching this line. **FIX HOLDS [VF]** (`test_snapshot_load_returns_none_when_absent`).
- **Invalid input** — flat state written directly via `save_snapshot`: no `state` key, fallback returns the flat dict. **FIX HOLDS [VF]** (`test_snapshot_load_accepts_flat_state_written_directly`).
- **State** — `snapshot_data` is not a dict (a JSON list from a hand-corrupted row): `.get` raises `AttributeError` instead of `TypeError`. Both are unhandled either way; behaviour is not worsened. **FIX HOLDS [HYP]**.
- **Regression** — no in-repo caller (M1); the only behaviour change is success where there was a crash. **FIX HOLDS [VF]** (`test_snapshot_round_trip_returns_pipeline_state_data`).
- **Concurrency** — pure function of its argument, no shared state. **FIX HOLDS [VF]**.
- **New defect** — re-ran the class taxonomy over `load_snapshot`: no SQL, no resource acquired, no mutation, no ordering. **FIX HOLDS [VF]**.

### FIX-2 (D2 + D3)
- **Boundary** — empty tail (`events == []`): guard compares `[] != []` → False, loop applies nothing, snapshot state returned. **FIX HOLDS [VF]** (`test_load_with_snapshot_at_head_returns_the_aggregate`). Snapshot at v0 with events from v1: `from_version=0` returns all, `expected == [1..n]`. **FIX HOLDS [VF]** (covered by the equivalence test).
- **Invalid input** — a genuine gap (versions 1,2,3,5 with a snapshot at 3) must still raise. **FIX HOLDS [VF]** (`test_load_with_snapshot_still_detects_a_real_event_gap`).
- **State** — no snapshot **and** no events must still be `None`. **FIX HOLDS [VF]** (`test_load_without_snapshot_still_returns_none_when_empty`).
- **Regression** — the load-bearing invariant is that both replay paths agree. **FIX HOLDS [VF]** (`test_snapshot_path_and_full_history_path_agree` asserts `asdict()` equality of the two reconstructions and equal versions).
- **Concurrency** — `get_snapshot` and `get_events` are two separate awaits, so an event written between them is picked up by neither an inconsistent snapshot nor a stale tail *in a way the fix changes*; the pre-existing read-skew window is untouched by this diff. **CANNOT DETERMINE** — pre-existing, out of this fix's scope, recorded in Residual Risk.
- **New defect** — `aggregate.apply` still enforces `version == self.version + 1` (`core/aggregates/pipeline.py:66-70`), so a bad tail fails loudly rather than corrupting state. **FIX HOLDS [VF]**.

### FIX-3 (D4)
- **Boundary** — `events == []`: the `for` body never runs, `conn.commit()` on a no-op transaction. Unchanged from before. **FIX HOLDS [VF]**.
- **Invalid input** — `_get_connection` raising `sqlite3.OperationalError`: propagates as itself. **FIX HOLDS [VF]** (`test_save_events_propagates_the_connection_error`).
- **State** — a real mid-batch DB failure must still roll back and re-raise. **FIX HOLDS [VF]** (`test_save_events_still_rolls_back_on_a_mid_batch_failure`, which drops the `events` table).
- **Regression** — DLQ writes on serialization failure are unchanged; the connection is open by then. **FIX HOLDS [VF]** (existing `tests/test_event_store_concurrency.py` passes).
- **Concurrency** — `_get_connection` now runs inside `locked_func` exactly as before (`event_store_connection.py:56-60` wraps the whole callable); the lock scope is unchanged. **FIX HOLDS [VF]**.
- **New defect** — no resource is acquired-and-not-released: `EventStoreConnection` owns a single long-lived connection; `save_events` never closed it before or after. **FIX HOLDS [VF]**.

### FIX-4 (D9)
- **Boundary** — the very first event takes the INSERT arm where `MAX()` does not apply; `current_version` must seed to that event's version and a later lower one must not win. **FIX HOLDS [VF]** (`test_current_version_starts_at_the_first_events_version`).
- **Invalid input** — `event.version` is `int` on a frozen dataclass; SQLite `MAX(int, int)` is total. A hypothetical `NULL` would make `MAX` return `NULL`, but the column is `NOT NULL DEFAULT 0` and `version` has no `None` default. **FIX HOLDS [HYP]**.
- **State** — an existing row written before this fix with a too-low `current_version` self-heals on the next higher event. **FIX HOLDS [VF]** (`test_current_version_never_regresses_on_an_older_event`).
- **Regression** — the ordinary ascending path must still advance on every event. **FIX HOLDS [VF]** (`test_current_version_still_advances_on_ascending_appends`; `tests/unit/test_compaction_sqlite.py` and `tests/test_event_store_concurrency.py` still pass).
- **Concurrency** — the repeated-trial harness (30 trials × 6 shuffled concurrent batches) went from 85% wrong to 0/30. **FIX HOLDS [VF]** (`test_current_version_is_the_head_under_concurrent_appends`).
- **New defect** — re-ran the taxonomy over `_update_aggregate`: the f-string still interpolates only `', '.join(updates)`, whose elements are fixed literals (no user value); the positional/`values` alignment is unchanged because the edit alters SQL text, not the parameter list. Verified by the passing tests, which would fail on a binding misalignment. **FIX HOLDS [VF]**.
  *Note:* the sibling **status** regression in the same function is deliberately **not** fixed — see Residual Risk.

### FIX-5 (D6)
- **Boundary** — the default tier `FREE`, whose `.value` differs from its name. **FIX HOLDS [VF]** (`test_free_tier_round_trips`).
- **Invalid input** — a corrupt cached tier string: `SubscriptionTier("not-a-tier")` raises `ValueError` inside the existing `try`, degrading to a DB read rather than a 500. **FIX HOLDS [VF]** (`test_unreadable_cache_entry_falls_back_to_the_database`).
- **State** — cache empty / Redis unavailable: unchanged fall-through to the underlying repo. **FIX HOLDS [VF]** (existing `tests/test_quota_redis_fallback.py` passes).
- **Regression** — every other field must survive the round trip, and write paths must still invalidate. **FIX HOLDS [VF]** (`test_cached_quota_round_trips_every_field`, `test_write_paths_still_invalidate_the_cache`; existing `tests/test_saas_cached_quota.py` passes).
- **Concurrency** — no shared mutable state introduced; the enum is a singleton. **FIX HOLDS [VF]**.
- **New defect** — the new `ValueError` path is the only behaviour added, and it lands inside a handler that already logs and falls back. **FIX HOLDS [VF]**.

**No fix reported FIX BREAKS on any vector.** The two `[HYP]` tags (FIX-1 non-dict snapshot; FIX-4 `NULL` version) concern inputs that cannot be produced through any in-repo path, and are recorded here rather than turned into tests that would assert behaviour on impossible states. The one **CANNOT DETERMINE** (FIX-2 concurrency read-skew) is pre-existing and out of this fix's causal scope; it is listed in Residual Risk.

---

## PHASE 7 — Tests

Two new files, 19 tests, all executed.

**`tests/unit/test_snapshot_replay_sqlite.py`** (14 tests) — real temp SQLite via `tmp_path`, matching the fixture style of `tests/unit/test_compaction_sqlite.py`:

| Test | Role |
|------|------|
| `test_snapshot_round_trip_returns_pipeline_state_data` | proof-of-defect D1 |
| `test_snapshot_load_accepts_flat_state_written_directly` | boundary D1 |
| `test_snapshot_load_returns_none_when_absent` | boundary D1 |
| `test_load_with_snapshot_applies_every_event_after_the_snapshot` | proof-of-defect D2 |
| `test_load_with_snapshot_at_head_returns_the_aggregate` | proof-of-defect D3 |
| `test_load_with_snapshot_still_detects_a_real_event_gap` | no-regression D2 |
| `test_load_without_snapshot_still_returns_none_when_empty` | no-regression D3 |
| `test_snapshot_path_and_full_history_path_agree` | no-regression — the snapshot-replay equivalence invariant |
| `test_save_events_propagates_the_connection_error` | proof-of-defect D4 |
| `test_save_events_still_rolls_back_on_a_mid_batch_failure` | no-regression D4 |
| `test_current_version_never_regresses_on_an_older_event` | proof-of-defect D9 |
| `test_current_version_is_the_head_under_concurrent_appends` | proof-of-defect D9, repeated-trial (30 trials, `@pytest.mark.integration`) |
| `test_current_version_still_advances_on_ascending_appends` | no-regression D9 |
| `test_current_version_starts_at_the_first_events_version` | boundary D9 (INSERT arm) |

**`tests/unit/test_cached_quota_repo_types.py`** (5 tests) — only `get_valkey_pool` is faked:

`test_cache_hit_returns_the_same_tier_type_as_a_cache_miss` (proof-of-defect D6) · `test_cached_quota_round_trips_every_field` (boundary) · `test_free_tier_round_trips` (boundary) · `test_unreadable_cache_entry_falls_back_to_the_database` (no-regression) · `test_write_paths_still_invalidate_the_cache` (no-regression).

### Executed results

```
tests/unit/test_snapshot_replay_sqlite.py .............. [100%]  14 passed in 226.64s

tests/unit/test_cached_quota_repo_types.py
tests/unit/test_compaction_sqlite.py
tests/test_event_store_concurrency.py ............... [100%]      15 passed in 211.54s
```

Wider no-regression run over every existing suite that touches the changed modules —
`test_aggregates`, `test_domain_events`, `test_error_store_sql_safety`,
`test_event_store_gdpr_ownership`, `test_event_types`,
`architecture/test_integration_events`, `test_postgres_event_store_concurrent`,
`test_postgres_gdpr_ownership`, `test_quota_redis_fallback`, `test_quota_tier_lookup`,
`test_saas_cached_quota`, `test_saas_quota_repo`, `test_saas_quota_service`:

```
........................................................................ [ 88%]
.........                                                                [100%]
81 passed in 176.32s
```

**Total: 110 tests passing across the changed surface, 0 failures, 0 regressions.**

Fail-without-fix was demonstrated before the fixes were applied (Phase 3 trigger transcripts above); pass-with-fix is the run recorded here.

### Gates

```
python scripts/ruff_ratchet.py --max 2249
ruff violations: 2249
PASS: 2249 violations matches ratchet MAX=2249
```
The ratchet is exact-equality and the count is **unchanged** — no constant needed updating in `scripts/ci-local.sh:51` or `.github/workflows/test.yml:66`. Both new test files are ruff-clean. No module moved across a layer boundary, so `import-linter` is untouched.

---

## PHASE 8 — Verdict, coverage and residual risk

### Surface audited
`infrastructure/persistence/`: `event_store.py`, `event_store_connection.py`, `snapshots.py`, `error_store.py`, `auth_store.py`, `pipeline_ownership_repo.py`, `cached_quota_repo.py`, `cached_subscription_repo.py`, `credit_repo_memory.py`, `billing_deadletter_repo.py` — read in full by me. `postgres_store.py`, `telemetry_store.py`, `feedback_store.py`, `api_key_repo_memory.py`, `api_key_repo_postgres.py`, `credit_repo_postgres.py`, `quota_repo_postgres.py`, `subscription_repo.py` — read in full by delegated read agents whose findings I treated as **[HYP] until independently verified**; only the claims I re-verified myself appear as confirmed above.
`core/aggregates/pipeline.py` and `core/events/domain_events.py` — read in full.

### Surface NOT audited
Everything outside T2. Within T2: `postgres_store.py`'s runtime behaviour (no server), `infrastructure/valkey/` (not in scope), the alembic migrations under `migrations/` (not listed in scope, but see below), and the four Postgres repos' live SQL against a real schema.

### Defect classes covered
(1) data corruption — **covered**, 4 confirmed. (2) transactions & resource lifecycle — **covered**, 2 confirmed + 1 cleared + 1 `[UNK]`. (3) type & serialization — **covered**, 2 confirmed. (4) TOCTOU/concurrency — **partially covered**: SQLite paths executed with a repeated-trial harness; Postgres optimistic-concurrency `[UNK]`. (5) trust boundary — **covered and clean** for every file I read: the only non-constant SQL interpolations are `error_store.py`'s `_safe_int`-gated day/hour windows (cleared) and `event_store.py:307-313`'s `', '.join(updates)` over a fixed literal set.

### Confirmed defects by severity
- HIGH: 2 (D2, D1)
- MEDIUM-HIGH: 1 (D3)
- MEDIUM: 4 (D9, D4, D6, D7)
- **Total: 7 verified, 6 fixed, 1 escalated.**

### Cleared as innocent: 3
D5 (per-call ownership repo — CPython reclaims both resources), D10 (**the previously reported ErrorStore SQL-injection regression is fixed in the current tree** — `_safe_int` gates every interpolation), D11 (`_read_pool` unguarded at 4 of 5 sites, but no construction site enables the branch).

### Residual UNKNOWN set — needs runtime instrumentation
1. **D12** `postgres_store.py:958-991` — untransacted two-statement compaction. Needs a live PostgreSQL with an induced failure between the DELETEs.
2. **Postgres `save_events` optimistic concurrency** — `postgres_store.py:311-317` has `ON CONFLICT (event_id)` only; the schema (`:156`, `:178-179`) declares no unique constraint on `(aggregate_id, version)`. Two writers can commit the same version. Needs a live server to confirm.
3. **`quota_repo_postgres.py:71` / `subscription_repo.py:207`** `UUID(row["user_id"])` where asyncpg is expected to return a `uuid.UUID` for a `UUID` column — `uuid.UUID(UUID(...))` raises `AttributeError`. `credit_repo_postgres.py:101` does `user_id=row["user_id"]` (no conversion) for the same column type, so the package contradicts itself. **[HYP], high prior, needs a live server.** *This is the single highest-value unverified item in the residual set.*
4. **FIX-2 read-skew** — `get_snapshot` and `get_events` are separate awaits; an event landing between them is a pre-existing window this fix neither opens nor closes.
5. **D9b terminal-status regression** — `event_store.py:303-305` lets a late `PipelineStarted` rewrite `status` from `completed` to `running` (reproduced above). Not fixed: no in-repo emitter can produce that order, and a `CASE WHEN status IN ('completed','failed')` guard would change documented behaviour on a path I cannot exercise.
6. **D8 `saas` partition** — latent, no emitter today. Adding `USER_REGISTERED`/`USER_LOGGED_IN` emission on a Postgres deployment would lose whole event batches.

### Clean-claim scope
> Regions **R1–R11 and R13–R14** were audited for defect classes 1 (data corruption), 2 (transactions and resource lifecycle), 3 (type and serialization), 4 (TOCTOU/concurrency) and 5 (trust boundary). Seven VERIFIED defects were found and are listed above; three candidates were cleared as innocent. **Region R12 (`postgres_store.py`) was audited statically only** — its runtime behaviour was not exercised and no clean claim is made for it. Region R15 was read but its findings were not independently verified by me and are carried as hypotheses, not clean.

This is **not** a claim that the persistence tier is bug-free.

### Highest-value next hunt
**`postgres_store.py` and the four Postgres repositories, against a live PostgreSQL container.** That is where the whole `[UNK]` set lives, it is where the schema/DTO contract is only assertable at runtime, and residual item 3 (`UUID(UUID)`) would be a hard 500 on every quota and subscription read on the Postgres backend if confirmed. Second priority: the `subscription_repo.py` upsert path, where a delegated read reports a check-then-act across three separate pooled connections with no unique constraint behind it — a webhook-retry double-subscription hazard I did not verify.

---

## Uncertainty acknowledgment

**Finding most likely to be a false positive.** **D6** (`cached_quota_repo` enum drift). The type violation is executed and real, but `SubscriptionTier` subclasses `str`, so equality, comparison and JSON all still behave — and I found no current consumer that calls `.tier.value` on a `UsageQuota`. If the team's position is "a str-enum is interchangeable with its value", D6 is a style fix, not a defect. I fixed it because the sibling repo does the conversion and the declared type is unambiguous, but its practical severity may be zero. Runner-up: **D1/D2/D3**, which are indisputably wrong code but sit in a class with **no production caller** — their real-world impact today is zero, and their value is that the resume path will not work when someone finally wires it up (and that `CLAUDE.md` currently claims it already does).

**Real defect most likely missed.** Something in `postgres_store.py`'s transaction and partition behaviour that only a live server reveals — most likely a schema/DTO mismatch of the `UUID(UUID)` shape, or a partition-routing failure. Static reading cannot distinguish "the tracked migration describes the deployed table" from "it does not", and every Postgres claim in this report rests on that assumption.

**What requires runtime validation.** All six residual items. Specifically: a PostgreSQL 15+ container with the alembic baseline applied, then (a) an induced failure between compaction's two DELETEs, (b) two concurrent `save_events` with a colliding `(aggregate_id, version)`, (c) a single `get_quota` and `get_subscription_by_user` round trip to settle the `UUID(UUID)` question, (d) an emitted `USER_REGISTERED` event to settle the partition question.

**What static analysis cannot determine.** Whether the deployed database schema matches `migrations/`; asyncpg's actual decoded Python types for `UUID`/`JSONB` columns under this project's pool configuration; the real interleaving of the two concurrent event writers under production load (my 85% figure is from a deliberately shuffled harness, not from measured production ordering); and whether `SnapshotManager` is dead code by design or by accident.

**What additional input would most increase confidence.** A disposable PostgreSQL instance plus permission to run the Postgres-marked tests against it. Second: a decision from the owner on whether `SnapshotManager`/`SnapshotStrategy` is intended to be wired into the resume path or should be deleted — that single answer moves D1/D2/D3 from "latent in exported API" to either "critical, was silently broken" or "delete the module", and it determines whether `CLAUDE.md`'s replay claim should be corrected or made true.

---

## Files changed (uncommitted, for review)

**Source (3):**
- `src/reasoner/infrastructure/persistence/snapshots.py` — FIX-1, FIX-2 (+17 −8)
- `src/reasoner/infrastructure/persistence/event_store.py` — FIX-3, FIX-4 (+12 −3)
- `src/reasoner/infrastructure/persistence/cached_quota_repo.py` — FIX-5 (+8 −2)

**Tests (2, new):**
- `tests/unit/test_snapshot_replay_sqlite.py` (14 tests)
- `tests/unit/test_cached_quota_repo_types.py` (5 tests)

**This report (new):** `docs/reports/defect-hunt-2026-09-01/T2-persistence.md`

Nothing committed, nothing pushed. `src/reasoner/application/services/quota_service.py` and `src/reasoner/application/services/run_metering.py` also appear modified in this worktree — **those are not mine**; they belong to the concurrent billing/metering audit.

### Documentation correction requested (not applied — outside T2)
`CLAUDE.md` §"Architecture Style" states snapshot replay is *"verified working: snapshot + full-history replay both exercised, `infrastructure/persistence/snapshots.py`"*. Before this change, **no test exercised either snapshot method and both snapshot code paths raised** (M2, D1, D2). The claim is now closer to true — `tests/unit/test_snapshot_replay_sqlite.py::test_snapshot_path_and_full_history_path_agree` exercises exactly that equivalence — but the sentence should be rewritten to cite that test rather than the module.

### Out-of-tier observations (recorded, not fixed)
- `api/__init__.py:280-284` calls the possibly-async `_event_store.close()` bare (D7's other half) and never closes `_compaction_store` (`:241-251`). **API tier.**
- `migrations/alembic/versions/df9629e72f17_baseline.py:132-144` creates partitions for `pipeline`/`widget`/`memory` only — it is missing **`generic`**, which is the aggregate_type for the *majority* of event types (`event_store.py:253`). `postgres_store._init_schema` creates it with `IF NOT EXISTS` at every `initialize()`, so a store-initialised deployment is covered; an alembic-only one may not be. **Migrations, out of scope — worth a look by whoever owns them.**
- `src/reasoner/domain/saas.py`, `application/services/quota_service.py`, `run_metering.py` — billing/metering tier, deliberately untouched.
