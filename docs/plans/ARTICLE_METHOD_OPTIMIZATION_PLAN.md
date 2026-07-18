# Article Method — Optimization & Refactor Plan

**Scope:** re-architect the Article pipeline (the 9-phase editorial method) to fix the correctness, consistency, and trust defects surfaced in review, using paradigms and patterns chosen *surgically* — each one earns its place by removing a specific, named pain.

**Non-goal:** a pattern showcase. The system's disease is a small number of root causes; ~80% of the benefit comes from three paradigm choices. The rest is applied only where it pays.

---

## 0. Executive thesis

**The disease is uncontrolled shared mutable state.** `state.writing_state["final_article"]` is a god-object mutated in place by phases 3, 6, and 7, while the trust artifacts (`claim_ledger`, `metrics`, `claim_labels`) are computed once against phase 4's version and never reconciled. Every CRITICAL/HIGH finding is a symptom of this one fact:

- Stale ledger/metadata describing a document that no longer exists → *mutation without versioning*.
- Style edit silently breaking claims/citations → *no immutability boundary around verified content*.
- Audit re-deriving claim support impressionistically → *the ledger isn't a first-class value passed forward*.
- Retry looping on stale critique → *feedback isn't tied to a document version*.

**The cure, in order of leverage:**

1. **Immutable, versioned document model** (functional core / imperative shell). Make the article a value, not a mutable field. Staleness becomes a *diff between versions* instead of a silent overwrite — which makes reconciliation possible and the stale-ledger bug structurally impossible.
2. **A single canonical `Claim` value object + reconciliation pass.** One taxonomy, one ledger, always computed against the current version. Resolves the taxonomy inconsistency, the lossy ratio, the stale labels, and the "audit doesn't see the ledger" problem in one move.
3. **Typed effects (`Result`) at phase boundaries.** Turns the ad-hoc try/catch/fallback web (§16) into an explicit, composable, testable error channel that honors the "no cascading failures" invariant *by construction*.

Everything else — Strategy/Registry routing, Specification gates, conditional gap-retrieval, budget circuit-breaker, event surfacing — is a targeted pattern hung off that spine. **Resist adding more.** For a solo-maintained system, over-abstraction is the same kitchen-sink failure mode we already diagnosed at the product level, transposed to code.

---

## 1. Optimization goals, mapped to findings

Every goal traces to a specific defect from review. No invented work.

| # | Goal | Finding it fixes | Severity |
|---|------|------------------|----------|
| G1 | Ledger/metadata always describe the *shipped* version | Stale ledger (mutation w/o reconciliation) | CRITICAL |
| G2 | Verified factual content cannot be silently altered downstream | Style edit manufactures overconfidence / breaks claims | CRITICAL |
| G3 | One canonical claim taxonomy + honest ratio | 3-value verdict vs 4-value label mismatch; lossy `claim_support_ratio`; cosmetic gate | HIGH |
| G4 | Verifier is provider-independent of the drafter | Sonar retrieves → drafts-from → verifies (monoculture) | HIGH (correctness) |
| G5 | Audit consumes the ledger; retry refreshes feedback | Audit re-derives support; retry uses stale critique | HIGH |
| G6 | Per-phase config (temperature, thresholds, weights) | Temp unset; uniform 0.6 gates; equal weighting | HIGH/MED |
| G7 | Evidence gaps trigger *retrieval*, not deletion | Delete-not-retrieve response to gaps | MED |
| G8 | Quality-failure and confidence signals reach the user | `passes_audit=false` hidden; labels buried | VERIFIED values contradiction |
| G9 | Regression safety before any of the above | No eval harness ("subsystem zero") | Foundational |
| G10 | Cost/latency stay first-class under new work | Cost table doesn't reconcile; new passes add spend | HIGH (doc) |

---

## 2. Paradigm choices (the load-bearing three)

These are chosen, not defaulted. Each includes the alternative I rejected and why.

### 2.1 Functional Core, Imperative Shell
**Decision:** all *decisions and transformations* are pure functions over immutable values (`build_prompt`, `parse_factcheck`, `reconcile`, `compute_metrics`, `evaluate_gates`, `map_verdict`); all *effects* (LLM calls, web search, timeouts) live in a thin shell that injects dependencies.

