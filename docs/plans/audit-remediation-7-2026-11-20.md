# Audit remediation 7 — 2026-11-20

Source: the ponytail audit of 2026-11-20, run on main at `db0f128f` (20 findings). This plan
fixes all 20 inside Reasoner's architecture. That means the hexagonal inner ring, ports in
`core/ports` or `application/ports`, and adapters in `infrastructure/`. Billed runs keep one
admission sequence (`api/run_admission.py`). Billing writes keep their idempotency keys.

Finding numbers match the audit report. Labels:
- VERIFIED: I read it in the code during the audit or while writing this plan.
- INFERENCE: it follows from the code, but nothing was executed.
- UNKNOWN: not checked. Each phase says what to confirm first.

## Ground rules (apply to every phase)

- **Layering.** `.importlinter` contract 2 (`application -> infrastructure`) only falls. No
  phase adds an exception. `PYTHONPATH=src lint-imports` must pass before and after each phase.
  New behaviour reaches adapters through an existing port. Add a new port only where no port
  exists.
- **No new exception classes under `infrastructure/`.** `test_infrastructure_defines_no_new_exception_classes`
  enforces this. Use the `core.exceptions` hierarchy (`ProviderError` subclasses,
  `is_run_fatal`).
- **One test per fix that fails before and passes after.** Name it in the PR body.
- **Ruff ratchet.** Deleting code lowers the violation count. Lower `--max` in both
  `.github/workflows/test.yml` and `scripts/ci-local.sh` in the same PR (it is 2052 today).
- **Living docs.** After any file is added or removed, run `python scripts/update_mindmap_meta.py`
  (it guards against `generated-docs-drift`) and `python scripts/check_skill_maps.py`. Run
  `/update-maps` for a folder only when its map is reported stale.
- **`ui-next/`** files keep LF line endings (`page.patterns.test.ts` matches `\n`). They use
  no raw design values (no UI phase here touches styling).
- **Gate commands before each PR:**
  - `python -m pytest tests/ -m "not slow and not integration" -n 4 --dist loadscope`
  - `PYTHONPATH=src lint-imports`
  - `ruff check src tests` / `python scripts/ruff_ratchet.py --max <N>`
  - for `ui-next`: `cd ui-next && npx tsc --noEmit && npx vitest run`
- **Known local failures that are not regressions:**
  - 2 MCP tests in `tests/unit/test_security_review_round3.py` fail with `mcp` 2.x installed.
  - `tests/test_jev_router.py::test_a_slow_jev_does_not_cost_the_llm_fallback_its_budget` is
    flaky under `-n 4`.

## Decisions (D1-D4 approved 2026-11-20: all four recommendations accepted)

| # | Finding | Question | Recommendation | Why |
|---|---------|----------|----------------|-----|
| D1 | 10, 14, 20 | Who runs the periodic jobs? | **An in-process loop started in the FastAPI lifespan.** A Valkey `SET NX EX` lock lets one worker per interval run it. First check that no scheduler exists outside the repo (deploy config, platform cron, a GitHub workflow). If one exists, wire the jobs there instead. | `api/cron.py` already holds the job bodies. Only the trigger is missing. Valkey is already a hard dependency (idempotency, webhook dedup). |
| D2 | 9 | Widget paid searches: charge, or require sign-in? | **Charge through `admit_flat_charge` / `close_flat_charge`**, as `/api/search` does. | This uses one admission sequence and one price list. Anonymous use stays bounded by the existing anonymous trial cap, so no new rule is needed. |
| D3 | 6 | Which model judges quality? | **The model `gate_service` already uses for its JSON verdict**, for every tier. | It is Western, so it passes on every run. It is already proven to return JSON reliably. One judge model means one row to price. |
| D4 | 14, 20 | Retention for `failed_webhook_events` and `feedback`? | **90 days** for both. | That is longer than Stripe's 30-day event replay window and PayPal's retry window. Older rows have no use beyond being kept as records, which the payment provider already does. |

## Phase order

