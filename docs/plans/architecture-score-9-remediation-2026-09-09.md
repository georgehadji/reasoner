# Remediation Plan: Architecture Score 5/10 → >9/10

**Baseline:** `docs/architecture-audit-2026-09-09.md`. Score **5/10** — 2 CRITICAL,
6 HIGH, 4 MEDIUM. Tree: `studio-adopt` at `2b4555e`.

**Target:** **>9/10**, which the rubric defines as five properties, not a
feeling: *all layers correctly separated, patterns consistent, observable,
testable, scalable*. Every phase below closes findings **and** ends in a fitness
function, because a property nothing verifies is a claim.

**Relationship to prior plans:**

- **Supersedes** `docs/plans/architecture-score-9-remediation-plan.md`
  (2026-08-20, 4/10 baseline). Its **Phase 0 landed** — verified on this tree,
  see §0. Its Phases 1–6 are partially open and are folded in below rather than
  re-litigated.
- **Extends** `docs/plans/audit-remediation-2026-09-08.md` (the P5
  "signal and proceed" work). Its R1 landed today as `25cc8bd`. Its R2/R3/R4 are
  **not duplicated here**; Phase C below adds the fourth instance of the same
  defect shape that the P5 plan did not have, and defers to it for the other
  three.
- **Does not supersede** `docs/plans/architecture-score-8.5-remediation-plan.md`
  (WS1/WS2 closed, the rest already folded into the 2026-08-20 plan).

---

## §0. What already landed — verified on this tree, do not redo

The 2026-08-20 plan's thesis was "the previous plan optimized the codebase and
left the ratchet broken." That plan fixed its own ratchet. Confirmed by reading
the tree, not the doc:

| Item | Status | Evidence |
|---|---|---|
| 0.3 — pytest config de-duplicated | **Done** | `grep tool.pytest.ini_options pyproject.toml` → 0 matches |
| 0.4 — layer fitness function walks `ast.Import` too | **Done** | `tests/architecture/test_layer_boundaries.py:88,90` |
| 0.5 — `xfail` god-file caps replaced with real thresholds | **Done** | `test_layer_boundaries.py:146` records the swap |
| 0.6 — import-linter budget is a two-way ratchet | **Done** | `scripts/count_importlinter_exceptions.py:47-52`, wired at `ci-local.sh:70 --max 59` |
| 0.7 — `unmatched_ignore_imports_alerting` | **Done, as `warn`, deliberately** | `.importlinter:8-13` — see the correction below |
| 0.9 — mypy over all of `src/` | **Done** | `scripts/mypy_ratchet.py --max 423`, `ci-local.sh:56` |
| 0.10 — per-package coverage floors | **Done** | `ci-local.sh:95` — `--package domain:85 --package core:75` |
| P5 ratchet detector | **Done today** | `25cc8bd` — AST pass, 58 → 105, `tests/unit/test_silent_failure_detector.py` |

Still open from that plan and carried forward here: **1.5**
(`infrastructure/execution/subprocess_executor.py` still exists, 8.7 KB) and
**Phase 2** (`EventStorePort` was never created — `core/ports/` holds 18 ports
and none of them is it).

### Correction to the 2026-09-09 audit

`docs/architecture-audit-2026-09-09.md` Phase 7 recommends flipping
`.importlinter`'s `unmatched_ignore_imports_alerting` from `warn` to `error`.
**That recommendation is withdrawn.** `.importlinter:8-12` documents why it is
`warn`:

> grimp's chain-resolution granularity differs across platforms (Linux CI vs
> Windows dev) even on the same pinned version, so some ignore_imports edges
> match on one OS but appear "unused" on the other.

Flipping it would fail every Windows dev run on an edge that is legitimately
matched in CI. The mechanism that actually stops stale exceptions accumulating
already exists and is the two-way count ratchet (0.6); the fix is to **delete
the four confirmed-dead entries and lower `--max` in the same change**, which is
D-4 below. Deleting dead entries stays; changing the alerting level does not.

Worth naming rather than quietly dropping: the audit recommended something the
code had already considered and rejected for a stated reason. A plan that
repeated it would be worse than no plan.

---

## The organizing thesis

The 5/10 has one cause with three faces, and the sequencing follows from it.