**Why:** the pure core is trivially unit-testable and deterministic — you can test parsing, reconciliation, metric math, and gate logic with zero network and zero cost. This is the difference between a pipeline you can regression-test (G9) and one you can only observe in production. It also maps cleanly to your instinct from computational-physics work: a deterministic core with controlled, explicit effects at the boundary.

**Rejected:** "OO phases that call the LLM and mutate `self.state`." That's the current design; it's why nothing downstream is testable and why the ledger goes stale.

### 2.2 Immutable, versioned domain model
**Decision:** `Document` is a frozen value carrying `version` and `produced_by`. Phases return a *new* `Context` (via `dataclasses.replace`), never mutate. The blackboard survives as a *concept* (a shared knowledge structure many specialists contribute to) but writes are append/replace-into-new-version, never in-place.

**Why:** makes G1/G2 structural. If the article is immutable and versioned, then "the ledger was computed against v2 but we shipped v4" is a *visible, checkable invariant*, not a silent bug. Reconciliation is `reconcile(ledger_at_v2, doc_v4)`. Span-locking verified content is a property of a value, not a plea in a prompt.

**Rejected:** full **event-sourcing as the control plane** (the document as a pure projection over an event log). It's the "document-as-graph" temptation again: real benefits (replay, audit) but heavy, and *replay is partly illusory for a stochastic generator* — temp>0 won't reproduce, temp=0 isn't reliably deterministic across model/backend versions. So: keep an **append-only event log as an additive observability/provenance channel** (cheap, useful for G8 and audit trails), but **not** as the spine. Provenance ≠ reproducibility; don't build for the latter.

### 2.3 Typed effects via `Result[T, E]`
**Decision:** every phase returns `Result[Context, PhaseError]`. `Err` carries an optional degraded fallback. The pipeline runner interprets `Ok`/`Err` centrally.

**Why:** §16's "each phase emits JSON; parse errors are non-fatal; use fallback" is a *policy* currently scattered across try/catch blocks. A `Result` type makes that policy explicit and composable, distinguishes recoverable-with-fallback from fatal, and lets you test degradation paths deterministically. "Never ships empty" becomes a property of the runner, not an accident of each handler.

**Rejected:** exceptions-as-control-flow (status quo) — invisible in signatures, hard to test, easy to accidentally make fatal.

> **Pragmatism clause:** Python is not Haskell. Allow ordinary local mutation *inside* a phase for ergonomics; enforce immutability only at phase *boundaries*. Don't import a monad library and don't turn this into category theory. The value is the boundary discipline, not purity theater.

---

## 3. Three architectural approaches (pick one)

### Approach A — In-place hardening (minimal)
Keep the linear pipeline and blackboard; bolt on: immutable `Document`, a reconciliation pass, `Result` at boundaries, per-phase config, formalized registry.
- **Pros:** lowest risk, fastest, smallest diff, no re-plumbing of control flow.
- **Cons:** phases stay hard to test in isolation; retry stays special-cased; composability (branching for gap-retrieval) is awkward. You fix the bugs but not the *shape* that produced them.
- **Effort:** low. **Ceiling:** medium.

### Approach B — Functional pipeline of composable phase-functions (**recommended**)
`Phase = (Context, Deps) -> Result[Context, PhaseError]`. The pipeline is composition of phases with **combinators** — `with_retry`, `with_budget_guard`, `branch` — as higher-order functions. Routing via **Strategy + Registry**, gates via **Specification**, errors via **Result**, the document immutable and versioned.
- **Pros:** kills the root cause structurally (G1/G2); phases are pure-given-response and unit-testable (G9); retry, budget-guard, and conditional gap-retrieval become *reusable combinators* instead of bespoke branches; the "capabilities not agents" idea from the product review lands here as **one orchestration policy over composable capabilities**.
- **Cons:** a real refactor; requires the domain model and a runner up front. Functional style has ergonomic limits in Python (mitigated by the pragmatism clause).
- **Effort:** medium. **Ceiling:** high. **This is the right balance for a live, solo-maintained, cost-bounded system.**

