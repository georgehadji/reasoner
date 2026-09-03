# Running the V7 Autonomous Defect-Hunt Protocol Against the Reasoner Backend

**Status:** plan, not yet executed
**Date:** 2026-09-01
**Source protocol:** *Autonomous Defect-Hunt Protocol — V7 (Proactive)*; EGFV / RAR / MRADO / PCST
**Target surface:** `src/reasoner/**` (Python backend). `ui-next/**` is explicitly out of scope.

---

## 0. The blocking problem, stated first

V7's Phase 0 has a hard blocking condition:

> If runtime version or entry point cannot be determined, **OR if no scope can be bounded**
> (no way to know what "in scope" means) → emit `[BLOCKED: missing environment/scope data]`,
> list exactly what is needed, and **do not proceed**.

"Run it on the whole backend" is that condition, verbatim. The backend measures:

| Package | Files | Lines |
|---|---:|---:|
| `infrastructure/` | 146 | 25,809 |
| `application/` | 117 | 20,629 |
| `api/` | 51 | 8,557 |
| `core/` | 52 | 7,639 |
| `domain/` | 24 | 5,657 |
| `phases/` | 36 | 4,911 |
| `neuro/` | 8 | 2,574 |
| `subagents/` | 30 | 1,986 |
| `healing/` | 5 | 1,507 |
| `hypergate/` | 13 | 1,274 |
| **`src/reasoner` total** | **528** | **84,988** |
| (`tests/` for reference) | 299 | 50,188 |

*(VERIFIED — counted 2026-09-01 by walking the tree.)*

A single V7 run over 85k lines does not terminate and cannot produce an honest Coverage
Statement. **So the plan is not "run V7 once." It is "partition the backend into bounded
region tiers, run V7 once per tier, and compose the Coverage Statements."** That partitioning
is the actual deliverable below.

---

## 1. Threat model (Phase 0 requirement)

V7 requires a per-system threat model to rank its 8-class defect taxonomy. Reasoner is a
metered, multi-tenant LLM orchestrator with an event-sourced core. Ranked by what actually
costs money or corrupts state here:

1. **Money loss / metering** — credits, spend ceilings, `run_metering`, billing routes.
   A double-charge or a bypassed ceiling is unrecoverable customer harm.
2. **Data corruption** — event store, snapshots, aggregate replay. A corrupt event stream
   silently poisons every future replay.
3. **Trust boundary** — prompt-injection defense, `sanitize_for_prompt` /
   `neutralize_for_replay`, auth, CSRF, rate limiting. Documented invariants exist here
   (`CLAUDE.md` §5), which makes violations *provable* rather than speculative.
4. **Resource lifecycle** — httpx clients across 12 direct LLM adapters, Valkey/Redis
   pools, DB connections, asyncio tasks. Leak-on-error-path is the classic shape.
5. **Concurrency** — parallel phase fan-out, HyperGate's 5 parallel sub-agents, L1/L2/L3
   cache. Check-then-act and unsynchronized shared state.
6. **Contract / dependency** — every provider adapter assumes upstream behavior the vendor
   docs do not guarantee (ordering, nullability, retry semantics).
7. **Error & exception paths** — swallowed exceptions, partial state on failure.
8. **Boundary & arithmetic / type & serialization / state machine** — lower priority, but
   in scope for the parsing and pipeline-state tiers specifically.

---

## 2. Region tiers (the partition)

Seven tiers, ordered by `hunt_priority ≈ likelihood × blast_radius × reachability`. Each tier
is a self-contained V7 run with its own Phase 0 census, budget, and Coverage Statement.