**The system has more mechanism than it has wiring.** Almost every capability
the rubric asks for already exists somewhere in this repo, built and often
tested — and is then not connected, connected behind a flag that has never been
on, or connected after a `break`. The quality gate exists twice and runs zero
times. `check_preset_access` exists and is called by nothing. `SharedCachePort`
and `DistributedStatePort` exist with working Valkey adapters while the monthly
billing ceiling uses a module-level dict. `LLMPort` exists and has two importers
against twenty-six of the concrete class. `set_build_provider` is called at
startup and read by nobody.

So this plan is **wiring-dominant, not construction-dominant**. That is good
news for effort and bad news for confidence: unwired mechanism is untested
mechanism, and every phase below therefore needs its test written *before* the
wire, because a suite that passes today passes precisely because the code does
not run.

The second face is **three ledgers and no arbiter** — `CLAUDE.md:19`,
`.importlinter:14-27` and `test_layer_boundaries.py:54-70` encode three
different architectures. No amount of local cleanup reaches "layers correctly
separated" while the definition is contested. Phase D picks one.

The third face is **failure semantics that return success shapes**. The P5 audit
named it; the router does it too (`router.py:585-588`). Phase C turns the fix
into a type the caller cannot ignore.

---

## Per-module paradigm and pattern selection

The rubric word is *consistent*, so the point of this table is not that each
choice is defensible in isolation but that a reader can predict, from the
module, what shape the code takes.

| Module | Paradigm | Patterns | Why this and not the alternative |
|---|---|---|---|
| `domain/` | Rich domain model, functional core — no I/O, no clock, no env | Value Object with invariants in `__post_init__`; **Specification** for rules; **Repository** *interface* only | Already 90% there, and `domain/watermark/rules.py` (8 rule classes with real predicates) proves the shape is achievable here. The three leaks — import-time file read, env read, vendor ids — are the whole gap. Rejected: keeping `pricing.py`'s module-level catalogue load for convenience, which makes `import domain.pricing` a filesystem operation and forces domain tests to have a disk |
| `core/ports/` | Ports and adapters, *earned* | **Port** kept only where ≥2 real implementations or a genuine test seam exists; delete the rest | Four ports have zero references outside their own file. A port with no adapter is not a seam, it is a comment with syntax. Rejected: keeping them "for later" — they inflate the apparent abstraction level, which is itself misleading to the next reader |
| `core/settings.py` | Explicit configuration object | **Parameter Object** resolved once at the **Composition Root**, injected thereafter | 100 direct importers of a module-level singleton frozen at first import is a service locator. The file says so itself at `:28-40`: a fixture running after collection is "already too late to isolate anything." Rejected: pydantic-settings with lazy resolution — same coupling, deferred |
| `application/` | CQRS over a **functional core / imperative shell** | **Command Handler**, **Strategy** (flows), **Template Method** (one runner), **Result/Either** for degradation | CQRS is already the shape and works. The missing half is that the shell *swallows* failure instead of *returning* it. Rejected: exceptions for degradation — this codebase has demonstrated four times that an exception path plus a fallback value becomes "log and proceed on the wrong value" |
| `application/flows` | Single Strategy hierarchy, single runner | **Template Method** in `WorkflowRunner`; **Null Object** for absent executors (already used) | Two engines with divergent semantics is one of the CRITICALs. One `PhaseStep` contract, one loop; strategies supply only the steps |
| `infrastructure/llm` | Adapter + **Anti-Corruption Layer** | **Decorator** chain for cross-cutting concerns; **Circuit Breaker** (present); **Bulkhead** for concurrency | `LLMExecutor.execute()` spans 475 lines and its own docstring lists six responsibilities, including **spend caps** — a billing rule inside a transport adapter. Decompose to `LLMExecutor` (transport) wrapped by `CachingExecutor`, `MeteredExecutor`, `SpendCappedExecutor`. Rejected: more flags on one class |
| `infrastructure/persistence` | Repository + **Unit of Work** | One `EventStorePort`, two adapters; **Outbox** where a write must be paired with an event | Two engines run simultaneously and three tables have multiple unrelated writers. The port was specified in the 2026-08-20 plan and never built |
| `api/` | Thin imperative shell | **Dependency Injection** via `Depends` from the composition root; no logic in handlers | `execute_run` is a 690-line method in the API layer that re-implements orchestration. This layer should translate HTTP to a command and back, nothing more |
| Concurrency | **Structured concurrency** | `asyncio.TaskGroup`; **Bulkhead** per model; bounded queues | Zero `TaskGroup` today; fan-outs use bare `gather`, most with no local bound. `TaskGroup` makes "one perspective failed" a decision instead of an accident |
| `hypergate/`, `subagents/` | Unchanged — parallel sub-agents with fail-safe fallback | **Chain of Responsibility** into the TieBreaker (already) | This subsystem is sound. Its only debt is 3 infra imports already tagged "needs DI to remove" |
| `neuro/` | Unchanged | Tiered cache; tenant key as a **chokepoint** | Best-defended subsystem in the codebase. Do not refactor it; only govern it — it is absent from `.importlinter` layers entirely |
| Enforcement | **Architectural fitness functions** | Two-way ratchets, AST guards | Already the house style, and it works. Every phase below adds one |