### Approach C — Graph/DAG orchestration + event log (destination)
Model phases as nodes in a declared graph (LangGraph-style) with an event log; supports dynamic re-planning, parallel branches, full replay/observability.
- **Pros:** highest capability; native support for dynamic orchestration and parallelism; best observability.
- **Cons:** heaviest; over-engineered for 9 mostly-sequential phases with one retry; adds a framework dependency and a mental-model tax; the replay selling point is weak for stochastic LLMs (see §2.2).
- **Effort:** high. **Ceiling:** highest. **Verdict:** the 3–5-year destination, not now. Adopt B; borrow only C's *additive event log*.

**Recommendation:** **B now**, with C's event log as an additive provenance channel, and C's full graph deferred until you have parallel/branchy workflows that a linear-with-combinators runner can't express cleanly. This mirrors the destination-vs-path split we already agreed on at the product level.

---

## 4. Target architecture (Approach B)

### 4.1 Domain model (immutable core)

```python
from __future__ import annotations
from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol, Callable, Generic, TypeVar, Union

# ---- Typed effects -------------------------------------------------
T = TypeVar("T"); E = TypeVar("E")

@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T

@dataclass(frozen=True)
class Err(Generic[E]):
    error: E
    fallback: object | None = None   # degraded Context, if any

Result = Union[Ok, Err]

# ---- Canonical claim taxonomy (fixes G3) ---------------------------
class Verdict(Enum):
    VERIFIED     = "verified"      # verbatim / direct source match
    SUPPORTED    = "supported"     # entailed by source, reworded
    PARTIAL      = "partial"       # some support, incomplete
    SPECULATIVE  = "speculative"   # opinion / hypothesis / unverifiable
    UNSUPPORTED  = "unsupported"   # no source found

class VerifyMethod(Enum):
    QUOTE_MATCH = "quote_match"
    ENTAILMENT  = "entailment"
    LIVE_SEARCH = "live_search"
    NONE        = "none"

class HumanDecision(Enum):
    NONE = "none"; ACCEPTED = "accepted"; REJECTED = "rejected"; EDITED = "edited"

@dataclass(frozen=True)
class Claim:
    id: str
    text: str                          # normalized claim text
    span: tuple[int, int] | None       # char offsets into `verified_against_version`
    sources: tuple[str, ...]
    verdict: Verdict
    confidence: float                  # 0..1
    method: VerifyMethod
    verified_against_version: int      # WHICH doc revision this verdict describes
    human: HumanDecision = HumanDecision.NONE
    needs_review: bool = False

# ---- Versioned document (fixes G1/G2) ------------------------------
@dataclass(frozen=True)
class Document:
    version: int
    markdown: str
    title: str
    produced_by: str                   # phase name that emitted this revision
    locked_spans: tuple[tuple[int, int], ...] = ()   # verified content (G2)

@dataclass(frozen=True)
class Budget:
    usd_cap: float
    seconds_cap: float
    usd_spent: float = 0.0
    seconds_spent: float = 0.0
    def remaining_usd(self) -> float: return self.usd_cap - self.usd_spent

@dataclass(frozen=True)
class Context:
    problem: str
    content_class: str                 # drives gate policy + routing (G6/G8)
    sources: tuple[dict, ...]
    outline: dict | None
    doc: Document | None
    ledger: tuple[Claim, ...]
    audit: dict | None
    metrics: dict | None
    budget: Budget
    events: tuple[dict, ...] = ()       # append-only provenance log (additive)
```

### 4.2 The Phase abstraction + combinators

