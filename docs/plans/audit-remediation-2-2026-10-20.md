# Second Whole-Repo Audit: Remediation Plan

**Date:** 2026-10-20
**Status:** Draft for review
**Source:** the read-only audit run on 2026-10-20 after PRs #135 to #142 merged. It covered five slices:

- money and auth (re-checked after the merges);
- method flows, preset routing and HyperGate;
- storage, documents, migrations and Neuro storage;
- the `ui-next/` frontend;
- prompts, subagents, memory and healing.

The plan covers all 44 findings: the 20 ranked ones and the 24 "left out" ones.
**Supersedes:** nothing. **Related:** [`audit-remediation-2026-10-20.md`](audit-remediation-2026-10-20.md)
is the first audit. All of its items are merged. Several findings below are bugs in how those fixes
interact with older code, so each item names the earlier ID it builds on.
**Branch target:** one branch per PR below, each cut from `main`.

### Architectural constraints

No item changes the Dependency Rule (CLAUDE.md §1):

- `domain/` and `core/` stay a dependency-free functional core.
- `application/` reaches infrastructure only through `core/ports` or `application/ports`.
- `.importlinter` contract 2 is at **51** declared exceptions and must not rise. No PR may add an
  `ignore_imports` line.
- New infrastructure code implements an existing port wherever one exists: `CreditRepository`,
  `BillingPort`, `BillingDeadLetterPort`, `PipelineOwnershipPort`, `QuotaRepository`, `MemoryPort`,
  `AuthPort`, `TranslationPort`.
