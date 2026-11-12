# Implicit State Machines: Discovery and Remediation Plan

Date: 2026-11-11 · Branch base: `fix/audit7` · Status: PLAN (no code changed)

## 0. Goal and the one decision

**Goal.** Find every place where an entity moves through states that the code never
names, and make each one explicit in a way that improves:

- **UX:** users never see an impossible screen, such as a Stop button with no running
  answer, a paying user shown as free, or a cancelled plan that comes back to life.
- **DX:** a developer can read the legal states and moves of any lifecycle in one place,
  and a wrong move fails a test instead of shipping.
- **AX:** an agent can find every lifecycle with one grep, read the transition table
  instead of tracing 10 writers, and change it without breaking the others.

**The decision.** Every lifecycle uses one pattern: a named set of states plus a
**declarative transition table**, checked by one small helper. We will not add a
state-machine library (no `xstate`, no `transitions`) in either stack.

- **Python:** a `StrEnum` of states, plus a module-level `TRANSITIONS: dict[State,
  frozenset[State]]`, checked by one pure function in `core/state_machine.py`. An
  illegal move raises `InvalidTransitionError`, defined in `core/exceptions.py`.
- **Postgres:** a status column gets a `CHECK (status IN (...))` built from the same
  enum, plus guarded `UPDATE ... WHERE status IN (<allowed predecessors>)` statements,
  so the database refuses illegal moves even under races.
- **TypeScript:** a discriminated union (`{ status: 'streaming'; ticket: RunTicket } | ...`)
  driven by a reducer, either `useReducer` or a Zustand slice with a `dispatch`-style
  action. Booleans that can be derived (`running`, `isAuthenticated`, `gateChecking`)
  become selectors.

**Why this choice and not the alternatives:**

| Option | UX | DX | AX | Risk | Verdict |
|---|---|---|---|---|---|
| Leave as is, fix bugs one by one | bugs return | 10 writers per field | must trace every writer | low now, high later | rejected |
| Library (`xstate` / `transitions`) | same | new API, new dependency, two styles | agents must learn the library; harder to grep | big rewrite | rejected |
| **Enum + transition table + one helper + DB CHECK** | impossible states removed | one place per lifecycle, tests from the table | `grep TRANSITIONS` lists all machines | small, incremental | **chosen** |

Precedent already in the repo, to keep the style consistent:

- `infrastructure/circuit_breaker.py:39`: `CircuitState`.
- `application/ports/run_outcome.py:17`: `RunStatus` Literal plus a frozen `RunOutcome`. Its
  docstring records the same move away from "state-or-None plus side effects".
- `domain/saas.py:27`: `SubscriptionStatus` and `LIVE_STATUSES`.
- `infrastructure/billing/paypal_adapter.py:23`: `PAYPAL_EVENT_STATUS`, an event-to-state table.
- `ui-next/src/app/chat/page.tsx:62`: `messagesReducer`.
- `ui-next/src/app/status/StatusClient.tsx:16`: the `PollState` union.
- `ui-next/src/stores/app-store.ts:21`: `selectAuthStatus`, a derived status.

**Non-negotiable rule: never break anything.** Every machine goes through
*observe → enforce*:

1. **Observe.** The helper logs and counts (Prometheus `illegal_transition_total{machine,from,to}`)
   but does not raise.
2. **Enforce.** Once the counter has stayed at zero in production for one release, or every
   hit is explained and fixed, the helper raises.

DB `CHECK` constraints are added `NOT VALID` first, then `VALIDATE`d after a data audit.

---

## 1. Inventory (Phase 0 output so far)

Three read-only agents (Sonnet 5.5) produced this list on 2026-11-11.

**Status:** every row is INFERENCE from code reading until Phase 1 confirms it. No test
was run and no bug was reproduced. Line numbers are from `fix/audit7` at `70f6051a+`.

### 1.1 Backend: run lifecycle

