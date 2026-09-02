# Backend Defect Remediation Plan

**Status:** plan, not executed
**Date:** 2026-09-02
**Input:** `docs/reports/defect-hunt-2026-09-01/ROLLUP.md` and the seven tier reports
**Scope:** `src/reasoner/**`. `ui-next/**` untouched.

Closes the 9 open escalations, the residual UNKNOWN set, and the three loose items found while running the hunt. Ordered by dependency, not by severity, because three of the fixes unblock others.

---

## 0. The one thing to read first

Two defects in this list were concealed by **test fakes that were faithful to nothing**:

- `tests/test_saas_quota_repo.py` mocked `user_id` as a `str`; asyncpg returns `uuid.UUID`. `UUID(str)` passes, `UUID(UUID)` raises. Quota enforcement was absent on every PostgreSQL deployment.
- A provider test stubbed an async `create` as **synchronous**, hiding a `TypeError` on the streaming path.

Seven tiers of static analysis could not see either, because in both cases the code was consistent with its test and the test was inconsistent with reality. **Section 7 makes fixing that class of problem a work item, not an observation.** If only one thing here gets done, it should be that.

---

## 1. Architectural constraints binding every item below

From `CLAUDE.md`. A fix that violates one of these is not a fix.

| Constraint | Consequence for this plan |
|---|---|
| Domain has no outer dependencies | Value objects introduced in §2.1 go in `core/`, never importing `infrastructure` |
| Application depends on Domain and Core only | `application/` must not import `infrastructure.llm` directly; use the port |
| Infrastructure implements Core ports | Provider changes are adapter-side; the contract lives in `core/ports/` |
| API depends on Application | Wiring changes land in `api/__init__.py`, `main.py`, `headless.py` |
| `import-linter`: 1 contract, exactly 60 exceptions | Exact-equality gate. Moving a module across a layer trips it |
| ruff ratchet: exactly 2243 | Exact-equality. **Removing lint fails the gate as hard as adding it.** Constant lives in `scripts/ci-local.sh:51` AND `.github/workflows/test.yml` |
| Coverage: 60% fail, 80% warn | Adding tests helps; deleting a covered branch can drop it |
| `.get()` never subscript on method-specific state | Protects `--resume` across version skew. Verified holding; do not regress |
| All LLM responses via `parsing.extract_json()` | Never `json.loads` on model output |
| Four propagation-resistance invariants | Verified holding. Two hold by *omission*, so any refactor can break them silently |

**Ratchet protocol for this plan:** every group below states its expected ruff delta. Update the constant **once per PR**, in both files, in the same commit as the code. Never mid-group.

---

## 2. Group A: contract changes (do first, they unblock the rest)

### A1. Return LLM usage as a value object instead of stashing it on the provider

**Closes escalation 1**, the most severe open item: usage counters attributed to the wrong run in 82.5% of concurrent calls (99 of 120).

**Root cause, precisely.** `ProviderRouter._dedupe` (`router.py:313`) returns one shared provider instance per identity. `_get_llm_semaphore` (`router.py:264`) permits up to 30 concurrent calls per model. Each call writes `self.last_input_tokens`, `self.last_output_tokens`, `self.last_cost_usd` onto that shared object. `_build_metadata` (`router.py:439`) then reads those attributes **after** the semaphore is released:

```python
    def _build_metadata(self, provider: BaseLLMProvider, response: str) -> dict[str, Any]:
        metadata = {"model": provider.model}
        if hasattr(provider, "last_input_tokens"):
            metadata["input_tokens"] = provider.last_input_tokens
```

Per-call state on a shared mutable object read outside the critical section. Capturing earlier does not fix it: 30 concurrent calls share the same instance regardless of when you read.

**Why the obvious fix is wrong.** Narrowing the semaphore to 1 per model serialises all LLM traffic and destroys the parallel fan-out the pipeline is built on. Copying counters inside the lock still races the 30 permitted holders.

**The fix that removes the class.** Make per-call usage a *returned value*, not instance state.

1. Add to `core/ports/` (Domain-safe, no outer imports):

```python
@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    finish_reason: str = "stop"
    cache_read_tokens: int = 0

@dataclass(frozen=True)
class LLMResult:
    text: str
    usage: LLMUsage
```