| # | Tier | Surface | Primary defect classes | Blast radius | Budget (candidates) |
|---|---|---|---|---|---|
| T1 | **Billing & metering** | `application/services/{billing,metering,pricing}*`, `domain/credits*`, `api/run_observability.py`, billing routes | money-loss, arithmetic, state machine, concurrency | EXTERNALLY-VISIBLE | 12 |
| T2 | **Persistence & event sourcing** | `infrastructure/persistence/**`, `core/aggregates/**`, `core/events/**` | data corruption, transactions, serialization, TOCTOU | SYSTEM | 12 |
| T3 | **Trust boundary & API** | `api/**` (auth_deps, middleware, streaming, CSRF), `core/sanitization*`, `security/**` | injection, unvalidated input, authz bypass | EXTERNALLY-VISIBLE | 14 |
| T4 | **LLM transport & routing** | `infrastructure/llm/**` (registry, router, 12 providers) | resource lifecycle, contract/dependency, error paths | SYSTEM | 12 |
| T5 | **Pipeline orchestration** | `application/{pipeline,orchestrator}.py`, `application/flows/**`, `handlers/**`, `mixins/**` | concurrency, state machine, partial-state-on-failure | SYSTEM | 12 |
| T6 | **Parsing & state model** | `core/parsing*`, `domain/pipeline_state.py`, `domain/preset*` | type/serialization, boundary, `None` propagation | MODULE | 8 |
| T7 | **Memory & cache** | `neuro/**`, `healing/**`, `hypergate/**` caching | concurrency, resource lifecycle, cache coherence | MODULE | 8 |

**Deliberately deprioritized (not skipped — recorded as unaudited):** `phases/**` and
`subagents/**` are prompt-template modules; their failure mode is output quality, not a
defect class in V7's taxonomy. They enter the Coverage Statement's "Surface NOT audited"
line with that reason, per the protocol's epistemic-honesty clause.

**Total budget: 78 candidate defects.** Termination per tier is the protocol's own: budget
exhausted OR the tier's region map fully triaged, whichever comes first.

---

## 3. Phase 0 census (pre-filled — the same for every tier)

Supplying this up front is what unblocks the protocol. Each tier run gets this header:

```
Language:        Python
Runtime:         3.12+ (VERIFY exact patch with `python -V` at run time)
Framework(s):    FastAPI 0.109+, Pydantic v2, httpx, uvicorn
Test framework:  pytest (299 test files; markers incl. `slow`, `integration`)
Entry point(s):  asgi:app (HTTP/SSE) · main.py (CLI) · reasoner.headless.ask() (in-process)
                 · api/mcp (MCP server, optional extra)
Invariants:      DOCUMENTED — CLAUDE.md §5 "Key Invariants" + §5 propagation-resistance.
                 Load these into every run; they are the difference between a provable
                 violation and a speculative one.
Build/lockfile:  requirements.txt; CI gates in .github/workflows/{test,quality,security,coverage}.yml
```

**The documented invariants are the single highest-value input to this hunt.** V7 says a
candidate must name the property it violates; Reasoner already has named, load-bearing
properties (memory never enters a system prompt; Phase-2 generators are blind to each other;
`harden_system_prompt()` applied at both chokepoints; model/web text always wrapped). Those
convert straight into falsifiable candidates.

---

## 4. Execution mechanics

### 4.1 One tier = one agent run

Each tier runs as an isolated agent with: the V7 protocol text, the Phase 0 census above,
that tier's file list, and the CLAUDE.md invariants section. Isolation matters — V7 forbids
regenerating innocence-cleared candidates, which only works if a run holds its own full
candidate history.

Tiers are independent and can run in parallel. **T1 and T2 first** — highest blast radius,
and they are the two where a confirmed defect most justifies continuing.

### 4.2 Phase 3a triggers must actually execute

This is where most protocol runs quietly degrade into reasoning-only output. V7 is explicit:
a candidate that cannot produce an executable trigger stays `[UNK]` and **does not get
promoted on reasoning alone**. Enforcement:

- Every trigger is a real `pytest` invocation against a real entry point.
- **No live LLM API calls.** Fake at the transport boundary (httpx transport / provider
  adapter), never at the mechanism under suspicion — V7 forbids mocking away the suspected
  mechanism, so a candidate about router fallback logic may stub the HTTP response but not
  the router.
- Concurrency candidates (T5, T7) need the repeated-trial harness: N ≥ 100, result labeled
  `STATISTICAL(rate)`, never deterministic `[VF]`.
- Set `CSRF_ENFORCE_BACKEND=false` for T3 runs that aren't specifically about CSRF (per
  CLAUDE.md); a run that trips CSRF on every request produces false triggers.

### 4.3 Operational hazards specific to this repo

These will bite during Phase 5/7 and are worth pre-loading into each run:

- **The ruff ratchet is exact-equality.** Fixing lint fails the gate exactly as adding lint
  does. The constant lives in *both* `scripts/ci-local.sh` and `test.yml`. Any V7 fix that
  incidentally changes lint count must update both.