| # | Machine | Where state lives | States | Illegal move the code allows (reported) |
|---|---|---|---|---|
| B1 | **Pipeline aggregate status** | `core/aggregates/pipeline.py:137`, a `str` | pending, running, completed, failed (cancelled missing) | A `failed` event after `completed` overwrites it. A `started` event after a terminal state resets it to running. A run killed with no terminal event stays `running`, so `can_resume()` says yes. |
| B2 | **Run outcome vocabulary** | `RunOutcome` (4 values), aggregate (`failed`), history (`completed`/`error`/`cancelled`, `api/history.py:28`), observer (`success`/`error`), SSE frames (`done`/`error`/`cancelled`) | 5 vocabularies for one fact | Cancel and disconnect are stored as `PIPELINE_FAILED` with a string prefix. `RunStream.failed()` emits `done` after `error`. A disconnect has no `RunOutcome` at all. |
| B3 | **PipelineState terminal status** | `domain/pipeline_state.py`: `final_solution`, `errors`, `degradations`, `ranking_degraded`, `cost_state.spend_cap_hit` (free `str`) | inferred from flags | A run with errors and no solution emits `done`, and the aggregate says `completed` while history says `error`. |
| B4 | **Metering and settlement** | locals in `metered()` (`application/services/run_metering.py:217-293`) plus `RunContext` | reserved, started, streaming, completed, completed_with_errors, abandoned, settled, unsettled | `completed=False` with `cost>0` releases the claim, so a retry bills again. `release_unstarted` and `finally` can both release. |
| B5 | **Admission resources** | `api/run_admission.py:56-86`, `Admission` | claim held, exclusive held, quota slot, credits, anon charge | Each resource has its own release rule. Forgetting one leaves a claim held until its TTL. |
| B6 | **Idempotency claim** | Valkey SET NX (`application/services/idempotency.py:70`) | unclaimed, claimed, released (no `done`) | A finished run's claim gives "already in progress" for 1 h. The release is not owner-checked. |
| B7 | **Run registry and cancel** | `infrastructure/redis/run_state.py`: active set, `CANCELLED_SET`, local `asyncio.Event` | flag soup | A late stop leaves the cancel flag for 300 s, so a reused `run_id` is cancelled at once. `pop_cancelled` has no caller. |
| B8 | **WebSocket pipeline stream** | `infrastructure/websocket/manager.py` replay buffers | open, complete, evicted | Events can follow `broadcast_complete`. A late subscriber replays a finished run. |
| B9 | **Neuro session tier** | directory location (`neuro/sessions.py:69-71`) | hot, warm, cold | Archiving is not atomic, so a session can sit in both hot and warm. `stats` counts warm and cold by different globs. |

### 1.2 Backend: money, account and data

| # | Machine | Where | States | Illegal move (reported) |
|---|---|---|---|---|
| M1 | **Subscription status** | `subscriptions.status` TEXT, no CHECK | active, trialing, past_due, cancelled | Stripe `cancelled → active` when `deleted` and `updated` share a second (`last_event_at <= $9`). Unknown Stripe statuses (`incomplete`, `unpaid`, `paused`) map to `cancelled`. `past_due` keeps the paid tier, contradicting the comment in `quota_service.py:63`. A tombstone can be adopted by a later Stripe upsert. |
| M2 | **Webhook claim** | `processed_webhooks.status`, plus Valkey processing and completed keys | absent, processing, done | Release and complete are not owner-checked. A worker whose lease expired can delete another worker's `done` row, so the event is applied twice. A dead-letter entry reads "replayed" when nothing ran. |
| M3 | **Credit reservation and settlement** | `credit_ledger` rows by `reference_id` suffix, plus the Valkey `unsettled_run_replay` set | reserved, released, charged, unsettled, dropped | A release does not check that the reserve landed. An unsettled entry is dropped after 30 days with no record. |
| M4 | **Quota period and slot** | `usage_quotas` | period open, slot claimed, slot released, reset | A slot released after the month reset takes one from the new month. Two identical UPDATE branches in `sync_quota_for_subscription`. |
| M5 | **Anonymous trial counter** | Valkey `anon_spend:{ip}:{day}` | absent, counting, over cap | `exists` then `decrby` across midnight leaves a negative key with no TTL (marked `shortcut:`). |
| M6 | **API key** | `api_keys.revoked_at`, `expires_at` | live, revoked, expired | Low risk: a touch after a revoke. Kept for completeness. |
| M7 | **Account deletion** | `account_deletion_log` (no status, no unique index) | active, subs cancelled, logged, erased, gone | A partial erase leaves the account permanently refused with data still in place, and no retry. A repeat call writes a second log row. A crash after the cancel and before the log leaves the account usable with no plan. |
| M8 | **Upload usage** | `upload_usage.bytes`, plus `meta.json` | reserved, stored, settled, deleted | The settle in `finally` is not shielded from cancellation, so a disconnect leaks the reservation. Delete then adjust is not atomic. |
| M9 | **WS ticket** | HMAC plus Valkey NX | issued, redeemed, expired | A deleted account's ticket still redeems within its TTL. |
| M10 | **Email verification** | `users.email_verified` | — | Has no writer. A dead column, not a machine; flag it for deletion or design. |