2. `BaseLLMProvider.complete()` returns `LLMResult`. The `last_*` attributes stay for one release as deprecated read-only shims mirroring the most recent call, so nothing outside the router breaks at once.
3. `_call_with_circuit` (`router.py:106`) returns `LLMResult` instead of `str`. This is the return-type change across three functions that T4 correctly refused to make unsupervised.
4. `_build_metadata` takes `usage: LLMUsage` instead of `provider`.

**Layer check.** `LLMUsage`/`LLMResult` are value objects in `core/`, so `application/` may consume them without importing `infrastructure`. Provider adapters in `infrastructure/llm/providers/**` implement the port. No layer inversion, no new `import-linter` exception.

**Blast radius.** 12+ adapters, `router.py`, `executor.py`, and every caller reading `last_*`. Large, and it must be done in one PR: a half-migrated contract is worse than either end state.

**Tests.** The `xfail(strict=True)` tripwire T4 left flips to passing. Add a concurrency harness of N>=120 calls across >=2 models asserting every call's returned usage matches what its own transport stub emitted. Report `STATISTICAL(rate)`, never a deterministic claim.

**Expected ruff delta:** likely negative, since removing `hasattr` chains removes lines. Measure and set once.

**Risk:** HIGH scope, LOW conceptual. Reversible per commit; the shims mean partial rollback is survivable.

---

### A2. Add the two missing `EventType` members and align the phase event fields

**Unblocks escalation 2 and, transitively, 8.**

`flows/runner.py:99` references `EventType.PHASE_QUALITY_CHECKED` and `:121` references `EventType.PHASE_RETRIED`. Neither exists. `core/events/domain_events.py` defines only:

```
PHASE_STARTED = "phase_started"
PHASE_COMPLETED = "phase_completed"
PHASE_FAILED = "phase_failed"
```

The runner also constructs `PhaseStarted(phase_number=...)` and `PhaseFailed(is_fatal=...)`, but the dataclasses declare:

```
class PhaseStarted(DomainEvent):  phase_name: str, config: dict
class PhaseFailed(DomainEvent):   phase_name: str, error: str, retry_count: int
```

So the runner cannot construct a single event successfully. That is why it has never run.

**Fix.** In `core/events/domain_events.py`: add `PHASE_QUALITY_CHECKED` and `PHASE_RETRIED` to `EventType`; add `phase_number: int = 0` to `PhaseStarted` and `is_fatal: bool = False` to `PhaseFailed`. **New fields need defaults** so existing persisted events still deserialize, which is the same version-skew property `--resume` relies on.

**Do NOT** change the runner's call sites to match the current dataclasses instead. The runner's shape is the intended design; the events are the incomplete half.

**Tests.** Construct each event with the runner's exact kwargs. Replay a stored event stream written *before* the new fields to prove the defaults preserve backward compatibility.

**Risk:** LOW. Additive, defaulted, no layer change.

---

## 3. Group B: wiring gaps (depend on Group A)

### B1. Wire `WorkflowRunner` into the non-SSE path

**Closes escalation 2.** Depends on A2.

`application/pipeline.py:492-495`:

```python
runner = WorkflowRunner(PipelineWorkflowServices(self))
services = PipelineWorkflowServices(self, runner=runner)   # never read
await runner.run(strategy, state)
```

The runner-aware `services` is a dead local. Every CLI and headless run has therefore executed with no retries, no timeouts, no quality monitoring and no phase events. Probe evidence: `run_phase` calls `[]`, zero phase events, `phase_tokens {}`.

**Fix.** One line: pass `services` into the runner. But treat this as a **behavior change, not a bug fix**. It switches on a retry, timeout and quality layer that has never executed, for every CLI and headless run at once.

**Required staging, and this is the part not to skip:**

1. Land A2 first, or the first phase raises.
2. Put it behind a setting (`WORKFLOW_RUNNER_ENABLED`, default **off**) for one release.
3. Run the full mock preset end-to-end suite (`tests/test_e2e_budget_presets_mock.py`) with it **on**, and diff phase-by-phase output against off. Any difference is a finding to triage before flipping the default.
4. Flip the default in a separate, revertable commit.

**Tests.** The `xfail` tripwire T5 left flips. Add: retries actually retry, timeouts actually fire, `phase_tokens` is populated, phase events reach the bus.