| Phase | Findings | Depends on |
|-------|----------|------------|
| 1. User-data erasure | 1, 8, 14 (erase half) | none |
| 2. Western-only enforcement | 2, 3 | none |
| 3. Run-fatal errors and cost accounting | 4, 6, 15 | D3 |
| 4. Paid and abusable endpoints | 9, 20 (rate limit) | D2 |
| 5. Scheduled maintenance | 10, 14 (prune), 20 (prune) | D1, D4, phases 1 and 4 |
| 6. Token cache | 7 | none |
| 7. `ui-next` fixes | 5, 11, 12, 13 | none |
| 8. Dead code and slow paths | 16, 17, 18, 19 | phase 3 (both edit `router.py`) |

Phases 1, 2, 3, 6 and 7 touch disjoint files. They can run as parallel sessions in separate
worktrees. Phase 5 builds on 1 and 4. Phase 8 goes after 3.

---

## Phase 1 — User-data erasure (findings 1, 8, 14)

All three findings sit in one registry: `api/user_data.py` builds the list of `UserDataStore`
adapters, and the PG adapters live in `infrastructure/persistence/user_data_pg.py`. The
pattern stays as it is: a registry of adapters, one per store, each owning its own
erase/export.

### Finding 1 — data erase resets billing (VERIFIED)

- **Cause:** `data_stores()` removes only `ACCOUNT_STORE_NAMES = {"profile", "identity"}`
  (`api/user_data.py:28`). So `DELETE /api/user/data` erases `credit_ledger`, `quota` and
  `subscriptions`, but not the balance in `user_credits`. The `monthly:<period>` ledger row
  that blocks a second grant is gone, so the next grant pays again.
- **Fix:** add `BILLING_STORE_NAMES = frozenset({"credit_ledger", "quota", "subscriptions"})`.
  `data_stores()` excludes `ACCOUNT_STORE_NAMES | BILLING_STORE_NAMES`. Full account deletion
  (`user_data_stores()`) still erases them. Export is unchanged: billing rows remain the
  user's data to download.
- **Why there:** billing records are account records. The fix restates the domain boundary
  in the one place that defines it. It adds no special case in the credit service.
- **First confirm:**
  - `grep` the callers of `data_stores()` and `user_data_stores()`.
  - Check that the account-delete path erases `user_credits` as well. If it does not, that
    is a second bug with the same cause. Fix it in the same PR by adding the store.
- **Tests:**
  - Update `tests/test_delete_account_erases_everything.py`: data erase leaves the three
    billing stores, and account delete erases them.
  - New test: grant the monthly credits, run data erase, call the grant again. The balance
    does not change.

### Finding 8 — Valkey erase pattern matches nothing (VERIFIED)

- **Cause:** `ValkeyStore.erase` (`infrastructure/persistence/user_data_local.py:180-184`)
  runs `KEYS user:{id}:*`. No code writes that prefix. The real keys are `spend:<id>:<month>`
  and `quota:<id>`.
- **Fix:**
  - Import the key builders from the modules that write the keys: the spend tracker and the
    quota adapter. Do not retype the strings. One source of truth means the next new key
    cannot drift.
  - If those modules format their keys inline, extract a module-level `spend_key(uid, month)`
    / `spend_key_pattern(uid)` / `quota_key(uid)` in each one, and use them in the writer
    and in the eraser.
  - Delete with `scan_iter(match=...)` and batched `unlink`, never `KEYS`.
  - Note: once finding 1 lands, `quota:<id>` belongs to the billing set. Data erase must not
    delete it. Account erase must delete it.
- **Tests:** the existing fake-client test checked the wrong pattern. Write keys through the
  real writers into a fake that supports `scan_iter` (`fakeredis`, if it is in
  `requirements-dev.txt`; otherwise a dict-backed fake with glob match). Then assert they
  are gone after the erase.

### Finding 14 (erase half) — webhook dead letter keeps PII (INFERENCE)

- **Cause:** `failed_webhook_events.payload` holds the raw provider event (email, name,
  customer ids). The table has no user column, and no `UserDataStore` covers it.
- **Fix:**
  - Add a `WebhookDeadLetterStore` adapter next to the other PG stores in `user_data_pg.py`,
    and register it in `pg_user_data_stores`. It is an account-level store, so it runs on
    account delete only.
  - It erases rows whose payload contains the user's provider customer ids or their email,
    using a JSONB containment or `payload::text LIKE` query over the indexed recent window.
  - It needs the customer ids, which live in `subscriptions`. So it must erase **before**
    `subscriptions` does: register it ahead of the subscriptions store, and add a comment
    giving that reason.