```python
class PhaseError(Enum):
    PARSE = "parse"; TIMEOUT = "timeout"; LLM = "llm"; BUDGET = "budget"

class Phase(Protocol):
    name: str
    def __call__(self, ctx: Context, deps: "Deps") -> Result: ...

# Higher-order combinators replace bespoke control flow ------------------
def with_budget_guard(phase: Phase) -> Phase:
    """Circuit breaker: trip to graceful degradation if budget exhausted."""
    def run(ctx, deps):
        if ctx.budget.remaining_usd() <= 0:
            return Err(PhaseError.BUDGET, fallback=ctx)   # never empty
        return phase(ctx, deps)
    run.name = phase.name
    return run

def branch(pred: Callable[[Context], bool], then: Phase) -> Phase:
    """Conditional phase, e.g. gap-driven re-retrieval (G7)."""
    def run(ctx, deps):
        return then(ctx, deps) if pred(ctx) else Ok(ctx)
    run.name = f"branch::{then.name}"
    return run

def with_retry(phase: Phase,
               refresh: Callable[[Context, "Deps"], Context],
               passed: Callable[[Context], bool],
               max_tries: int = 1) -> Phase:
    """Retry that REFRESHES feedback against the current version (G5)."""
    def run(ctx, deps):
        res = phase(ctx, deps)
        tries = 0
        cur = res.value if isinstance(res, Ok) else ctx
        while not passed(cur) and tries < max_tries:
            cur = refresh(cur, deps)          # re-run cheap critic on CURRENT doc
            res = phase(cur, deps)
            cur = res.value if isinstance(res, Ok) else cur
            tries += 1
        return Ok(cur)
    run.name = f"retry::{phase.name}"
    return run

def pipeline(*phases: Phase) -> Phase:
    def run(ctx, deps):
        cur = ctx
        for p in phases:
            res = p(cur, deps)
            if isinstance(res, Ok):
                cur = res.value
            else:
                # non-fatal policy centralized here, not scattered (Result payoff)
                cur = res.fallback if res.fallback is not None else cur
                cur = _log_event(cur, "phase_degraded", p.name, res.error)
        return Ok(cur)
    run.name = "pipeline"
    return run
```

The assembled article pipeline then reads as a declarative composition:

```python
article = pipeline(
    branch(is_deep_question, augment),
    retrieve_sources,
    build_outline,
    draft,
    fact_check,                                   # builds ledger @ v(draft)
    structural_critique,
    developmental_edit,                           # -> new doc version
    branch(has_evidence_gaps, gap_retrieval),     # G7: seek, don't delete
    developmental_edit_gaps,                      # only if gap_retrieval ran
    style_copy_edit,                              # -> new version, respects locked_spans
    reconcile_ledger,                             # G1: re-verify deltas @ current version
    with_retry(final_audit, refresh=refresh_critique, passed=passes_gates, max_tries=1),
    surface_signals,                              # G8
    synthesis,
)
```

Note what disappeared: no phase mutates a shared field; retry is a combinator with fresh feedback; gap-retrieval is a `branch`; budget is a wrapper; the ledger is reconciled *before* audit and synthesis so every reported number describes the shipped version.

---

## 5. Pattern-to-problem map (ranked by ROI)

Applied only where a specific pain justifies it. "Why not X" included so you can veto.

| Priority | Pattern | Solves | Why this, not the alternative |
|---|---|---|---|
| **P0** | **Functional Core / Imperative Shell** | testability, determinism, G9 | vs OO-with-effects (status quo): untestable, stateful |
| **P0** | **Immutable Value Object** (`Document`, `Claim`) | G1, G2, G3 | vs mutable state: staleness is silent; here it's a checkable diff |
| **P0** | **Result/Either type** | §16 error policy, "never empty" | vs exceptions: invisible in signatures, hard to test |
| **P0** | **Canonical type + mapping fn** (`Verdict`) | G3 | vs two ad-hoc enums: no source of truth |
| **P0** | **Router invariant / Policy object** | G4 | vs "trust the preset": monoculture ships correlated errors |
| **P1** | **Strategy + Registry** (routing) | model churn, A/B | already present (invariant 5) — formalize, add per-class routing |
| **P1** | **Specification** (quality gates) | G6 (per-class, weighted) | vs hardcoded `all ≥ 0.6`: rigid, untestable, one-size |
| **P1** | **Combinator / HOF** (retry, branch, guard) | G5, G7, budget | vs bespoke `if` branches: not reusable, not testable |
| **P1** | **Span-lock (immutability constraint)** | G2 | vs prompt "please preserve facts": unenforced, probabilistic |
| **P2** | **Chain of Responsibility** (fallback chain) | provider fallback | already implicit — make explicit & ordered |
| **P2** | **Observer / event emission** | G8 (surface signals) | vs coupling phases to UI: violates separation |
| **P2** | **Circuit Breaker** (budget guard) | G10 | vs hoping cost stays low: cost is first-class here |

**Deliberately NOT used (YAGNI for a solo, 9-phase, cost-bounded system):**