**Risk:** HIGH behavioral. The staging above is what makes it acceptable.

---

### B2. Give `QuotaService.increment()` a caller

**Closes escalation 3.** Independent of A and B1.

`increment()` has zero callers in `src/` (verified by grep) while the class is wired live at `api/dependencies.py:413`. `used_queries` never advances, so the query quota can never deny. With the PostgreSQL bypass now fixed, this is the **only** remaining reason quota does not enforce.

**Fix.** Call `increment()` after a successful run, not before. The service's own docstring states the intent: "Does NOT increment usage, call increment() separately after a successful pipeline run to avoid charging for failed runs." Honor that.

**Where.** The metering path already brackets a run and already knows success or failure: `application/services/run_metering.py` with its sink bound at `api/run_observability.py`. Add quota increment as a **sink concern** alongside credits, rather than sprinkling calls at 5 call sites. That keeps it in Application, keeps API as the composition root, and gives one place to reason about "what a completed run costs".

**Tests.** A denied run does not increment. A successful run increments exactly once. Two concurrent successful runs increment exactly twice, N>=100 trials.

**Risk:** MEDIUM. This makes quota actually deny for the first time; users previously over their limit will start getting 429. Name that in the release notes.

---

### B3. Make the jury Critic Pool's `critical=True` effective

**Closes escalation 8.** Blocked on B1: the flag is only read by the runner.

`application/flows/jury.py:70-76` sets `critical=True` on the Critic Pool, but the return is discarded, so the flag is inert. Once B1 lands, verify the runner honors it, and add a test where a critical phase failure aborts the run rather than continuing with a missing critique.

**Risk:** LOW once B1 is in.

---

## 4. Group C: local correctness fixes (independent, parallelisable)

### C1. Reject `NaN` and `Infinity` at the parse boundary

**Closes escalation 4.** Highest value-per-line in this plan.

`safe_float` is at **`core/parsing.py:636`**, not `utils/`:

```python
def safe_float(value: Any, default: float = 0.0, min_val: float = 0.0, max_val: float = 10.0) -> float:
```