---

## Phase A — Stop the two CRITICALs

Both are wiring defects, both are small, and both are currently invisible to a
green suite. **Nothing else in this plan matters more, and nothing else should
start first.**

### A-1. The unreachable quality gate — CRITICAL

`api/execution/pipeline.py:479-520` sits after a `try` whose body (`break` @396)
and both handlers (`break` @428, `break` @478) all terminate, so it never runs.
It contains the entire per-phase quality gate.

**Pattern: none.** This is a dedent. Resist refactoring while fixing it — the
surrounding method is 690 lines and Phase B deletes it.

Order of operations, non-negotiable:

1. Write a test that **fails on the current tree**: a phase whose
   `phase_monitor.evaluate` returns `passed=False` with budget remaining must
   produce a second attempt and emit `phase_retry`. If it passes before the fix,
   it is testing something else.
2. Move `:479-520` inside the `try`, replacing the bare `break` at `:396`.
   Preserve the handlers' existing `break`.
3. Add a **repo-wide fitness function** for the defect class: flag any statement
   following a `try` whose every branch — body plus all handlers — terminates in
   `break`/`continue`/`return`/`raise`. Put it in `tests/architecture/` beside
   the existing AST guards.

Why (3) and not just (1): coverage cannot see this. The enclosing loop *is*
exercised, so line coverage of the loop looks healthy while eleven statements
inside it are unreachable. This defect class needs a structural check, not a
behavioural one.

**Fitness function:** the new AST guard, plus the failing-first test.

### A-2. `WorkflowRunner` has never run — CRITICAL

`WORKFLOW_RUNNER_ENABLED` defaults false (`core/settings.py:121-122`), and
`application/pipeline.py:507-513` records that enabling it raises `TypeError` on
the first phase because `PhaseStarted(phase_number=...)`,
`PhaseFailed(is_fatal=...)`, `EventType.PHASE_QUALITY_CHECKED` and
`PHASE_RETRIED` do not exist.

**Pattern:** complete the **domain event** vocabulary first, then flip the flag.
Events are part of the domain language (`core/events/`), so the missing members
are a domain gap, not a runner bug.

1. Add the four missing event members to `core/events/`, with the same
   `make_event()` factory shape as their siblings.
2. Turn the flag on **in tests first** — a parametrized fixture that runs the
   existing flow tests both ways. That is the diff the source comment asks for
   ("Flip it only after diffing a full preset run both ways"), expressed as a
   test rather than as a manual ritual nobody repeats.
3. Default it on once the parametrized suite is green.

**Risk, stated plainly:** this is a behaviour change on every CLI and headless
run, not a bug fix. Retries, per-phase timeouts and the quality gate begin
executing where they never have. Expect previously-passing phases to start
retrying. That is the point, and it is also why A-2 lands before B, not during.

**Fitness function:** the parametrized both-ways suite; a test asserting the
flag's default is `true` once flipped, so nobody silently reverts it.

**Landed 2026-09-09.** The prediction above was confirmed on the first run.
The staged diff (`WORKFLOW_RUNNER_ENABLED` off vs on over the full fast lane)
produced **0 failures off, 9 on**. Triage found three distinct causes, and two
of them were product defects rather than test noise:

1. *Mock fidelity.* `test_e2e_budget_presets_mock.py`'s shared payload
   documents itself as "a superset of what any phase parser looks for" and had
   neither `scores` nor `stress_tests`. Nothing noticed because the gate never
   ran. Fixed by making the payload true to its own docstring.
2. **The gate contradicted the phases' own skip contracts.**
   `run_critique_phase` returns early on "No candidates to critique"
   (`perspective_phases.py:243`) and `run_stress_test_phase` on "No top
   candidates to stress test" (`:297`), while `_check_critique` /
   `_check_stress_testing` scored the resulting empty state as a failure. Every
   research-shaped flow — no Perspectives phase in front of the critique — hit
   its retry budget and ended with no synthesis. Fixed in
   `quality/criteria.py`; `tests/unit/test_phase_quality.py` pins both.