- `neuro/` sits **below** `infrastructure/` in contract 1, so `neuro/` code cannot import a helper
  from `infrastructure/`. Shared file helpers go in a module that both may import (see §1, "Atomic
  file write").

The four propagation-resistance invariants (CLAUDE.md §5) are treated as requirements, not advice.
PR 7 (§2) restores invariant 4 where it is broken, and closes the gaps around it.

---

## 0. Findings register

**Check** says who confirmed it:

- **R:** re-read in the main session.
- **A:** traced end to end by an audit agent, not re-read.
- **X:** reproduced by running code.
- **P:** plausible; the row names the link that is not traced.

Every item's first task is to turn the failure case into a failing test. That test also confirms the
A and P items before any code changes.

### Money: open leaks and billing correctness

| ID | Finding | Evidence | Check | Builds on |
|----|---------|----------|-------|-----------|
| BIL-10 | `/api/run-with-context` runs paid pipelines with no credit check, no reservation, no `metered()`, no preset-tier gate and no spend cap. The default preset is `jury-premium`. | `api/routes/context.py:40-140`, `api/schemas.py:379` | R | BIL-2 |
| BIL-11 | `POST /api/pipelines/{id}/resume-stream` runs a full pipeline with no rate limit, no credit check, no reservation and no `metered()`. The UI's Resume button calls it. | `api/routes/pipelines.py:171-240` | R | — |
| BIL-12 | A client disconnect cancels the stream task. The cancellation interrupts the awaits in `metered()`'s `finally`, so neither the reservation release nor the true-up runs. `CancelledError` is not an `Exception`. | `application/services/run_metering.py:167-182` | R+X | BIL-2 |
| BIL-13 | Nothing writes Stripe customer metadata `reasoner_user_id`; three readers depend on it. Every renewal and plan change raises and returns 500, which BIL-4 turns into a 3-day retry loop. Cancellation resolves to a random user. The billing portal always returns 500. | `infrastructure/billing/stripe_adapter.py:66-72, 124-136, 202` | R | BIL-4 |
| BIL-14 | A second checkout overwrites the existing subscription row, so a live subscription is no longer tracked. Account deletion cannot cancel it. | `api/billing_router.py:27-64`, `infrastructure/persistence/subscription_repo.py:107-142` | A | BIL-8 |
| BIL-15 | Webhook retries (BIL-4) and the dead-letter replay re-apply payload snapshots with no ordering guard. A retried `updated(active)` after `deleted` reactivates a cancelled plan. | `application/services/billing_service.py:59-80` | P (Stripe retry timing) | BIL-4 |
| BIL-16 | When the same `reference_id` races, the credit ledger re-raises `UniqueViolationError` (500) instead of returning the entry that won. | `infrastructure/persistence/credit_repo_postgres.py:136-193` | A | BIL-1 |
| BIL-17 | `POST /api/gate` is anonymous and makes five LLM calls. The anonymous rate-limit bucket is `ip:sha(User-Agent)`, so rotating the User-Agent gives a fresh bucket. | `api/routes/gate.py`, `api/dependencies.py:440` | A | BIL-7 |
| BIL-18 | After account deletion the Supabase identity and JWT stay valid, and `_provisioned_user_ids` is a per-process set with no expiry. A deleted user on a worker that cached the id skips re-provisioning, and the credit calls fail open. | `api/dependencies.py:72, 94` | P (whether the run then succeeds without a `users` row) | BIL-5, BIL-8 |
| BIL-19 | `account/delete` returns 502 indefinitely when the provider rejects cancelling a subscription that is already cancelled but still `active` locally. | `api/saas_router.py:~208` | A | BIL-8 |

### Auth and identity

| ID | Finding | Evidence | Check |
|----|---------|----------|-------|
| SEC-6 | No production principal can hold `admin`. The Supabase adapter builds `User` with no scopes, and keys cannot be granted `admin`. As a result, dead-letter replay (BIL-4), credit grants and the global stop always return 403 in production. | `infrastructure/auth/supabase_adapter.py:105`, `api/routes/admin.py:21-30`, `domain/api_keys.py:40` | R |
| SEC-7 | The `client_run_id` claim `SET run:{id} NX EX 3600` is global across tenants and is never released. A retry after a 402 or a dropped connection gets 409 for an hour. Two tenants can collide on the same id. `set_owner` upserts unconditionally, so after the TTL the second tenant becomes the owner of the first tenant's pipeline. | `infrastructure/redis/run_state.py:192`, `api/execution/pipeline.py:68`, `pipeline_ownership_repo.py:68-80` | R |

### Prompt trust (propagation resistance)

| ID | Finding | Evidence | Check |
|----|---------|----------|-------|
| SEC-8 | The follow-up learn stores the caller-supplied `previous_synthesis` as the assistant's answer when there is no final solution. This breaks invariant 4. `postflight` already learns the same turn, so every follow-up is stored twice. | `api/streaming.py:232-255`; the removed twin is in `application/orchestrator.py:521-530` | R |
| SEC-9 | Context vetting interpolates snippets raw, without the `<<<EXTERNAL_CONTENT>>>` marker, and fails open: an unparseable reply passes every result as clean and sets the context to "good". | `application/flows/search_phases.py:277-311`, `phases/_universal.py:264-282` | R |
| SEC-10 | Deep-read falls back to the raw page text exactly when `sanitize_for_prompt` rejects the page, and when the deep-read LLM is off. Those entries skip vetting. | `application/flows/search_phases.py:370-449` | A |
| SEC-11 | `decomposition_prompt` and `fusion_prompt` interpolate the Python repr of the raw web result dicts, unwrapped and uncapped. | `phases/_universal.py:72, 91` | A |
| SEC-12 | The cross-language pivot replaces `state.problem` with translated text that is never re-checked. The translator call is unhardened and unwrapped. | `application/pipeline.py:569-579, 621`, `infrastructure/translation/llm_translator.py:21-45` | A (bypass P) |
| SEC-13 | Model-authored text passed between phases is `json.dumps`-ed but not wrapped. This affects critique candidates, debate, jury, delphi, dialectical, analogical and bayesian. The `build_memory_context` provenance header also prints caller-writable metadata outside the wrapper. | `phases/multi_perspective.py:110`, `phases/debate.py:39,79`, `phases/jury.py:16-66`, `phases/_shared.py:~251` | A |
| SEC-14 | Subagent prompts use `state.problem` and candidate content raw. The subagent synthesis path returns a `FinalSolution` that skips the `finalize_solution` URL allowlist. These paths are behind flags (`USE_SUBAGENT_*`, default false). | `subagents/synthesis/*.py`, `subagents/*/context_enricher.py` | A |

### Persistence and storage

| ID | Finding | Evidence | Check |
|----|---------|----------|-------|
| PER-7 | Alembic never creates `user_credits`, `credit_ledger`, the Postgres `api_keys` table or the ledger's unique index. Those exist only in the raw `migrations/004`, `006`, `007` and `008` `.sql` files. The baseline also declares `UNIQUE (event_id)` on a table partitioned by `aggregate_type`, which Postgres rejects. It has no `events_default` partition, and its `snapshots` table has no unique `aggregate_id`. | `migrations/alembic/versions/df9629e72f17_baseline.py:105-150`, `postgres_store.py:172-205`, `docker-entrypoint.sh:10` | R (not applied to real Postgres) |
| PER-8 | The upload hash index lives in the package directory, so it resets on every deploy. It does a whole-file read-modify-write with no lock, so concurrent writes lose entries. The write is not atomic, so a half-written file reads as `{}`. The quota (OPS-7) is computed from this index. | `infrastructure/uploader.py:31-53, 366, 537, 558-571` | R |
| PER-9 | Upload write order leaves orphan content files when an error happens before `meta.json` is written. A delete that races indexing leaves an orphan `.vectors.json`. The `.text.json` and `.vectors.json` sidecars are not counted in the quota. | `infrastructure/uploader.py:481-537, 637-686`, `documents/vector_store.py:162-175` | A |
| PER-10 | The Neuro L2 index adds duplicates, writes non-atomically, and replaces a corrupt file with an empty one on the next save, which wipes the tenant's memory. Several workers overwrite each other. L1 hits carry no metadata, so they are dropped, but they still use up recall slots, which leaves active users with empty recall. | `neuro/cache.py:83-130, 149-189`, `neuro/server.py:600-620, 761-767` | A |
| PER-11 | Neuro tenant directory names collide after sanitising and truncating `agent_id`. This happens within one owner only, not across tenants. | `neuro/config.py:343-368`, `neuro/server.py:369-391` | A |

### Data and content

| ID | Finding | Evidence | Check |
|----|---------|----------|-------|
| DAT-8 | `_chunk_text` stops at 500 chunks (about 400K characters) and says so only in a log line. It also emits a redundant tail chunk that is a suffix of the one before it. | `documents/vector_store.py:44-54, 122-124` | A |
| DAT-9 | Compression edge cases: an unclosed `/*` on one line drops everything after it. When enabled, `#` lines are stripped from user code fences for user-input roles. Both are behind `TOKEN_NEURO_COMPRESSION`, which defaults to false. | `neuro/compression.py:75`, `infrastructure/llm/executor.py:914-922` | A |

### Pipeline core: flows, routing and presets

| ID | Finding | Evidence | Check |
|----|---------|----------|-------|
| FLOW-1 | `errored` is set on a retryable failure and never cleared. A critical phase that succeeds on its retry still returns `False` and ends the run. | `application/flows/runner.py:163, 239-246, 276` | R |
| FLOW-2 | Jury roles `generator_1..3`, `critic_1..3` and `panel_critic`, and the dialectical and socratic roles `constructive`/`destructive`/`systemic`, are not routed by any preset, so they all run on the preset's primary model. Jury critics see only a one-line summary of each candidate. | `flows/jury_phases.py:54, 125`, `router.py:390-393`, `phases/jury.py:28` | R |
| FLOW-3 | When every model call in a generation phase fails, nothing raises, so the `critical` flag never triggers and the run keeps spending. Affects Generation Pool, Critic Pool, Opening Statements and Delphi Round 1. | `jury_phases.py:79-85, 128-136`, `debate_phases.py:42-49`, `delphi_phases.py:36-60` | A |
| FLOW-4 | A model reply of `"open_questions": null` crashes synthesis. The Scientific and Socratic prompts subscript method state with `["…"]`. | `flows/synthesis_phase.py:250-254`, `phases/scientific.py:31`, `phases/socratic.py:16` | R |
| FLOW-5 | HyperGate fast paths misroute common inputs: `research_override`, `_WRITING_INTENT` ("write a report generator"), the realtime "current value", and unanchored factual patterns. | `hypergate/hyperagent.py:57, 75-80, 112-133, 376-387` | A |
| FLOW-6 | ToT expands only the first decision point, and its evaluate and backtrack prompts contain no problem, no evaluations and no path. | `phases/tot.py:19-34`, `flows/cognitive_phases.py` | A |
| FLOW-7 | Iterative Critique checks `verdict == "ACCEPT"` against an unnormalized string, so a critic answering "Accept" never converges and the loop runs all 5 rounds. | `flows/iterative_critique_phases.py:148, ~372` | A |
| FLOW-8 | The cross-language translate-out mutates `fs.core_solution` before the other fields, so a failure partway through leaves half the solution translated. | `application/pipeline.py` `_phase_cross_language_translate_out` | A |
| FLOW-9 | Prism `mode="quality"` allows 25 iterations inside a 120s critical phase, and citations are written only when the loop ends. A timeout therefore loses everything and aborts the run. | `flows/research_phases.py:~48`, `flows/prism_research.py:27, ~281` | A |
| FLOW-10 | SoT sub-problems and Coding files fan out with no count cap. Failed Coding files are stored as `"# Error: …"` and treated as real code. | `flows/cognitive_phases.py:~89`, `flows/coding_phases.py:149-184` | A |
| FLOW-11 | Jury and Self-Discover store `call_llm`'s meta dict as `model_used`, so the renderer prints `str(dict)`. | `flows/jury_phases.py:~50, ~76`, `flows/cognitive_phases.py:418`, `_render_jury.py:38` | A |

### Frontend

| ID | Finding | Evidence | Check |
|----|---------|----------|-------|
| UI-1 | A resumed run cannot be stopped. `resumePipelineStream` has no AbortController, and Stop only sets `running=false` while the paid run continues. | `ui-next/src/lib/api-client.ts:102-109`, `app/chat/page.tsx:962-1060` | R |
| UI-2 | Pressing Enter twice during the routing check starts two runs. The submit guard ignores `gateChecking`. | `app/chat/page.tsx:247, 304-336`, `components/layout/Composer.tsx:176-179, 337` | A |
| UI-3 | New or Load during a run saves that run into the newly opened thread, because `done` reads `conversationIdRef.current` at save time. | `app/chat/page.tsx:785-830, 968-1075` | A |
| UI-4 | The REST stop sends no `run_id`. For a normal user it is a 403 that the UI swallows. For an admin it cancels every user's runs. | `hooks/usePipelineStream.ts:94-98`, `app/api/stop/route.ts`, `api/__init__.py:875-920` | R |
| UI-5 | IndexedDB history and the cached subscription survive sign-out and account deletion, so user B sees user A's conversations on a shared browser. | `lib/db.ts:12`, `app/providers.tsx:28-33`, `stores/app-store.ts` `logout` | A |

### Operations and lean

| ID | Finding | Evidence | Check |
|----|---------|----------|-------|
| OPS-9 | The Next proxy's rate-limit key is wrong behind a CDN plus load balancer when `TRUSTED_PROXIES` is unset: every user shares one bucket. The buckets are also per Node instance. | `ui-next/src/lib/security-server.ts:422, 466-528` | P (production topology) |
| LEAN-6 | `domain/preset_core.get_method_from_preset` is a stale duplicate of `reasoner/presets.py:47` with no coding branch. Only tests import it. | `domain/preset_core.py` | A |

---

## 1. Design principles applied

Each pattern is chosen for the module it lives in. Where the codebase already has a mechanism, the
plan reuses it.

| Module | Paradigm / pattern | Applied to | Why |
|--------|-------------------|------------|-----|
| `api/` run entry points | **Single admission pipeline** (Template Method over the guard steps): one `admit_run()` that returns an immutable `Admission` value | BIL-10, BIL-11, SEC-7 ordering | Six entry points each hand-assemble the same sequence today: `/api/run`, follow-up, agent, MCP run, MCP follow-up and now context and resume. BIL-10 and BIL-11 exist because two of them forgot steps. One function cannot forget a step that its siblings have. |
| `application/services/run_metering` | **Shielded finalizer** (structured concurrency: settlement is a critical section, protected from cancellation and bounded by a timeout) | BIL-12 | Settlement must finish on every exit path, including the client hanging up. A `finally` that awaits without a shield is not every exit path. |
| `application/services/billing_service` | **Monotonic event guard** (an event older than the stored state is a no-op) and **re-read from the source of truth** for Stripe | BIL-15 | Retries and replays are now durable (BIL-4). Durable delivery needs order-insensitive application. |
| `infrastructure/billing/*` | **Anti-corruption layer**: the adapter alone maps provider ids to our user id, through metadata first and then our own table | BIL-13, BIL-19 | Provider payload quirks stay in the adapter. The application sees a resolved `user_id` or a typed "unresolved" result, never a random UUID. |
| `domain/saas`, `domain/api_keys` | **Pure policy functions** (Specification style) | BIL-14 `checkout_allowed()`, SEC-6 `admin_scopes()` | Rules that decide money and access get exhaustive tests without mocks, which is the pattern PR 1 of the first audit set (`key_allows()`). |
| Auth adapter | **Mapper** from identity-provider claims to domain `User.scopes` | SEC-6 | The adapter is the one place that knows how Supabase spells a role. |
| Idempotency and ownership | **Tenant-scoped idempotency key**, **release on non-completion**, **first writer wins** (`INSERT … ON CONFLICT DO NOTHING`, then compare) | SEC-7 | An idempotency key is a promise to one caller, not a global name. Ownership must never move. |
| Credit ledger | **Idempotent receiver**: a duplicate reference returns the original entry | BIL-16 | This matches what the code comment already promises. |
| `application/flows/runner` | **Explicit per-attempt outcome** (a small state machine: `ok`, `retry` or `failed` per attempt, decided once) | FLOW-1 | A flag that outlives the attempt it describes is the bug, so state is scoped to the attempt. |
| Flow phases | **Postcondition at the phase boundary** (fail fast: a phase that produced nothing raises `PhaseError`) | FLOW-3 | This reuses the rule `perspective_phases.py` already applies. Callers then see failure through the existing `critical` mechanism. |
| Model JSON readers | **Tolerant reader** at the trust boundary: one `coerce_list()` and one `coerce_str()` in `core/parsing` | FLOW-4, FLOW-7 | Model output is untrusted input. It is normalized once at the boundary, never at every use. This sits next to `extract_json`, which is already the only JSON entry point. |
| `domain/` presets | **Declarative configuration validated as a specification**, plus a **contract test** between the roles a flow calls and the roles the presets route | FLOW-2 | `validate_presets` passes today only because it checks fewer roles than the flows use. The contract test makes the two lists one fact. |
| `hypergate/` | **Table-driven classifier with a golden corpus** (characterization tests) | FLOW-5 | Regex fast paths drift silently. A labelled corpus of real inputs is the only spec they can be held to. |
| `phases/` prompt builders | **Wrap by construction** with the existing `_wrap_external_content` and `build_web_sources_block`, plus a **lint-style test** that forbids raw interpolation of known untrusted fields | SEC-9, SEC-11, SEC-13 | Invariant 4 holds by omission, so a refactor breaks it silently. A test turns the omission into a checked rule. |
| Search, vetting, deep-read | **Fail closed with visible degradation** (`core.degrade.degraded()`) | SEC-9, SEC-10 | A security check that fails must not report success. This uses the repo's existing helper for visible fallbacks. |
| Memory writes | **Single writer** (`postflight` is the only `learn` caller for a run) | SEC-8 | A second writer is how invariant 4 broke twice. |
| Translation | **Re-validate at every trust transition** | SEC-12 | Text produced by a model from user input is still user input. |
| File-backed indexes (uploads, Neuro) | **Atomic file write** (temp file + `os.replace`, the pattern already in `api/cache.py:184-200`), **read-modify-write under an advisory lock**, and **quarantine on corruption** | PER-8, PER-10 | `api/cache.py` already solved partial writes. The helper is extracted and reused instead of written a third time. |
| Upload quota | **Atomic conditional increment** (the ledger pattern: `UPDATE … SET bytes = bytes + $n WHERE bytes + $n <= $cap`) behind the existing `QuotaRepository` port | PER-8 | Check-then-write on a file cannot be made correct across workers. The conditional update is the same pattern credits and run quotas already use. |
| Upload writes | **Write the commit record first, compensate on failure** (`meta.json` first, then delete what was created in `except`) | PER-9 | Every file on disk then belongs to a record. Orphans become impossible instead of merely rare. |
| `documents/` chunking | **Pure function with property-based tests** (`hypothesis` is already in `requirements-dev.txt`) | DAT-8, DAT-9 | Boundary bugs are what property tests find, and these functions have no I/O. |
| Pipeline state updates | **Immutable update** (build the translated `FinalSolution`, then assign it once) | FLOW-8 | No half-updated state is visible on failure. |
| Fan-out | **Bounded fan-out** from named constants in `core/constants_limits.py` | FLOW-10 | Concurrency caps (`Semaphore`) limit speed, not cost. Count caps limit cost. |
| `ui-next/` run lifecycle | **One run controller** (a hook that owns a finite state machine: `idle → gating → streaming → stopping → idle`, with one AbortController and the run's identity captured at start) | UI-1, UI-2, UI-3, UI-4 | Four bugs share one cause: run state is spread across refs, flags and handlers. One owner with explicit states makes each of them unrepresentable. |
| `ui-next/` local data | **Per-principal namespace** (IndexedDB name keyed by user id) plus **clear on sign-out** | UI-5 | Local data must not outlive the identity that wrote it. |
| Deploy config | **Fail-fast configuration validation** at startup | OPS-9 | A misconfigured proxy must not boot into a silent shared bucket. |
| Schema | **One migration authority** (Alembic only) with **expand-only, idempotent revisions** and a **schema contract test** | PER-7 | Two sources of truth for the schema is why the credit tables are missing. |

---

## 2. Work packages

There are **nine PRs**. PR 1 is a hotfix and goes first. PR 2 waits on one decision (Q1) and should
merge before the next production deploy. The rest are independent after PR 1; §3 lists the files
they share. Each item lists the design, the changes, the **test that must fail before the fix**,
and the risk.

**Ratchets.** Every PR re-measures ruff, vulture and silent-failure at merge time and sets the
limits to the measured value, in both `.github/workflows/test.yml` and `scripts/ci-local.sh` (the
first audit's merges showed these drift). The import-linter contract 2 count stays at 51.

---

### PR 1: `fix/audit2-money-leaks` (BIL-10, BIL-11, BIL-12)

These are open money leaks that need nothing more than a normal login. They ship first.

#### Shared design: `admit_run()`

Add `api/run_admission.py`. It belongs in the API layer, next to `dependencies.py`, because it
composes HTTP guards.

```python
@dataclass(frozen=True)
class Admission:
    user: User | None
    preset: str
    tier: str
    reference_id: str
    reserved_credits: int

async def admit_run(
    request: Request, *, user: User | None, problem: str, preset: str | None,
    client_run_id: str | None, kind: str = "run",
) -> Admission:
    # 1. _require_auth_if_legacy_disabled(user)
    # 2. check_preset_access_if_authenticated(preset, user, request)   # before claiming the id
    # 3. check_run_allowed / apply_spend_limits for the tier           # today only in execution/pipeline
    # 4. register_run_or_error(user, client_run_id)                    # SEC-7 makes this tenant-scoped
    # 5. anonymous: enforce_anonymous_trial_cap(...)
    # 6. reference_id = run_reference(client_run_id, kind)
    # 7. reserved = await reserve_or_402(...)
```

The FastAPI `Depends` guards that stay per-route are `check_rate_limit`,
`check_quota_if_authenticated`, `require_credits_if_authenticated` and `require_csrf`. Every route
that streams a pipeline then does:

```python
adm = await admit_run(request, user=user, problem=..., preset=..., client_run_id=..., kind=...)
return StreamingResponse(metered(stream, RunContext.from_admission(adm, interface=...), CreditSink(), observer))
```

Migrate `/api/run`, `/api/run-followup`, `routes/agent.py` and `api/mcp/tools.py` (MCP keeps BIL-7's
validate, then claim, then reserve order, which `admit_run` encodes) in the same PR. This is a
refactor of four working call sites. The tests from BIL-1, BIL-2 and BIL-7 must stay green
unchanged.

**Architecture test:** add `tests/architecture/test_run_admission.py`. It walks `app.routes`. For
each route whose endpoint module streams `run_stream`, `run_stream_cached` or `run_followup_stream`,
it asserts the endpoint calls `admit_run` and `metered`, using an AST scan of the endpoint function.
This is the test that would have caught BIL-10 and BIL-11.

#### BIL-10: bill `/api/run-with-context`, or delete it (Q2)

- **Design:** if the route stays, it goes through `admit_run` + `metered()`. Its phases are
  hand-rolled and emit no cost frames, so it must emit one final `done` frame carrying
  `state.total_cost_usd` (`extract_run_cost` already reads that frame), or route through
  `WorkflowRunner`. If Q2 says delete: remove the route, its `widgets.py:44` mention and its tests.
  The grep found no UI caller.
- **Failing test first:** a FREE user with a balance of 0 POSTs `/api/run-with-context` and gets
  `402`. A funded user's ledger shows a reservation and a settlement with the same `reference_id`.
- **Risk:** low. No UI caller.

#### BIL-11: bill resume

- **Design:** `resume_pipeline_stream` adds `Depends(check_rate_limit)` and
  `Depends(require_credits_if_authenticated)`. It calls
  `admit_run(..., client_run_id=pipeline_id, kind="resume")`, where `run_reference(pipeline_id,
  "resume")` gives a fresh ledger reference per resume, and wraps `stream_with_resume_meta` in
  `metered()`. Q3 decides whether the estimate covers the full preset or only the remaining phases.
  Until Q3 is answered, reserve the full estimate. The true-up then charges actual cost, so the
  user is never overcharged beyond the hold.
- **Failing test first:** resume with a balance of 0 returns `402`. A funded resume leaves a
  release plus a charge on the ledger.
- **Risk:** medium. This changes a user-visible behavior from free to billed. Note it in the
  release notes.

#### BIL-12: shield the settlement

- **Design:** wrap the whole `finally` body in a shielded, bounded scope:

  ```python
  finally:
      with anyio.CancelScope(shield=True):
          with anyio.fail_after(SETTLE_TIMEOUT_S):   # new constant in core/constants_limits.py
              await _finalize(sink, ctx, cost_usd, has_error, observer)
  ```

  `anyio` is already a Starlette dependency. Use it here rather than `asyncio.shield`, because the
  cancellation comes from Starlette's anyio task group. The timeout keeps a hung ledger call from
  holding a worker forever. On timeout, `degraded("run_metering.settle_timeout", …)` records an
  unsettled reservation, which `BIL-5`'s dead-letter path already replays.
- **Narrow window:** a client that drops before the first `__anext__` never starts the generator,
  so no `finally` runs and the reservation stays held. Close it by having `admit_run`'s caller
  register a `BackgroundTask` that releases the reservation if the stream never started. Track this
  with a `started` flag that `metered()` sets on entry.
- **Failing test first:** a real ASGI disconnect, not `aclose()`. Run the app under `uvicorn` in a
  thread, or drive Starlette's `StreamingResponse` with an ASGI `receive` that yields
  `http.disconnect` after the first frame. Assert the ledger has the release and the true-up. The
  audit's repro script is the template.
- **Risk:** low. This only adds protection.

---

### PR 2: `fix/audit2-schema` (PER-7)

**Blocked on Q1** (the same question as the first audit's Q3): was production built by Alembic, by
the raw `.sql` files, or by hand?

- **Design:** Alembic is the only schema authority.
  - **One new revision** `20261021_000000_credits_keys_and_event_constraints.py`. It is expand-only
    and idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE UNIQUE INDEX IF NOT EXISTS`), so it is
    safe on a database built from raw SQL and on a fresh one. It creates:
    - the 004 dead-letter table, `user_credits`, `credit_ledger` and the unique
      `idx_credit_ledger_user_reference`;
    - the Postgres `api_keys` table;
    - 006 `call_telemetry`, if Postgres uses it (check its repo);
    - the 008 `DROP INDEX IF EXISTS idx_events_type`;
    - `events_default` (`CREATE TABLE IF NOT EXISTS events_default PARTITION OF events DEFAULT`).
  - **Baseline fix.** Replace the inline `UNIQUE` with
    `CREATE UNIQUE INDEX uq_events_event_id_type ON events(event_id, aggregate_type)`. Make
    `snapshots.aggregate_id` unique. Editing a baseline is normally wrong. It is right here because
    the baseline as written cannot have been applied to Postgres. Q1 confirms this. If production was
    built from the baseline anyway, the new revision does the same fix with `IF NOT EXISTS` guards
    instead.
  - **Move** `migrations/*.sql` to `migrations/legacy/` with a README saying they are reference
    only, as `plans/PRODUCTION_READINESS_PLAN.md:532` already proposes.
  - **One index definition.** Remove the `CREATE INDEX IF NOT EXISTS` duplicates from
    `postgres_store.py` startup, so the index definition comes from Alembic only, not from boot order.
- **Schema contract test:** add `tests/integration/test_alembic_schema_contract.py`, marked
  `integration` and run in a new CI job with a `postgres:16` service. It runs `alembic upgrade head`
  on an empty database, then reads `information_schema` and `pg_indexes`. It asserts every table,
  column and unique index that the Postgres repos rely on: the `ON CONFLICT` targets in
  `postgres_store.py`, `credit_repo_postgres.py`, `api_key_repo_postgres.py` and
  `subscription_repo.py`. Locally, the test container `reasoner-pg-test` on port 55499 serves.
- **Failing test first:** that contract test, on the current `main`.
- **Risk:** high if Q1 is answered wrongly. Run it against a copy of the production database first.

---

### PR 3: `fix/audit2-billing-provider` (BIL-13, BIL-14, BIL-15, BIL-16, BIL-19, SEC-6)

#### BIL-13: resolve the Stripe customer to our user

- **Design (anti-corruption layer):**
  - At checkout: `subscription_data={"metadata": {"reasoner_user_id": user_id}}`, plus
    `customer_creation="always"` and `metadata` on the session.
  - In `_handle_checkout_completed`: `stripe.Customer.modify(customer, metadata={...})`.
  - `_customer_user_id()` becomes `resolve_user_id(event) -> str | None`. It tries the customer
    metadata, then subscription metadata, then `SubscriptionRepository.get_user_by_stripe_sub_id()`,
    which is a new read on the existing repo.
  - It returns `None` instead of raising. `None` is a typed "unresolved" result: the handler
    dead-letters it once (BIL-4's dead-letter port) and returns 200, so Stripe stops retrying.
  - `_handle_payment_failed` and `_handle_subscription_deleted` never invent a `uuid4` user. Delete
    that fallback.
  - `create_portal_session` uses the stored `stripe_customer_id` from the subscription row instead
    of searching customers by metadata.
- **Backfill:** a one-off script `scripts/backfill_stripe_customer_metadata.py` (dry-run by
  default) that sets metadata on the customers of existing `subscriptions` rows.
- **Failing test first:** with recorded fixtures for `customer.subscription.updated` and `deleted`
  on a customer with no metadata, the handler resolves the user through the subscription table, and
  no `usage_quotas` row is written for an unknown user.
- **Risk:** medium. The backfill touches live Stripe data, so it is a dry run first and the person
  running it confirms.

#### BIL-14: one live subscription per user

- **Design:**
  - Add the pure policy `domain/saas.checkout_allowed(existing: Subscription | None,
    target_tier) -> CheckoutDecision`, which returns `ALLOW`, `USE_PORTAL` or `SAME_PLAN`.
    `create_checkout` returns 409 with a portal URL for anything but `ALLOW`. Q4 decides whether an
    upgrade goes through the portal (proration) or is blocked.
  - `upsert_subscription` uses the user-id fallback only when the matched row has no id for the
    incoming provider. Otherwise it inserts a new row, so a second live subscription is still
    tracked and account deletion can cancel it.
  - Cross-provider: `deleted` for Stripe sets `stripe_status`, not the shared row's entitlement,
    when a PayPal id on the same row is active. Or simpler, one row per provider subscription, which
    the previous bullet already gives.
- **Failing test first:** two checkouts for one user leave two rows. Account deletion cancels both.
- **Risk:** low.

#### BIL-15: order-insensitive webhook application

- **Design:** add a column `subscriptions.last_event_at TIMESTAMPTZ`, in the PR 2 revision or its
  own. Apply an event only if `event.created >= last_event_at`, using the conditional `UPDATE … WHERE
  last_event_at IS NULL OR last_event_at <= $ts`. For Stripe `customer.subscription.*`, also
  re-fetch `stripe.Subscription.retrieve(id)` inside the adapter and apply the live state. That
  makes an out-of-order retry harmless even when timestamps tie. PayPal uses `event.create_time`.
- **Failing test first:** apply `deleted(t=2)`, then `updated(active, t=1)`. The subscription
  stays cancelled.
- **Risk:** low.

#### BIL-16: idempotent ledger receiver

- **Design:** move the reference lookup **after** `SELECT … FOR UPDATE` on `user_credits`, inside
  the same transaction. A racing duplicate then waits on the lock and finds the winner's entry,
  without ever hitting the unique violation. Keep `except UniqueViolationError` as a fallback that
  re-reads in a fresh transaction and returns `_to_entry(row)`.
- **Failing test first:** two concurrent `record()` calls with one `reference_id` against Postgres:
  one entry, and both calls return it. Use the `reasoner-pg-test` container.

#### BIL-19: idempotent provider cancel

- **Design:** in `cancel_subscription` (both adapters), treat the provider's "already cancelled" or
  "not found" response as success, and sync the local status. The adapter decides which provider
  error codes mean that. The application only sees success or a real failure.
- **Failing test first:** cancel a subscription the fake provider reports as already cancelled.
  Account deletion completes.

#### SEC-6: a real admin principal

- **Design (Mapper):**
  - The Supabase adapter maps `app_metadata.role == "admin"` (users cannot edit `app_metadata`) to
    `User(scopes=frozenset({"admin"}))`.
  - As an alternative or addition, use an allowlist `ADMIN_USER_IDS` in `core/settings.py`. Q5
    decides which.
  - The pure function `domain/api_keys.admin_scopes(role, user_id, allowlist) -> frozenset[str]`
    holds the rule. The adapter calls it.
  - Keys still cannot hold `admin` (`ASSIGNABLE_SCOPES` is unchanged).
- **Failing test first:** a Supabase user with the admin role can `POST
  /api/admin/billing/dead-letter/replay` in production mode. A normal user still gets 403.
- **Risk:** medium. This grants power. The tests cover the negative case first.

---

### PR 4: `fix/audit2-run-identity` (SEC-7, BIL-17, BIL-18)

Touches `api/idempotency_http.py`, `application/services/idempotency.py`, `run_state.py`,
`pipeline_ownership_repo.py`, `routes/gate.py` and `dependencies.py`. **After PR 1**, because
`admit_run` calls `register_run_or_error`.

#### SEC-7: tenant-scoped, releasable run claims; ownership never moves

- **Design:**
  - `register_run(owner_key, client_run_id)`, where `owner_key` is the user id, or for anonymous
    callers the anonymous bucket key. The key becomes `run:{owner_key}:{client_run_id}`.
  - `metered()`'s finalizer releases the claim (`DEL`) when the run did not complete. A completed
    run keeps its claim for the TTL, so a duplicate still gets 409. The `has_error` flag already
    tells the two cases apart.
  - The `PipelineOwnershipPort.set_owner` contract becomes **insert if absent**: `INSERT … ON
    CONFLICT (pipeline_id) DO NOTHING RETURNING user_id`, followed by a compare. A mismatch raises
    `OwnershipConflict`, and the API maps that to 409. Document it on the port.
  - The aggregate id stays the caller's `client_run_id` for the owner. Two tenants with the same id
    now get different claims, and the ownership insert stops the second one from taking the
    pipeline id.
- **Failing test first:**
  - A 402 with `client_run_id="job-1"`, then a top-up, then a retry with `"job-1"` succeeds.
  - Two tenants on `"job-1"`: the second gets 409 and never becomes the owner.
- **Risk:** medium. The public docs (`ui-next/src/lib/docs.ts:641`, `DevelopersPage.tsx:90`)
  describe the retry behavior. Make the code match them, and re-read them in this PR.

#### BIL-17: gate the gate

- **Design:** reuse BIL-7's MCP fix. `/api/gate` requires a principal, either a JWT or an API key
  (Q6 confirms, since the landing page might call it anonymously), and uses a per-user rate bucket.
  If anonymous access must stay, key the anonymous bucket on the client IP alone, not on IP plus
  User-Agent. Add a per-IP daily cap through `enforce_anonymous_trial_cap`.
- **Failing test first:** anonymous `/api/gate` returns 401. Or, if Q6 keeps it anonymous, rotating
  the User-Agent does not reset the bucket.

#### BIL-18: deleted accounts stop working everywhere

- **Design:**
  - Account deletion calls a new `AuthPort.delete_identity(user_id)`. The Supabase adapter
    implements it with the admin API, which revokes sessions and deletes the auth user. Q7 confirms.
  - `_provisioned_user_ids` becomes a bounded TTL cache (the house pattern: `OrderedDict` plus
    expiry, as OPS-3's token cache does).
  - Provisioning checks `account_deletion_log`, which already exists from migration 005 / revision
    `20260929`, and refuses a deleted id.
  - Credit fail-open (BIL-5 kept some paths open) must not apply when the cause is a missing
    `users` row. That is a hard 403.
- **Failing test first:** delete an account, then send a request with the old JWT on a worker that
  cached the id. It gets 401 or 403, and no LLM call is made.

---

### PR 5: `fix/audit2-flows` (FLOW-1, FLOW-3, FLOW-4, FLOW-6 to FLOW-11, LEAN-6)

All in `application/flows/`, `phases/` and `core/parsing`. No API change.

| ID | Design | Changes | Failing test first |
|----|--------|---------|--------------------|
| FLOW-1 | Per-attempt outcome | Move `errored` inside the loop and reset it at the top of each attempt. Decide `is_fatal` only on the final attempt, so `PHASE_FAILED(fatal)` is not emitted for an error that will be retried. | A critical phase raises a retryable error once, then succeeds. The run continues to synthesis and `phase_complete` is emitted. |
| FLOW-3 | Postcondition | Add a shared `require_survivors(items, phase_name)` in `flows/_shared.py` (or wherever `perspective_phases` raises today; reuse its message), called at the end of Generation Pool, Critic Pool, Opening Statements and Delphi Round 1. Mark Delphi Round 1 `critical`. | All three jury generators fail. The run ends at Generation Pool and no further LLM call is made. |
| FLOW-4 | Tolerant reader | Add `core/parsing.coerce_list(value) -> list` (`None` becomes `[]`, a string becomes `[s]`, anything else is wrapped or dropped) and use it at `synthesis_phase.py:250-254` and the other `json_data.get(…, [])` sites. A grep for `.get("…", [])` on `extract_json` output gives the list. Use `.get("hypotheses", [])` and `.get("questions", [])` in `scientific.py:31` and `socratic.py:16`, and skip the phase when the list is empty, as ToT does. Use `None` instead of `0.0` for a hypothesis with no tests. | Synthesis given `{"open_questions": null}` returns a solution. The Scientific prompt with no hypotheses does not raise. |
| FLOW-6 | Bounded loop | Pass `state.problem`, `current_path` and `evaluations` into `tot_generate_prompt`, `tot_evaluate_prompt` and `tot_backtrack_prompt`. Loop generate and evaluate over `dps[:MAX_TOT_DEPTH]` inside the ToT phase. Guard the index. | With 4 decision points the path has 4 elements, and the backtrack prompt contains the problem text. |
| FLOW-7 | Tolerant reader | Add `coerce_verdict()` (`strip().upper()`) at the parse site (`iterative_critique_phases.py:~372`). Compare only normalized values. | A critic that answers "Accept" converges in round 1. |
| FLOW-8 | Immutable update | Build the translated `FinalSolution` with `dataclasses.replace` (or a copy), then assign `state.final_solution` once. | A translator that fails on the second field leaves the original solution intact. |
| FLOW-9 | Bounded work, incremental output | Default Prism to `mode="balanced"` under the 120s timeout, or derive iterations from the timeout. Write citations to state on each iteration. | A Prism loop that times out keeps the citations collected so far. |
| FLOW-10 | Bounded fan-out | Add `MAX_SOT_SUBPROBLEMS` and `MAX_CODING_FILES` to `core/constants_limits.py`, and slice before `gather`. Coding: skip failed files and raise `PhaseError` if all fail. | A 40-file spec makes `MAX_CODING_FILES` calls. An all-failed Coding generation raises. |
| FLOW-11 | — | Use `(meta or {}).get("model", "")` at the three sites. | `GenerationCandidate.model_used` is a `str`. |
| LEAN-6 | Delete | Delete `domain/preset_core.get_method_from_preset`, and point its tests at `reasoner.presets.get_method_from_preset`. | — (the existing tests keep passing) |

**Risk:** FLOW-1 changes run outcomes, in the right direction. FLOW-3 makes some runs end earlier and
cheaper. Both belong in the release notes.

---

### PR 6: `fix/audit2-routing-and-presets` (FLOW-2, FLOW-5)

Kept separate from PR 5 because it changes which models and methods users get. That is a product
change, and it should be reviewed alone.

#### FLOW-2: route every role a flow uses

- **Design (declarative configuration + contract test):**
  - Add `generator_1..3`, `critic_1..3` and `panel_critic` routing and fallbacks to the jury
    presets.
  - Add `constructive`, `destructive` and `systemic` to the dialectical and socratic presets, with
    the bloc rules from CLAUDE.md (≥3 labs budget, ≥4 premium, scorer outside the dominant
    generator's ecosystem).
  - Add the jury roles to `_KNOWN_ROUTING_ROLES`.
  - Extend `scripts/validate_presets.py`'s bloc check to these role groups.
  - Jury critics get `solution` (truncated with `TRUNCATION.CONTENT`) and `key_claims` per
    candidate (`phases/jury.py:28`).
- **Contract test:** add `tests/unit/test_flow_roles_are_routed.py`. It collects every role
  literal passed to `call_llm(…, role=…)` in `application/flows/**` (AST scan), and asserts that
  each one is in `_KNOWN_ROUTING_ROLES`. For each preset whose method uses the role, the role must
  be routed or be listed in an explicit `PRIMARY_OK_ROLES` set.
- **Failing test first:** the contract test, on `main`.
- **Risk:** cost. Premium jury presets may get more expensive models for critics. Re-run
  `benchmarks/measure_pipeline.py` and update the preset cost notes (CLAUDE.md "Presets (49)": budget
  about $0.02, premium $0.15–$0.30).

#### FLOW-5: HyperGate golden corpus

- **Design:**
  - Add `tests/fixtures/hypergate_routing.jsonl`, about 60 labelled real-world prompts covering
    direct, web_search and pipeline routes, writing versus coding, and advice versus fact. Include
    every misroute in the register.
  - Add a table-driven test that runs only the fast paths (no sub-agents) and asserts the label.
  - Then fix the regexes:
    - Remove the `(about|on|regarding|…)\s+\w{4,}` alternative from `_RESEARCH_INDICATORS` (keep it
      in writing detection only).
    - `_WRITING_INTENT` requires a topic marker (`about|on|for`) or a clause-final noun, and runs
      after the coding signal.
    - Drop `value|cost` from the realtime pattern, or require a market noun.
    - Anchor `_FACTUAL_PATTERNS` at `^` and exclude advice words (`best|should|vs|tradeoff|compare`).
- **Failing test first:** the corpus test on `main`, which fails on the register's examples.
- **Risk:** routing changes cost and latency for every request. The corpus is the safety net, so
  it lands before the regex edits.

---

### PR 7: `fix/audit2-prompt-trust` (SEC-8 to SEC-14, DAT-9)

#### Shared enforcement test

Add `tests/test_prompt_trust_boundaries.py`, next to `tests/test_mind_virus_resistance.py`:

- An AST scan of `phases/**/*.py` and `subagents/**/*.py`. It fails when an f-string interpolates a
  known untrusted field (`web_discovery_results`, `vetted_context`, `candidates`, `.content`,
  `snippet`, `s["text"]`, `previous_synthesis`) without passing through `_wrap_external_content`,
  `build_web_sources_block` or `_wrap_user_input`.
- An allowlist file for justified exceptions, each with a one-line reason.

This makes invariant 4 a checked rule instead of a convention.

| ID | Design | Changes | Failing test first |
|----|--------|---------|--------------------|
| SEC-8 | Single writer | Delete the learn block at `api/streaming.py:232-255`. `run_stream` → `_finish_run` → `postflight` already learns with provenance. | A follow-up that routes DIRECT stores nothing whose `response` equals the caller's `previous_synthesis`, and a normal follow-up stores exactly one entry. |
| SEC-9 | Wrap + fail closed | Wrap each snippet with `_wrap_external_content` in `cot_detection_prompt` and `cot_detection_batch_prompt`. On a vetting exception call `degraded("search.vetting", …)`, set `context_quality="partial"`, and mark the results unvetted, never clean. | A vetter reply that fails to parse leaves `context_quality != "good"`. |
| SEC-10 | Fail closed | On `ValueError` from `sanitize_for_prompt`, use `neutralize_for_replay(content)[0]` or drop the source. Never use the raw text. Route deep-read entries through vetting, or mark them unvetted. | A page containing "ignore previous instructions" never appears verbatim in `vetted_context`. |
| SEC-11 | Wrap | Replace the `web_context` repr in `decomposition_prompt` and `fusion_prompt` with `build_web_sources_block(state)`. | The enforcement test flags the current code. |
| SEC-12 | Re-validate at transition | After `translate_in`, run `neutralize_for_replay` on the result, then `degraded()` and a counter if anything was stripped. Wrap the text in the translator's user prompt. Route the translator through `harden_system_prompt`, so the LLM translator joins the hardened chokepoint. | An instruction-override written in German comes back translated and neutralized. |
| SEC-13 | Wrap | Wrap the `json.dumps(...)` blobs at the listed call sites with `_wrap_external_content`, which is the one-line change already in `writing.py`. In `build_memory_context`, move `run_id`, `model_id` and `created_at` inside the wrapper, or validate their format (UUID, model-id regex, ISO date). | The enforcement test flags the current call sites. |
| SEC-14 | Wrap, then reuse finalize | Before any `USE_SUBAGENT_*` flag can be turned on: wrap the subagent inputs, feed the writer `build_web_sources_block`, and send `SynthesisHyperAgent` output through `finalize_solution`. Add an assert in `core/settings.py` validation that refuses `USE_SUBAGENT_SYNTHESIS=true` until a test marker confirms this. Or simpler: leave the flag off and let the enforcement test cover `subagents/`. | The enforcement test covers `subagents/`. |
| DAT-9 | Pure function + property test | `_compress_minimal` enters block-comment mode only when a closing `*/` exists later in the text. The executor never strips `#` lines for roles that carry user input (`primary`, `deep_read`, `context_vetting`). | A property test: compressing text with a `/*` and no closer keeps all the text after it. |

**Risk:** low. Wrapping changes prompt text, so re-run the recorded fixtures under `tests/` before
merging, as the first audit's DAT items did.

---

### PR 8: `fix/audit2-storage` (PER-8 to PER-11, DAT-8)

#### Shared helper

Add `reasoner/utils/atomic_file.py`. `reasoner.utils` is the lowest layer in `.importlinter`
contract 1, below `infrastructure`, `neuro` and `core`, so both callers may import it. It may import
nothing from `reasoner`, which is why `read_json_or_quarantine` returns a flag rather than calling
`core.degrade.degraded()` itself. It contains:

- `atomic_write_text(path, text)`: a unique temp file in the same directory (the
  `{pid}.{ms}.tmp` scheme from `api/cache.py:184-200`), `fsync`, then `os.replace`.
- `locked(path)`: an advisory lock around a read-modify-write. It uses `fcntl.flock` on POSIX and
  `msvcrt.locking` on Windows dev. It is stdlib only; no new dependency.
- `read_json_or_quarantine(path, default) -> tuple[value, quarantined: bool]`: on a parse error,
  rename the file to `*.corrupt-{ts}` and return `(default, True)`. The caller (`uploader.py`,
  `neuro/cache.py`) reports it with `degraded()`. Data is never silently replaced by an empty file.

Then migrate `api/cache.py` to the helper, which is a lean win.

#### PER-8: upload quota and index

- **Design:**
  - **Quota.** Add an atomic conditional increment behind the existing `QuotaRepository` port:
    `reserve_upload_bytes(user_id, n, cap) -> bool` and `release_upload_bytes(user_id, n)`.
    Postgres: `UPDATE upload_usage SET bytes = bytes + $2 WHERE user_id = $1 AND bytes + $2 <= $3`,
    with the table in the PR 2 revision. SQLite: the same statement inside a transaction.
    `uploads.py` reserves before writing and releases on failure or delete.
  - **Index.** Move the dedup index from `Path(__file__).parent` to `UPLOAD_DIR`, written with
    `atomic_write_text` under `locked()`. It now only does dedup, not quota.
  - **Remove** the `shortcut:` comment on `stored_bytes`, or `stored_bytes` itself if nothing else
    reads it.
- **Failing test first:**
  - Two concurrent uploads by one user: both entries survive.
  - N parallel uploads under the remaining quota cannot exceed it in total.
  - A redeploy, simulated by a fresh index path, keeps usage.
- **Risk:** medium. Existing users start at zero usage until a backfill script sums their
  `meta.json` sizes. Add `scripts/backfill_upload_usage.py`.

#### PER-9: no orphan upload files

- **Design (commit record first, compensate on failure):**
  - Write `meta.json` first, with `status: "writing"`. Write the content and the sidecars, then set
    `status: "ready"`. On any exception, delete what was created.
  - `delete_file` works from `meta.json` or a bare `file_id` prefix, so existing orphans can be
    cleaned.
  - `index_file` checks that `meta.json` exists before writing `.vectors.json`.
  - Count `.text.json` and `.vectors.json` in the quota reservation, using their real size after
    writing (`release`/`reserve` the difference).
- **Failing test first:** an exception raised between the content write and the meta write leaves
  no file. A delete during indexing leaves no `.vectors.json`.

#### PER-10: Neuro L2 index

- **Design:**
  - `L2Index.add` filters out `e["id"] == entry_id` before appending (content-addressed id, so
    `add` is idempotent).
  - `_save` uses `atomic_write_text` under `locked()`, and re-reads and merges inside the lock. Two
    workers then never drop each other's entries.
  - `_load` uses `read_json_or_quarantine`.
  - `L1Cache.add` takes the provenance `metadata`, so L1 hits pass the `schema_version` filter.
    `recall_chunks` asks for `top_k * 2` candidates and keeps `top_k` after the filter, so dropped
    hits never use up slots.
- **Failing test first:**
  - The same synthesis learned twice gives one entry.
  - A truncated `index.json` is quarantined, not wiped.
  - Five L1 hits plus L2 hits still return L2 results.

#### PER-11: tenant directory names

- **Design:** the directory name is `{sanitized[:80]}-{sha256(raw)[:12]}`, and the in-memory tenant
  map is keyed by the same string. Read old directory names as a fallback (migration on first
  access: rename if the new name is absent).
- **Failing test first:** `agent_id` values `"a.b"` and `"ab"` get different directories.

#### DAT-8: chunking

- **Design (pure function, property tests):** stop the loop once `end >= len(text)` after appending
  a chunk. Return a `ChunkResult(chunks, truncated: bool)`, store `truncated` in the sidecar, and
  show it in the file listing. Raise `_MAX_CHUNKS_PER_FILE` or switch to a character budget (Q8).
- **Property tests** (`hypothesis`):
  - the chunks cover the text;
  - no chunk is a suffix of the one before it;
  - `truncated` is true exactly when coverage is partial.

---

### PR 9: `fix/audit2-ui-run-lifecycle` (UI-1 to UI-5, OPS-9)

#### Shared design: `useRunController`

Add `ui-next/src/hooks/useRunController.ts`, which owns the run lifecycle as a finite state machine:

```ts
type RunState =
  | { kind: 'idle' }
  | { kind: 'gating'; ticket: RunTicket }
  | { kind: 'streaming'; ticket: RunTicket }
  | { kind: 'stopping'; ticket: RunTicket };

interface RunTicket {            // captured once, at start; never read from refs later
  clientRunId: string;
  conversationId: string;
  abort: AbortController;
  mode: 'run' | 'followup' | 'resume';
}
```

- `start()` is a no-op unless the state is `idle` (UI-2). It creates the ticket, including the
  AbortController and the conversation id snapshot (UI-3).
- Every stream (run, follow-up, resume) receives `ticket.abort.signal`, which fixes UI-1:
  `resumePipelineStream(id, signal)` and `readSSEStream(body, cb, signal)`.
- `stop()` aborts the signal, sends the WS stop, and POSTs `/api/stop?run_id=${clientRunId}` (UI-4).
  `app/api/stop/route.ts` forwards `req.nextUrl.search`. It never sends a bare `/api/stop`, so the
  global admin stop stays a separate, explicit admin action.
- `done`, `error` and `cancelled` handlers receive the ticket and write to
  `ticket.conversationId`, never `conversationIdRef.current` (UI-3).
- New and Load call `stop()` first while a run is active.
- Unmount calls `stop()`.
- `page.tsx` stops tracking `running`, `gateChecking` and `abortControllerRef` separately. They are
  derived from `state.kind`. `Composer` disables send unless the state is `idle`.

Zustand keeps only what other components read (`running` derived as `state.kind !== 'idle'`). The
state machine itself lives in the hook, because it holds non-serializable objects
(`AbortController`).

**Failing tests first** (Vitest + Testing Library; Playwright for the stop round-trip):

- Resume followed by Stop aborts the fetch.
- Enter pressed twice during the gate check makes one `fetchGateDecision` call.
- Load during a run saves the run under its original conversation id.
- Stop sends `run_id`.

#### UI-5: per-user local data

- **Design (per-principal namespace):** `openDb(userId)` uses `ARA_Pipeline_v2_${userId ??
  'anon'}`. `providers.tsx` handles `onAuthStateChange`: on `SIGNED_OUT` it closes the open handle,
  resets `subscription` to `null`, and drops the anonymous database. Account deletion deletes that
  user's database (`indexedDB.deleteDatabase`). Q9 decides whether existing `ARA_Pipeline_v2` data
  migrates to the first user who signs in, or is cleared.
- **Failing test first** (`fake-indexeddb`): A writes a conversation and signs out. B signs in and
  lists nothing.

#### OPS-9: proxy topology must be declared

- **Design (fail-fast configuration):** in production, when `TRUSTED_PROXIES` is unset and a
  request arrives with more than one `X-Forwarded-For` hop, log once at error level and set a
  `/api/status` health flag. Document `TRUSTED_PROXIES` in `docs/` deploy notes and in the compose
  and Caddy examples. Do not refuse requests: the backend limiter remains the real control.
- **Failing test first:** with `NODE_ENV=production`, no `TRUSTED_PROXIES`, and a 3-hop header,
  the warning is emitted once.

---

## 3. Order, overlaps and rollout

```
PR 1 money-leaks ──┬─> PR 4 run-identity
                   ├─> PR 3 billing-provider ──> (backfill script, manual)
PR 2 schema (Q1) ──┘        └─ PR 8 storage (needs PR 2's upload_usage table)
PR 5 flows, PR 6 routing, PR 7 prompt-trust, PR 9 ui: independent after PR 1
```

| File | PRs | Note |
|------|-----|------|
| `api/__init__.py` | 1, 4 | PR 4 rebases onto PR 1's `admit_run`. |
| `api/streaming.py` | 1 (resume path), 7 (delete follow-up learn) | Different functions; trivial merge. |
| `application/services/run_metering.py` | 1, 4 | PR 4 adds the claim release to PR 1's shielded finalizer. |
| `migrations/alembic/versions/*` | 2, 3, 8 | PR 2 owns the revision. PR 3 (`last_event_at`) and PR 8 (`upload_usage`) either add to it before it merges, or add their own later revisions. |
| `core/constants_limits.py` | 1 (`SETTLE_TIMEOUT_S`), 5 (fan-out caps) | Append-only. |
| `.claude/skills/map-*` and generated counts | every PR | Regenerate with `scripts/update_mindmap_meta.py` and run `scripts/check_skill_maps.py` after the merge. |
| `.github/workflows/test.yml`, `scripts/ci-local.sh` | every PR | Ratchet limits are re-measured at merge time. |

**Rollout notes**

- **PR 1:** resume and run-with-context become billed. Announce it.
- **PR 2:** run against a copy of the production database first (Q1).
- **PR 3:** run the Stripe metadata backfill as a dry run first, then for real, by a person.
- **PR 5 and PR 6:** run outcomes and routing change. Watch the runs-completed rate, cost per run
  and the method mix for a week.
- **PR 8:** run the upload-usage backfill before turning the quota back on.
- **PR 9:** existing local history follows Q9.

---

## 4. Definition of done

- Every register row has a test that failed on `main` before its fix and passes after it.
- The new architecture and contract tests are in the PR-enforced suite:
  `test_run_admission.py`, `test_flow_roles_are_routed.py`, `test_prompt_trust_boundaries.py`, the
  HyperGate corpus test and the Alembic schema contract test (a CI job with a Postgres service).
- `.importlinter` contract 2 is still at 51. Both contracts are kept.
- The ratchet limits match the measured counts in `test.yml` and `ci-local.sh`.
- `docs/plans/audit-remediation-2-2026-10-20.md` gets an "As implemented" note per PR, as the first
  audit's plan did.

---

## 5. Out of scope

- **Areas no audit has read yet:**
  - `ui-next/src/lib/markdown.ts` and most components (only grepped for HTML sinks);
  - watermark `domain/*` and the non-JPEG image codecs;
  - most persistence repos (`snapshots`, `quota_repo_postgres`, `cached_*`, the telemetry and error
    stores);
  - the writing, augmentation and egress flows;
  - the HyperGate sub-agents other than the method classifier;
  - `neuro/sessions.py` and `providers.py`;
  - the per-method prompt modules beyond the shared ones.
- **The JPEG scrub dropping EXIF orientation and ICC profiles** under `strip_all_metadata`. This
  needs a product decision about watermark versus fidelity, so it is not counted as a defect.
- **The anonymous trial cap per IPv6 address:** still Q7 of the first audit.
- **Performance work** beyond the items above.

## 6. Open questions

| # | Question | Blocks |
|---|----------|--------|
| Q1 | Was the production database built from Alembic, from the raw `migrations/*.sql`, or by hand? (The first audit's Q3, still open.) | PER-7 / PR 2 |
| Q2 | `/api/run-with-context`: keep it and bill it, or delete it? No UI calls it. | BIL-10 |
| Q3 | Resume: reserve the full preset estimate, or only the remaining phases? | BIL-11 |
| Q4 | A second checkout by a subscribed user: block it, or send upgrades to the Stripe portal for proration? | BIL-14 |
| Q5 | Admin identity: the Supabase `app_metadata.role`, an `ADMIN_USER_IDS` allowlist, or both? | SEC-6 |
| Q6 | `/api/gate`: require a signed-in principal, or keep it anonymous for the landing page with a stricter per-IP cap? | BIL-17 |
| Q7 | Account deletion: delete the Supabase identity too, or only revoke sessions? | BIL-18 |
| Q8 | Long documents: raise the 500-chunk cap, or switch to a character budget and show "indexed partially"? | DAT-8 |
| Q9 | Existing shared-browser history in `ARA_Pipeline_v2`: migrate it to the first user who signs in, or clear it? | UI-5 |