Bare `NaN`/`Infinity` survive JSON parsing (Python's `json` accepts them by default). `safe_float(nan)` returns **10.0**, the maximum bound rather than the default, because a NaN comparison is always False and the clamp falls through to `max_val`. `_parse_review_hypotheses` clamps NaN to probability **1.0**. A malformed model response therefore produces a *maximum confidence score*.

**Fix, two parts:**

1. `utils/json_safe.py:safe_json_loads` (line 25): pass `parse_constant` to reject `NaN`, `Infinity`, `-Infinity` outright. Model output containing them is malformed; failing loudly beats guessing.
2. `core/parsing.py:safe_float`: guard `math.isnan(v) or math.isinf(v)` **before** clamping, returning `default`.

Both, not one. The parse boundary should reject them, and the numeric helper should not mistranslate them if they arrive another way.

**Widening warning.** This makes the parser accept *less*. That is the correct direction, but name what could newly fail: any producer legitimately emitting `Infinity`. Grep before landing.

**Tests.** T6's `xfail(strict=True)` flips. Add: `safe_float(nan)` returns `default`; a score payload with `NaN` does not yield a maximum score.

**Risk:** LOW code, MEDIUM behavioral. Previously-silent garbage now raises.

---

### C2. Await the async close in `reset_event_store`

**Closes escalation 6.**

`infrastructure/persistence/event_store.py:853` calls `PostgreSQLEventStore.close()` without awaiting, so the asyncpg pool is never closed. The other half is `api/__init__.py:280`, which is why it was escalated as cross-boundary.

**Fix.** Make `reset_event_store` async and await the close, then update the API call site. Both halves in one commit; a coroutine-returning function whose callers ignore it is the defect.

**Tests.** After reset, the pool reports closed. Guard against a `RuntimeWarning: coroutine was never awaited`, which is the symptom that should never return.

**Risk:** LOW. Contained, two call sites.

---

### C3. Re-sync quota on the `past_due` branches

**Closes escalation 7.**

Two `past_due` branches in `application/services/billing_service.py` omit `sync_quota_for_subscription`, unlike all six siblings. A lapsed subscription keeps its old allowance until something else re-syncs.

Note the interaction: T1's entitlement-ceiling fix in `QuotaService.check()` already makes the divergence **harmless at the enforcement point**, because the tier ceiling now bounds the persisted row. So this is consistency work, not an active hole. Fix it anyway: leaving two of eight branches different is how the next defect gets planted.

**Tests.** All eight branches re-sync. Table-driven over the branch set, not eight separate tests.

**Risk:** LOW.

---

### C4. Bill spend on abandoned runs

**Closes escalation 5.**

A run whose response generator is never entered leaves a reservation orphaned and spend unbilled. Needs a running cost carried on intermediate frames.

**Why it is last in this group.** It invalidates a test that deliberately pins current behavior (`test_run_metering.py:256-267`), which T1 verified is intentional, not stale. Changing it means changing a **decision**, not a bug. Confirm the intended policy first:

> `[INPUT REQUIRED: should a run abandoned mid-stream be billed for tokens already spent, or released? The current code deliberately releases the whole reservation and a test pins that.]`

Do not land this until that question is answered. Everything else in this plan is a defect; this one is a product decision wearing a defect's clothes.

---

## 5. Group D: concurrency and lifecycle

### D1. One lock per index file in `TenantManager`

**Closes escalation 9**, currently UNKNOWN rather than CONFIRMED.

LRU/TTL eviction hands a recreated tenant a **different** `index_lock` over the same `index.json`. T7 proved both halves separately (two `L2Index` objects over one directory silently drop an entry; eviction then re-get yields a new lock over the same `data_dir`) but could not compose them offline, so it was not promoted.

**First step is not a fix, it is a trigger.** Compose the two halves into one executable test that forces eviction under concurrent writes and asserts the dropped entry. If it fires, the item becomes CONFIRMED and the fix is a lock keyed by resolved `data_dir` rather than by tenant object identity. If it does not fire, record the innocence and close it.

**Risk:** MEDIUM. Do not fix what has not been proven; the protocol treats a false positive as seriously as a miss.

---

## 6. Group E: the unexecuted surface

These are UNKNOWN, not clean. A disposable PostgreSQL container (`reasoner-defect-hunt-pg`, port 55432, PostgreSQL 16.14) has already been shown to work for this.

| Item | What to do |
|---|---|
| Untransacted compaction (T2) | Execute against the container: interrupt compaction mid-run, assert the stream is still replayable |
| Missing `(aggregate_id, version)` uniqueness (T2) | Attempt a duplicate `(aggregate_id, version)` insert. If it succeeds, the event stream can fork silently: add the constraint in a migration |
| WebSocket authz (T3) | `websocket_endpoint` never calls `_check_pipeline_ownership`. Named by T3 as its own highest-value next hunt. **Treat as CRITICAL until disproven**: it is an authorization gap on a live channel |
| `/api/keys/validate` | Uses legacy `require_auth` with no admin scope |
| Unkeyed admin credit grant | `reference_id` optional, so a retry can double-grant |
| `/api/search` error text | Forwards provider exception text to the caller |
| `circuit_breaker.py` | Never opened by any tier |
| Per-preset fallback | Behavior unverified |
| Streaming path end to end | Unverified; note `executor.execute_stream` has no caller in `src/` |

### E-policy. `check_quota` fails open, by design, and that design just failed

`api/dependencies.py:659-667` catches `Exception` and returns `allowed=True, remaining=10`. Its own comment records a *previous* fail-open fix. The PostgreSQL defect proved the failure mode: `get_quota` raised on every call, and this catch silently converted a total outage into unlimited access.

This is a policy question, not a defect:

> `[INPUT REQUIRED: on a quota-backend outage, should requests be allowed (current), denied, or allowed with a hard low ceiling plus an alert? The current behavior means a backend failure is indistinguishable from having quota.]`

At minimum, make it **loud**: emit a metric and an alert, not just `logger.warning`. A silent fail-open is how this stayed invisible.

---

## 7. Group F: verification debt (the highest-leverage work here)

The defect hunt found that **test fixtures lying about reality is this codebase's most productive defect signature**. Two confirmed defects hid behind it. Fixing individual defects without fixing this guarantees a third.

### F1. Audit test fakes for type fidelity

Sweep `tests/` for fakes that return a different type than the real dependency:

- asyncpg returns `uuid.UUID` for `uuid` columns, `datetime` for `timestamptz`, `Decimal` for `numeric`. Any fake returning `str` for these is lying.
- Async methods stubbed as sync (T4's `create`).
- `MagicMock` where `AsyncMock` is required.

Start with `tests/test_saas_quota_repo.py`, the known offender. Deliverable: a short `tests/README` note stating the rule, plus corrected fixtures.

### F2. Prefer contract tests at adapter boundaries

Where a fake stands in for a driver, add one integration test against the real thing, marked `integration`, gated on the container. The unit tests stay fast; the contract test catches the lie.

### F3. Fix the flaky timing test

`tests/test_phase_span.py::TestPhaseSpan::test_phase_span_latency_tracking` asserts `elapsed >= 0.01` after `await asyncio.sleep(0.01)`. Measured on this machine: **31 of 2000 trials under threshold (1.55%), minimum 0.0** from clock granularity. Its docstring says "reasonable duration (>= 0)" while the assertion demands `>= 0.01`, and it tests `asyncio.sleep` rather than `PhaseSpan`.

**Fix by testing the subject:** assert `PhaseSpan` recorded a non-negative duration, per its own docstring. Do **not** simply relax the number; that is weakening an assertion to make a suite green. Test what the class promises.

### F4. Repair `migrations/003_add_indexes.sql`

Fails to apply: `ERROR: relation "query_log" does not exist`. Either the table belongs in an earlier migration or the index belongs in a later one. A migration set that cannot be applied from scratch means no environment can be rebuilt from zero.

---

## 8. Sequencing

Dependencies, not severity.

| Step | Work | Blocks | PR |
|---|---|---|---|
| 1 | **F1, F3, F4** verification debt | Nothing. Do first: cheap, and F1 prevents the next hidden defect | 1 |
| 2 | **A2** event types and fields | B1, B3 | 2 |
| 3 | **C1, C2, C3** local fixes, parallelisable | Nothing | 3 |
| 4 | **A1** LLM usage value object | Nothing, but large: own PR | 4 |
| 5 | **B2** quota increment | Nothing | 5 |
| 6 | **B1** runner wiring, behind a flag | B3 | 6 |
| 7 | **B3** jury critical flag | After B1 | 6 |
| 8 | **D1** tenant lock, trigger first | Nothing | 7 |
| 9 | **Group E** unexecuted surface, container-backed | Nothing | 8+ |
| 10 | **C4** and **E-policy**, after the two `[INPUT REQUIRED]` answers | Blocked on decisions | last |

**One PR per group.** Never one large PR: the hunt's own findings were reviewable because each tier committed separately.

---

## 9. Verification, per PR

Non-negotiable, all four, on every PR:

```bash
python -m pytest tests/ -q -p no:randomly -m "not slow and not integration"
python scripts/ruff_ratchet.py --max <current>
PYTHONPATH=src lint-imports --no-cache --verbose
python scripts/count_importlinter_exceptions.py --max 60
```

Current baseline, all verified 2026-09-02:

```
4033 passed, 83 skipped, 5 xfailed          (1 pre-existing flake, see F3)
PASS: 2243 violations matches ratchet MAX=2243
Contracts: 1 kept, 0 broken
PASS: 60 exceptions matches ratchet MAX=60
```

`lint-imports` needs `PYTHONPATH=src` and `--verbose`; without `--verbose` it dies with "Only one live display may be active at once".

**Per fix, the protocol's own bar:** a proof-of-defect test that fails without the fix and passes with it, at least two boundary tests, and one no-regression test. A fix without a test that fails beforehand is unverified, whatever the suite says afterwards.

---

## 10. What this plan will not claim

- It does not audit `phases/**` (36 files) or `subagents/**` (30 files). Still **unaudited**, not clean.
- Completing every item does not make the backend sound. It closes the defects that were found, in the regions that were examined, for the classes that were hunted.
- Three items are decisions, not defects, and are marked `[INPUT REQUIRED]`: the abandoned-run billing policy, the quota-outage policy, and whether the runner's default flips.
- The `82.5%` figure for escalation 1 and the `1.55%` for the flaky test are **statistical**, measured under specific load. They are evidence a race exists, not a prediction of production frequency.