- **Template Method / deep inheritance hierarchies** for phases — composition (functions + combinators) is strictly better here; inheritance would re-couple what we just decoupled.
- **Actor model / message bus** — 9 mostly-sequential phases don't need concurrency machinery; adds deploy and reasoning cost for nothing.
- **Microservice-per-phase** — latency, ops burden, and distributed-failure modes with zero benefit at this scale.
- **Full workflow engine (Temporal/Airflow)** — function composition + one retry combinator covers today's needs; revisit only at Approach C.
- **DI framework** — plain function arguments (`deps`) are the DI. Don't import a container.
- **Full event-sourcing as control plane** — additive log only (see §2.2). Replay is not a real guarantee for stochastic generation.

> **Guardrail:** if a proposed pattern doesn't map to a row in the *findings* table (§1), it doesn't go in. That rule is what keeps this from becoming the 14-subsystem kitchen sink at the code layer.

---

## 6. The through-line fix: a living claim ledger

This single subsystem resolves G1, G3, part of G5, and enables G8. It's the "claim ledger as living artifact" made concrete.

### 6.1 Verdict mapping (kills the taxonomy inconsistency)

The fact-check currently emits `supported | partially_supported | unsupported`; labels use a different 4-value set with no crosswalk. Collapse to **one** canonical `Verdict` produced by a pure mapping:

```python
def map_verdict(raw_verdict: str, method: VerifyMethod, is_opinion: bool) -> Verdict:
    if is_opinion:                      return Verdict.SPECULATIVE
    if raw_verdict == "unsupported":    return Verdict.UNSUPPORTED
    if raw_verdict == "partially_supported": return Verdict.PARTIAL
    if method == VerifyMethod.QUOTE_MATCH:   return Verdict.VERIFIED   # verbatim
    return Verdict.SUPPORTED                                          # entailed, reworded
```

### 6.2 Honest support ratio (fixes the lossy metric)

Partial support is not zero. Define it once, use it everywhere:

```python
def claim_support_ratio(ledger: tuple[Claim, ...]) -> float:
    factual = [c for c in ledger if c.verdict != Verdict.SPECULATIVE]
    if not factual: return 0.0
    score = sum({Verdict.VERIFIED: 1.0, Verdict.SUPPORTED: 1.0,
                 Verdict.PARTIAL: 0.5}.get(c.verdict, 0.0) for c in factual)
    return score / len(factual)
```

And make the `< threshold` gate *actually do something* (route low-support articles to the reconcile→re-retrieve branch or to human hold), instead of setting a flag nobody reads.

### 6.3 Reconciliation (the core of G1)

Pure function; only the *deltas* cost an LLM call, so this is cheap:

```python
def reconcile(prev: tuple[Claim, ...],
              new_doc: Document,
              extract: Callable[[Document], tuple[dict, ...]]
              ) -> tuple[tuple[Claim, ...], tuple[dict, ...]]:
    """
    Returns (carried_ledger, deltas_to_verify).
    - claims whose normalized text still present  -> carried, span re-anchored
    - claims whose text vanished (dev-edit removed) -> dropped from ledger
    - new claims introduced by edits               -> deltas_to_verify (re-verify only these)
    Pure: no I/O. The shell verifies `deltas_to_verify`, then re-computes metrics
    against new_doc.version so shipped numbers describe the shipped text.
    """
    ...
```

**Span re-anchoring (v1, pragmatic):** match by normalized-text hash; fuzzy fallback for minor rewordings; anything unmatched → treat as removed (old) or added (new). Don't over-engineer offset tracking; re-extract + match is robust and cheap for 800–1200 words.

**Placement:** `reconcile_ledger` runs *after* `style_copy_edit`, *before* `final_audit` and `synthesis`. Result: `claim_support_ratio`, `claims_verified_count`, and `claim_labels` in `meta_audit` always describe the version you ship.

### 6.4 Span-lock (G2, and it neuters the overconfidence bug)

After fact-check, record the char spans of `VERIFIED`/`SUPPORTED` claims into `Document.locked_spans`. The style/copy phase receives locked spans and is constrained to edit *around* them. Concretely: (a) delete the "replace hedging with confident language" directive outright — confidence is a property of `Verdict`, not of prose polish; (b) diff the style output against locked spans and reject/revert changes that touch verified factual text. Prompt-level "please preserve facts" is not enforcement; a post-hoc span diff is.

