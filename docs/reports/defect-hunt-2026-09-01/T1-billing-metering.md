# Autonomous Defect-Hunt V7 — T1: Billing & Metering

- **Worktree:** `E:\Documents\Vibe-Coding\Reasoner\.worktrees\defect-hunt` (branch `chore/backend-defect-hunt-plan`)
- **Date:** 2026-09-01
- **Tier:** T1 — Billing & Metering (threat-model rank #1: money loss is unrecoverable customer harm)
- **Audit budget:** 12 candidates. `budget_spent = 12`. Terminated on budget exhaustion; in-scope surface fully triaged.

Every claim below is tagged `[VF]` verified fact, `[HYP]` hypothesis, `[UNK]` unknown, `[FALSE]` contradicted.

---

## PHASE 1 — Defect-surface map

| Region | Site | Defect classes present | Entry reachability | Blast radius | Invariant density |
|---|---|---|---|---|---|
| R1 | `application/services/quota_service.py::QuotaService.check` | 1 (off-by-one / ceiling), 4 (error path), 5 (None boundary) | REACHABLE from `asgi:app` via `POST /api/run` → `Depends(check_quota_if_authenticated)` → `check_quota` → `check` | EXTERNALLY-VISIBLE (429 gate) | HIGH — named contract restored by BUG-502 (`tests/test_quota_tier_lookup.py`) |
| R2 | `application/services/quota_service.py::QuotaService.increment` | 4 (deliver-without-charge) | **DEAD** — no caller in `src/` | SYSTEM | MEDIUM |
| R3 | `application/services/quota_service.py::_seconds_until_month_end` | 1 (date arithmetic) | REACHABLE — `Retry-After` header on 429 | EXTERNALLY-VISIBLE | LOW |
| R4 | `application/services/run_metering.py::metered` / `_true_up` / `_settle` | 3 (check-then-act across await), 4 (partial state on failure) | REACHABLE from 4 adapters: `api/__init__.py:587,641`, `api/routes/agent.py:134`, `api/mcp/tools.py:121,241` | EXTERNALLY-VISIBLE (ledger) | HIGH — module docstring states the settlement contract |
| R5 | `application/services/run_metering.py::reserve_run_budget` + `api/dependencies.py::reserve_or_402` | 2 (TOCTOU), 4 (orphaned reservation) | REACHABLE — every metered route | EXTERNALLY-VISIBLE | HIGH |
| R6 | `application/services/billing_service.py::_apply_webhook` | 2 (illegal subscription transition), 4 (partial state) | REACHABLE from `POST /api/billing/webhook` | SYSTEM | MEDIUM |
| R7 | `application/services/spend_limit_service.py::check_run_allowed` / `global_ceiling` | 1 (off-by-one), 5 (negative config) | REACHABLE — preflight | MODULE | MEDIUM |
| R8 | `domain/credits.py::usd_to_credits` / `can_afford` | 1 (rounding), 5 (inf/NaN) | REACHABLE — every charge | MODULE | HIGH — `CREDITS_PER_USD` integer-ledger invariant |
| R9 | `domain/spend_limits.py::_stricter` / `limits_for_tier` | 1 (sentinel semantics: `0.0 == unlimited`) | REACHABLE | MODULE | HIGH |
| R10 | `api/run_observability.py::CreditSink` | 4 (missing rollback) | REACHABLE | EXTERNALLY-VISIBLE | MEDIUM |
| R11 | `domain/pricing.py` / `domain/saas.py` | 1 (float money math) | REACHABLE (estimate only) | LOCAL | LOW |

**Hunt queue** (likelihood × blast_radius × reachability): R1 → R4 → R2 → R6 → R5 → R7 → R8 → R10 → R9 → R3 → R11.

Three atomic assertions about the map itself:

1. `[VF]` The credit ledger is integer-valued end to end; the only float in the money path is `cost_usd`, converted exactly once by `usd_to_credits` (`domain/credits.py:136-145`) with `math.ceil`. Classic float-money-drift is therefore structurally absent from the ledger — only from *estimates*.
2. `[VF]` `QuotaService.increment` (`quota_service.py:70-77`) has zero callers under `src/`; the only references are its own definition, the port declaration, and the three repository implementations. The query-quota counter is therefore never advanced in production.
3. `[VF]` Two mutually-inconsistent enforcement models coexist on the same request: a query-count quota (R1/R2) and a credit reservation/settlement ledger (R4/R5). They share no state, and each of them separately gates `POST /api/run`.

---

## PHASE 2 — Suspicion generation

> Ranked by severity × prior × reachability, preferring decisive executable triggers.

**D1 — Entitlement tier is ignored when sizing the quota.**
Under a caller whose subscription no longer entitles its tier, `quota_service.py:44,59` computes `limit` from `TIER_LIMITS[tier]` and then never uses it, sizing `remaining` from the persisted `usage_quotas.max_queries` instead — violating the **named contract of BUG-502** (`tests/test_quota_tier_lookup.py:1-10`: "the tier the entitlement resolver produces is what the quota check applies"), producing a free-tier account served at a paid-tier query ceiling.
Class 1 (off-by-one on quota) · Violated property: BUG-502 entitlement contract · Reachability: REACHABLE · Severity: HIGH (silent wrong result, revenue) · Prior: HIGH · Innocence path: the persisted row is authoritative *if* every un-entitling transition re-syncs it.

**D2 — `period_start` is NULL on a never-reset quota row.**
Under a brand-new account, `quota_service.py:55` compares `quota.period_start` (None) to a `datetime`, raising `TypeError`, which `api/dependencies.py:661-667` swallows into the "emergency limits" fall-back — violating **`UsageQuota.period_start: datetime`** (`domain/saas.py:67`, non-Optional) and producing permanent, silent non-enforcement of quota for that user.
Class 5 (None boundary) → class 4 (error path) · Violated property: domain field type + fail-closed posture · Reachability: REACHABLE · Severity: HIGH · Prior: MED · Innocence path: a DB `DEFAULT` or an INSERT that sets the column.

**D3 — `Retry-After` overshoots by the current time-of-day.**
`quota_service.py:83` computes `now.replace(day=1) + 32d → replace(day=1)`, carrying the wall-clock time into the next-month boundary — violating the documented meaning of `QuotaResult.retry_after` ("seconds until reset", `domain/saas.py:91`).
Class 1 · Severity: LOW (degradation) · Prior: HIGH · Innocence path: none plausible.

**D4 — A run abandoned before its terminal frame releases its whole reservation.**
`run_metering.py:130-146` only learns `cost_usd` from the terminal `done` frame, so a mid-run disconnect leaves `cost_usd = 0.0`, `_true_up` releases the full hold and skips `_settle` — contradicting the module docstring's stated contract ("a client that disconnects mid-run is still charged for the work already performed").
Class 4 (deliver-without-charge) · Severity: HIGH if real · Prior: MED · Innocence path: an existing test that deliberately pins the release-on-abort behaviour.

**D5 — The query quota can never be exceeded.**
`QuotaService.increment` is never called, so `used_queries` stays 0 forever and `check` can never deny — violating the service's own documented protocol (`quota_service.py:41-42`: "call increment() separately after a successful pipeline run").
Class 4 · Severity: HIGH · Prior: HIGH · Innocence path: quota is vestigial by design, superseded by credits.

**D6 — `past_due` never re-syncs the quota row.**
`billing_service.py:114-120` (Stripe `invoice.payment_failed`) and `:75-89` (PayPal `SUSPENDED` / `PAYMENT.FAILED`) call `set_subscription_status(..., "past_due")` and, unlike every other branch, omit `sync_quota_for_subscription` — so `subscriptions.status` and `usage_quotas.max_queries` diverge.
Class 2 (illegal state transition) · Severity: MEDIUM · Prior: HIGH · Innocence path: the adapter downgrades `sub.tier` on these events.

**D7 — Monthly ceiling admits a run it cannot afford.** `spend_limit_service.py:239` tests `spent >= monthly_usd` without adding the run's own estimate. Class 1 · Severity: LOW · Prior: MED · Innocence path: the mid-run executor ceiling.

**D8 — Non-idempotent admin grant.** `credit_service.py:62-80` accepts `reference_id=None`, and `POST /api/credits/grant` declares that field Optional while documenting it as an idempotency key (`api/routes/credits.py:37-41`). A double-submitted grant double-credits. Class 1 (double-charge, inverted) · Severity: MEDIUM · Prior: MED · Innocence path: admin-scoped, deliberate opt-in.

**D9 — `usd_to_credits(inf)`.** `math.ceil(inf)` raises `OverflowError`; `extract_run_cost` admits `inf` (`inf > 0`). Class 5 · Severity: LOW · Prior: LOW · Innocence path: `_settle`'s `except Exception`, and cost is not caller-controlled.

**D10 — Balance TOCTOU across the reserve/settle await boundary.** Class 3 · Severity: CRITICAL if real · Prior: LOW · Innocence path: `SELECT … FOR UPDATE` inside a transaction.

**D11 — Negative `SPEND_CAP_*_USD` reads as unlimited.** `spend_limit_service.py:76-77` `max(setting, 0.0)`. Class 5 · Severity: LOW · Prior: MED · Innocence path: `_stricter` semantics.

**D12 — Orphaned reservation when the response generator never starts.** `reserve_or_402` debits before `StreamingResponse` is constructed; only `metered`'s `finally` releases. An async generator that is closed without ever being started does not run its `finally`. Class 4 · Severity: HIGH if real · Prior: LOW · Innocence path: Starlette always enters the generator.

---

## PHASE 3 — Proof of defect

Trigger tests live in `tests/test_quota_tier_enforcement.py` (9 tests). Executed with `python -m pytest -o addopts=""`.

### D1 — FIRED
```python
repo = FakeQuotaRepository(_quota(used_queries=100, max_queries=500))
result = await QuotaService(repo).check("u1", SubscriptionTier.FREE)
assert result.allowed is False
```
Observed pre-fix: `QuotaResult(allowed=True, remaining=400, retry_after=None, reason=None)`. A FREE-entitled caller who has already used 100 of a FREE ceiling of 20 was admitted with 400 remaining. `[VF]`

Two further sub-triggers fired on the same mechanism:
- `max_queries = -1` (a downgraded enterprise row) under FREE entitlement → `max(0, -1 - 3) == 0` → **denied**. The sentinel was read as a negative ceiling. `[VF]`
- A tier value outside the enum → `TIER_LIMITS.get` default was computed and discarded; the row's 500 applied. `[VF]`

**Innocence attempt.** The only defence would be an upstream guarantee that `usage_quotas.max_queries` always matches the entitlement tier. `sync_quota_for_subscription` is invoked on `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_succeeded`, PayPal `ACTIVATED` and PayPal `CANCELLED` — but **not** on `invoice.payment_failed`, PayPal `SUSPENDED`, or PayPal `PAYMENT.FAILED` (`billing_service.py:75-89, 114-120`). Those set `past_due`, and `resolve_user_tier` (`spend_limit_service.py:104`) demotes `past_due` to FREE. The divergence is produced by a routine production event. → **NO-DEFENSE-FOUND.**

> Note: the cancellation path *is* innocent — `stripe_adapter._handle_subscription_deleted` returns `tier=SubscriptionTier.FREE`, so the quota row is correctly downgraded to 20. `[VF]` The reachable path is `past_due`, not `cancelled`.

**Net verdict: CONFIRMED.**

### D2 — FIRED
```python
repo = FakeQuotaRepository(_quota(period_start=None))
await QuotaService(repo).check("u1", SubscriptionTier.FREE)
```
Observed pre-fix: `TypeError: '<' not supported between instances of 'NoneType' and 'datetime.datetime'` at `quota_service.py:55`. `[VF]`

**Innocence attempt.** `migrations/001_saas_init.sql:40` and `migrations/alembic/versions/df9629e72f17_baseline.py:65` both declare `period_start TIMESTAMP WITH TIME ZONE` — nullable, **no DEFAULT**. All three INSERT paths omit the column: `quota_repo_postgres.get_quota:60-64`, `quota_repo_postgres.check_and_increment:93-96`, `subscription_repo.sync_quota_for_subscription:138-146`. Only `reset_monthly` ever writes it. `api/dependencies.py:661-667` catches the resulting `TypeError`, but converts a hard failure into `QuotaResult(allowed=True, remaining=10)` *on every subsequent call as well* — a permanent silent bypass rather than a defence. → **NO-DEFENSE-FOUND.**

**Net verdict: CONFIRMED.**

### D3 — FIRED
Observed pre-fix: `retry_after` differed from the true seconds-to-next-month-start by 60 033 s (≈16.7 h — the time of day the test ran). `[VF]` No guard exists. **CONFIRMED (LOW).**

### D4 — DID-NOT-FIRE as a defect; **CODE-INNOCENT**
The mechanism is real (`[VF]`: `extract_run_cost` returns non-None only for `type == "done"`, and `api/execution/pipeline.py:653-660` is the only emitter of `total_cost_usd` — no intermediate frame carries a running cost). But `tests/test_run_metering.py:256-267`, `test_a_reserved_run_that_cost_nothing_still_releases_the_reservation`, states in its own docstring: *"A cache hit **or an aborted run** must return the whole hold."* The behaviour is deliberate and test-pinned. Under the protocol's innocence rule this is not a defect of `metered`; the module **docstring was inaccurate**, and that has been corrected. The revenue exposure is real but accepted, and partially bounded by `infrastructure/llm/spend_tracker.py` (per-worker, volatile). **CLEARED (innocent) — recorded as residual risk.**

### D5 — FIRED (static, decisive)
`[VF]` `rg 'check_and_increment|increment\('` over `src/reasoner/**/*.py` returns only: the port declaration, `QuotaService.increment` itself, and the three repository implementations. No call site exists. Combined with D2 (which makes `check` fail open for every fresh account) the query quota cannot deny anyone.
**Innocence attempt.** If quota were vestigial-by-design the gate would have been removed; instead `check_quota` still raises 429 (`api/dependencies.py:669-683`), is wired into six routes, and `quota_service.py:73-75` records a deliberate earlier fix ("This was a no-op stub. Now delegates to repository") — i.e. someone repaired `increment` *expecting* it to be called. → **NO-DEFENSE-FOUND.** **CONFIRMED**, but the fix is a missing call site in the run path, not a change inside this function → escalated (Phase 5, E1).

### D6 — FIRED (static)
`[VF]` `billing_service.py:83-89` and `:114-120` omit `sync_quota_for_subscription`, unlike all six sibling branches. **Innocence attempt:** the adapter would have to downgrade `sub.tier` on these events; `stripe_adapter.sync_subscription:82-83` routes `invoice.payment_failed` to `_handle_payment_failed`, which does not force FREE the way `_handle_subscription_deleted` does. → **NO-DEFENSE-FOUND.** **CONFIRMED (MEDIUM)**; causally defended by the D1 fix, root cause escalated (E3).

### D7 — CODE-INNOCENT → **CLEARED**
`[VF]` The module docstring (`spend_limit_service.py:6-9`) scopes `check_run_allowed` to "reject a run whose preset cannot fit the ceiling **before spending anything on it**", with the mid-run executor as the authoritative stop. Admitting one final run at the boundary is the documented design, not an off-by-one.

### D8 — INDETERMINATE → **SUSPECTED**
`[VF]` `reference_id` is optional at both the service and the HTTP schema, so a replayed admin grant double-credits. No executable trigger distinguishes this from an intentional "unkeyed adjustment" affordance, and the endpoint is admin-scoped. Left as SUSPECTED; not fixed.

### D9 — CODE-INNOCENT → **CLEARED**
`[VF]` `cost_usd` originates from `PipelineState.total_cost_usd`, accumulated internally (`subagents/base.py:171`); it is not caller-controlled. `_settle`'s `except Exception` contains any `OverflowError`.

### D10 — CODE-INNOCENT → **CLEARED**
`[VF]` `credit_repo_postgres.record:138-163` opens a transaction, does `INSERT … ON CONFLICT DO NOTHING` then `SELECT balance … FOR UPDATE`, and only then evaluates `can_afford`. Idempotency is a partial unique index on `(user_id, reference_id)`. `tests/test_run_metering.py:343-379` already proves the in-memory equivalent under `asyncio.gather` (exactly one of two competing charges succeeds).

### D11 — CODE-INNOCENT → **CLEARED**
`[VF]` A negative setting clamps to `0.0`, and `_stricter(a, 0.0)` returns `a` — the tier default binds. A misconfiguration degrades to the tier ceiling, not to unlimited.

### D12 — no executable trigger → **UNKNOWN**
`[VF]` The hazard is structurally present: `reserve_or_402` debits before `StreamingResponse` construction (`api/__init__.py:713`, `:772`) and only `metered`'s `finally` releases. `[UNK]` Whether Starlette can close the body generator without entering it (client aborts during response start) cannot be settled without an ASGI-level runtime harness. Not promoted.

---

## PHASE 4 — Triage inventory

| Candidate | Trigger | Innocence | Evidence basis | Status |
|---|---|---|---|---|
| D1 entitlement tier ignored | FIRED | NO-DEFENSE-FOUND | VERIFIED DEFECT | **CONFIRMED — HIGH** |
| D2 NULL `period_start` → fail-open | FIRED (`TypeError`) | NO-DEFENSE-FOUND | VERIFIED DEFECT | **CONFIRMED — HIGH** |
| D5 `increment()` never called | FIRED (static, decisive) | NO-DEFENSE-FOUND | VERIFIED DEFECT | **CONFIRMED — HIGH** (escalated) |
| D6 `past_due` skips quota re-sync | FIRED (static) | NO-DEFENSE-FOUND | VERIFIED DEFECT | **CONFIRMED — MEDIUM** (escalated) |
| D3 `Retry-After` overshoot | FIRED (Δ 60 033 s) | NO-DEFENSE-FOUND | VERIFIED DEFECT | **CONFIRMED — LOW** |
| D4 abort releases whole reservation | mechanism real | CODE-INNOCENT (test-pinned) | FALSE (innocent) | CLEARED — doc corrected |
| D7 monthly cap excludes estimate | n/a | CODE-INNOCENT | FALSE (innocent) | CLEARED |
| D9 `usd_to_credits(inf)` | n/a | CODE-INNOCENT | FALSE (innocent) | CLEARED |
| D10 reserve/settle TOCTOU | DID-NOT-FIRE | CODE-INNOCENT | FALSE (innocent) | CLEARED |
| D11 negative spend cap | n/a | CODE-INNOCENT | FALSE (innocent) | CLEARED |
| D8 unkeyed admin grant | no decisive trigger | partial | SUSPECTED | INDETERMINATE |
| D12 orphaned reservation | none writable | — | UNKNOWN | INDETERMINATE |

**Ranked verified defects** (severity × reachability × blast_radius): D5 > D1 > D2 > D6 > D3.

---

## PHASE 5 — Fix design

### FIX A — D1 + D2 (merged; both live in `QuotaService.check`)

Merged deliberately: they touch the same function and the D2 guard must execute *before* the D1 arithmetic (a NULL `period_start` aborts the function before any ceiling is computed). Sequencing them as separate edits would leave an intermediate state where the D1 fix is unreachable for exactly the accounts D2 affects.

```diff
--- a/src/reasoner/application/services/quota_service.py
+++ b/src/reasoner/application/services/quota_service.py
@@
-        if quota.period_start < current_period_start:
+        # period_start is nullable and no INSERT path sets it, so a row that has
+        # never been reset arrives as None. Treat it as a stale period rather
+        # than comparing None to a datetime.
+        if quota.period_start is None or quota.period_start < current_period_start:
             await self._repository.reset_monthly(user_id)
             quota = await self._repository.get_quota(user_id)
 
-        remaining = max(0, quota.max_queries - quota.used_queries)
+        # The entitlement tier is a ceiling over the persisted row, not a
+        # synonym for it: invoice.payment_failed demotes a subscription to
+        # past_due (tier -> FREE) without re-syncing max_queries, so the row
+        # can still say 500. -1 on the row means unlimited, not a negative cap.
+        row_max = limit if quota.max_queries < 0 else quota.max_queries
+        effective_max = min(limit, row_max)
+
+        remaining = max(0, effective_max - quota.used_queries)
         if remaining <= 0:
             return QuotaResult(
                 allowed=False,
                 remaining=0,
                 retry_after=self._seconds_until_month_end(),
-                reason=f"Quota exceeded: {quota.used_queries}/{quota.max_queries} queries used this period.",
+                reason=f"Quota exceeded: {quota.used_queries}/{effective_max} queries used this period.",
             )
```
*11 lines changed, 1 function.*

**Causal justification.** The verified mechanism for D1 is that `limit` was computed and then discarded, leaving the persisted row as the sole ceiling. `min(limit, row_max)` breaks it by making the entitlement tier bind whenever it is stricter — the exact direction the BUG-502 contract requires — while still honouring a row deliberately capped below its tier. `row_max = limit if quota.max_queries < 0` is required, not cosmetic: without it the `-1` unlimited sentinel becomes the strictest possible ceiling and denies an enterprise-rowed caller outright (that sub-trigger fired). The verified mechanism for D2 is an unguarded ordered comparison against a nullable column; short-circuiting on `is None` breaks it by routing a never-reset row into the same branch a stale row takes, which is also the semantically right answer (a row with no period *has* no current period). No lower-side-effect fix exists: repairing the column default would fix D2 only for new rows, requires a migration, cannot heal existing NULLs without a backfill, and leaves this fail-open comparison one bad row away from recurring.

**Risk.** Scope: one method, read-path only — no writes added, no new imports (import-linter untouched). Side effects: the `reason` string now reports the effective ceiling rather than the row's; a caller on an un-synced `past_due` row will start receiving 429 where it previously got 200 — that *is* the intended behaviour change. Regression risk: LOW; the tier argument was previously inert, so entitled callers are unaffected (verified by the no-regression test). Reversibility: FULL (pure revert).

### FIX B — D3

```diff
-        next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
+        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
+        next_month = (month_start + timedelta(days=32)).replace(day=1)
```
*2 lines changed, 1 function.* **Causal justification:** the verified mechanism is that `replace(day=1)` preserves the time fields, so the "next month" anchor sat at the current wall-clock time on the 1st; zeroing the time fields first breaks it. The `+32d → replace(day=1)` idiom is retained because it is already correct for every month length. **Risk:** LOW/LOW/LOW, reversible.

### FIX C — D4 documentation correction

`run_metering.metered`'s docstring asserted a settlement guarantee the code does not provide. Replaced with the accurate statement plus an explicit "Known gap" paragraph naming the missing mechanism (a running cost on intermediate frames) and the residual bound (`spend_tracker`). Comment-only; no behavioural change. Left unfixed in code because the behaviour is deliberate and test-pinned (`tests/test_run_metering.py:256-267`).

### Escalations

**`[REQUIRES HUMAN REVIEW: cross-boundary mechanism]` — E1 (D5): the query quota is never advanced.**
Fixing this means adding a call site, not editing a function in this tier. The counter must advance exactly once per *successful* run, which means it belongs where settlement already lives, so that the four adapters (`api/__init__.py`, `api/routes/agent.py`, `api/mcp/tools.py`) inherit it the way they inherit billing. Proposed larger diff, for review:

```diff
--- a/src/reasoner/application/services/run_metering.py
+++ b/src/reasoner/application/services/run_metering.py
@@ class RunObserver(Protocol):
     def observe(self, *, status: str) -> None: ...
+
+
+class QuotaCounter(Protocol):
+    """Advances the caller's monthly query count for a delivered run."""
+
+    async def increment(self, *, user_id: str, preset: str) -> None: ...
@@ async def metered(
-    observer: RunObserver | None = None,
+    observer: RunObserver | None = None,
+    quota: QuotaCounter | None = None,
 ) -> AsyncIterator[str]:
@@
     finally:
+        # Only a run that reported a cost was delivered; a failed or abandoned
+        # run must not consume the caller's monthly allowance.
+        if quota is not None and ctx.user_id and cost_usd > 0:
+            try:
+                await quota.increment(user_id=ctx.user_id, preset=ctx.preset)
+            except Exception as exc:
+                logger.warning("Quota increment failed for %s: %s", ctx.reference_id, exc)
         if ctx.user_id and ctx.reserved_credits > 0:
```
plus a `QuotaSink` binding in `api/run_observability.py` delegating to `_get_quota_service().increment(...)`, and passing it at the five `metered(...)` call sites. **Not applied**: it adds a protocol, a binding class, and five call-site changes — well outside the one-function limit — and it makes a currently-inert 429 gate live for every authenticated user, which is a product decision, not a defect fix. Note that `check_and_increment` re-reads the row's `max_queries`, so E1 should land *after* FIX A or the repository will need the same ceiling composition.

**`[REQUIRES HUMAN REVIEW: cross-boundary mechanism]` — E2 (D4): unbilled spend on an abandoned run.** Closing it requires the pipeline to emit a running `total_cost_usd` on intermediate frames (`api/execution/pipeline.py` / `api/serializers.py`) and relaxing `extract_run_cost` to accept it from any frame — two modules, and it invalidates a currently-passing pinned test (`test_cost_comes_only_from_a_terminal_done_frame` asserts a phase frame's cost is ignored). Requires a product decision about charging for partial work.

**`[REQUIRES HUMAN REVIEW]` — E3 (D6): `past_due` never re-syncs the quota row.** The one-line-looking fix — adding `await repo.sync_quota_for_subscription(sub)` to the two `past_due` branches of `billing_service._apply_webhook` — is not safe as written: `sub.tier` on `invoice.payment_failed` comes from `_handle_payment_failed`, which does not force FREE the way `_handle_subscription_deleted` does, so the call could re-affirm the paid ceiling rather than remove it. Correcting it means changing the adapter's tier mapping for these events (`infrastructure/billing/stripe_adapter.py`, `paypal_adapter.py`) — outside this tier, and outside the one-function limit. FIX A makes the divergence harmless at the enforcement point, so this is a data-hygiene follow-up rather than a live exposure.

### Fix interactions

`[VF]` FIX A and FIX B touch the same class; FIX B is called from the branch FIX A modifies (`retry_after=self._seconds_until_month_end()`), and FIX A *increases* how often that branch is reached — so FIX B's correctness is now more load-bearing than before, which is why both ship together and both are covered by tests. FIX C is comment-only and interacts with nothing. E1 must be sequenced *after* FIX A (see above).

---

## PHASE 6 — Self-review (RAR)

### FIX A

| Vector | Attack | Verdict |
|---|---|---|
| Boundary | `used_queries == effective_max` exactly; `max_queries == 0`; `max_queries == -1` under a bounded tier; `max_queries` above the tier limit; `max_queries` below it | **FIX HOLDS [VF]** — `test_the_persisted_row_still_binds_when_it_is_the_stricter_of_the_two`, `test_an_unlimited_row_is_still_bounded_by_a_non_unlimited_tier`, `test_quota_service_free_blocks_when_exhausted` (pre-existing) |
| Invalid input | `tier` = a plain string outside the enum; `tier = None` | **FIX HOLDS [VF]** — `TIER_LIMITS.get(tier, TIER_LIMITS[FREE])` now actually binds; `test_an_unknown_tier_falls_back_to_the_free_ceiling` |
| State (corrupt/partial) | `period_start = None`; `period_start` in a past month; repository returning the same object after `reset_monthly` | **FIX HOLDS [VF]** — `test_a_quota_row_with_no_period_start_is_reset_rather_than_crashing`, `test_a_stale_period_still_triggers_the_monthly_auto_reset` |
| Regression | Does an entitled PRO subscriber still get 500? Does ENTERPRISE still short-circuit? | **FIX HOLDS [VF]** — `test_an_entitled_pro_subscriber_keeps_the_full_pro_allowance`, `test_enterprise_entitlement_short_circuits_before_any_repository_read`, plus all 3 pre-existing `test_saas_quota_service.py` cases and all 6 `test_quota_tier_lookup.py` cases green |
| Concurrency | The function is read-only apart from `reset_monthly`, which was already there and is unchanged; no new check-then-act window is introduced across an `await` | **FIX HOLDS [HYP]** — reasoned; no new shared-state mutation exists to test |
| New defect | Re-ran the taxonomy over the changed region: `min()` on two ints (no float), no division, no subscript (all `.get()`/attribute), no new `await`, no new import | **FIX HOLDS [VF]** — full neighbouring suite green |

One vector reached `[HYP]` (concurrency). Per Phase 7's rule it is downgraded rather than asserted: the claim "FIX A introduces no new race" is `[HYP]`, justified by the absence of any added mutation, not by an executed concurrency harness.

### FIX B

| Vector | Verdict |
|---|---|
| Boundary (31-day months, December→January, the 1st at 00:00:00) | **FIX HOLDS [VF]** — `+32d` from a zeroed month start still lands inside the following month for every month length; asserted against an independently computed expectation in `test_retry_after_points_at_the_start_of_next_month_not_the_current_clock_time` |
| Invalid input / state | No inputs — reads `datetime.now(UTC)` only | **FIX HOLDS [VF]** |
| Regression | Only ever reached on the 429 path; the value is advisory | **FIX HOLDS [VF]** |
| Concurrency / new defect | Pure function, no shared state | **FIX HOLDS [VF]** |

No `FIX BREAKS` on any vector for either fix; no revision cycle was needed.

---

## PHASE 7 — Tests

`tests/test_quota_tier_enforcement.py` — 9 tests, matching the conventions of the neighbouring `tests/test_quota_tier_lookup.py` (module docstring naming the bug and the contract, behaviour-named tests, a hand-written fake repository rather than mocks, `pytestmark = pytest.mark.unit`).

| Test | Role |
|---|---|
| `test_a_lapsed_pro_row_does_not_grant_pro_quota_to_a_free_tier_caller` | proof-of-defect (D1) |
| `test_a_quota_row_with_no_period_start_is_reset_rather_than_crashing` | proof-of-defect (D2) |
| `test_retry_after_points_at_the_start_of_next_month_not_the_current_clock_time` | proof-of-defect (D3) |
| `test_the_persisted_row_still_binds_when_it_is_the_stricter_of_the_two` | boundary |
| `test_an_unlimited_row_is_still_bounded_by_a_non_unlimited_tier` | boundary (`-1` sentinel) |
| `test_an_unknown_tier_falls_back_to_the_free_ceiling` | boundary (invalid input) |
| `test_enterprise_entitlement_short_circuits_before_any_repository_read` | no-regression |
| `test_an_entitled_pro_subscriber_keeps_the_full_pro_allowance` | no-regression (BUG-502) |
| `test_a_stale_period_still_triggers_the_monthly_auto_reset` | no-regression |

**Before the fix:** 5 failed, 4 passed. **After the fix:** 9 passed.

Full regression sweep over the tier's neighbourhood:
```
tests/test_quota_tier_enforcement.py tests/test_saas_quota_service.py tests/test_quota_tier_lookup.py
tests/test_run_metering.py tests/test_credits.py tests/test_saas_quota_integration.py
tests/test_saas_quota_repo.py tests/test_saas_cached_quota.py tests/test_quota_redis_fallback.py
tests/test_saas_stripe_webhooks.py tests/test_saas_domain.py tests/test_images_metering.py
tests/test_metered_auth_policy.py
→ 109 passed in 137.86s
```

Gates: `python scripts/ruff_ratchet.py --max 2249` → `PASS: 2249 violations matches ratchet MAX=2249` (unchanged — no `scripts/ci-local.sh` / `.github/workflows/test.yml` constant update needed). No modules moved and no imports added, so the import-linter contract (58/65) is untouched.

---

## PHASE 8 — Verdict, coverage & residual risk

### Surface audited
`application/services/{billing_service, credit_service, quota_service, run_metering, spend_limit_service}.py`; `domain/{credits, pricing, saas, spend_limits}.py`; `api/run_observability.py`; `api/routes/credits.py`. Traced outward for reachability and innocence only: `api/dependencies.py` (`reserve_or_402`, `check_quota`), `api/__init__.py` (`/api/run`, `/api/run-followup`), `infrastructure/persistence/{credit_repo_postgres, quota_repo_postgres, cached_quota_repo, subscription_repo}.py`, `infrastructure/billing/stripe_adapter.py`, `infrastructure/llm/spend_tracker.py`, `migrations/001_saas_init.sql`.

### Surface NOT audited
`application/services/{estimate_service, anonymous_trial_policy, api_key_service}.py`; `api/routes/{images, admin, account_keys}.py` (image credits use a separate reserve/release path at `routes/images.py:216-257`); `infrastructure/billing/paypal_adapter.py` (read for branch names only); `billing_deadletter_repo.py` and `deadletter_replay_service.py`; `api/mcp/tools.py`; the mid-run ceiling enforcement in `infrastructure/llm/executor`. Everything outside T1 by tier assignment.

### Defect classes covered
(1) money-loss arithmetic — covered (D1, D3, D7, D9, D11). (2) state machine — covered (D6, D10). (3) concurrency — covered by static reading plus the pre-existing `asyncio.gather` harness; **no new repeated-trial harness was written**, so no STATISTICAL claim is made. (4) error paths — covered (D2, D4, D5, D12). (5) boundary — covered (D1 sentinel, D2 None, D9 inf/NaN, D11 negative).

### Confirmed defects by severity
- **HIGH ×3** — D1 (`quota_service.py:44,59`), D2 (`quota_service.py:55`), D5 (`quota_service.py:70`, no call site).
- **MEDIUM ×1** — D6 (`billing_service.py:83-89, 114-120`).
- **LOW ×1** — D3 (`quota_service.py:83`).
- **CRITICAL ×0.**

**Cleared as innocent: 5** (D4, D7, D9, D10, D11). **Indeterminate: 2** (D8 SUSPECTED, D12 UNKNOWN).

### Residual UNKNOWN set — needs runtime instrumentation
1. D12 — whether a client abort during response start can leave a reservation orphaned. Needs an ASGI-level harness driving `StreamingResponse` with a disconnect before first send.
2. The real-world rate at which runs terminate without a `done` frame (sets the size of E2's exposure). Needs production SSE telemetry.
3. How many live `usage_quotas` rows currently hold `period_start IS NULL` or a `max_queries` that disagrees with the subscription's entitled tier. Needs a query against production data.
4. Whether `spend_tracker`'s per-worker ceiling is the only thing bounding an abandoned run in the deployed topology (`worker_count` multiplies it).

### Clean-claim scope
Regions R1–R11 as listed in Phase 1 were audited for defect classes 1–5. Outside the five confirmed defects and the two indeterminates, no VERIFIED defect was found in those regions. This is **not** a claim that the billing surface is bug-free: three of the eleven regions were cleared on reasoning plus an existing test rather than on a new executed trigger, and the not-audited list above is substantial.

### Highest-value next hunt
`application/services/estimate_service.py` together with `api/routes/images.py`. Estimation is the input to every reservation — an under-estimate becomes an under-reservation and, on the abandoned-run path (E2), an unbilled run; and the image route hand-rolls its own reserve/release rather than composing `metered()`, which is exactly the divergence `run_metering`'s docstring says the module exists to prevent.

---

## Uncertainty Acknowledgment

**Most likely false positive.** D6. It is verified as a *divergence* — the two `past_due` branches genuinely omit a call every sibling branch makes — but the omission may be deliberate: `past_due` is a transient dunning state, and preserving the paid quota row across a retried payment could be intentional rather than an oversight. I did not read `_handle_payment_failed`'s body in full, and I did not find a comment either way. Its severity (MEDIUM) rests entirely on the combination with D1, which is now fixed.

**Real defect most likely missed.** Something in the image-credit path (`api/routes/images.py:216-257`), which reserves and releases credits through its own bespoke sequence instead of `metered()`. It is explicitly out of scope for T1's file list, it is the one place the shared metering invariant is deliberately bypassed, and bespoke reserve/release sequences are exactly where partial-failure bugs live. Second most likely: an ordering bug in webhook handling, since Stripe does not guarantee event order and nothing in `_apply_webhook` compares timestamps or versions.

**Requires runtime validation.** D12 (orphaned reservation on early disconnect); the true frequency of pre-terminal aborts; the actual state of production `usage_quotas` rows; and whether `check_quota`'s "emergency limits" path is currently firing in production — if it is, D2 is live today rather than latent, and the logs would say so.

**What static analysis cannot determine.** Whether the query quota and the credit ledger are meant to be two independent gates or one superseding the other — D5's severity flips entirely on that product intent. Also: real concurrency behaviour under Postgres isolation levels (`FOR UPDATE` was read, not exercised), the actual event ordering Stripe delivers, and whether `worker_count > 1` in the deployed topology.

**What would most increase confidence.** (a) A one-line answer on whether the query quota is meant to be enforced — it decides E1 outright. (b) A production query: `SELECT count(*) FROM usage_quotas WHERE period_start IS NULL`, and a count of rows whose `max_queries` disagrees with the entitled tier — that converts D1 and D2 from "reachable" to a measured blast radius. (c) A grep of production logs for "Quota check failed due to DB error" and "Credit settlement failed".

---

## Files changed (uncommitted, in this worktree)

**Mine:**
- `src/reasoner/application/services/quota_service.py` — FIX A + FIX B (+15 / −4)
- `src/reasoner/application/services/run_metering.py` — FIX C, docstring only (+10 / −4)
- `tests/test_quota_tier_enforcement.py` — new, 9 tests
- `docs/reports/defect-hunt-2026-09-01/T1-billing-metering.md` — this report

**Not mine — present in this shared worktree from a concurrent tier, left untouched:**
`src/reasoner/infrastructure/persistence/cached_quota_repo.py`, `.../event_store.py`, `.../snapshots.py`, `tests/unit/test_snapshot_replay_sqlite.py`.