- **import-linter gate** sits at 58 exceptions / MAX 65 with grimp pinned. A fix that moves
  a module across a layer boundary will trip it.
- **Coverage gates**: 60% fail / 80% warn. Phase 7 adds tests, so this should move the right
  way — but a fix that deletes a covered branch can drop it.
- **`pre-push` hooks gate the whole working tree**, not just your commit. Peer sessions share
  this checkout; push from a detached worktree at HEAD.
- **Bandit ratchet** on security workflow — T3 fixes are the likely trigger.

### 4.4 Expect a high escalation rate — this is not failure

V7 caps fixes at ≤15 lines / ≤1 function. In a hexagonal codebase, a genuine defect in, say,
the router fallback chain routinely needs a caller + callee change. The protocol has the
right vocabulary for this (`[CONSTRAINT-FORCED ESCALATION]`, `[REQUIRES HUMAN REVIEW:
cross-boundary mechanism]`) and explicitly wants the distinction recorded so a reviewer can
tell a risky fix from a policy artifact. **Plan for a meaningful share of confirmed defects
to land as escalations rather than applied diffs.** That is the protocol working, not
stalling.

---

## 5. Deliverables

Per tier:
- Defect inventory (Phase 4 table: candidate / trigger / innocence / evidence basis / status)
- Applied fixes with causal justification + risk block (Phase 5)
- Tests: proof-of-defect + ≥2 boundary + no-regression, per verified defect (Phase 7)
- Coverage & Residual-Risk Statement (Phase 8) — **the core deliverable**
- Uncertainty Acknowledgment

Composed across tiers:
- `docs/reports/defect-hunt-<date>/` — one file per tier + a rollup
- A single merged residual-risk register: what stayed `UNKNOWN`, what needs runtime
  instrumentation, which regions the budget left thinnest
- One PR per tier (never one giant PR), each gated on the existing CI

---

## 6. Sequencing

| Step | Work | Gate |
|---|---|---|
| 1 | Confirm exact Python patch version + `pip freeze` snapshot | Phase 0 census closes |
| 2 | T1 (billing) + T2 (persistence) in parallel | Review both inventories before continuing |
| 3 | T3 (trust boundary) | Security-sensitive: `security-reviewer` on every fix |
| 4 | T4 + T5 in parallel | — |
| 5 | T6 + T7 in parallel | — |
| 6 | Rollup: merged residual-risk register, next-hunt recommendation | — |

Stopping after step 2 is a legitimate outcome. If T1 and T2 come back clean, the marginal
value of T4–T7 drops sharply and the budget is better spent on runtime instrumentation for
whatever landed in the UNKNOWN set.

---

## 7. What this plan does NOT claim

Per V7's epistemic-honesty clause, stated before the hunt rather than after:

- Completeness is over **defect classes examined**, not defect instances. A clean tier means
  "regions R… were audited for classes … and no VERIFIED defect was found" — never "this
  code is bug-free."
- `phases/**` and `subagents/**` are unaudited by design (§2).
- Anything requiring live provider behavior, real concurrency timing, or production data
  volume is `UNKNOWN` to static analysis and routes to the runtime-instrumentation list.
- **The 78-candidate budget is a judgment call, not a derived number.** It is sized to be
  affordable, not to be sufficient. `[INPUT REQUIRED: is 78 the right budget, or should T1/T2
  run deeper before the rest run at all?]`

---

## 8. Open questions for the human before execution

1. **Budget** — is ~78 candidates the right ceiling, or run T1/T2 deep first and decide after?
2. **Fix authority** — should confirmed defects be *fixed* (Phase 5 diffs applied, PR per
   tier), or should the run stop at the inventory and let a human triage what gets fixed?
3. **Escalation handling** — when a fix needs a cross-boundary change, escalate and stop, or
   escalate and propose the larger diff anyway for review?
4. **The dirty working tree** — this checkout currently has uncommitted backend changes from
   another session (`api/__init__.py`, `harness_metrics.py`, `evolution_agent.py`,
   `openai_compat.py`, `test_pool_cleanup.py`). The hunt must run against a known commit.
   Stash them, or run from a clean worktree at HEAD?