- **Tests:** a PG test on `reasoner-pg-test :55499`. Insert a dead-letter row with the
  user's customer id and one row for another user. After the account erase, only the other
  user's row is left.

---

## Phase 2 — Western-only enforcement (findings 2, 3)

The rule (CLAUDE.md §5): set `restrict_blocs` at the choke point, and never build a provider
around it.

### Finding 2 — `/api/run-with-context` never restricts blocs (VERIFIED)

- **Fix:** in `api/routes/context.py`, wrap the phase loop of `_cost_frames` **inside the
  generator body** with
  `with model_policy.restrict_blocs(model_policy.run_blocs(effective_preset)):`.
  The generator runs after the handler returns, so a `with` outside the generator would not
  cover the phases.
- **Altitude:** this route builds its pipeline by hand, which is why it missed the handler's
  choke point. The smaller fix is the `with`. The deeper fix is to route this endpoint
  through `RunPipelineCommandHandler`. That is out of scope here: it changes the SSE frame
  shape and billing. Record it as a follow-up in the PR body.
- **Test:** call the route with a `*-western-*` preset and a stub phase that records
  `model_policy`'s active blocs. Assert the recorded value is the Western set. Also assert
  that a non-Western `build_provider` call inside the loop raises.

### Finding 3 — fresh Western runs use the shared memory store (VERIFIED)

- **Fix:** in `core/model_policy.memory_agent_id` (lines 60-62), return
  `f"{agent_id or 'anon'}-western"` whenever the restriction is on. This is a pure function
  in `core/`: no I/O and no new imports.
- **First confirm:**
  - `neuro/server.py:237` maps `None` to `"default"` after this call, not before it.
    Otherwise the suffix must be applied at that point instead.
  - The `-western` tenant is built with the OpenAI-only embedder. That holds for named
    agents today, and `anon-western` must take the same branch.
- **Tests:**
  - Unit test of `memory_agent_id(None)` with and without the restriction active.
  - A neuro test: recall in a non-Western run does not return a memory learned in an
    anonymous Western run.

---

## Phase 3 — Run-fatal errors and cost accounting (findings 4, 6, 15)

### Finding 4 — fan-out phases hide a 402 (VERIFIED)

- **Cause:** `require_survivors(items, errors: list[str], ...)`
  (`application/flows/base.py:100`) gets only strings. Its 4 callers are `debate_phases.py:53`,
  `delphi_phases.py:63`, `coding_phases.py:203` and the jury phase. `is_run_fatal`
  (`core/exceptions.py:322`) never sees the exception.
- **Fix:**
  - Change the parameter to `failures: Sequence[BaseException]`.
  - Inside it, first re-raise the first failure for which `is_run_fatal` is true.
  - Then raise `PhaseError` with `"; ".join(str(f) for f in failures)`.
  - Update the 4 callers to keep the exception objects. They already hold them before
    formatting, or get them from `gather(..., return_exceptions=True)`.
- **Semantics:** re-raise a run-fatal failure **even when some calls survived**. A 402 or a
  spend cap means every later phase fails or bills past the limit. This matches #257, where
  a run-fatal error ends the run at the executor level.
- **Pattern:** no new type. The function stays a pure guard in `application/flows/base.py`
  and reuses the core error classification.
- **Tests:**
  - Parametrize over the 4 phases. Use a stub `call_llm` that raises the core 402 error for
    one call and succeeds for the others. Assert the 402 propagates.
  - A second test: all calls fail with non-fatal errors, and `PhaseError` is raised as today.

### Finding 6 — quality judge unbilled, Chinese model on Western runs (VERIFIED)

- **Cause:** `quality/monitor.py:221-222` calls the router directly and drops `_meta`, which
  skips the executor's cost accounting, spend caps and bloc policy. The judge model is
  `QUALITY_JUDGE_MODELS["budget"] = MODEL_QWEN35_FLASH` (`core/constants_limits.py:322`).
- **Fix:**
  1. Send the judge call through the same chokepoint the phases use (`flows/services.call_llm`
     → `LLMExecutor`), so cost, caps, hardening and bloc policy apply with no extra code.
     If `quality/` cannot import `application/` under the layer contract, add the
     `call_llm`-shaped callable that the monitor already receives as a parameter (injection,
     not import). Check the `.importlinter` layer of `quality` first.
  2. Set every `QUALITY_JUDGE_MODELS` entry to the D3 model. Keep the dict, since the
     threshold table and its callers key on it.
  3. Parse the verdict with `parsing.extract_json` (CLAUDE.md invariant), not `json.loads`.
