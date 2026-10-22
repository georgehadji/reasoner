# Third Whole-Repo Audit: Remediation Plan

**Date:** 2026-10-21
**Status:** Draft for review
**Source:** the read-only audit run on 2026-10-21 against `main` (`c636eda2`) plus every open PR
(#143 to #153). Five slices were audited:

- money and access control;
- the run lifecycle (streaming, stop, resume, event store, WebSocket);
- LLM routing and shared infrastructure (router, circuit breaker, Valkey, sanitization);
- the `ui-next/` frontend;
- data rights and lean.

The plan covers all 27 findings: the 20 ranked ones and the 7 "left out" ones. Findings already
fixed by an open PR are not repeated here:

- unmetered resume and run-ID takeover (#150);
- unshielded settlement (#144);
- Stripe customer resolution and the second checkout (#148);
- follow-up memory written from `previous_synthesis` (#146);
- the WebSocket ticket format and the dev ticket secret (#153).

**Supersedes:** nothing.
**Related:** [`audit-remediation-2-2026-10-20.md`](audit-remediation-2-2026-10-20.md), whose nine PRs are
still open. Several items below build on code those PRs introduce. Each work package names the PR it
must follow.
**Branch target:** one branch per PR below, each cut from `main` once the PRs it depends on are merged.
PR 1 is the exception: it can be cut from `fix/audit2-ui-run-lifecycle` and retargeted after #152 merges.

### Architectural constraints

No item changes the Dependency Rule (CLAUDE.md §1).

- **Layering.**
  - `domain/` and `core/` stay a dependency-free functional core.
  - `application/` reaches infrastructure only through `core/ports` or `application/ports`.
  - `.importlinter` contract 2 is at **51** declared exceptions (measured 2026-10-21 with
    `scripts/count_importlinter_exceptions.py --contract 2`) and must not rise. No PR adds an
    `ignore_imports` line.
- **Ports.** New infrastructure code implements an existing port where one exists:
  `PipelineOwnershipPort`, `QuotaRepository`, `MemoryPort`, `BillingPort`, `AuthPort`. The two new
  ports in this plan, `UserDataStore` and `HistoryRepository`, go in `application/ports/` next to
  the existing ones.
- **`neuro/`.** It sits **below** `infrastructure/` in contract 1, so `neuro/` cannot use the Valkey
  client. Anything Neuro shares across workers goes through the filesystem, using
  `reasoner.utils.atomic_file` (added by #151; `utils` is the lowest layer).
- **Propagation resistance.** The four invariants in CLAUDE.md §5 are requirements. SEC-15 restores
  invariant 4 at one more site, and SEC-16 makes the sanitizer do what §7 says it does.

---

## 0. Findings register

The **Check** column says how each finding was confirmed:

- **R:** re-read in the main session.
- **A:** traced end to end by an audit agent, not re-read.
- **X:** reproduced by running code.

Every item's first task is to turn the failure case into a failing test. That test also confirms
the A items before any code changes.

### Frontend and auth flow

| ID | Finding | Sev | Check | Where |
|----|---------|-----|-------|-------|
| UI-6 | The CSP `connect-src` allows only `'self'` and the WS hosts. Supabase auth calls (`signInWithPassword`, `signUp`, token refresh) are blocked in production. A `wss://` URL with no port is given port 8000, not 443. | Must | R | `ui-next/src/lib/security-csp.ts:5-28` |
| UI-7 | `UserMenu` calls `useSubscription()` for anonymous visitors. That GET gets a 401, and `fetchWithCsrf` turns every 401 into `location = '/login'`. Public pages (`/privacy`, `/pricing`, `/docs`) send logged-out visitors to `/login`. | Must | R | `components/layout/UserMenu.tsx:24`, `hooks/useSubscription.ts:25-29`, `lib/security-client.ts:41-45` |
| UI-8 | `/settings` and `/settings/api-keys` redirect when `user` is null, before the async `INITIAL_SESSION` arrives. A reload signs the user out in effect. `isAuthLoading` exists but no component reads it. | Must | R | `app/settings/page.tsx:23-26`, `app/settings/api-keys/page.tsx:110-113` |
| UI-9 | `getToken()` refreshes with `GET /api/csrf`. In production Caddy sends `/api/*` to FastAPI, which has only `POST /api/csrf`, so the request gets 405, then null, and every later POST gets 403. | Should | R | `lib/security-client.ts:18`, `src/reasoner/api/__init__.py:524` |
| UI-10 | When an attachment upload fails, the error is only logged and the billed run starts without the file. Partial success is also silent. | Should | R | `app/chat/page.tsx:354-368` |
| UI-11 | `getClientIp` trusts a client-sent `X-Real-IP` when no XFF hop is untrusted. The rate-limit store is per instance. This matters wherever Next is reachable without Caddy. | Nice | A | `lib/security-server.ts:457-501` |
| UI-12 | `navigator.clipboard.writeText` is called with no rejection handler. | Nice | A | `app/chat/page.tsx:294,1332` |

### Data rights

| ID | Finding | Sev | Check | Where |
|----|---------|-----|-------|-------|
| DAT-10 | `GET /api/account/export` selects columns that do not exist: `users.display_name`, `subscriptions.stripe_subscription_id`, and `query_audit_logs.preset/method/tokens_*`. It returns 500 for everyone. The export also omits history, runs, memory, uploads and the credit ledger. | Must | R, X (schema in `reasoner-pg-test`) | `api/saas_router.py:151-168` |
| DAT-11 | `/api/account/delete` never calls `UserDataEraser`, so Neuro tenants and event-store aggregates survive. `DELETE /api/user/data` skips uploads, history files and vectors. There are two erase lists and both are incomplete. | Must | R | `api/saas_router.py:185-338`, `application/services/data_eraser.py`, `api/routes/gdpr.py:35-38` |
| DAT-12 | Anonymous `GET /api/neuro/health` returns `tenants.active_tenants`, which holds raw `u-<uuid>-<conversation>` keys. | Should | R | `neuro/server.py:568` |
| DAT-13 | A Neuro erasure tombstone exists only in the worker that served the request. The other 7 workers keep serving the memory. Their next L2 save rewrites the erased index. | Should | A | `neuro/server.py:156-161,248-300`, `neuro/cache.py:127-128` |

### Run lifecycle

| ID | Finding | Sev | Check | Where |
|----|---------|-----|-------|-------|
| RUN-5 | WebSocket `stop` cancels any `pipeline_id` with no ownership check. `subscribe` and HTTP `/api/stop` both check it. | Must | R | `infrastructure/websocket/manager.py:561-570` |
| RUN-6 | The handler emits `{"type":"end"}` after the real `done`. `extract_terminal_frame` takes the last `done`/`end` frame, so agent and MCP results report cost 0, tokens 0 and `errors: []`. Phase errors use the key `message`, which the error filter ignores. | Should | R | `application/handlers/handlers.py:229`, `application/services/agent_results.py:144,188-193` |
| RUN-7 | `execute_run` returns the state after Stop or failure. The handler then runs its success block (`PIPELINE_COMPLETED`, the `end` frame). `CancelledError` (disconnect) skips every terminal write, so the aggregate stays `running`. | Should | R (return paths), A (bus effects) | `api/execution/pipeline.py:515-530`, `handlers.py:179-234` |
| RUN-8 | When preflight fails, the state is `None`, and `_completion_payload` raises `AttributeError: 'NoneType' object has no attribute 'phase_tokens'`. The user sees "Internal error" instead of the cause. | Should | X | `handlers.py:67` |
| RUN-9 | `_persist_event` swallows a failed save, and `RunStream.persist` still increments `event_version`. The gap makes `PipelineAggregate.apply` raise on every later load of that run. | Should | R | `api/execution/sse_observer.py:81-84`, `api/sse_utils.py:62-75` |

### Providers and shared infrastructure

| ID | Finding | Sev | Check | Where |
|----|---------|-----|-------|-------|
| PRV-1 | The circuit breaker records a failure for every exception, including client-caused 400 and 422 (`translate_http_status` returns None for them). One user's oversized request can open `llm:<model>` for every tenant on all 8 workers. | Must | R | `infrastructure/llm/router.py:185-186,237-238`, `infrastructure/llm/base.py:48-76` |
| PRV-2 | `TIER_LOOKUP_TIMEOUT_S = 1.0` is shorter than the Valkey socket timeout (2 s). A hung Valkey uses up the budget before the DB is read, so a paying user resolves to FREE. | Should | X (seen locally: an Enterprise user resolved to `free`) | `application/services/spend_limit_service.py:60,168-181`, `infrastructure/persistence/cached_subscription_repo.py:103-120` |
| PRV-3 | A role with no explicit fallback retries on the preset primary with no price check. 43 role/preset pairs fall back to a model that costs 10x or more (`tot-premium` `tot_evaluate`: qwen3.5-9b to claude-sonnet, 48x). The direct-vendor chain also always starts at each vendor's flagship. | Should | A (price computation) | `infrastructure/llm/router.py:49-108,407-422`, `providers/direct.py:54,143` |
| PRV-4 | The Redis circuit breaker has no cooldown after a Valkey error. A hung Valkey adds up to 4 s to each LLM call, outside the call's `wait_for`, which can use up the HyperGate budget. | Nice | A | `infrastructure/circuit_breaker.py:391-472` |

### Billing

| ID | Finding | Sev | Check | Where |
|----|---------|-----|-------|-------|
| BIL-20 | PayPal `BILLING.SUBSCRIPTION.RE-ACTIVATED` and `EXPIRED` are unhandled, also on the #148 branch. A user who pays after a failed payment stays FREE, and an expired subscription stays active. | Should | R | `application/services/billing_service.py:65-109` (#148) |
| BIL-21 | The webhook claim is written before processing and released only on a handled exception. A worker that dies mid-processing leaves the claim, so the provider's retry is treated as a duplicate and the event is lost. | Nice | A | `infrastructure/billing/webhooks.py:128-168,216-268` (#148) |

### Persistence and prompt trust

| ID | Finding | Sev | Check | Where |
|----|---------|-----|-------|-------|
| PER-12 | `GET /api/history` reads and parses every user's history file synchronously on the event loop. Nothing prunes the files. `/api/history/tagged` takes the last N entries across all users before filtering by user. | Nice | R | `api/history.py:23-51`, `api/routes/history.py:26` |
| SEC-15 | YouTube oEmbed title and author are interpolated raw into `state.problem`, so attacker-controlled text reaches the search pre-plan prompts. | Nice | R | `application/flows/search_phases.py:62-76` |
| SEC-16 | CLAUDE.md §7 says `sanitize_for_prompt` applies NFKC normalization. It does not, so fullwidth text such as `ｉｇｎｏｒｅ previous instructions` passes the denylist. | Nice | R | `core/sanitization.py:188` |

### Lean

| ID | Finding | Lines | Check | Where |
|----|---------|-------|-------|-------|
| LEAN-7 | Modules with no importers (verified by grep across code, tests, scripts and config): `security/persuasion_defense.py`, its shim and its test (about 1,560 lines); the evolution chain (`healing/evolution_agent.py`, `harness_replay`, `harness_diagnosis`, `promotion_service`, `regression_gate`); `providers/finetuned.py`, `core/ports/capability_registry_port.py`, `phases/_vs_shared.py` and `api/cron.py` (about 790 lines); and about 30 scratch scripts at the repo root (about 1,800 lines). | about −4,150 | R | see §2, PR 8 |
| LEAN-8 | `import-linter` (CI only) and `lxml` (never imported; `python-docx` pulls it in) are in the production `requirements.txt`. | −2 deps | A | `requirements.txt:55,78` |

---

## 1. Design principles applied

Each pattern is chosen for the module it lives in. Where the codebase already has a mechanism, the
plan reuses it instead of adding a second one.

| Module | Paradigm / pattern | Applied to | Why |
|--------|-------------------|------------|-----|
| `ui-next/` auth | **Tri-state auth status** (`loading` / `anonymous` / `authenticated`, derived from the existing store) plus a **route guard hook** (`useRequireAuth`). The transport stays dumb: `fetchWithCsrf` returns a 401 and never navigates. | UI-7, UI-8 | Three bugs come from one design error: navigation lives in the transport and in render bodies, where the page's auth needs are unknown. The page decides whether it needs a user, and only once auth has settled. |
| `ui-next/` CSP | **Pure builder over config** (`buildContentSecurityPolicy(env)`) with a **table-driven test** | UI-6 | The policy is data computed from env. A pure function can be tested exhaustively without a browser, and `next.config.ts` and `proxy.ts` already share it. |
| `ui-next/` proxy layer | **Contract (parity) test** between client calls and upstream routes. This extends the existing `proxy-parity.test.ts`. | UI-9 | The client called a verb that exists only in the dev-time Next handler. A parity test makes "the client calls X" and "the backend serves X" one checked fact. |
| `ui-next/` chat submit | **Fail closed before spend**: a run never starts on a partial input set | UI-10 | Billing is irreversible and an upload failure is not. Abort while abort is still free. |
| `application/ports/user_data` | **Registry of `UserDataStore` strategies** (one strategy per store; each exposes `export` and `erase`). Export and both erase routes iterate **the same ordered registry**. | DAT-10, DAT-11, PER-12 (the history store) | Both GDPR bugs exist because three hand-written lists drifted apart. With one registry a store cannot be erasable but not exportable, or erased by one route and not the other. This replaces the two partial erase lists. |
| `neuro/` erasure | **Shared, persisted tombstone with TTL** (a marker file written atomically with `utils.atomic_file`, checked on read and write) | DAT-13 | Per-process state cannot carry a cross-process fact. Layering rules out Valkey, and the L2 index is already on the shared filesystem. |
| `neuro/server` health | **Least disclosure**: return aggregates, not identifiers | DAT-12 | A public health probe needs counts, not tenant keys. |
| Run execution port | **Explicit outcome type** (a sum type: `RunOutcome` with `completed`, `cancelled`, `failed` or `rejected`), **pattern-matched** by the handler | RUN-6, RUN-7, RUN-8 | Three bugs share one cause: "how did the run end" is encoded as `state is None` plus side effects. A closed set of outcomes makes a cancelled run unable to take the success branch, and makes `None` impossible to dereference. |
| Run teardown | **Shielded finalizer** (the pattern #144 uses for settlement) for the terminal event on `CancelledError` | RUN-7 | Disconnect is a normal exit path, so its terminal write must survive cancellation. |
| Event persistence | **Commit-then-advance** (the version moves only after a successful append) | RUN-9 | A sequence number describes what was stored, not what was attempted. |
| WebSocket and HTTP run actions | **One authorization policy** (`_authorized_for_pipeline`) applied to every action that names a pipeline id | RUN-5 | `subscribe` and HTTP stop already use it. The bug is the one action that forgot. |
| `infrastructure/llm` errors | **Table-driven classification policy** (`is_provider_fault(exc)`) next to `translate_http_status` | PRV-1 | The breaker must answer "is the provider unhealthy?", which is a different question from "did the call fail?". One pure function, tested in a table, answers it for both adapter families. |
| Valkey access | **Decorator** (`GuardedValkey`): a per-operation timeout and a process-local cooldown after failure, shared by the cached repos and the Redis circuit breaker. The rate limiter's own copy of this logic is migrated onto it. | PRV-2, PRV-4 | The fix for a hung Valkey is the same in every caller: fail fast, skip the network for a while, fall back. One decorator replaces three variants (one existing, two missing). |
| Timeouts | **Budget invariant test**: the outer budget is greater than the inner timeout plus the fallback | PRV-2 | The bug is two constants in two files that silently disagree. A test that asserts the relation keeps them consistent. |
| `domain/` pricing + presets | **Specification** (`fallback_within_budget(assigned, candidate, ratio)`, pure) enforced twice: a **contract test over `PRESETS`** (static) and a **runtime guard** in `_resolve_fallback` (dynamic, for auto-built routers) | PRV-3 | Presets are declarative config. The test catches config drift at review time, and the guard covers routers built at runtime (`build_auto_preset`). |
| Direct-vendor fallback | **Price-class lookup table** (`budget` / `premium` default per vendor) instead of one flagship per vendor | PRV-3 | The chain stays one table, now with a price-class column. |
| `application/services/billing_service` | **Event dispatch table** (provider event type mapped to a handler) instead of an `if` chain | BIL-20 | A missing case becomes a visible missing row, and the test parametrizes over the table. |
| Webhook idempotency | **Lease** (`status` + `claimed_at`, reclaimable after expiry) instead of a permanent claim | BIL-21 | A claim with no expiry is a lock that a crash never releases. |
| History | **Repository port with a per-owner partitioned file adapter**; all I/O goes through `asyncio.to_thread`, writes go through `atomic_write_text` | PER-12 | The query is always "this user's entries". Partitioning the storage by owner makes that query O(own entries), and erasure becomes one directory removal. |
| Prompt assembly | **Wrap by construction** with the existing `_wrap_external_content` | SEC-15 | This is the repo's existing rule for web- or model-authored text. |
| Sanitization | **Normalize-then-match on a canonical copy** (NFKC + casefold), returning the original text | SEC-16 | Detection must see what the model will read. Returning the original avoids rewriting legitimate CJK or typographic text. |
| Lean | **Delete, don't deprecate** (verified by grep, vulture and the test suite) | LEAN-7, LEAN-8 | Dead code with tests still costs review and CI time. |

---

## 2. Work packages

There are **eight PRs**. None is a hotfix in isolation, but PR 1 (UI-6, UI-7, UI-8) blocks
production sign-in and should go first. Each item lists the design, the changes, the **test that
must fail before the fix**, and the risk.

**Ratchets.** Every PR re-measures ruff, mypy, vulture and silent-failure at merge time, and sets
the limits to the measured value in both `.github/workflows/test.yml` and `scripts/ci-local.sh`.
Import-linter contract 2 stays at 51. Every PR runs `python scripts/update_mindmap_meta.py` and
`scripts/check_skill_maps.py`.

### PR 1: `fix/audit3-frontend-auth` (UI-6 to UI-12)

**Depends on:** #152 (it touches `app/chat/page.tsx`, `lib/security-server.ts` and
`app/settings/page.tsx`). Cut it from `fix/audit2-ui-run-lifecycle`, and retarget it to `main`
after #152 merges.

#### Shared design: auth status and the route guard

- **`stores/app-store.ts`:** add one derived selector,
  `selectAuthStatus(s): 'loading' | 'anonymous' | 'authenticated'`, computed from
  `isAuthLoading` and `user`. It adds no new state, so it cannot disagree with the two fields it
  reads.
- **New `hooks/useRequireAuth.ts`:** returns the status. In an effect keyed on the status, it
  calls `router.replace('/login?next=' + encodeURIComponent(pathname))` only when the status is
  `anonymous`. It never navigates during render.
- **`lib/security-client.ts`:** delete the 401 redirect and its never-resolving promise. A 401 is
  returned to the caller like any other status. Session expiry on a protected page is handled
  where it is observed:
  - `providers.tsx` already receives `SIGNED_OUT` and `TOKEN_REFRESHED`.
  - On a 401, `fetchWithCsrf` calls `useAppStore.getState().markSessionExpired()`, which sets
    `user = null`.
  - The guard on a protected page then redirects. Public pages ignore it.
- **`hooks/useSubscription.ts`:** fetch only when the status is `authenticated`. Key the cached
  subscription by user id, so a sign-in as someone else re-fetches. (#152 resets it on
  `SIGNED_OUT`; this also covers a direct switch of account.)
- **`app/login/page.tsx`:** when the status is already `authenticated`, forward to `next` (or
  `/chat`).

#### UI-7 and UI-8

- **Changes:** `settings/page.tsx` and `settings/api-keys/page.tsx` use
  `const status = useRequireAuth(); if (status !== 'authenticated') return null;`. Grep for every
  other `router.push('/login')` guard and convert it the same way (dashboard, billing).
- **Failing tests:**
  - `useRequireAuth.test.ts`: no redirect while loading; redirects once on anonymous; never
    redirects when authenticated.
  - `security-client.test.ts`: a 401 response is returned, and `window.location` is untouched.
  - `useSubscription.test.ts`: no fetch while anonymous.
- **Risk:** any page that relied on the transport redirect now shows its own unauthenticated
  state. The grep step finds them all.

#### UI-6: CSP

- **Design:** `buildContentSecurityPolicy(env)` adds three things to `connect-src`:
  - `new URL(NEXT_PUBLIC_SUPABASE_URL).origin`, when it is set;
  - the Sentry ingest origin, when Sentry is configured (verify in `sentry.*.config.ts`);
  - the WS origin with the scheme's default port (`u.port || (u.protocol === 'wss:' ? '443' : '80')`).
- **Failing test:** in `security-csp.test.ts`, assert that with
  `NEXT_PUBLIC_SUPABASE_URL=https://x.supabase.co` the `connect-src` contains
  `https://x.supabase.co`, and that `wss://app.example/ws` yields `wss://app.example:443`, not
  `:8000`.
- **Risk:** low. A Playwright login smoke test against a staging build should be the release
  check.

#### UI-9: CSRF refresh

- **Changes:** `getToken()` uses `fetch('/api/csrf', { method: 'POST' })`. The Next handler
  `app/api/csrf/route.ts` gains a `POST` export, so dev and prod accept the same verb.
- **Failing test:** extend `proxy-parity.test.ts` so that every `(method, path)` the client calls
  must exist upstream. The current GET fails it.

#### UI-10: upload failure

- **Design:** extract `uploadAttachments(files): Promise<UploadedAttachment[]>` into
  `lib/attachments.ts`. It throws `AttachmentUploadError(failedNames)` on a request failure, and
  also when fewer files succeed than were sent.
- **Changes:** `handleSubmit` catches the error, shows it in the feed, calls `run.finish(ticket)`
  and returns before the run starts. The attachments stay in the composer for a retry.
- **Failing test:** `attachments.test.ts`. A partial result must throw and name the failed files.

#### UI-11 and UI-12

- **UI-11:** `getClientIp` reads `x-real-ip` only when `TRUSTED_PROXIES` is configured, the same
  rule it already applies to XFF. Failing test in `security-server.edge-cases.test.ts`: with no
  trusted proxies, a spoofed `X-Real-IP` does not change the bucket key.
- **UI-12:** add `lib/clipboard.ts` `copyText(text): Promise<boolean>`, which catches the
  rejection. Both call sites show a toast on false. Test: a rejected `writeText` resolves to false.

### PR 2: `fix/audit3-data-rights` (DAT-10 to DAT-13)

**Depends on:**
- #150, which changes `delete_account` (identity deletion and the deletion log);
- #151, which adds `utils/atomic_file.py`, upload usage `forget` and Neuro directory names;
- #147, whose Alembic schema contract test this PR extends.

#### Shared design: the `UserDataStore` registry

- **The port.** `application/ports/user_data.py`:

  ```python
  class UserDataStore(Protocol):
      name: str                               # stable key in receipts and exports
      async def export(self, user_id: str) -> Any: ...   # JSON-serialisable, or None
      async def erase(self, user_id: str) -> None: ...   # raises on failure
  ```

- **The orchestrator.** `UserDataEraser` becomes the orchestrator over an ordered
  `Sequence[UserDataStore]`. It keeps its receipt shape, `{status, failed[], erased[]}`. A new
  `UserDataExporter` iterates the same sequence and returns `{store.name: store.export(...)}`.
- **The stores.** Implementations go where their data lives:
  - **Postgres, `infrastructure/persistence/user_data_pg.py`:**
    - `profile`;
    - `subscriptions`;
    - `quota`;
    - `query_log` (not `query_audit_logs`, which nothing writes);
    - `credit_ledger`.
  - **Event store:** the aggregates.
  - **Files:**
    - uploads, through the existing `delete_file` and `list_uploads(include_incomplete=True)`
      from #151;
    - vector indexes;
    - history (PR 6's repository; until PR 6 lands, an adapter over the current flat files).
  - **Valkey:** the `user:{id}:*` keys.
  - **Neuro:** an adapter over `MemoryPort` (`erase_owner`, plus a new `export_owner`).
- **The composition root.** `api/user_data.py` builds the registry once, in erase order:
  - content stores first;
  - Valkey;
  - the Postgres rows;
  - the identity last (users row, then the Supabase identity from #150).

  `delete_account`, `DELETE /api/user/data` and `GET /api/account/export` all take the registry
  from there.
- **The routes.** `delete_account` keeps its billing cancel and the deletion log (#150) around the
  registry call. `api/routes/gdpr.py` becomes a thin call into the same registry.

#### DAT-10: export

- **Changes:** export becomes `UserDataExporter(registry).export(user.id)`. Each Postgres store
  names its columns in one module-level tuple.
- **Failing tests:**
  - `test_user_data_export.py`: export returns 200 with every store key present (registry with
    fakes).
  - A live-PG case in the Alembic schema contract test asserts that every column in every export
    tuple exists in `information_schema.columns`. `display_name` fails it on `main`.
- **Open question:** Q1, the export scope.

#### DAT-11: delete

- **Failing test:** `test_delete_account_erases_everything.py`. Put a fake store in the registry
  and call `delete_account`. Its `erase` must be called. Then erase through `/api/user/data` too:
  both routes must reach the same set of store names.
- **Architecture test:** `test_user_data_registry.py` asserts that the registry contains at least
  `{profile, subscriptions, quota, query_log, credit_ledger, events, uploads, vectors, history,
  valkey, neuro, identity}`. A store removed by accident fails the build.
- **Risk:** deletion now removes more. That is the point, but announce it in the changelog.
  Order matters: `identity` runs last, because the other stores key on the user id.

#### DAT-12: health leak

- **Changes:** `NeuroHealthResponse` drops tenant keys from `agents_configured`, which keeps only
  `config.agents`, and adds `active_tenant_count: int`. Update the Next proxy's fallback body to
  match.
- **Failing test:** an anonymous `GET /api/neuro/health` after a `learn` for user U must not
  contain `str(U)`.

#### DAT-13: cross-worker tombstone

- **Design:** `TenantRegistry.finish_erase(prefix)` also writes
  `{data_dir}/agents/.erased/<sha256(prefix)[:32]>` with its expiry time, using
  `atomic_write_text`.
  - `is_erased(key)` checks memory first, then the marker files. It caches the directory listing
    for 1 s, so the check is O(markers) per second, not one disk read per call.
  - `get()` evicts a local L1/L2 entry whose prefix has a live marker.
  - `L2Index` save and `learn` refuse to write under an erased prefix.
  - Expired markers are swept on read.
- **Failing test:** `test_neuro_erasure_cross_worker.py` uses two `TenantRegistry` instances (two
  workers) over one temp `data_dir`. Erase on A; B must answer `is_erased` true, B's recall must
  return nothing, and B's `learn` must not recreate the directory.
- **Risk:** a multi-host deployment needs a shared `data_dir`, which the L2 index already
  requires. Document this in `DEPLOY.md`.

### PR 3: `fix/audit3-run-outcome` (RUN-5 to RUN-9)

**Depends on:** #150, which changes `api/execution/pipeline.py` (`_claim_ownership`, admission).

#### Shared design: `RunOutcome`

```python
# application/ports/run_outcome.py  (next to PipelineExecutionPort's module)
@dataclass(frozen=True)
class RunOutcome:
    status: Literal["completed", "cancelled", "failed", "rejected"]
    state: PipelineState | None = None      # None only for "rejected"
    reason: str | None = None
```

- **`PipelineExecutionPort.execute_run`** returns `RunOutcome` on every path:
  - preflight returned nothing: `rejected`;
  - `_run_phases` returned False: `cancelled`;
  - `except Exception`: `failed`;
  - otherwise: `completed`.
- **`RunPipelineCommandHandler.handle`:**

  ```python
  match outcome.status:
      case "completed": ...   # existing success block; never emits "end"
      case "cancelled": ...   # publish PIPELINE_CANCELLED (or FAILED with reason), no completion payload
      case "failed" | "rejected": ...  # publish FAILED; payload built from reason, not state
  ```

#### RUN-7 and RUN-8

- **Changes:**
  - The return paths become `RunOutcome`, as above.
  - The `finally` in `execute_run` gains a branch for `CancelledError`: under
    `anyio.CancelScope(shield=True)` with `move_on_after(SETTLE_TIMEOUT_SECONDS)`, the pattern #144
    introduced, it persists a terminal `PIPELINE_FAILED` with `reason="client_disconnected"`. If
    `EventType` already has a cancelled member, use it; check `core/events`.
  - `_completion_payload` is only reachable from the `completed` arm, so it can never see `None`.
- **Failing tests:**
  - `test_run_outcome.py`, Stop mid-run: the bus receives no `PIPELINE_COMPLETED`.
  - Preflight raises `ValueError("API key ... not set")`: the SSE stream carries that reason, and
    no `AttributeError` is logged (RUN-8).
  - Cancel the task: the event store holds a terminal event, and `can_resume()` is false.
- **Risk:** Langfuse and metrics completion counts drop by the number of stopped runs. That is a
  correction, not a regression, so note it in the PR.

#### RUN-6: `end` frame

- **Changes:**
  - Delete the `end` emit at `handlers.py:229`. Grep `ui-next/src`, `sdk/` and `docs/` first; the
    audit found no reader.
  - `extract_terminal_frame` matches `done` only.
  - The error collector reads `event.get("error") or event.get("message")`.
- **Failing test:** `test_agent_results.py` feeds the real frame sequence from a fake run,
  `done(total_cost_usd=0.12)` followed by phase `error{message}`. Assert cost 0.12 and a non-empty
  `errors`.

#### RUN-5: WebSocket stop

- **Change:** the `stop` branch calls `_authorized_for_pipeline(pipeline_id, metadata["user_id"])`
  first. When that fails, it sends an `error` frame and does not cancel.
- **Failing test:** in `test_websocket_authz.py`, user B's `stop` on A's run leaves A's cancel
  event unset.

#### RUN-9: version gap

- **Changes:** `_persist_event` returns `bool`, and `RunStream.persist` increments `event_version`
  only on `True`. A failed save is already reported through `degraded()`; the event is lost, not
  the run.
- **Failing test:** a store that fails once on `PHASE_COMPLETED`. Afterwards, `GET /api/pipelines/{id}`
  returns 200 and replays the events.
- **Risk:** none for callers. The versions in storage stay contiguous by construction.

### PR 4: `fix/audit3-provider-resilience` (PRV-1 to PRV-4)

**Depends on:** #149, which adds `fallback_routing` for every routed role and the
"route every role" contract test that PRV-3 extends.

#### PRV-1: classify before counting

- **Design:** add `is_provider_fault(exc: BaseException) -> bool` to `infrastructure/llm/base.py`,
  below `translate_http_status`, as a pure, table-driven function.

  | Error | Counts against the provider? |
  |-------|------------------------------|
  | `ProviderTimeoutError`, `asyncio.TimeoutError` | yes |
  | `ProviderUnavailableError` (5xx), `httpx.TransportError` | yes |
  | `RateLimitError` (429) | yes |
  | `ProviderCreditsExhaustedError` (402) | yes (operator account) |
  | `AuthenticationError` (401/403) | yes (operator key) |
  | `ModelNotFoundError` (404) | yes (configuration; same for every caller) |
  | residual `LLMError` (400, 422, content filter, context length) | **no** |
  | anything else | yes (unknown errors stay conservative) |

- **Changes:** both `except Exception` sites in `router.py` call
  `circuit.record_failure() if is_provider_fault(exc) else circuit.release()`. `release` is the
  existing RUN-3 path.
- **Failing tests:**
  - `test_circuit_classification.py`: five consecutive 400s leave the breaker closed; five
    timeouts open it.
  - A table test for `is_provider_fault`.
- **Risk:** a provider that answers every request with 400 because of a real outage is no longer
  tripped. The fallback still handles it per call, so it is accepted.

#### PRV-2 and PRV-4: `GuardedValkey`

- **Design:** new `infrastructure/valkey/guarded.py`.

  ```python
  class GuardedValkey:
      """Decorator over the Valkey client: every op bounded, fast-fail cooldown after an error."""
      def __init__(self, client, op_timeout_s=VALKEY_OP_TIMEOUT_S,
                   cooldown_s=VALKEY_RETRY_SECONDS, clock=time.monotonic): ...
      async def get(self, key): ...      # likewise set, setex, delete, eval, evalsha, incr, expire
  ```

  - Every operation is `asyncio.wait_for(op, op_timeout_s)`.
  - Any failure records `last_fail`. For `cooldown_s` after that, operations raise
    `ValkeyUnavailable` at once, with no network call.
  - The constants go in `core/constants_limits.py`: `VALKEY_OP_TIMEOUT_S = 0.2`, and
    `VALKEY_RETRY_SECONDS` replaces `RATE_LIMITER_REDIS_RETRY_SECONDS`.
- **Changes:**
  - `cached_subscription_repo.py` and `cached_quota_repo.py` wrap their client in `GuardedValkey`.
    The DB fallback then always runs within the tier budget.
  - The Redis circuit breaker uses `GuardedValkey`. On `ValkeyUnavailable` it delegates to the
    in-memory breaker for that model, which is the existing memory implementation in the same
    file.
  - The rate limiter's private `_redis_last_fail` logic is deleted in favour of the decorator
    (reuse).
- **Failing tests:**
  - `test_guarded_valkey.py`: a fake client that sleeps 5 s. The first call raises within 0.25 s,
    and the second raises with no call to the client.
  - `test_tier_lookup_valkey_hang.py`: a hung cache plus a DB returning ENTERPRISE gives
    `resolve_user_tier` returning ENTERPRISE within `TIER_LOOKUP_TIMEOUT_S`.
  - A budget-invariant test: `TIER_LOOKUP_TIMEOUT_S > VALKEY_OP_TIMEOUT_S + DB_TIER_QUERY_BUDGET_S`.
- **Risk:** the circuit state becomes per-worker while Valkey is down. That is the documented
  degraded mode, and it is logged through `degraded()`.

#### PRV-3: price-bounded fallback

- **Design:**
  - In `domain/pricing` (pure):
    `fallback_within_budget(assigned_usd_per_mtok, candidate_usd_per_mtok, ratio=FALLBACK_MAX_PRICE_RATIO) -> bool`.
    The ratio goes in `core/constants_limits.py`; see Q3.
  - **Static:** extend #149's preset contract test. For every preset and routed role, the
    effective fallback (explicit, else primary) satisfies the specification. Fix the failing pairs
    in `domain/preset_registry.py` with explicit, same-class, cross-lab `fallback_routing` entries,
    keeping the cross-lab rule in CLAUDE.md §5.
  - **Runtime:** `_resolve_fallback` drops the primary candidate when it fails the specification,
    and records `degraded("router.fallback_over_budget")`. This covers `build_auto_preset` routers,
    which the static test cannot see.
  - **Direct-vendor chain:** `_DIRECT_FALLBACK_CHAIN` gains a price-class column
    (`budget_model`, `premium_model`). The class is picked from the failed model's price. The whole
    chain is wrapped in one `asyncio.wait_for(DIRECT_FALLBACK_BUDGET_S)`.
- **Failing tests:** the contract test fails on today's `PRESETS` (43 pairs). `test_router_fallback_budget.py`
  checks that a cheap role whose primary is 48x is not retried on the primary.
- **Risk:** routing changes for the fixed pairs. Watch the fallback rate and cost per run for a
  week (`run_metering` already records the actual model).

### PR 5: `fix/audit3-billing-webhooks` (BIL-20, BIL-21)

**Depends on:** #148, which owns `billing_service.py` and `webhooks.py` and adds the monotonic
event guard (BIL-15). #147 must be merged first, because BIL-21 needs a migration.

#### BIL-20: PayPal event table

- **Design:** replace the PayPal `if` chain with a dispatch table:

  ```python
  _PAYPAL_HANDLERS: dict[str, Callable[..., Awaitable[None]]] = {
      "BILLING.SUBSCRIPTION.ACTIVATED":     _activate,
      "BILLING.SUBSCRIPTION.RE-ACTIVATED":  _activate,
      "BILLING.SUBSCRIPTION.CANCELLED":     _cancel,
      "BILLING.SUBSCRIPTION.EXPIRED":       _cancel,
      "BILLING.SUBSCRIPTION.SUSPENDED":     _suspend,
      "BILLING.SUBSCRIPTION.PAYMENT.FAILED": _payment_failed,
  }
  ```

  The handlers are the existing branches, moved, and #148's monotonic guard still wraps each one.
- **Failing test:** `test_paypal_events.py`, parametrized over the table. The sequence `PAYMENT.FAILED`
  then `RE-ACTIVATED` ends `active`, and `EXPIRED` ends `cancelled`.

#### BIL-21: webhook lease

- **Migration:** a new Alembic revision (expand-only) adds
  `processed_webhooks.status TEXT NOT NULL DEFAULT 'done'` and
  `claimed_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
- **Claim:**

  ```sql
  INSERT INTO processed_webhooks (event_id, provider, status, claimed_at)
  VALUES ($1, $2, 'processing', now())
  ON CONFLICT (event_id, provider) DO UPDATE
     SET claimed_at = now()
   WHERE processed_webhooks.status = 'processing'
     AND processed_webhooks.claimed_at < now() - make_interval(secs => $3)
  RETURNING 1
  ```

  On success, `UPDATE … SET status = 'done'`. A handled failure still deletes the claim (BIL-4).
  `WEBHOOK_LEASE_SECONDS` (300) goes in `core/constants_limits.py`.
- **Failing test:** an integration test against `reasoner-pg-test`. Claim, then do not finish (a
  simulated crash), then advance past the lease. The retry claims and processes; a retry inside
  the lease is a duplicate.
- **Risk:** the lease must be longer than the slowest handler (the Stripe API calls in
  `sync_subscription`). 300 s is about 10 times the observed worst case. Rows that existed before
  the migration default to `done`, so nothing replays.

### PR 6: `fix/audit3-history` (PER-12)

**Depends on:** #151 (`atomic_write_text`). Coordinate with PR 2, whose history store adapts this
repository.

- **Design:**
  - The port, `application/ports/history.py`, is a `HistoryRepository` with `save(entry)`,
    `list(owner, limit, offset, tag=None)`, `get(owner, id)` and `erase(owner)`.
  - The adapter, `infrastructure/persistence/history_files.py`, stores
    `history/<owner_key>/<id>.json`, where `owner_key` is `u-<sha256(user_id)[:16]>` or `anon`.
    - All file I/O goes through `asyncio.to_thread`.
    - `list` sorts that owner's directory by mtime and parses only the requested page.
    - The tag filter is applied per owner, before the limit.
    - Writes use `atomic_write_text`.
    - Each owner keeps the newest `HISTORY_MAX_ENTRIES_PER_OWNER` entries; older ones are pruned
      on save (Q6).
- **Migration script:** `scripts/migrate_history_layout.py`, dry run by default and `--apply` to
  write (the same shape as `backfill_upload_usage.py`). It moves flat files into owner directories
  and is idempotent.
- **Changes:**
  - `api/history.py` and `api/routes/history.py` call the port.
  - `api/execution/pipeline.py`'s `_record_history` calls `await repo.save(...)`.
  - `delete_account` reaches history through PR 2's registry.
- **Failing tests:** `test_history_repository.py`:
  - Listing for A opens none of B's files (count the reads).
  - `tagged` returns A's entries when B has newer ones.
  - Listing does not block the loop (run it under a 50 ms `wait_for` with 10,000 of B's files
    present).
- **Risk:** a deploy that runs before the migration script shows empty history until the script
  runs. The repository falls back to the flat layout for reads until a marker file says the
  migration is done.

### PR 7: `fix/audit3-prompt-trust` (SEC-15, SEC-16)

**Depends on:** #146, which owns `search_phases.py` and adds `test_prompt_trust_boundaries.py`.

- **SEC-15:**
  - **Change:** `enrich_problem_with_youtube` builds the metadata line, then appends
    `_wrap_external_content(line)`.
  - **Failing test:** add the YouTube title to the untrusted-field list in
    `test_prompt_trust_boundaries.py`. A title containing `Ignore previous instructions` must
    appear only inside the wrapper.
- **SEC-16:**
  - **Changes:** `sanitize_for_prompt` and `neutralize_for_replay` match their denylist patterns
    against `unicodedata.normalize("NFKC", text).casefold()`. They return (or strip from) the
    original text, using the match spans of the normalized copy only to decide.
  - **Why match on a copy:** NFKC can change string length (ligatures), so for stripping,
    `neutralize_for_replay` operates on the normalized text and returns it. That is acceptable
    for replayed content.
  - **Docs:** correct CLAUDE.md §7 to say exactly that.
  - **Failing test:** fullwidth `ｉｇｎｏｒｅ ｐｒｅｖｉｏｕｓ ｉｎｓｔｒｕｃｔｉｏｎｓ` raises in
    `sanitize_for_prompt` and is stripped by `neutralize_for_replay`.
  - **Risk:** extra false positives on legitimate fullwidth input. The denylist is
    phrase-level, so this is unlikely.

### PR 8: `chore/audit3-lean` (LEAN-7, LEAN-8)

**Depends on:** merge it last. `requirements.txt` is also touched by #134, #144 and #150, and
`AGENTS.md` and the map skills are touched by most PRs.

- **LEAN-7:**
  - **Delete:**
    - `security/persuasion_defense.py`, `reasoner_persuasion_defense.py` and
      `tests/test_persuasion_defense.py`, plus the `AGENTS.md:645` mention and the
      `autonomous_debug.py` rename-table string.
    - `healing/evolution_agent.py`, `application/services/harness_replay.py`, `harness_diagnosis.py`,
      `promotion_service.py` and `regression_gate.py`. Keep `domain/harness_metrics.py` and
      `core/evolution_constants.py`, which have other users.
    - `infrastructure/llm/providers/finetuned.py`, `core/ports/capability_registry_port.py`
      (replace the three `Any  # CapabilityRegistryPort` comments with plain `Any`),
      `phases/_vs_shared.py`, and `reset_all_quotas_monthly` in `api/cron.py`.
    - The root scratch scripts (`check_modules*.py`, `check_shadow.py`, `check_sitecustomize.py`,
      `find_*.py`, `temp_*.py`, `patch_rt.py`, `patch_silent.py`, `run_test*.py`,
      `run_real_test.py`, `repro_search_bug.py`, `debug_env.py`, `verify_*.py`, `parse_models.py`,
      `map_workspace.py`, `build_chunk_07.py`, `generate_skills.py`, `autonomous_debug.py`),
      `.tmp_manual_temp/`, and `scripts/start_all.py` (the duplicate; the root shim and the
      Dockerfile use `src/reasoner/start_all.py`).
    - `push_to_github.py` and `kill_servers.py` only after Q5.
  - **Procedure:**
    - Re-grep each path, including `.github/`, `Dockerfile`, `docker-compose.yml`,
      `.claude/settings*.json` and `pyproject.toml`.
    - Delete, then run the full suite, vulture and import-linter.
    - Lower the vulture ratchet to the measured value.
    - Update `CONTEXT.md` and the map skills through `/update-maps`, and run
      `update_mindmap_meta.py`.
- **LEAN-8:**
  - **Changes:** move `import-linter` to `requirements-dev.txt` (CI installs both), and remove the
    direct `lxml` pin. `python-docx` keeps it as a transitive dependency.
  - **Check:** `docker build`, then `python -c "import docx"` in the image.
  - **Risk:** any CI job that installs only `requirements.txt` and runs `lint-imports` breaks.
    Grep `.github/workflows` for it first.

---

## 3. Order, overlaps and rollout

```
#152 ──> PR 1 frontend-auth            (first: production sign-in)
#147 ─┬> #148 ──> PR 5 billing-webhooks
      ├> #150 ─┬> PR 3 run-outcome
      │        └> PR 2 data-rights <── #151
      └> #151 ──> PR 6 history ──(store adapter)──> PR 2
#149 ──> PR 4 provider-resilience
#146 ──> PR 7 prompt-trust
all  ──> PR 8 lean                     (last)
```

| File | PRs | Note |
|------|-----|------|
| `api/saas_router.py` | #150, #151, PR 2 | PR 2 rebases onto both. It keeps #150's identity deletion and deletion log, and #151's upload-usage `forget`, inside the registry's `identity` and `uploads` stores. |
| `api/execution/pipeline.py` | #150, PR 3, PR 6 | PR 3 changes the return type, and PR 6 changes `_record_history`. These are different functions. |
| `application/handlers/handlers.py` | PR 3 | `PipelineExecutionPort` signature change; the only implementer is `api/execution/pipeline.py`. |
| `neuro/server.py` | #151, PR 2 | PR 2 touches `TenantRegistry` and the health response only. |
| `domain/preset_registry.py` | #149, PR 4 | PR 4 adds `fallback_routing` rows on top of #149's. |
| `infrastructure/billing/webhooks.py`, `billing_service.py` | #148, PR 5 | PR 5 rebases onto #148. |
| `migrations/alembic/versions/*` | #147, #151, PR 5 | PR 5 adds a revision after `20261021_000100` (#151). |
| `core/constants_limits.py` | PR 4, PR 5, PR 6 | Append-only. |
| `ui-next/src/app/chat/page.tsx`, `lib/security-server.ts` | #152, PR 1 | PR 1 is cut from #152. |
| `requirements.txt` | #134, #144, #150, PR 8 | PR 8 merges last. |
| `.claude/skills/map-*`, generated counts | every PR | Regenerate after each merge. |

**Rollout notes**

- **PR 1:** test sign-in on staging before production. The CSP change is what makes it work at
  all.
- **PR 2:**
  - Account deletion now also erases Neuro memory and stored runs.
  - Export returns more data (Q1).
  - Both go in the changelog.
  - On a multi-host deployment, confirm `data_dir` is shared before relying on DAT-13.
- **PR 3:**
  - Agent and MCP clients start seeing real `total_cost_usd` and errors; announce it to API
    users.
  - Completion metrics drop by the number of stopped runs.
- **PR 4:** routing changes for about 43 role/preset pairs. Watch the fallback rate, cost per run
  and the circuit-open events for a week.
- **PR 5:** run `alembic upgrade head` before deploy. Existing rows become `done`.
- **PR 6:** run `scripts/migrate_history_layout.py` as a dry run, then with `--apply`, by a
  person, after deploy.
- **PR 8:** after the merge, rebuild the image and run the smoke tests.

---

## 4. Definition of done

- Every register row has a test that failed on its base branch before the fix and passes after it.
- The new architecture and contract tests are in the PR-enforced suite:
  - `test_user_data_registry.py`;
  - the export-columns case in the Alembic schema contract test;
  - `test_run_outcome.py`;
  - `test_circuit_classification.py`;
  - the preset fallback-budget contract test;
  - the budget-invariant test;
  - the extended `proxy-parity.test.ts`;
  - the extended `test_prompt_trust_boundaries.py`.
- `.importlinter` contract 2 is still at 51. Both contracts are kept.
- The ratchet limits match the measured counts in `test.yml` and `ci-local.sh`.
- This file gets an "As implemented" note per PR.

---

## 5. Out of scope

- **Areas no audit has read yet:**
  - most of `application/pipeline.py` and `application/flows/*`;
  - the HyperGate sub-agent prompts and parsers;
  - `scripts/`, `sdk/` and `benchmarks/` for dead code;
  - estimate versus actual cost drift;
  - the Stripe and PayPal checkout pages in the UI (`pricing`, `UpgradeModal`);
  - `lib/markdown.ts` beyond its href handling;
  - whether Caddy blocks `/api/neuro/health` at the edge.
- **Anonymous users without Supabase are sent to `/login`** (seen while testing #152). PR 1 fixes
  the mechanism, because the transport no longer redirects. Whether a deployment without auth
  should allow anonymous chat at all is a product decision, not a defect.
- **`_ensure_user_in_db` swallowing a `users.email` UNIQUE collision** (an unconfirmed suspicion
  from the money audit). It needs a live-database reproduction before it can become a finding.
- **Search-source `href`s are not scheme-checked.** React 19 blocks `javascript:` URLs, so this is
  not exploitable today.

## 6. Open questions

| # | Question | Blocks |
|---|----------|--------|
| Q1 | What does the GDPR export include? The proposal is profile, subscriptions, quota, query log, credit ledger, history entries, stored run events, Neuro memory entries and upload metadata, without the uploaded files themselves. Should it include the files (as a zip)? | DAT-10 |
| Q2 | When a session expires on a protected page, should it redirect to `/login?next=…` silently, or show a "session expired" notice first? | UI-7, UI-8 |
| Q3 | What is the fallback price ceiling: 3x the assigned model's price, or another ratio? Should budget presets keep the direct-vendor fallback at all? | PRV-3 |
| Q4 | Should `/api/neuro/health` stay public (with counts only), or require the admin principal from #148 (SEC-6)? | DAT-12 |
| Q5 | Can `push_to_github.py` and `kill_servers.py` be deleted, or does someone run them by hand? | LEAN-7 |
| Q6 | How many history entries should each user keep (proposed: 500), and should older ones be deleted or moved to cold storage? | PER-12 |
| Q7 | Should a cancelled run get its own event type (`PIPELINE_CANCELLED`), or `PIPELINE_FAILED` with `reason="cancelled"`? A new type needs a projection and a Langfuse mapping. | RUN-7 |

---

## 7. As implemented

All eight work packages are merged into `main` as PRs #155 to #162, after the audit-2
PRs (#144 to #153) they depend on. Open questions Q1 to Q7 were settled with the defaults
proposed in section 6. Where the code differs from this plan:

| PR | Package | Difference from the plan |
|----|---------|--------------------------|
| #155 | PR 1, frontend auth (UI-6 to 10, UI-12) | A real Supabase sign-in against the new CSP was not exercised; the CSP builder is covered by a table-driven test only. |
| #156 | PR 3, run outcome (RUN-5 to 9) | The completed branch guards `outcome.state` with a `RuntimeError`, not an `assert` (bandit B101). |
| #157 | PR 4, provider resilience (PRV-1 to 4) | The rate limiter is not on `GuardedValkey`; there is no direct-vendor price table; 45 preset pairs stay over the fallback budget behind a ratchet (`MAX_IMPLICIT_OVER_BUDGET`). |
| #158 | PR 7, prompt trust (SEC-15, SEC-16) | `neutralize_for_replay` reports a fullwidth override and keeps the text, as its policy says; the YouTube title is covered by a behavioural test, not the scan list. |
| #159 | PR 5, billing webhooks (BIL-20, BIL-21) | The PayPal adapter's event table changed too. The migration creates `processed_webhooks` (no migration ever had) and revises the merge revision `20261021_000150`. |
| #160 | PR 6, history (PER-12) | The port gained `delete`; tags are derived from method and preset, so the shared per-tag `*.jsonl` files are no longer written (the old ones still hold every user's entries and need deleting by hand). |
| #161 | PR 2, data rights (DAT-10 to 13) | `DELETE /api/user/data` erases the registry minus `profile` and `identity` (it needs only a `history:delete` key); the deletion log is written before the registry runs; the erasure marker directory is `<data_dir>/.erased`; `L2Index` has no erase check of its own. |
| #162 | PR 8, lean (LEAN-7, LEAN-8) | `push_to_github.py` and `kill_servers.py` stay (Q5); `TaggedMemory` is also deleted, once PR 6 left it unused. |

Merging found one problem the plan did not predict: audit-2 PRs #148 and #151 both revised
migration `20261021_000000`, so `main` had two Alembic heads. Migration `20261021_000150`
joins them.

Known gaps left open: `delete_aggregate` leaves the `pipeline_owners` rows, so the link from
an erased user id to pipeline ids survives; `application/handlers/handlers.py::_get_file_history`
reads a directory that does not exist; `test_watermark_properties::test_code_fence_content_survives_aggressive_normalization`
(a Hypothesis counterexample in the watermark scrubber) fails on `main`.