### 1.3 Frontend (`ui-next/src`)

| # | Machine | Where | States | Illegal combination (reported) and UX symptom |
|---|---|---|---|---|
| U1 | **Chat run** | `app-store.ts:33` `running`, plus about 10 `useState` in `app/chat/page.tsx` (244-258), plus `useRunController` refs | idle, gating, confirming, uploading, streaming, stopping, done, error | **Stop race:** the old run's `finally` (page.tsx:975) clears `running` and closes the WS of the *new* run after stop and resubmit, leaving no Stop button and a dead socket. An SSE `error` clears `isStreaming` but not `running`. Resume does not reset `phaseOpenMode` or `autoSelectedMethod`. A dead `activeRun` slice duplicates the model. |
| U2 | **WebSocket client** | `hooks/useWebSocketPipeline.ts` | idle, connecting, connected, reconnecting, disconnected, error | `connected` with a stale `lastError`. A ticket or health failure during reconnect becomes terminal `error`. Concurrent `connect()` calls can leak a socket. |
| U3 | **SSE stream** | `hooks/usePipelineStream.ts` | fetching, reading, aborted, ended | A stream that closes with no `done` or `error` is treated as success, so the user sees a silent half answer. The abort listener is never removed. |
| U4 | **Auth** | `app-store.ts:55-57` | loading, anonymous, authenticated, expired | `isAuthenticated` duplicates `user`. `logout` and `markSessionExpired` are identical. A 401 mid-run does not stop the run. |
| U5 | **Subscription cache** | `app-store.ts:86-92` | loading, loaded, error | A failed load sets `subscription=null` with `error=null`, so **a paying user sees the free UI**. |
| U6 | **Conversation history** | `hooks/useConversationHistory.ts` | loading, loaded, loading more, error | `loadMore` writes from a stale closure, so deleted rows come back. There is no loading state, so the sidebar shows empty on first paint. |
| U7 | **Checkout** | `app/pricing/page.tsx:68-105` (same shape in UpgradeModal, settings, dashboard) | idle, redirecting, error | Two clicks run two checkouts and the last one wins. A spinner stays after a bfcache restore. |
| U8 | **Auth forms** | login, signup and reset pages | idle, submitting, success, error | The same union copied three times. `oauth` and `submitting` can both be set. |
| U9 | **Data hooks** | `useCredits`, `useQuota`, `NeuroPanel` | loading, ok, error | `useQuota` starts with `loading=false`, so the first render looks loaded. One error is shared by three features. |

### 1.4 Not yet covered (Phase 1 must sweep)

- `hypergate/jev_router.py` and `hyperagent.py` routing decision.
- `application/flows/runner.py` phase progression and the critical-phase halt.
- `pivot_active` (`domain/pipeline_state.py:132`).
- Per-method flows: debate rounds, ToT search, iterative critique (already has `Verdict`/`NextStep`).
- The `email`/OAuth modules, `spend_limit_service`, `pipeline_ownership_repo`.
- `ui-next` `lib/db.ts`, `providers.tsx`, `UpgradeModal`, and the `onEvent` body in `page.tsx:384-735`.
- The SDK (`sdk/typescript`), CLI `--resume`, and `headless.py`.

---

## 2. Phases

Each phase ends green: pytest fast lane, vitest, `tsc`, `lint-imports` (2 kept), and
the ruff, mypy, bandit and silent-failure ratchets. "Verified" in this plan means a
named test exists, per `CLAUDE.md`.

### Phase 1: Complete and confirm the inventory (read-only)

1. **Mechanical sweep (Haiku 5.5, 2 agents in parallel).** Run these greps and return
   raw hit lists with file:line:
   - Python:
     - `status\s*[:=]`, `state\s*[:=]`
     - `= "(pending|running|active|done|failed|cancel)`
     - bool fields named `is_*`/`*_done`/`*_started`
     - `Optional[...]`/`| None` fields compared to `None` in 3+ places
     - `Literal[` status types
     - SQL `status` columns in `migrations/` and `alembic/`
   - TypeScript:
     - `useState<boolean>` clusters (3+ per component)
     - `status:` string unions
     - `set(Running|Loading|Streaming|Error)` writers
     - Zustand fields with more than 2 writers