- **Tests:**
  - The judge's cost shows up in `state.total_cost_usd`.
  - Under `restrict_blocs(WESTERN)` the judge call does not raise.
  - A fenced-JSON judge reply parses.

### Finding 15 — discarded cost suppresses the estimate (INFERENCE)

- **Cause:** `router.py:709-733` adds the cost of discarded empty replies into the final
  call's `cost_usd`. `executor.py:649-657` estimates from tokens only when `cost_usd == 0`.
  So a backup vendor that reports no cost is never priced.
- **Fix:**
  - The router carries the discarded cost under its own key, `discarded_cost_usd` (and the
    token counts likewise). It does not touch `cost_usd`.
  - The executor works out the call's own cost first: the reported cost, or the estimate
    when none is reported. Then it adds `discarded_cost_usd` before the cap check.
- **Tests:** a stub router that returns `cost_usd=0, discarded_cost_usd=0.01` with token
  counts for a priced model. The executor records the estimate plus 0.01.

---

## Phase 4 — Paid and abusable endpoints (findings 9, 20 rate limit)

### Finding 9 — widget searches free and anonymous (VERIFIED, D2)

- **Fix:**
  - In `api/routes/widgets.py`, wrap the paid widget types (web, image and video search,
    discover) in `admit_flat_charge(request, user=..., cost_usd=..., kind="widget_<type>")`,
    then call `close_flat_charge` on success or refund on failure, exactly as `/api/search`
    does.
  - Take the per-type price from the same constant `/api/search` uses. Add no new price
    table.
  - Free widget types are unchanged.
- **Tests:**
  - An anonymous call past the trial cap gets a 402 or 429.
  - A signed-in call debits once.
  - A failed search refunds.

### Finding 20 (rate limit) — contact form (INFERENCE)

- **Fix:** add the existing `rate_limiter` dependency to `api/routes/contact.py` with a
  strict per-IP bucket, for example 5 an hour. Put the number in `core/constants_limits.py`
  next to the other limits.
- **Test:** the 6th request in the window gets a 429.

---

## Phase 5 — Scheduled maintenance (findings 10, 14 prune, 20 prune; D1, D4)

- **First confirm (UNKNOWN):** look for any scheduler in deploy config, platform manifests or
  `.github/workflows/`. If one exists, wire it to the existing admin cron endpoints and skip
  the loop below.
- **Fix (in-process):**
  - Add `api/maintenance.py` with one `async def maintenance_loop()`. Each interval it takes
    the Valkey lock `maintenance:lock` (`SET NX EX`, TTL slightly under the interval) and,
    if it holds the lock, runs in turn:
    - `cron.run_reservation_sweep()`;
    - the unsettled-settlement replay (the body behind the admin endpoint in
      `api/routes/admin.py:108-149`);
    - the dead-letter prune (finding 14);
    - the feedback prune (finding 20).
  - Each job runs in its own `try/except`, which logs and records a degradation, so one
    failing job cannot stop the rest.
  - Start it as a task in the FastAPI lifespan, and cancel it on shutdown.
  - Turn it off with a setting (`MAINTENANCE_LOOP_ENABLED`, default true), so tests and CLI
    runs never start it.
- **Prunes:** each prune is a method on the repo that owns the table:
  `BillingDeadLetterRepo.prune_older_than(days)` and the feedback repo's equivalent. Write
  them as one `DELETE ... WHERE created_at < now() - interval`. Put the retention constants
  in `core/constants_limits.py`, set to the D4 value.
- **Pattern:** do not add a job framework or a registry. One loop and one list of coroutine
  functions is enough for 4 jobs.
- **Tests:**
  - The loop runs each job once when it holds the lock, and none when it does not (fake
    Valkey).
  - A failing job does not stop the others.
  - The prune deletes old rows only (PG test).

---

## Phase 6 — Token cache (finding 7, VERIFIED)

File: `infrastructure/token_cache.py:303-328`.