3. **`scores` means two different shapes in two flows.**
   `perspective_phases.run_critique_phase` reads it as a *list* of
   per-perspective objects; `iterative_critique_phases.run_critic_phase` reads
   it as an *object* of dimensions, and the read sits outside the try/except
   that exists to turn a malformed critic response into a REVISE round. A model
   returning the first shape crashed the phase with `AttributeError: 'list'
   object has no attribute 'get'`. Fixed defensively with a WARNING;
   `tests/test_iterative_critique_score_shapes.py` pins it. **The name
   collision itself is unresolved** — a candidate for Phase C, where the answer
   is a typed critic response rather than a shared dict key.

Worth naming: (2) and (3) were both invisible for as long as the gate was off.
Neither is caused by turning it on; turning it on is what made them observable.

### A-3. The quality gate's LLM judge has never run — new, found by A-2

Not in the audit; found by turning the gate on. `quality/monitor.py:218` calls
`self._router.complete(model_id=..., messages=..., system=...)`. `ProviderRouter`
has **no** `complete` method — the API is `call(role, system_prompt,
user_prompt, ...)`. Every judge invocation raises `AttributeError`, is caught at
`monitor.py:176-177`, and returns the rule result:

> `LLM judge failed for phase 'Critique & Pruning': 'ProviderRouter' object has
> no attribute 'complete' — using rule result`

So `QUALITY_JUDGE_MODELS` and `QUALITY_JUDGE_THRESHOLDS` (`constants_limits.py`,
budget vs premium) select a judge that is never consulted, and the gate is
rules-only on both paths. It is logged at WARNING, so it is not a silent failure
by the ratchet's definition — but nothing was reading the log, because until
A-1 and A-2 the gate never ran at all.

**Deliberately not fixed inside A-2.** Repairing the call turns on *another*
never-executed path, one that can overturn a rule failure and let a phase pass.
That needs its own failing-first test and its own both-ways diff, exactly like
A-2. Treat the WARNING as expected noise until A-3 lands.

1. A test that fails today: a phase whose rule check fails and whose judge
   would pass it must come back passed.
2. Route through `ProviderRouter.call` with the judge role, or give the router
   the `complete` the monitor was written against — decide which is the real
   contract rather than adapting whichever is easier to type.
3. Assert the tier split actually reaches the provider: budget and premium
   presets must send different judge models.

**Fitness function:** a test asserting no `PhaseMonitor.evaluate` call logs the
fallback warning during a full mocked run.

---

## Phase B — One execution engine

**Closes:** the `api/execution/pipeline.py` god-method; the duplicate-engine
CRITICAL row; `docs/architecture_audit_remediation_plan.md` FIX-1.

Startable only after A-2. Deleting the engine that works in favour of one that
has never run, before proving the latter, would be reckless.

- **B-1.** Delete the phase loop at `api/execution/pipeline.py:293-560` and route
  the SSE path through `WorkflowRunner`. The SSE-specific concerns — `sse_emit`,
  `_tracked_broadcast`, the `errors_before_phase` watermark — become an
  **Observer** on the runner's existing `PHASE_*` events, not a second loop.
- **B-2.** Decompose what remains of `execute_run` by extracting preflight, the
  emit adapter and postflight into collaborators. Target: no method over 60
  lines in `api/`.
- **B-3.** Delete the ~40 back-compat delegators at
  `application/pipeline.py:220-366` once B-1 removes their last caller — or keep
  them behind the deprecation-shim convention `src/reasoner/pipeline.py` already
  uses. Decide once; do not leave both conventions in the tree.

**Fitness function:** a test asserting exactly one code path constructs
`PhaseStep`s and iterates them — e.g. `WorkflowRunner.run_phase` is the only
symbol that calls `step.fn`. Plus the existing god-file line thresholds in
`test_layer_boundaries.py`, lowered in the same commit.

---

## Phase C — Failure semantics: make "unknown" a value the caller must handle

**Closes:** the router's success-shaped terminal failure; generalizes
`docs/plans/audit-remediation-2026-09-08.md` R2a/R2b/R2c.

**Paradigm: Result/Either.** The P5 plan already named the third state — *signal
and proceed on the value you just admitted was wrong.* Four independent
instances have now been found, three in that audit and one here. Four instances
of one shape is a missing type, not four mistakes.