2. **Triage (Sonnet 5.5, 1 agent).** Merge the hit lists with §1. Drop anything that is
   not a lifecycle (a single flag with one writer is not a machine). Add new machines with
   the same columns.
3. **Confirm the dangerous rows (Sonnet 5.5, 3 agents: run, money, UI).** For each row
   marked as a bug in §1 (B1, B2, B4, B6, B7, M1, M2, M3, M7, M8, U1, U3, U5, U6, U7),
   write a **failing test** that shows the illegal move, or mark it FALSE with the guard
   that prevents it. Tests go in `tests/test_state_machines_repro.py` and
   `ui-next/src/**/*.statemachine.test.ts(x)`, marked `xfail(strict=True)` so CI stays
   green until each fix lands.

**Output:** `docs/STATE_MACHINES.md`. One section per machine: states, transition
table (as a Mermaid `stateDiagram-v2`), owner module, writers, the repro test, and the
priority. This file is the AX entry point. Agents read it before touching any lifecycle.

**Done when:** every §1.4 area is swept, every bug row has a strict-xfail test or a
FALSE verdict, and `docs/STATE_MACHINES.md` exists.

### Phase 2: Foundation (one small PR)

1. **`src/reasoner/core/state_machine.py`.** A pure module with no infrastructure
   imports, about 40 lines. This sketch shows the shape; the code in the PR may differ.
   ```python
   class Machine(Generic[S]):
       def __init__(self, name: str, transitions: Mapping[S, frozenset[S]], *, enforce: bool): ...
       def check(self, current: S, target: S) -> bool        # observe: log + count, return ok
       def move(self, current: S, target: S) -> S            # enforce: raise InvalidTransitionError
       def allowed_from(self, current: S) -> frozenset[S]    # read-only (no side effects): for docs, tests and UI
       def to_mermaid(self) -> str                           # docs are generated, never hand-drawn
   ```
   - The observe counter goes through an injected callback, keeping hexagonal rules intact:
     `core` must not import Prometheus. `api/__init__.py` wires the callback, the same
     way `set_model_registry_port()` is wired.
   - `InvalidTransitionError(ReasonerError)` goes in `core/exceptions.py`. The architecture
     test forbids new exception classes in `infrastructure/`.
2. **Registry for AX and DX.**
   - Every `Machine` registers itself by name.
   - `scripts/update_mindmap_meta.py` gains a step that regenerates the diagrams in
     `docs/STATE_MACHINES.md` from the registry, so the docs cannot drift. The existing
     `generated-docs-drift` CI gate then covers them for free.
3. **Contract test** `tests/architecture/test_state_machines.py`:
   - Every registered machine has a reachable terminal state.
   - No state is orphaned.
   - Every enum member appears in the table.
   - A parametrized test walks every allowed edge and asserts that every disallowed edge
     raises.
   - New machines get this coverage for free.
4. **TypeScript twin.** `ui-next/src/lib/state-machine.ts` (about 30 lines):
   - `defineMachine<S extends string>(name, transitions)` returns `{ can(from, to), assertMove(from, to) }`.
   - In dev it warns on an illegal move, and in tests it throws.
   - It works with reducers, so it is not a framework. A vitest contract test mirrors the
     Python one.

**Risk:** none. Nothing uses the module yet.

**Done 2026-11-11.** As built, with these departures from the sketch above:

- The counter is wired the way `count_degradation` already is: `core/ports/metrics_port.py`
  declares `set_illegal_transition_counter` / `count_illegal_transition`, and
  `infrastructure/metrics.py` fills it at import. `api/__init__.py` is untouched; a
  composition-root step would be a second wiring pattern for the same job.
- `check()` and `move()` are one method. `move()` raises when `enforce=True`; otherwise it
  logs, counts and returns the target, so a machine flips from observe to enforce by
  changing one argument. `can()` is the side-effect-free query.
- Machines are found by grepping `src/` for the `reasoner.core.state_machine` import (the
  contract test and the doc generator both do this), so there is no module list to keep.
- Generated diagrams go between `<!-- gen:state-machines:start/end -->` in
  `docs/STATE_MACHINES.md`; the verdict tables around them stay hand-written.