---

## 7. Correctness & values fixes as first-class code

### 7.1 Verifier independence (G4) — a routing *invariant*, not a preset preference

```python
def route_verifier(drafter: ModelId, registry: Registry, content_class: str) -> ModelId:
    v = registry.pick("writing_factcheck", content_class)
    # HARD invariant: verifier must not share a provider family or a
    # retrieval substrate with the drafter/retriever.
    assert provider_family(v) != provider_family(drafter)
    assert retrieval_substrate(v) != retrieval_substrate(primary_retriever())
    return v
```

Because sonar now supersedes the Brave/Tavily chain and also does fact-check, **repurpose the dormant Brave/Tavily chain as the fact-check's independent retrieval path — excluding Perplexity** (sonar *is* Perplexity; overlap defeats the point). Cheaper fallback if you keep one vendor for retrieval: at minimum force the fact-check *model* into a different family than the drafter. Partial decorrelation beats none.

### 7.2 Quality gates via Specification (G6)

```python
@dataclass(frozen=True)
class Threshold:
    dimension: str; min_value: float; weight: float

@dataclass(frozen=True)
class GatePolicy:
    thresholds: tuple[Threshold, ...]
    def evaluate(self, audit: dict) -> tuple[bool, dict]:
        weighted = sum(audit[t.dimension] * t.weight for t in self.thresholds)
        total_w  = sum(t.weight for t in self.thresholds)
        hard_ok  = all(audit[t.dimension] >= t.min_value for t in self.thresholds)
        score    = weighted / total_w
        return (hard_ok and score >= 0.6), {"score": score, "hard_ok": hard_ok}

# Trust dimensions weigh more and floor higher than prose dimensions:
TRUST_FIRST = GatePolicy((
    Threshold("claim_support",       0.75, 3.0),
    Threshold("citation_accuracy",   0.80, 3.0),
    Threshold("internal_consistency",0.65, 2.0),
    Threshold("thesis_advancement",  0.60, 1.0),
    Threshold("transition_quality",  0.55, 1.0),
    Threshold("redundancy_removed",  0.55, 1.0),
    Threshold("policy_compliance",   0.90, 2.0),
))
```

Gate policy is selected per `content_class`, so a low-stakes blog post and a parliamentary briefing don't share a bar. Also: have the audit **read the reconciled ledger** for `claim_support` instead of re-scoring it by eye (kills the double-spend in G5).

### 7.3 Surfacing signals (G8) via event emission

`surface_signals` reads the final `Context` and emits user-facing events without any phase knowing about the UI:

- If `not passes_gates`: emit `quality_warning` naming the failing dimension(s) and the `issues[]` sections — you already compute these. Default **hold-for-review** on high-stakes `content_class`; **ship-with-banner** on low-stakes.
- Always emit per-claim `Verdict` so the reader *sees* which claims are `SPECULATIVE`/`PARTIAL`. The labels already exist; stop burying them in metadata. This is the uncertainty-into-UI win at zero model cost.

Silent shipping of a self-failed article contradicts the product's entire trust positioning and decapitates the human-in-the-loop backstop exactly when it's needed. Treat G8 as non-negotiable given your venues (own imprint, NIKH briefings, clients).

---

## 8. Eval harness — build this first (G9)

You cannot safely refactor a system you can't regression-test, and the pure core (§2.1) makes this cheap.

- **Golden set:** 15–30 frozen `(problem, content_class)` inputs spanning your real venues, each with a recorded baseline output and metric snapshot from the *current* system. This is your "don't regress" net before touching anything.
- **Pure-core property tests:** `map_verdict` totality; `claim_support_ratio` monotonicity; `reconcile` invariants (no orphan claims; every shipped factual sentence maps to a ledger entry; ledger `verified_against_version == doc.version`).
- **Router invariant test:** `provider_family(verifier) != provider_family(drafter)` holds for every preset × content_class.
- **Gate specification tests:** hand-built audits that must pass/fail each `GatePolicy`.
- **Cost/latency regression:** assert each preset stays within its envelope (also forces you to *reconcile the cost table*, G10 — sum the per-role numbers and make §1/§13 agree or relabel the units).
- **Ledger-freshness invariant (the CRITICAL one):** for every run, assert `metrics` were computed against `doc.version` == the shipped version. This test failing = the stale-ledger bug is back.