- **C-1.** Define `Ok[T]` / `Degraded[T]` in `core/` — a minimal sum type, not a
  library. `degraded()` already logs at WARNING, increments
  `reasoner_degradation_total` and appends to `PipelineState.degradations`; it
  gains a sibling that **returns a value the caller must unwrap**.
- **C-2.** `router.py:585-588,598-601,621-624,634-637` — total fallback
  exhaustion currently returns `(DegradedLLMResponse(text=""), {})`. Return the
  `Degraded` variant instead, so `extract_json("")` stops being how a provider
  outage is discovered.
- **C-3.** Execute R2a/R2b/R2c from the P5 plan **against the new type** rather
  than as three bespoke fixes: `_required_tier` fails closed; pricing and
  routing fall back to `settings.SPEND_CAP_PER_RUN_USD` per the existing
  `executor.py:739` precedent; benchmark suites gain `failed_count` rather than
  redefining `sample_count`, whose second consumer is the budget line at
  `runner.py:124`.
- **C-4.** Reconcile the four retry layers — provider `max_retries=2`, router
  fallback-only, phase budget 1 with a fixed 1s sleep, executor one-shot — into
  one declared policy object, and either use `DEFAULT_MAX_RETRIES` or delete it,
  since it currently matches none of them. Add jitter to the phase layer:
  `flows/runner.py:161`'s fixed 1s sleep synchronizes retries across concurrent
  runs.
- **C-5.** `base.py:248` — `isinstance(exc, ProviderError)` short-circuits before
  `.retryable` is consulted, so `RateLimitError.retryable = True` never fires.
  The in-code comment defers this; undefer it here.
