# Code-as-Agent-Harness — Reasoner Enhancement Plan

> **Source:** Ning et al., *Code as Agent Harness: Toward Executable, Verifiable, and Stateful Agent Systems* (arXiv:2605.18747, May 2026).
> **Status:** DRAFT / not started. **Owner:** TBD. **Created:** 2026-06-15.
> **Scope:** Seven enhancements (Tier 1–3) that close the gap between Reasoner's current *LLM-judged* reasoning and the paper's *executable, inspectable, stateful, governed* harness model.

---

## 0. Guiding thesis & the core mismatch

The paper's central claim: **code is special because it is executable** — so verification should rest on *deterministic sensors* (compilers, tests, linters, type checkers, runtimes), and LLM critique should **interpret** those sensors rather than replace them (§3.4.4, §5.2.2). A harness that scores correctness by *asking another model* suffers an **oracle-adequacy gap** (§5.2.1): it labels work `VERIFIED` on self-report, not on a check that ran.

Reasoner exhibits this gap pervasively. Every verification surface — Phase 3 critique, Phase 4 stress test, CoVE verify, Scientific falsification, the new VS `review_hypotheses` — is **LLM-judged natural language**. Most starkly, **PoT does not execute code at all**:

```python
# src/reasoner/phases/pot.py:26
POT_EXECUTE_SYSTEM = (
    "You are a code execution engine. Simulate or describe the execution of the given Python code. "
    "If actual execution is unavailable, trace through the code logically and produce the output. ..."
)
# src/reasoner/application/flows/cognitive_phases.py:262  → run_pot_execute_phase calls role="pot_execute" (an LLM)
```

The four properties the paper says future systems need — **executable, inspectable, stateful, governed** (§5.2.7) — become this plan's design axes.

### What Reasoner already has (leverage, not greenfield)