### Phase 3: Fix the bugs that hurt users or money (enforce early)

These rows already cause wrong behaviour, so each gets its own PR: convert the
machine and flip its xfail test to pass. Order is by user and money impact.

| Order | Row | Change | Why first |
|---|---|---|---|
| 1 | **U1 stop race** | Run status becomes a reducer union keyed by `ticket`. Every `finally` dispatches `{type:'ended', ticket}`, and the reducer ignores a stale ticket. `running` and `gateChecking` become selectors. The dead `activeRun` slice is deleted. | A visible broken UI after Stop + resubmit, which is common. |
| 2 | **M2 webhook claim** | `complete` and `release` become `UPDATE/DELETE ... WHERE status='processing' AND claimed_at = $owner_ts`. Add a CHECK on `status`. | A double-applied payment event. |
| 3 | **M1 subscription** | Add a `SUBSCRIPTION_TRANSITIONS` table in `domain/saas.py`. `cancelled` is terminal per provider subscription id. Fix the `<=` same-second tie: compare `(last_event_at, status_rank)`. Map Stripe `incomplete`/`unpaid`/`paused` explicitly. Decide whether `past_due` keeps the paid tier and make the code and comment agree. Add a status CHECK. | A free plan for cancelled users, or lost access for payers. |
| 4 | **U5 subscription cache** | `{status:'idle'|'loading'|'ok'|'error', data, owner}`. The error state keeps the last good data and shows a retry. | A paying user shown as free. |
| 5 | **B1, B2, B3 run outcome** | Choose one vocabulary: `RunStatus` with `cancelled` added (`completed`, `failed`, `cancelled`, `rejected`, `disconnected`). Aggregate status uses it with a transition table, and terminal states are absorbing. Add a `PipelineCancelled` event, with the old prefix strings still parsed on replay. History, observer and SSE frames map from it. A run with errors and no solution is `failed`, not `completed`. | Resume offers dead runs, and history and analytics disagree. |
| 6 | **B4, B6 metering and claim** | Metering locals become one `SettlementState` enum driven by the frame loop. Release the claim only when no cost was spent. Add a `done` state to the idempotency claim (`SET claim done KEEPTTL`), so a retry of a finished run returns the existing outcome, not "in progress". The release is owner-checked through a compare-and-delete Lua script. | Double billing on retry, and a confusing 409. |
| 7 | **M7 account deletion** | Add `account_deletion_log.status` (`requested`, `erasing`, `erased`, `partial`) with a unique `user_id`. Write the log row *before* cancelling subscriptions. Add a resumable erase job that drives `partial → erased`. | GDPR: data kept while access is refused. |
| 8 | **U3 SSE terminal** | The stream must end in `done`, `error` or `cancelled`. A close without one becomes `error: stream ended early`, and the UI offers Resume. | A silent half answer. |
| 9 | **B7 cancel flag** | `_cancel_requested` uses `pop_cancelled`. `remove()` clears the run's cancel flag. | A reused id is cancelled at once. |
| 10 | **M8 upload settle**, **M3 release guard** | Shield the settle (`asyncio.shield` / `anyio.CancelScope(shield=True)`, as `metered()` does). The ledger release checks that `<ref>:reserve` exists, in the same transaction. | A leaked quota, and credit given from nothing. |

Each PR includes:
- **Before/after table.** The machine's transition table, before and after.
- **The flipped test.** The repro test changes from xfail to pass.
- **Migration.** For a DB CHECK, the migration is two-step: `NOT VALID`, then `VALIDATE`
  after a `SELECT DISTINCT status` audit query recorded in the PR.
- **Rollback.** One line: revert the PR. A CHECK can be dropped without data loss.

### Phase 4: Convert the remaining machines (observe mode)

**Low-risk rows:** B5, B8, B9, M4, M5, M6, M9, U2, U4, U6, U7, U8, U9.

1. Each row gets its enum or union plus a table, wired through `Machine.check` in observe
   mode.
2. **Batching:** one PR per stack area, about 3 machines each, so reviews stay small.
3. **UI forms (U7, U8, U9)** share one generic `useAsyncAction()` hook. It covers
   `idle → pending → ok | error`, guards double submit, and resets on `pageshow` for
   bfcache. It replaces the copy-pasted `{loading, error}` pairs; per finding U8 the
   pattern is copied three times.