- **C-6.** `container_sandbox.py:122-134` indexes 9 keys off `response.json()`
  with no schema check, so a malformed worker reply raises `KeyError` —
  contradicting `core/ports/code_executor.py:80-82` ("MUST NOT raise on
  execution failure"). Validate the payload and return the port's failure value.

**Fitness function:** the AST silent-failure ratchet (`--max 105`) drops with
each conversion; a test asserting `ProviderRouter` never returns an
empty-`text` success; a test that a malformed sandbox payload returns rather
than raises.

---

## Phase D — One architecture, enforced

**Closes:** the three-ledger contradiction; the 59 `application → infrastructure`
imports; the `application → api` private-attribute reach.

**The decision, made explicitly:** adopt **N-tier for the outer ring and strict
hexagonal for the inner ring.** Concretely — `domain/` and `core/` are a
dependency-free functional core; `application/` may depend on `core/ports` but
**not** on `infrastructure/` concretes; `infrastructure/` and `api/` are
adapters.

Rationale for not chasing full hexagonal everywhere: the ports that matter
already exist — `LLMPort`, `SearchServicePort`, `MemoryPort`,
`ModelRegistryPort`, `SharedCachePort`, `DistributedStatePort` — and the 59
violations are overwhelmingly *not using ports that are already built*, rather
than *missing abstractions*. This is wiring, per the thesis.

- **D-1.** The 9 `application/flows/*.py → infrastructure.search.discovery`
  module-level imports go through `SearchServicePort`. One mechanical change,
  the largest single reduction.
- **D-2.** The `ProviderRouter` imports at `application/pipeline.py:47-48`,
  `orchestrator.py:30`, `services/pipeline_service.py:9`,
  `services/preset_service.py:10` and `services/gate_service.py:26` become
  `LLMPort`. That port has 2 importers against 26 for the concrete class; this
  is what "port adoption" actually means in this codebase.
- **D-3.** `application/handlers/handlers.py:318-319` reaches
  `api._run_store.request_cancel` — application calling a **private** attribute
  of the outermost layer. Introduce `RunCancellationPort` in
  `application/ports/`; the `infrastructure → application.ports` direction is
  already the sanctioned adapter shape (`.importlinter:16-24`).
- **D-4.** Delete the four confirmed-dead `.importlinter` entries — `:66`
  (`data_eraser → api.cache`, no such import exists), `:90` and `:100` (both
  `TYPE_CHECKING`-only, redundant under `:3`), and the `:29`/`:56` duplicate —
  and lower `count_importlinter_exceptions.py --max` by four in the same change.
  **Do not** change the alerting level; see §0.
- **D-5.** Add `phases`, `neuro`, `healing`, `documents` and `utils` to
  `.importlinter`'s `layers`. They are currently ungoverned, which is why
  `neuro/server.py:587 → api.dependencies` violates nothing.
- **D-6.** `core/search.py:37-40` uses `importlib.import_module` with a string
  literal, dodging static analysis. Phase G deletes the module; if it survives,
  the import becomes a real one with a real exception entry.
- **D-7.** Make `CLAUDE.md:19` and `tests/architecture/test_layer_boundaries.py`
  state the D decision verbatim. Three ledgers become one rule with three
  enforcement points.

**Fitness function:** the `application → infrastructure` count becomes its own
tracked number in the two-way import ratchet, so it can only fall.

---

## Phase E — Composition root; kill the service locator

**Closes:** the 100-importer settings singleton; five module-global DI slots; the
temporal coupling that silently no-ops the API-key preflight.

**Pattern: Composition Root.** One place constructs the object graph; everything
else receives what it needs.

- **E-1.** Build `src/reasoner/composition.py` — a single function returning a
  fully-wired container. The four entry points (`asgi.py`, `main.py`,
  `headless.py`, `mcp_server.py`) call it and nothing else. Today they wire
  *different subsets*: MCP calls **no** port setters at all, and CLI and
  headless both skip `set_build_provider`.
- **E-2.** `Settings` becomes constructor-injected from the composition root.
  Migrate the 100 import sites incrementally by leaving `settings` as a
  deprecated module-level alias the root populates — the same shim convention
  already used for `reasoner.pipeline`.
- **E-3.** `domain/preset_core.py:311-317` — the unset-registry case currently
  `return []`, which makes `check_keys()`/`missing_keys()` report nothing
  missing **for every preset**. Fail loud. Its docstring says this bug already
  shipped once; the fix is to make it inexpressible, not to remember harder.
- **E-4.** `domain/pricing.py:43-47,86,95` — the import-time filesystem load
  moves behind a `PricingRepository` port, injected. `import domain.pricing`
  stops being a disk operation and `domain/` stops needing a filesystem to test.
- **E-5.** `domain/preset_core.py:343` — the `os.environ` read leaves `domain/`.
- **E-6.** Remove the 26 secret-shaped env reads outside `settings.py`, or
  correct `settings.py:4-5`, which claims to be "the ONLY module in the project
  that reads from the process environment" and is `[FALSE]`. The concrete
  hazard: `settings.py:70` freezes `OPENROUTER_API_KEY` at import while
  `infrastructure/llm/registry.py:586,596` read it live.

**Fitness function:** an AST guard failing on `os.getenv`/`os.environ` outside
`core/settings.py`, with a ratcheted exception list —
`scripts/check_no_registry_bypass.py` is the working template. Plus a test that
constructing a `PipelinePreset` before injection raises.

---

## Phase F — Scale: make the orchestrator genuinely stateless

**Closes:** the per-worker billing ceiling; run lifetime coupled to the HTTP
connection; every process-local structure in the audit's Phase 3.

This is the rubric's *scalable* and the largest phase. It also has a real
switching trigger: **if the deployment stays single-worker, F-2 onward is
optional.** F-1 is not.

- **F-1.** `infrastructure/llm/spend_tracker.py` — back `_SPEND` with the
  existing `DistributedStatePort` (Valkey `INCRBYFLOAT` on
  `spend:{subject}:{period}`), exactly as the module's own docstring prescribes.
  **Do this even if you never scale**, because a restart currently forgives the
  month.
- **F-2.** Hoist the per-model bulkhead. `_PER_MODEL_SEMAPHORES`
  (`router.py:225`) is per process, so N workers means `limit × N` real provider
  concurrency. Either move the counter to Valkey or accept it — but **document
  the decision either way**, because an undocumented per-process limit reads as
  a global one.
- **F-3.** Move run execution behind a queue.
  `infrastructure/documents/index_queue.py` is already in-tree as the
  bounded-worker model; it was introduced for exactly this reason, to replace
  uncapped per-upload `create_task`. The event store already exists for
  durability.
- **F-4.** Adopt `asyncio.TaskGroup` for the unbounded LLM fan-outs —
  perspectives, jury, Delphi, debate, the five subagent hyper-agents and
  HyperGate's five. Zero exist today. Structured concurrency turns "one
  generator failed" into a handled outcome rather than a silently absent
  perspective.
- **F-5.** The four blocking `read_text`/`write_text` calls inside `async def`
  (`deadletter_replay_service.py:51,106,167`, `subprocess_executor.py:89-96`)
  move to `asyncio.to_thread` — the same file already does this correctly on its
  write path at `:172-188`.
- **F-6.** Consolidate persistence, or make the five hard-bound SQLite stores
  switchable the way `event_store.py:846-856` already is, and build the
  `EventStorePort` the 2026-08-20 plan specified. **Sequence `usage_quotas`
  first and alone** — it has two writers taking `FOR UPDATE` locks from
  different call graphs (`quota_repo_postgres.py:60,117,127` and
  `subscription_repo.py:140,150-157`).

**Fitness function:** a two-worker integration test asserting a spend ceiling is
honoured across workers; a guard that no new module-level mutable dict enters
`api/` or `infrastructure/` without a tracked entry.

---

## Phase G — Delete

**Closes:** ~1500 lines, four zero-reference ports, five false documentation
claims. Deletion over addition: this phase raises the score by shrinking the
denominator of "patterns consistent."

- **G-1.** `security/persuasion_defense.py` — 1092 lines, 4 Protocols, 1 ABC, 5
  stage classes, zero production call sites, and a docstring naming an insertion
  point (`ClaimExtractionStage` / `TwoTierVerificationStage`) whose classes do
  not exist anywhere in `src/`. Delete with its shim and its test.
- **G-2.** `application/services/feedback_router.py` — zero callers in `src/`,
  `tests/` or `scripts/`, while three docs and two skill maps describe it as
  shipped. Delete, and correct the five documents.
- **G-3.** `core/search.py:20-29` — the `_BUILD_PROVIDER` seam is inert:
  `_get_build_provider()` has zero callers and
  `infrastructure/search/discovery.py:36` defines its own. Confirmed verbatim by
  `tests/test_decompose_json_guard.py:23-27`. Delete the seam and the
  `api/__init__.py:206` call.
- **G-4.** `api/dependencies.py:708 check_preset_access` — decide. Either wire it
  as a `Depends(...)` (Phase C-3 supplies the tier logic) or delete it and every
  reference. It currently has zero callers while a source comment and
  `docs/plans/audit-remediation-2026-09-08.md:228` both cite it as the primary
  entitlement gate.
- **G-5.** Delete `circuit_breaker_port.py`, `telemetry_port.py` (duplicated by
  `application/ports/service_protocols.py:85`, which is the one actually used)
  and `crypto_port.py`. Type the three `capability_registry` consumers against
  `CapabilityRegistryPort` instead of `Any` — or delete that port too.
- **G-6.** `infrastructure/execution/subprocess_executor.py` — the 2026-08-20
  plan's item 1.5, still undone. Its `health_check` is designed to always return
  `False` so it can never be the approved path; a component that exists never to
  be selected is dead weight with a maintenance cost.

**Fitness function:** a dead-code gate — `vulture` or an AST reachability pass
over `src/`, ratcheted, so the next zero-caller module is caught at the commit
that adds it.

---

## Phase H — Observability and testability floors

**Closes:** the rubric's *observable* and *testable*.

- **H-1.** Reconcile the coverage numbers. The local gate is **30%**
  (`ci-local.sh:89`), `CLAUDE.md` §7 says the self-healing CI gates at **60%
  fail / 80% warn**, and the README badge is a static shield. The per-package
  floors (`domain:85`, `core:75`) are the honest ones; extend them per package
  rather than raising a global number that lets old covered code hide new
  uncovered code.
- **H-2.** `state._current_phase_key` is a private attribute set by two runners
  and read by the executor for cost attribution
  (`executor.py:520-523,834-847`). After Phase B there is one runner; promote it
  to a declared, typed field.
- **H-3.** Instrument the degradation contract end to end: every `degraded()`
  site's `site` label should appear on a dashboard, and Phase C's `Degraded`
  type should carry the same label. Degradation you cannot see is the original
  P5 finding restated.
- **H-4.** `application/flows/factory.py:67` — an unknown method silently
  resolves to `MultiPerspectiveFlow`, so a typo'd method produces a plausible
  run. Raise, or emit a degradation. Same defect family as Phase C, and one
  line.
- **H-5.** `neuro/server.py:245-261` — `require_neuro_key` allows all traffic
  when the key is unset. Fail closed in production, consistent with
  `settings.py:551-560`'s existing import-time guards.
- **H-6.** Resolve the Python version drift: `Dockerfile:2` and CI pin **3.14**
  while `pyproject.toml:9,30` declare **3.12** for mypy. The type checker is
  modelling a different runtime than production.

---

## Scoring ledger, mapped to the rubric's five words

| Phase | Closes | Rubric property it buys |
|---|---|---|
| A | 2 CRITICAL | Clears "no critical violations" — the hard gate below 8 |
| B | 1 HIGH (god-method) + duplicate engine | *patterns consistent* |
| C | 2 HIGH (router terminal failure, spend guard) + 4 MEDIUM | *patterns consistent*, and the failure half of *observable* |
| D | 2 HIGH (59 app→infra, app→api private) + 3 MEDIUM | ***all layers correctly separated*** |
| E | 1 HIGH (service locator) + temporal coupling + domain leaks | *all layers correctly separated*, *testable* |
| F | 2 HIGH (per-worker billing, request-coupled runs) | ***scalable*** |
| G | 1 MEDIUM + ~1500 dead lines | *patterns consistent* |
| H | — | ***observable***, ***testable*** |

**A through F close both CRITICALs and all six HIGHs.** G and H are what
separate 8 from >9: the rubric's top band names properties, and *observable*,
*testable* and *consistent* are not achieved by closing severities.

---

## Sequencing

```
A-1 ──┐                                    (LANDED 0a305b7)
A-2 ──┴──► B ──► H-2                       (B needs A-2 proven, not merely landed)
A-3 ──┘                                    (found by A-2; gate is rules-only until it lands)
   │
   ├────► C ──► C-3 defers to the P5 plan's R2/R3
   │       └──► H-3
   │
   ├────► D ──► D-7 (docs last, after the rule is enforced)
   │       └──► E                          (E's composition root needs D's port adoption)
   │
   ├────► G                                (independent; safest parallel filler)
   │
   └────► F-1                              (independent; revenue path; do early)
           └──► F-2..F-6                   (gated on the multi-worker decision)
```

**Critical path:** A → B → D → E. C, G and F-1 are genuinely parallel, and F-1
should not wait for anything.

**Do not parallelize A-1 with B.** A-1 is a dedent inside a method B deletes;
doing both at once makes the diff unreviewable and loses the failing-first test.

---

## What could go wrong

- **A-2 is a behaviour change, not a fix.** Turning on retries, timeouts and the
  quality gate for the first time will change output on runs that currently pass
  silently. Budget for triage, not just implementation.
- **B replaces the production path.** The engine being deleted is the one that
  works; the one replacing it has never run. If A-2's parametrized suite does
  not genuinely cover the flows, B ships an outage.
- **E-2 touches 100 files.** Shim-then-migrate, never one commit. The ruff
  ratchet is exact-equality and a 100-file change will move it.
- **F-6's `usage_quotas` has two writers with different lock orders.** That is a
  deadlock waiting for concurrency; consolidating the schema without sequencing
  that table first will find it in production.
- **G-4 is a policy decision, not an engineering one.** Whether every tier may
  reach every preset is a product question. Do not let a cleanup phase settle it
  by deletion — ask.

---

## Explicitly out of scope

- **Rebuilding code-execution isolation.** It exists, is container-based,
  health-gated per call and production-enforced. G-6 deletes the legacy adapter;
  nothing else changes.
- **Refactoring `neuro/`.** Best-defended subsystem here. D-5 governs it, H-5
  closes one gap, no structural change.
- **Migrating off SQLite entirely.** Local and CLI use stays SQLite; F-6 is about
  the port and the five hard-bound stores, not the engine.
- **Re-litigating `.importlinter`'s alerting level.** See §0.
- **A second implementation for any single-implementation port.** G-5 deletes the
  speculative ones; the remaining singles (`LLMPort`, `MemoryPort`,
  `ModelRegistryPort`, `FileSearchPort`) are real seams and stay.

---

## Switching triggers

- **Deployment stays single-worker** → F-2 through F-6 drop to backlog. F-1 does
  not, because a restart currently forgives the month.
- **A second backend replica appears** → F becomes the critical path, ahead of D.
- **`--resume` compatibility with old state files is dropped** → E and H-2
  simplify sharply; `PipelineState`'s `dict[str, Any]` convention exists largely
  to serve it.
- **Hosted CI billing is restored and the repo can require checks** → every
  fitness function here moves from advisory to blocking, and the `.githooks/`
  opt-in defaults (`pre-commit:18`, `pre-push:19`) should be reconsidered.
- **Anyone proposes a third phase-execution path** → stop and re-read Phase B.
  That is how the current CRITICAL was created.