- **Fix:**
  1. Keep the in-memory index as an `OrderedDict`, and evict with `popitem(last=False)`.
     That is O(1), and it replaces the `min()` scan.
  2. On eviction, also `unlink(missing_ok=True)` the entry's file, off the event loop
     (`asyncio.to_thread`, batched per eviction pass).
  3. `_load_from_disk` loads at most the max entries (512), newest by mtime. It deletes the
     rest in the same thread pass, so an existing backlog of files is cleared at the first
     restart.
  4. Plaintext prompts on disk: reuse the at-rest encryption helper that
     `documents/vector_store.py` already uses. If that helper reaches across the layer
     contract, keep this step out of the PR and say so in the PR body; the disk cap in step
     3 already bounds the exposure.
- **Tests:**
  - Write 600 entries: 512 stay in memory and 512 files stay on disk.
  - A restart with 2,000 seeded files loads 512 and leaves 512 files.
  - Eviction order is least recently used.

---

## Phase 7 — `ui-next` fixes (findings 5, 11, 12, 13)

These change no visuals, so the design gate is not involved. Each fix gets a vitest test in
the file next to it.

- **Finding 5 (VERIFIED):** the routes are `api/pipelines/[pipelineId]/resume-stream/route.ts`,
  `api/agent/run/route.ts` and `api/agent/run/sync/route.ts`. Pass `signal: req.signal` to
  the upstream fetch, and map an `AbortError` to the quiet 499, as `run/route.ts` does since
  #259.
  - This is now the 5th copy of that abort handling. Lift it once into the shared proxy
    helper module that the routes already import, and make all 5 routes call it.
  - Tests: one `route.test.ts` per route asserts the signal is forwarded and that an abort
    gives 499.
- **Finding 11 (VERIFIED):** in `lib/security-client.ts:47`, read the 403 body from
  `resp.clone().json()`, so the caller still gets an unread body. Test: a non-CSRF 403 with
  `{detail:"Confirm your email"}` reaches the caller's error message.
- **Finding 12 (VERIFIED):** in `app/chat/page.tsx:647`, keep a `researchSteps` array local
  to `submitRun`, as `phases` already is. Append to it, and write a copy into the assistant
  message. Never read the `messages` snapshot. Test: 3 `research_step_emitted` events give
  3 steps.
- **Finding 13 (VERIFIED):** in `lib/sse-reader.ts:31-36`, keep only `JSON.parse` inside the
  `try`. Call `onEvent` after it, so handler errors propagate to the stream consumer's
  existing error path. Test: a throwing `onEvent` rejects the read promise.

---

## Phase 8 — Dead code and slow paths (findings 16, 17, 18, 19)

- **Finding 16 (VERIFIED):** delete the streaming branch in `router.py:802-922`, and the
  `stream` parameter in `executor.py:121`.
  - First confirm with a whole-tree grep for `stream=True`, `stream=` and `call_stream`,
    including tests and `sdk/`.
  - Delete the tests that covered only that path.
- **Finding 17 (INFERENCE):** delete `require_tier` (`api/dependencies.py:482-512`) and its
  tests. First grep `src/`, `tests/` and `docs/` for `require_tier`.
- **Finding 18 (VERIFIED):** point the active-users gauge (`api/__init__.py:75-78`) at
  `query_log`. First confirm the table name and its user and timestamp column names in the
  Alembic baseline. Test: one row inside 24 hours gives a gauge of 1.
- **Finding 19 (INFERENCE):** in `documents/vector_store.py:191-193` and `:275-305`, move
  the JSON (de)serialization, encryption and similarity math into one `asyncio.to_thread`
  call per operation. Replace the pure-Python cosine loop with numpy, if `numpy` is already
  in `requirements.txt`; do not add a dependency for it. The path stays behind
  `DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED`. Test: results match the old implementation on a
  fixed fixture.
- Lower the ruff ratchet if the count falls. Expect about -170 lines in total.

---

## Done means

- All 20 findings have a merged fix and a named test, or a decision (D1-D4) recorded in its
  PR.
- `lint-imports` shows 2 contracts kept, and contract 2's exception count has not grown.
- CLAUDE.md §5 still holds, with no edit needed: Western-only enforcement stays at the choke
  points, and recalled memory stays out of system prompts.
- The follow-up "route `/api/run-with-context` through `RunPipelineCommandHandler`" is
  recorded.