4. **Neuro tiers (B9).** Archiving writes to a temp name, then does an atomic `os.replace`,
   then unlinks the source. The tier is derived from one place.
5. **M10.** Delete `email_verified`, or put it on the roadmap. Ask the user; do not build
   an email flow speculatively.

### Phase 5: Enforce and lock in

1. After one release with `illegal_transition_total == 0`, or with every hit explained,
   flip `enforce=True` per machine. One-line PRs.
2. **Guardrail against new implicit machines** (DX and AX):
   - A ratchet script `scripts/implicit_state_ratchet.py` counts the Phase 1 grep
     heuristics outside registered machines. It runs in `test.yml` and `ci-local.sh`
     like the other ratchets, and its max starts at the Phase 4 count and only falls.
   - In TypeScript, an ESLint rule bans 3 or more `useState<boolean>` calls in one component.
3. **Map skills.** Add one line to `map-core` (`state_machine.py`), `map-ui-next`
   (`lib/state-machine.ts`) and `map-docs` (`STATE_MACHINES.md`). Add one rule to
   `CLAUDE.md` §5 Key Invariants: "A lifecycle field is a registered `Machine`; never
   write a status directly." Agents then follow it by default.

---

## 3. How the work runs (agents and models)

| Work | Model | Why |
|---|---|---|
| Grep sweeps, hit lists, `SELECT DISTINCT status` audit queries, doc regeneration, ratchet counting | **Haiku 5.5** | mechanical, no judgement |
| Triage, repro tests, one machine conversion per PR, migrations, reducer refactors | **Sonnet 5.5** | needs reading callers and edge cases |
| Choosing the vocabulary (Phase 3 row 5), the `past_due` tier decision, final review of each Phase 3 PR | main session | cross-cutting decisions |

Rules for agents, carried from this repo's practice:
- **Ownership:** each agent owns a disjoint file list. Two agents never edit the same file.
- **Delivery:** no commits by agents. The main session reviews, runs the full gates and commits.
- **Ports and data:** never touch port 55432. Live Postgres tests use reasoner-pg-test on :55499.
- **Cost:** no billed model calls. The live lane stays deselected.
- **GateGuard:** state the facts the hook asks for, then retry.

Parallelism:
- Phase 1 runs 2 Haiku agents, then 1 Sonnet agent, then 3 Sonnet agents.
- In Phase 3, rows 1 (UI), 2 + 3 (billing) and 5 (run) touch disjoint files and can run in
  parallel. Rows 4, 6 and 8 depend on 1, 3 and 5 respectively.
- Phase 4 batches run in parallel by stack area.

---

## 4. What "without breaking anything" means here

- **Observe before enforce** for every machine that is not a confirmed bug.
- **Replay compatibility.** The event store keeps old events. New code reads the old
  `PIPELINE_FAILED` with a `cancelled:` or `client_disconnected:` prefix as `cancelled`. The
  `--resume` state files still load. `PipelineState` keeps `.get()` access per the invariants.
- **Wire compatibility.**
  - SSE frame names (`done`, `error`, `cancelled`) do not change.
  - New frames are additive.
  - The UI accepts both shapes for one release.
  - The SDK (`sdk/typescript`) is checked by its own tests.
- **DB.** Every CHECK is added `NOT VALID`, audited, then validated. No column is dropped
  until a later release.
- **Gates.**
  - Each PR passes the full fast lane, vitest, `tsc`, `lint-imports`, every ratchet, and
    `generated-docs-drift`.
  - Ratchets may only go down.
  - `.importlinter` contract 2 must not gain an exception: `core/state_machine.py` is pure.

## 5. Open questions for the user

1. **`past_due` tier.**
   - Option A: a past-due subscriber keeps paid features during the provider's retry window.
   - Option B: drops to FREE at once, as `quota_service.py:63` claims.
   - Today the code does A for quota and B for the tier check.
2. **Finished-run retry.** A retry of a finished `client_run_id` can either return the stored
   outcome (recommended) or get a fresh run.
3. **`email_verified`.** Delete it, or plan a verification flow?

## 6. Success measures

- **UX:** the Phase 3 repro tests pass, and `illegal_transition_total` stays at 0 in production.
- **DX:** every lifecycle has a table. `docs/STATE_MACHINES.md` is generated, and the drift
  gate keeps it current.
- **AX:** `grep -rn "Machine(" src ui-next/src` lists every lifecycle. The implicit-state
  ratchet only falls.