| Capability | Where | Reused by |
|---|---|---|
| Event-sourced replay | `core/aggregates/pipeline.py` (`PipelineAggregate`) | Evolution Agent (#4) |
| Per-phase telemetry (cost, duration, retries, quality, fallback) | `infrastructure/persistence/telemetry_store.py` | Scorecard (#2), Evolution Agent (#4) |
| Self-healing loop scaffolding | `healing/` (`run_healing`, `introspection_engine`, `telemetry_exporter`) | Evolution Agent (#4) |
| Declarative routing surface | `domain/preset_registry.py`, `infrastructure/llm/router.py`, `core/constants_limits.py` | Evolution Agent mutation targets (#4) |
| Epistemic labels | `domain/models.py` (`ClaimLabel`: VERIFIED/HYPOTHESIS/UNKNOWN) | Evidence bundles (#3) |
| Interpret-after-execute split | `run_pot_interpret_phase` (`cognitive_phases.py:283`) | Executable verification (#1) |
| Tiered prompts + tolerant parsing | VS critique work (this session) | All |

---

## 1. Architectural principles this plan must respect

These are derived from `CLAUDE.md` and the existing codebase. **Every task below is checked against this list.**

1. **Dependency rule (hexagonal DDD):** `Domain ← Application ← Infrastructure ← API`. Domain has no outward imports. New side-effecting capabilities (code execution) enter as a **Core port** + **Infrastructure adapter**, never as a direct import from a phase/flow.
2. **CQRS:** reads (Scorecard) are **Queries**; state-changing proposals (harness mutation) are **Commands**, routed through `application/handlers/` + the mediator — not ad-hoc calls.
3. **Event sourcing:** new observable facts (a code execution, a harness mutation proposal/promotion) are **domain events** via `core/events/` `make_event()`, applied by aggregates.
4. **State invariants:** method-specific state is `dict[str, Any]` with `field(default_factory=dict)`, accessed via `.get()`; typed lists follow the `CritiqueScore`/`ReviewHypothesis` precedent with all-default dataclasses + `_from_dict` reconstruction so `--resume` on older state never crashes.
5. **No magic numbers:** all thresholds/budgets live in `core/constants_limits.py` or a dedicated `*_constants.py` (the `vs_constants.py` pattern).
6. **Parsing discipline:** all LLM output through `parsing.extract_json()` + tolerant `_parse_*` helpers; never raw `json.loads`; never empty a whole collection on one malformed item.
7. **Security:** `sanitize_for_prompt()` gates user text; **executed code is hostile by default** → sandbox with resource limits, no network, no host FS, allowlist imports; permission tiers + HITL for anything irreversible.
8. **Tiering & flags:** new cost is **opt-in** (premium tier via `get_preset_price_tier`, or an explicit feature flag) so budget runs stay byte-identical — the pattern established by the VS critique work.
9. **Living docs:** update `ARCHITECTURE_MINDMAP.md` counters and `AGENTS.md` when methods/ports/presets are added.

---

## 2. Enhancement catalogue

Each enhancement: **Goal · Paper grounding · Current state · Target design · Data model · Integration · Governance/Safety · Testing · Risks · Effort.**

---

### TIER 1 — high leverage, grounded in existing structure

---

### #1 — Executable verification for PoT & Coding (deterministic sensors)

**Goal.** Replace simulated execution with a real sandboxed runtime whose compile/run/test output is the verification signal. The LLM moves to *interpreter of sensor output* (already its role in `run_pot_interpret_phase`).

**Paper grounding.** §2.1.3 (iterative code-grounded reasoning), §3.4.3 (sandboxed execution), §3.4.4 (verification through deterministic sensors), §5.2.2 (semantic verification beyond a single pass/fail).

**Current state.** `run_pot_execute_phase` (`cognitive_phases.py:262`) asks an LLM to fake execution; `POT_EXECUTE_SYSTEM`/`pot_execute_prompt` (`phases/pot.py:26`) explicitly permit "trace through logically." `state.pot_state["execution_success"]` gates interpretation but is model-asserted.

**Target design (port + adapter, dependency-rule clean):**

- **Core port** — `core/ports/code_executor.py`:
  ```python
  class ExecutionResult(BaseModel):
      success: bool
      stdout: str
      stderr: str
      exit_code: int
      timed_out: bool
      duration_ms: int
      truncated: bool          # output clipped to EXEC_MAX_OUTPUT_BYTES

  class CodeExecutorPort(Protocol):
      async def execute(self, code: str, *, language: str = "python",
                        stdin: str = "", limits: ExecutionLimits) -> ExecutionResult: ...
  ```
- **Infrastructure adapters** — `infrastructure/execution/`:
  - `subprocess_executor.py` — default. `python -I -S` in a tempdir, **no network** (deny via subprocess env / no sockets), CPU+wall timeout, memory cap (`resource` on POSIX; Job Objects/`psutil` fallback on Windows — the dev platform is win32, so ship a `WindowsSandbox` path), output byte cap, import allowlist enforced by an AST pre-check (`core/code_safety.py`).
  - `noop_executor.py` — returns `success=False, stderr="execution disabled"`; used when sandbox unavailable so the pipeline degrades, never crashes.
  - (future) `docker_executor.py` / WASM — behind the same port; out of scope for v1.
- **AST guard** — `core/code_safety.py`: reject `import os/sys/socket/subprocess/ctypes`, `open(`, `__import__`, dunder escapes before execution; tiered like the Weebot bash-guard (SAFE/SUSPICIOUS/DANGEROUS/BLOCKED). BLOCKED → skip execution, record `stderr`.
- **Phase rewrite** — `run_pot_execute_phase` becomes:
  1. AST-guard the generated code.
  2. `await services.code_executor.execute(...)` (port injected on `WorkflowServices`).
  3. Write real `execution_output/_success/_error` into `pot_state`.
  4. **No LLM call** in the execute phase. Interpretation stays in `run_pot_interpret_phase` (faithful to the paper's split).
- **Coding method** — add an optional verify step that runs generated snippets/tests through the same port; feed failures back (see #5 routing).

**Data model.** `pot_state` keys already exist; add `execution_exit_code`, `execution_timed_out`, `execution_truncated`, `execution_evidence_id` (links to #3 bundle). New domain event `CodeExecuted` (`core/events/`). New constants in **`core/exec_constants.py`**: `EXEC_TIMEOUT_MS`, `EXEC_MEM_LIMIT_MB`, `EXEC_MAX_OUTPUT_BYTES`, `EXEC_IMPORT_ALLOWLIST`.

**Integration.** Inject `CodeExecutorPort` on `WorkflowServices` (DI in the pipeline composition root / `orchestrator.py`), defaulting to `SubprocessExecutor`; tests inject a fake. Gate behind feature flag `EXEC_SANDBOX_ENABLED` (default **on** for PoT since it's the whole point, but degrades to `noop` if the platform sandbox can't initialize).

**Governance/Safety.** Read-only-to-host: tempdir only, deleted after. No network. Resource caps. AST allowlist. This is Tier-1 risk (sandbox-edit) per §3.4.3 — no HITL needed because it cannot touch the host or network; full-access execution is explicitly **out of scope**.

**Testing.** `tests/unit/test_code_executor.py` (success, syntax error, timeout, infinite loop, memory blowup, blocked-import, output truncation, Windows + POSIX paths); `tests/unit/test_pot_executable.py` (phase uses port, no `pot_execute` LLM call, degraded path when executor=noop). Mark sandbox-heavy cases `@pytest.mark.slow`.

**Risks.** Windows sandboxing is weaker than POSIX → ship conservative limits + AST allowlist, document the boundary, leave Docker/WASM as the hardening path. Flaky timeouts → generous defaults, deterministic seeds.

**Effort.** L (port + 2 adapters + AST guard + phase rewrite + tests). **The flagship — do first after #2.**

---

### #2 — Harness Scorecard (harness-level metrics from existing telemetry)

**Goal.** Evaluate the *operating substrate*, not just output quality: per-preset/per-phase **trajectory efficiency, recovery ability, verification strength, cost, fallback health**. This is the diagnostic foundation the Evolution Agent (#4) consumes.

**Paper grounding.** §3.5.1 (deep telemetry as optimization substrate), §5.2.1 harness-level metrics: trajectory efficiency, verification strength, recovery ability, state consistency, safety compliance, replayability.

**Current state.** `TelemetryStore` already persists everything needed: `phase_telemetry(cost_usd, duration_ms, retries, quality_score, quality_passed, models, is_fallback)` and `run_telemetry(total_cost_usd, fallback_count, fallback_events)`. `healing/telemetry_exporter.py` already aggregates *cost + fallbacks* per preset — the Scorecard generalizes that aggregation.

**Target design (CQRS read model — no new writes):**

- **Domain value objects** — `domain/harness_metrics.py` (frozen dataclasses): `PhaseMetrics`, `PresetScorecard`, `HarnessScorecard`. Metric definitions (all computable from existing columns):
  - *trajectory efficiency* = tokens (→cost) & duration per successful run; phase-level mean/p95 `duration_ms`, `cost_usd`.
  - *recovery ability* = fraction of runs with `fallback_count>0` that still completed (join `run_telemetry` ↔ aggregate status) — "did the fallback chain actually rescue the run."
  - *verification strength* = `quality_passed` rate and `quality_score` distribution per phase.
  - *fallback health* = fallback rate per preset/role, top fallback events.
  - *replayability* = % of runs with a reconstructable event history (cross-check EventStore).
- **Query + handler (CQRS)** — `application/queries/get_harness_scorecard.py` + handler under `application/handlers/`, registered with the mediator. Pure read over `TelemetryStore` (+ optional `EventStore` join). No event emission.
- **Aggregation service** — `application/services/scorecard_service.py`: runs the SQL aggregations (extend `telemetry_store` with `get_scorecard_rows(window)` returning grouped rows; keep SQL in the store, math in the service).
- **Surfaces:**
  - CLI: `python main.py --scorecard [--preset X] [--window 7d]`.
  - API: `GET /telemetry/scorecard` (read-only, auth-scoped) in `api/routes/`.
  - Optional UI widget later (out of scope v1).

**Data model.** No schema change required for v1. Add **`core/scorecard_constants.py`**: `SCORECARD_DEFAULT_WINDOW_DAYS`, `SCORECARD_P95`, efficiency normalization caps.

**Integration.** Reuse `get_telemetry_store()`. Reuse the existing `_build_context` aggregation pattern from `telemetry_exporter.py` (refactor shared aggregation into `scorecard_service` and have the exporter call it — DRY).

**Governance/Safety.** Read-only; auth-scoped API; no PII (telemetry is preset/phase/cost only).

**Testing.** `tests/unit/test_scorecard_service.py` with a seeded in-memory SQLite telemetry DB: assert efficiency/recovery/verification computations; empty-DB → empty scorecard (no crash); window filtering. `tests/integration/test_scorecard_api.py`.

**Risks.** Low. Main care: don't double-count tokens across phase vs run tables — define the join once and test it.

**Effort.** S–M. **Do first** (prereq for #4, immediate diagnostic value, zero write-path risk).

---

### #3 — Evidence-bundled epistemic labels

**Goal.** Make `VERIFIED/HYPOTHESIS/UNKNOWN` point at the evidence that justified the label: which check ran, what it returned, what's still untested, residual risk. Strengthens Reasoner's signature feature and links #1's sensor output to the claims.

**Paper grounding.** §5.2.2 — *"make every accepted action carry an evidence bundle: the checks run, the assumptions preserved, the untested regions, the remaining risks"*; epistemically-aware feedback.

**Current state.** `ClaimLabel` exists (`domain/models.py`); labels are applied inline in prompts ("Label claims with [VERIFIED]…") and surfaced in synthesis, but carry **no provenance**. The VS `ReviewHypothesis.verification` field (this session) is the natural hook — currently descriptive, not executed.

**Target design:**

- **Domain** — `domain/core_types.py`: add `EvidenceBundle` (all-default dataclass, `--resume`-safe):
  ```python
  @dataclass
  class EvidenceBundle:
      label: str = "UNKNOWN"            # mirrors ClaimLabel
      checks_run: list[str] = field(default_factory=list)     # e.g. "executed: exit 0", "pytest: 12 passed"
      evidence_refs: list[str] = field(default_factory=list)  # execution_evidence_id, source ids
      untested: str = ""
      residual_risk: str = ""
      source: str = "model"            # "model" | "sensor" | "search"
  ```
  Attach `evidence: EvidenceBundle | None` to `FinalSolution` claims and (optionally) to `ReviewHypothesis`.
- **Promotion rule** — `application/services/evidence_service.py`: a claim may be `VERIFIED` with `source="sensor"` **only if** a deterministic check (from #1, search grounding, or a test) backs it; otherwise it is capped at `HYPOTHESIS`. This operationalizes "a label is a claim about evidence, not confidence."
- **Synthesis wiring** — synthesis phase emits bundles; renderer (`application/services/renderers/`) displays "Verified by: pytest 12/12; untested: concurrency."
- **Parser** — `_parse_evidence_bundle` in `core/parsing.py` (tolerant, mirrors `_parse_review_hypotheses`).

**Data model.** `EvidenceBundle` added to `FinalSolution`; `_from_dict` reconstruction + `to_dict` round-trip; constants for label-capping policy in `core/constants_limits.py`.

**Integration.** Hook #1's `execution_evidence_id` into `evidence_refs`. Premium tier gets full bundles; budget keeps inline labels (tiered, byte-identical budget path).

**Governance/Safety.** Pure data enrichment; no new side effects.

**Testing.** `tests/unit/test_evidence_bundle.py`: VERIFIED requires sensor evidence; round-trip; tolerant parse; synthesis renders provenance.

**Effort.** M. Pairs naturally after #1 (it consumes #1's evidence ids).

---

### TIER 2 — ambitious, uniquely well-positioned

---

### #4 — Evolution Agent + Governed Harness Mutation

**Goal.** A meta-level loop that uses the Scorecard (#2) to diagnose where the *harness* (presets, routing, fallback chains, token budgets, HyperGate thresholds, prompts) wastes budget or mis-routes, proposes a **change-contract**, replays it against held-out problems, and **promotes only regression-free, governed** improvements. Self-healing today fixes *code*; this fixes the *substrate* (§3.5.2).

**Paper grounding.** §3.5 (Agentic Harness Engineering), §3.5.2 (Evolution Agent: observe→diagnose→propose→evaluate→promote), §3.5.3 (governed mutation — *"a harness mutation should be treated like a code change to a safety-critical runtime"*), §5.2.3 (self-evolving harnesses without regression).

**Current state.** `healing/run_healing.py` + `introspection_engine.py` + `telemetry_exporter.py` already form an observe→diagnose loop over telemetry; mutation targets (`preset_registry.py`, `router.py`, `constants_limits.py`) are declarative; `PipelineAggregate` gives replay. **The two hard prerequisites most systems lack — event-sourced replay and a declarative routing surface — already exist.**

**Target design (five governed stages, paper-faithful):**

1. **Observe** — consume `HarnessScorecard` (#2) over a window.
2. **Diagnose** — `healing/harness_diagnosis.py`: rank harness components by waste/failure (high fallback role, low quality phase, cost-heavy stage with no quality lift). Reuse/extend `introspection_engine`.
3. **Propose** — emit a **`HarnessMutation` change-contract** (domain object), NOT a free edit:
   ```python
   @dataclass(frozen=True)
   class HarnessMutation:
       target: str            # "preset:debate-budget.scoring" | "router.fallback:scoring" | "constants:PHASE_TOKEN_BUDGET"
       component: str         # preset | routing | budget | threshold | prompt
       failure_mode: str      # what it targets
       predicted_effect: str  # measurable hypothesis
       invariant_preserved: str  # e.g. "scoring stays cross-lab"
       rollback: str          # how to revert
       risk_tier: str         # "safe" | "cost" | "safety"
   ```
   Proposals are **diffs against declarative config**, applied to a *candidate* preset registry snapshot — never to live globals.
4. **Evaluate** — replay the candidate harness against a **held-out problem set** (`benchmarks/harness_eval_set.json`) in a sandboxed config; compute the Scorecard delta; require a **regression gate**: no solved-case regressions, improvement on the targeted metric, cost/safety not worse.
5. **Promote** — only regression-free wins, written as an **auditable** registry patch (PR-style artifact under `audit/harness_mutations/`), behind governance:
   - `risk_tier=safe` (e.g. token-budget trim that preserves quality) → auto-eligible.
   - `risk_tier∈{cost,safety}` (routing changes touching model spend or cross-lab diversity) → **HITL approval required** before activation.

**Data model.** Domain events `HarnessMutationProposed`, `HarnessMutationEvaluated`, `HarnessMutationPromoted` (`core/events/`). CQRS: `ProposeHarnessMutationCommand` + handler; `GetHarnessMutationsQuery`. Constants in **`core/evolution_constants.py`**: regression tolerance, min-improvement delta, held-out set size, max mutations/run.

**Integration.** New `healing/evolution_agent.py` orchestrates the five stages; invoked by an extended `run_healing.py` (CI cron) — **never inline in a user request**. Mutations target the declarative surfaces only; the router/registry gain a "load candidate snapshot" path for sandboxed replay (no change to live-run behavior until promotion).

**Governance/Safety (non-negotiable, per §3.5.3 & §5.2.5).** Every mutation: sandboxed eval, regression suite, auditable rationale, rollback. Permission/cost/safety-boundary changes require HITL. Mutations are subject to the same Plan-Execute-Verify discipline as task code. Hard invariant guard: a mutation may **not** reduce Phase-2 cross-lab diversity below preset minima or remove a fallback chain's cross-lab terminal.

**Testing.** `tests/unit/test_harness_mutation_contract.py` (contract validation, invariant guard rejects diversity-collapsing routing); `tests/unit/test_evolution_regression_gate.py` (a mutation that regresses a held-out case is rejected); `tests/integration/test_evolution_replay.py` (replay produces a Scorecard delta). All Evolution runs gated `@pytest.mark.slow`/`integration`.

**Risks.** Overfitting to the held-out set, hidden cost/safety regressions, runaway mutation. Mitigations: small bounded mutations/run, HITL on cost/safety tiers, invariant guard, audit trail, "change only when justified" (reject zero-or-negative-delta proposals).

**Effort.** XL. Sequence after #2 (required) and ideally #1/#3 (richer signals). Land in sub-phases: contract+guard → diagnosis → sandboxed replay → governance/promotion.

---

### #5 — Planning as Contract Formation (Coding method)

**Goal.** Turn decomposition from a reasoning trace into an **inspectable contract**: files/targets, invariants that must hold, validation commands, rollback points, risky operations, read/write sets. Later phases (and #1's executor) check against it. Also defines **typed feedback routing**.

**Paper grounding.** §3.4.2 (planning as contract formation), §5.2.2 feedback routing: *compiler errors → local syntax repair; test failures → behavioral diagnosis; coverage gaps → test generation; inconsistent reviews → arbitration.*

**Current state.** `Decomposition` (`core_types.py`) has `sub_problems`, `assumptions`, `failure_modes` — no validation commands/invariants/rollback. Coding flow (`flows/coding.py`, `phases/coding.py`) decomposes then generates without a checkable contract.

**Target design:**
- **Domain** — extend the coding decomposition schema (method-state dict, `.get()`-safe) with `contract`: `{targets[], invariants[], validation_commands[], rollback_points[], risky_ops[], read_set[], write_set[]}`. Optionally a typed `PlanContract` dataclass (all-default).
- **Verification binding** — `validation_commands` are executed via #1's `CodeExecutorPort`; results feed #3 evidence bundles.
- **Feedback router** — `application/services/feedback_router.py`: classify a failure (compile/test/coverage/review-conflict) → route to the matching repair path (local fix / behavioral re-decomposition / test-gen / arbitration). This generalizes the VS Phase-4 handoff already shipped.

**Data model.** Contract lives in coding method-state; constants for max validation commands, risky-op keywords in `core/constants_limits.py`.

**Testing.** `tests/unit/test_plan_contract.py` (schema tolerant-parse, contract drives validation); `tests/unit/test_feedback_router.py` (each failure type routes correctly).

**Effort.** M. Best after #1 (validation commands need a real executor).

---

### TIER 3 — situational (activate when code actually executes / scales)

---

### #6 — Permission tiers + HITL as durable harness state

**Goal.** A multi-tier permission model (read-only / sandbox-edit / full-access) with human-approval gates for irreversible or externally-consequential actions; HITL decisions stored as **durable harness state**, not one-off prompt interrupts.

**Paper grounding.** §3.4.3 (permissioned state transition), §5.2.5 (HITL safety & accountability as harness state — *"each approval/rejection should update permission rules, escalation policy, verification criteria"*).

**Current state.** Auth scopes (`api/auth_deps.py`), sanitization, circuit breaker exist. Code execution (#1) is sandbox-edit tier and self-contained. There is **no** full-access action surface yet → this is **pre-emptive design**, activated only if/when Reasoner gains tools that touch network/host/external services.

**Target design (when triggered):**
- **Domain** — `PermissionTier` enum + `ActionRequest{action, tier, args, sensitivity}`; `core/ports/permission_gateway.py` classifying actions by tier *and* arguments/context (the paper stresses context-sensitivity: same command safe in sandbox, risky in prod).
- **HITL state** — approvals/denials persisted as domain events (`ActionApproved/Denied`) and replayed into a durable policy that future runs read (not re-prompted).
- **Gateway** — `infrastructure/security/permission_gateway.py`; full-access tier → suspend autonomy, emit approval request, record auditable transition (who/what/evidence/risk).

**Effort.** M–L. **Deferred** until a full-access action exists; documented now so #1/#4 don't bake in unsafe assumptions.

---

### #7 — Transactional shared state for parallel phases

**Goal.** Make parallel agents (HyperGate's 5 sub-agents, parallel perspective generators, debate/jury roles) declare read-set/write-set/assumptions so conflicts (stale snapshot, obsolete invariant, divergent goal interpretation) are resolved semantically, not last-write-wins.

**Paper grounding.** §5.2.4 (transactional shared program state & semantic conflict resolution).

**Current state.** `run_perspectives_phase` writes candidates into shared `PipelineState` concurrently via `asyncio.gather`; HyperGate sub-agents run in parallel; Neuro L1/L2/L3 memory is shared. Today these append/last-write without conflict detection. **No active bug observed** → this is risk-reduction, not a fix.

**Target design (when triggered by an observed divergence bug):**
- Per parallel branch: declare `read_set`/`write_set`/`assumptions` (lightweight metadata on the task).
- Detect conflicting writes / stale-assumption reads at the merge point; resolve via explicit policy (semantic merge / re-verify / escalate) rather than silent overwrite.
- Start with **detection + logging** (cheap, surfaces real conflicts) before building resolution.

**Effort.** M. **Deferred**; instrument detection first, build resolution only if conflicts prove real.

---

## 3. Cross-cutting concerns

- **Constants & magic numbers.** New files: `core/exec_constants.py` (#1), `core/scorecard_constants.py` (#2), `core/evolution_constants.py` (#4). Extend `core/constants_limits.py` for #3/#5. Zero literals in phase/flow/service code.
- **Tiering / feature flags.** `EXEC_SANDBOX_ENABLED` (#1), premium-gating for evidence bundles (#3), Evolution Agent CI-only flag (#4). Budget runs remain byte-identical (VS-critique precedent).
- **Backward-compat & `--resume`.** All new state is all-default dataclasses / `.get()`-safe dicts with `_from_dict` reconstruction + round-trip tests (the `ReviewHypothesis` pattern). Old state files must load unchanged.
- **Parsing.** New tolerant `_parse_evidence_bundle`, `_parse_plan_contract`, `_parse_harness_mutation`; re-export from the `parsing.py` shim.
- **Telemetry schema.** v1 needs **no** schema change (#2 reads existing columns). If #4 needs richer signals later, add columns additively with defaults.
- **Security.** Executed code: AST allowlist + no-network + resource caps + tempdir. Harness mutations: sandboxed eval + regression gate + audit + HITL on cost/safety. No secrets in telemetry or audit artifacts.
- **Living docs.** Update `ARCHITECTURE_MINDMAP.md` (new ports/events/methods counters), `AGENTS.md` (new capabilities), and add a `docs/` note per shipped enhancement.

---

## 4. Dependency graph & rollout sequence

```
#2 Scorecard ─────────────┐ (prereq)
                          ▼
#1 Executable verify ──► #3 Evidence bundles ──► #5 Plan contract
        │                         │
        └─────────────► #4 Evolution Agent ◄──────┘
                              (consumes #2 telemetry, richer with #1/#3)

#6 Permissions/HITL  — deferred until a full-access action exists
#7 Transactional state — deferred until a divergence bug is observed
```

**Recommended order:**

| Phase | Deliverable | Why this order | Effort |
|---|---|---|---|
| **P0** | **#2 Harness Scorecard** | Read-only, zero write-risk, immediate diagnosis, prereq for #4 | S–M |
| **P1** | **#1 Executable verification (PoT)** | Paper's core thesis; Reasoner's biggest gap; flagship | L |
| **P2** | **#3 Evidence bundles** | Consumes #1's evidence ids; strengthens signature feature | M |
| **P3** | **#5 Plan contract + feedback routing (Coding)** | Validation commands need #1's executor | M |
| **P4** | **#4 Evolution Agent** | Needs #2; richer with #1/#3; land in 4 sub-phases (contract→diagnosis→replay→governance) | XL |
| **Deferred** | **#6, #7** | Activate on trigger (full-access action / observed conflict) | M–L |

---

## 5. Success metrics (harness-level, per the paper)

Measured **via the Scorecard (#2)** before/after each enhancement — not by anecdote:

- **Verification strength:** % of `VERIFIED` claims backed by a deterministic sensor (target: PoT → 100% sensor-backed after #1; 0% today).
- **Oracle adequacy:** PoT answers that pass real execution vs. previously model-asserted success (expect divergence — that delta *is* the value).
- **Trajectory efficiency:** cost/tokens/duration per successful run, per preset (Evolution Agent target: reduce without quality loss).
- **Recovery ability:** % of fallback-triggered runs that still complete.
- **Regression safety (#4):** zero solved-case regressions across promoted mutations; every promotion carries an audit rationale + rollback.
- **Replayability:** % of runs reconstructable from event history.

---

## 6. File manifest

**New (by enhancement):**
- #1: `core/ports/code_executor.py`, `core/code_safety.py`, `core/exec_constants.py`, `infrastructure/execution/{subprocess_executor,noop_executor,__init__}.py`, `tests/unit/{test_code_executor,test_pot_executable}.py`
- #2: `domain/harness_metrics.py`, `core/scorecard_constants.py`, `application/queries/get_harness_scorecard.py`, `application/services/scorecard_service.py`, `api/routes/` scorecard endpoint, `tests/unit/test_scorecard_service.py`, `tests/integration/test_scorecard_api.py`
- #3: `application/services/evidence_service.py`, `tests/unit/test_evidence_bundle.py` (+ `EvidenceBundle` in `core_types.py`, `_parse_evidence_bundle` in `core/parsing.py`)
- #4: `healing/{evolution_agent,harness_diagnosis}.py`, `domain/harness_mutation.py`, `core/evolution_constants.py`, `benchmarks/harness_eval_set.json`, `audit/harness_mutations/` (output dir), `application/handlers/` mutation command/query, `tests/unit/{test_harness_mutation_contract,test_evolution_regression_gate}.py`, `tests/integration/test_evolution_replay.py`
- #5: `application/services/feedback_router.py`, `tests/unit/{test_plan_contract,test_feedback_router}.py`
- #6 (deferred): `core/ports/permission_gateway.py`, `infrastructure/security/permission_gateway.py`
- #7 (deferred): conflict-detection instrumentation in perspective/HyperGate parallel paths

**Modified:**
- `application/flows/cognitive_phases.py` (#1: `run_pot_execute_phase`), `phases/pot.py` (#1: drop simulate prompt), `application/flows/base.py` + composition root (#1: inject `CodeExecutorPort` on `WorkflowServices`)
- `infrastructure/persistence/telemetry_store.py` (#2: `get_scorecard_rows`), `healing/telemetry_exporter.py` (#2: reuse scorecard aggregation)
- `domain/core_types.py` + `core/parsing.py` + `parsing.py` shim (#3/#5: new types & parsers)
- `domain/preset_registry.py`, `infrastructure/llm/router.py`, `core/constants_limits.py` (#4: candidate-snapshot load path)
- `phases/coding.py`, `flows/coding.py` (#5: contract schema)
- `ARCHITECTURE_MINDMAP.md`, `AGENTS.md` (docs)

---

## 7. Open questions (resolve before P1/P4)

1. **Sandbox depth (#1):** subprocess+AST for v1 (fast, win32-friendly) vs. invest in WASM/Docker now? *Recommendation: subprocess+AST v1, document boundary, Docker as hardening.*
2. **Held-out eval set (#4):** curate from real telemetry-sampled problems vs. synthetic? Size? *Recommendation: sample from `TelemetryStore` top presets, freeze a labeled set.*
3. **Promotion authority (#4):** who is the HITL approver for cost/safety-tier mutations, and where does the approval UI live (CLI artifact review vs. API)?
4. **Evidence granularity (#3):** per-claim bundles vs. per-synthesis bundle for v1? *Recommendation: per-synthesis v1, per-claim when #1 lands.*

---

*End of plan. No code changes made; this document is the deliverable.*