---

## 9. Migration roadmap (Strangler Fig — no big-bang; it's live)

Wrap, don't replace. Each phase ships independently behind the eval harness with a rollback.

**Phase 0 — Safety net (days).** Eval harness + golden set + freeze baseline. Reconcile the cost table. *No behavior change.* Rollback: n/a.

**Phase 1 — Boundaries (days).** Introduce immutable `Document` + `Result`; wrap *existing* phase bodies unchanged inside the new signatures (adapter). Pipeline runner replaces the hand-rolled sequence. *Behavior identical, now testable.* Rollback: keep old runner behind a flag.

**Phase 2 — Living ledger (1–2 wks).** Canonical `Claim` + `map_verdict` + honest ratio (G3); `reconcile_ledger` before audit/synthesis (G1); span-lock + delete the overconfidence directive (G2). **This closes both CRITICALs.** Rollback: feature-flag reconciliation; fall back to old (stale) metrics if reconcile errors — but log loudly.

**Phase 3 — Independence & gates (1 wk).** Router independence invariant + repurpose Brave/Tavily for fact-check (G4); Specification gates + per-class policy + audit-reads-ledger (G5/G6). Rollback: per-invariant flags.

**Phase 4 — Loop & signals (1 wk).** `with_retry(refresh=refresh_critique)` (G5); `branch(has_evidence_gaps, gap_retrieval)` (G7); `surface_signals` + hold-for-review policy (G8); budget circuit-breaker (G10). Rollback: combinators are individually removable.

**Phase 5 — (Deferred) Approach C.** Only if/when parallel or branchy workflows outgrow the linear-with-combinators runner. Additive event log can land earlier as pure provenance.

---

## 10. Risks, trade-offs, failure modes

- **Reconciliation adds cost/latency.** Bounded: only *deltas* hit the LLM, and deltas after a dev/style edit are typically few. Net add is small relative to the CRITICAL bug it removes. Make it skippable on the cheapest tier if needed, but default it on.
- **Independent fact-check retrieval raises cost.** Real trade for real correctness. Default it on premium; make it opt-in on budget. Document the cost delta honestly (feeds G10).
- **Immutability memory/perf.** Negligible for 800–1200-word docs; `dataclasses.replace` is cheap. A non-issue at this scale; don't prematurely optimize it.
- **Span re-anchoring imperfection.** Fuzzy matching can mis-anchor after heavy rewrites. Mitigation: on low match-confidence, mark the claim `needs_review=True` and let the human backstop catch it — failing *safe* (toward review), not silent.
- **Over-abstraction (the meta-risk).** The single biggest failure mode is you enjoying the patterns and building Approach C in disguise. The YAGNI list (§5) and the "must map to a finding" guardrail exist specifically to prevent that. If a change doesn't retire a row in §1, cut it.
- **CN-model audit on sensitive content.** Orthogonal but real for NIKH work: make `content_class` drive audit/critique routing away from blocs whose topic-specific behavior you can't reason about, for sensitive classes only.

---

## 11. Confidence & evidence summary

- **VERIFIED (from the spec + your confirmations):** stale ledger via in-place mutation; taxonomy inconsistency; cost table doesn't sum; temperature unset; sonar supersedes the search chain (so verifier independence is lost); `passes_audit=false` not surfaced.
- **INFERENCE (high confidence):** audit re-derives support impressionistically because the ledger isn't passed in; retry edits against stale critique; monoculture verification confirms correlated errors.
- **HYPOTHESIS (flagged, not asserted):** `is_deep_question` binary gate is miscalibrated; bloc-diversity meaningfully decorrelates *fact-checking* errors (plausible, unproven — the intervention here, provider/substrate disjointness, is the testable core of that idea).
- **Design recommendation confidence:** high that Approach B + the living ledger is the right shape; the pattern *set* is deliberately minimal, so the main way this goes wrong is scope creep, not wrong choices.

**Build order if you do nothing else:** (1) eval harness + ledger-freshness invariant, (2) immutable `Document` + `Result` boundaries, (3) canonical `Claim` + reconciliation + span-lock. That trio retires both CRITICALs and the worst HIGH, and everything after is incremental.
