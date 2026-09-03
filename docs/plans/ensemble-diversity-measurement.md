# Measured Ensemble Diversity — Implementation Plan

Implements the actionable items of [docs/ENSEMBLE_DIVERSITY.md](../ENSEMBLE_DIVERSITY.md)
(D0–D9), derived from Aitchison et al., arXiv:2606.29661v1.

Baseline: `main` @ `3ebeb5e` (2026-09-03). Citations verified against that tree.

**The thesis in one line.** Every diversity guarantee in this codebase today is
*asserted* from vendor and bloc metadata; none is *measured* against model output. This
plan builds the measurement, ships it as observability, and only then proposes turning it
into a gate.

**What this plan deliberately does not do.** It does not import the paper's model
rankings, its `a*₅` allocation, or its 1.7 BP figure. Those are one in-sample fit on one
tournament with models we do not run (see [ENSEMBLE_DIVERSITY §2](../ENSEMBLE_DIVERSITY.md)).
It does not re-partition `_VENDOR_BLOC`. It does not touch Phase 2 perspective routing —
free-text perspectives have no shared scalar and the paper's method does not reach them.

---

## 0. Scope and design principles

### 0.1 Bound by

| Constraint | Source | How this plan honours it |
|---|---|---|
| Domain has no outer dependencies | `CLAUDE.md` §1 | Divergence value objects and the pure metric functions live in `domain/divergence.py`; they import nothing outside `domain/` |
| Application → Domain/Core only | `.importlinter` | The matrix service sits in `application/services/`, consumes `core/ports/divergence_port.py`; the store is infrastructure behind that port |
| Infrastructure implements Core ports | `CLAUDE.md` §1 | `MeasuredDivergenceConstraint` implements the existing `RoutingConstraintPort`, exactly as the five current constraints do |
| `method_state` accessed via `.get()`, never subscript | `CLAUDE.md` §5 | Delphi capture reads `state.delphi_state.get("round_1_estimates", [])` — the existing accessor |
| `--resume` on older state files | `CLAUDE.md` §5 | No new `PipelineState` fields. Paired observations leave via the event bus, never via state |
| All LLM output through `parsing.extract_json()` | `CLAUDE.md` §5 | D3 reads already-parsed `estimate_value`; it adds no new parsing |
| Phase-2 blind independence | MIND_VIRUS M6 | Untouched. Nothing here lets a generator see a sibling |
| Recalled memory never enters a system prompt | MIND_VIRUS M1 | Untouched. This plan writes no memory |
| Preset routing keys must be in `_KNOWN_ROUTING_ROLES` | [preset_core.py:293-298](../../src/reasoner/domain/preset_core.py) | D0 adds no new roles — `expert_1..4` are **already** declared valid; only the preset entries are missing |

### 0.2 Patterns reused, not invented

| Need | Existing pattern | Reference |
|---|---|---|
| A routing rule that can veto an assignment | `RoutingConstraintPort` + `ConstraintResolver` | [constraint_resolver.py](../../src/reasoner/application/services/constraint_resolver.py) |
| Ship a constraint as observability before gating | Propagation-resistance shipped soft — "0/49 presets clear any floor, so that constraint is observability, not a gate" | `MIND_VIRUS_IMPLEMENTATION_PLAN.md` STATUS |
| Per-call telemetry behind a port | `LLMCallTelemetry` + `CallTelemetryPort` + `call_telemetry_store.py` | [telemetry.py](../../src/reasoner/domain/telemetry.py) |
| Emit analytics off the hot path | `event_emission_service.py` — "kept out of `PipelineState`" | `map-application` |
| Immutable analytic value objects | Frozen dataclasses in `domain/telemetry.py` | same |
| Mode ladder for risky routing changes | ACR's `shadow` → `advisory` → `adaptive` | [adaptive_routing.py:61-66](../../src/reasoner/application/services/adaptive_routing.py) |

### 0.3 How this avoids the paper's two methodological failures

Non-negotiable, because they are the reason we are measuring rather than importing:

1. **Held-out evaluation.** Any allocation or replaceability claim must be computed on
   runs not used to fit it. D7 splits by run timestamp — fit on the earlier window,
   report on the later. The paper takes the argmax over 101 allocations *on the test set*
   and then reports replaceability on the same data.
2. **Bootstrap confidence intervals on every reported number.** D5 and D7 report
   `(estimate, ci_low, ci_high, n_pairs)` or they report nothing. The paper reports no
   intervals and concedes it. A divergence estimate with `n < MIN_PAIRS` is surfaced as
   `UNKNOWN`, never as a value.

---

## D0 — Fix Delphi expert routing — **SHIPPED**

**The defect.** All four Delphi "independent forecasters" resolve to the preset primary.
Full evidence in [ENSEMBLE_DIVERSITY §4](../ENSEMBLE_DIVERSITY.md). Summary:
`run_delphi_round1_phase` calls `role=f"expert_{i+1}"`
([delphi_phases.py:15-26](../../src/reasoner/application/flows/delphi_phases.py)); no
preset defines those keys ([preset_registry.py:380-410](../../src/reasoner/domain/preset_registry.py));
`ProviderRouter.resolve` falls through to primary for unmapped roles
([router.py:349-354](../../src/reasoner/infrastructure/llm/router.py)); `ACR_MODE`
defaults to `shadow`, so static routing governs.

**Changes**

1. `domain/preset_registry.py` — add `expert_1`–`expert_4` to `delphi-budget` and
   `delphi-premium` routing, four distinct models spanning ≥2 blocs. Follow the existing
   comment convention (flag, vendor, price, context, rationale).
2. `infrastructure/llm/constraints/bloc_diversity.py` — add `"expert_1"`, `"expert_2"`,
   `"expert_3"`, `"expert_4"` to `_GENERATOR_ROLES` ([line 22](../../src/reasoner/infrastructure/llm/constraints/bloc_diversity.py)). This makes Rule 4 ("no two
   generator roles resolve to the identical underlying model") fire on Delphi, which is
   what it was written for. Note Rule 3 caps a bloc at 2 generator roles — with four
   experts this forces a genuine cross-bloc panel.
3. ~~Add a test that fails on any role in `_KNOWN_ROUTING_ROLES` unrouted by every
   preset.~~ **Dropped — the premise was wrong.** 37 of the 86 known roles are routed
   by no preset (`hypergate_*`, `subagent_*`, `classification`, `decomposition`,
   `perspective`, the `article_*`/`sot_*`/`pot_*` families), and falling through to
   `primary_id` is the intended behaviour for them. Being unrouted is not the defect.
   The defect is narrower: **a role whose prompt asserts independence from its sibling
   roles must resolve to a distinct model.** Delphi's panel is the case that matters;
   the test asserts that invariant instead, and its docstring records why the blanket
   rule was rejected.

**As built.** Both presets span 3 blocs / 4 labs, ≤2 slots per bloc, every slot a
distinct served model (`test_preset_model_uniqueness` requires distinctness against
`primary_id` and every other slot in the same preset, so the four picks had to avoid
eight models already in use):

| Slot | `delphi-budget` | `delphi-premium` |
|---|---|---|
| `expert_1` | `gpt-oss-120b` 🇺🇸 OpenAI | `nemotron-3-ultra` 🇺🇸 NVIDIA |
| `expert_2` | `ministral-3b` 🇪🇺 Mistral | `gemini-pro-real` 🇺🇸 Google |
| `expert_3` | `mimo-v2.5` 🇨🇳 Xiaomi | `qwen3-max-thinking` 🇨🇳 Qwen |
| `expert_4` | `llama-4-scout` 🇺🇸 Meta | `mistral-large-3` 🇪🇺 Mistral |

**Tests** — `tests/unit/test_delphi_expert_routing.py`, 10 cases: every expert slot is
routed; the four resolve to distinct served models; the panel spans ≥2 blocs with ≤2
per bloc; `expert_*` are in `_GENERATOR_ROLES`; rule 4 emits a hard violation on a
duplicated expert; a valid cross-bloc panel passes clean.

**Cost — the risk did not materialise.** Measured against `PRICING_DB`, not the
registry comments (they disagree, and `PRICING_DB` is what bills):
`delphi-premium` is **−34% input / −26% output** versus the 4× `claude-sonnet` it
collapsed onto; `delphi-budget` is **+49% input / −14% output** versus 4×
`qwen3.5-flash`, and round-1 generation is output-dominated, so the net is roughly
neutral. No budget-tier exemption was needed.

Registry price comments found wrong while costing this were fixed in a follow-up:
`llama-3.3-70b` ($0.13/$0.40 → $0.71/$0.71 — dropped as a candidate because of it),
`gpt-5.6-terra`/`-terra-pro` ($1/$6 → $2/$12), `gpt-5.6-sol`/`-sol-pro` ($5/$30 →
$2/$10), `nemotron-3-ultra` ($0.60/$3.60 → $0.50/$2.20) and DeepSeek v4-flash
($0.0615/$0.1229 → $0.0886/$0.1772). ~18 more remain: cost any new slot from
`PRICING_DB`, and note `glm-5.2` is the case where `PRICING_DB` itself is disputed.

---

## D1 — Divergence value objects and metrics *(domain, pure)*

New: `src/reasoner/domain/divergence.py`. No imports outside `domain/`.

```
@dataclass(frozen=True)
class PairedObservation:
    run_id, item_id, role_a, role_b, model_a, model_b
    value_a: float, value_b: float      # normalised to [0, 1]
    source: str                          # "delphi_round1" | "shadow_scorer"
    preset_id, method, timestamp

@dataclass(frozen=True)
class PairwiseDivergence:
    model_a, model_b
    js_divergence: float                 # paper-faithful
    rank_agreement: float | None         # Spearman ρ, decision-relevant (§5)
    ci_low: float, ci_high: float
    n_pairs: int
    sufficient: bool                     # n_pairs >= MIN_PAIRS
```

Pure functions, all total and defensive on degenerate input:
- `js_divergence_bernoulli(p, q)` — symmetric JS between `Bernoulli(p)` and
  `Bernoulli(q)`, the paper's metric. Clamp inputs away from `{0,1}`.
- `normalise(value, lo, hi)` — maps a 0–10 critique score or a raw Delphi estimate into
  `[0,1]`. **Delphi estimates are unbounded reals**, so normalisation must be per-item
  (min-max across that question's four experts), not global. Document that this makes
  Delphi JS a *relative-spread* measure, not a probability divergence.
- `spearman_rho(a, b)` — rank agreement over a candidate list.

Thresholds (`core/constants_limits.py`): `MIN_PAIRS_FOR_DIVERGENCE = 30`,
`DIVERGENCE_FLOOR = 0.05` (initial, soft-only).

**Tests** (`tests/unit/test_divergence_metrics.py`): JS symmetry; `JS(p,p) == 0`;
JS maximal at `(0,1)`; clamping; Spearman against a known fixture; empty/single-element
input returns `None`, never raises.

---

## D2 — Port and store

- `core/ports/divergence_port.py` — `DivergencePort` protocol: `record(obs)`,
  `pairs_for(model_a, model_b, since)`, `all_pairs(since)`. Mirrors `telemetry_port.py`.
- `infrastructure/telemetry/divergence_store.py` — SQLite implementation alongside
  [`call_telemetry_store.py`](../../src/reasoner/infrastructure/telemetry/call_telemetry_store.py).
  Reuse its connection handling and its failure posture: **recording must never raise
  into the pipeline**.
- `migrations/` — one table, indexed on `(model_a, model_b, timestamp)`.

**Tests** (`tests/integration/test_divergence_store.py`), modelled on
`test_call_telemetry_store.py`: round-trip, index usage, store failure does not propagate.

---

## D3 — Capture paired observations

Paired observations do not exist today and must be created
([ENSEMBLE_DIVERSITY §3](../ENSEMBLE_DIVERSITY.md)). Two sources.

**D3a — Delphi round 1 as a natural experiment (free, after D0).**
Four distinct models answer an identical prompt and emit `estimate_value`. That is
`C(4,2) = 6` paired observations per Delphi run at zero marginal cost. Emit after
`run_delphi_round1_phase` populates `round_1_estimates`, via the event bus — not from
inside the phase function, and not through `PipelineState`.

Guard: only pair experts whose `estimate_value` is numeric and non-null. Qualitative
estimates (`estimate_value: null`) are skipped, not coerced.

**D3b — Shadow scorer probe (optional, costed).**
On a sampled fraction of multi-perspective runs, a second `scoring`-class model from a
different bloc re-scores the *same* candidate set. Its output is logged and **discarded**
— it never influences ranking, synthesis, or cost accounting for the run's result.

- Setting: `DIVERGENCE_PROBE_RATE` (default `0.0` — **off**). Opt-in only.
- Runs after Phase 3 completes; failure is swallowed.
- Yields both JS (on normalised scores) and Spearman ρ (on candidate ordering) — the
  distinction that §5 of the note argues is decision-relevant.
- Must route through `run_metering` so probe cost is attributed, not hidden.

**Tests**: Delphi capture emits 6 observations for 4 numeric estimates, 0 for all-null,
3 for two-numeric; probe at rate 0.0 makes no LLM call; probe failure leaves
`state.scores` byte-identical.

---

## D4 — Divergence matrix service *(application read model)*

`application/services/divergence_matrix_service.py` — consumes `DivergencePort`,
produces `dict[tuple[str, str], PairwiseDivergence]` with bootstrap CIs and
`sufficient` flags. Pairs below `MIN_PAIRS_FOR_DIVERGENCE` are returned marked
insufficient — **never silently treated as zero divergence**, which would be the most
dangerous possible failure mode (an unmeasured pair looking maximally similar).

Surface read-only at `/admin/divergence` following the `get_harness_scorecard` query
pattern.

---

## D5 — `MeasuredDivergenceConstraint` — soft

`infrastructure/llm/constraints/measured_divergence.py`, implementing
`RoutingConstraintPort`. Given a proposed role→model assignment, look up measured
divergence for each generator pair and emit `severity="soft"` violations for pairs below
`DIVERGENCE_FLOOR` with sufficient data.

**Soft is the whole point.** `ConstraintResolver._check_all` collects every violation but
`resolve` only acts on `severity == "hard"`
([constraint_resolver.py](../../src/reasoner/application/services/constraint_resolver.py)),
so shipping soft changes **zero** routing behaviour while making the signal visible. This
is the same posture the propagation-resistance constraint shipped in.

Register in `_get_default_constraints()`.

**Tests**: soft violation for a below-floor measured pair; **no** violation for an
insufficient-data pair; `ConstraintResolver.resolve` returns an identical assignment with
and without the constraint registered (proves zero behaviour change).

---

## D6 — Replaceability report *(offline)*

`scripts/divergence_report.py` — the paper's Δ_m on our own data, with the two fixes from
§0.3: a held-out temporal split and bootstrap CIs. Reports per-model contribution to
observed ensemble quality, and flags any pair whose measured divergence contradicts its
bloc assignment — the empirical test of the `_VENDOR_BLOC` question the note declines to
answer from the paper alone.

Output is a report, not a routing change.

---

## D7 — Promotion to a hard gate *(gated, not scheduled)*

Flip `MeasuredDivergenceConstraint` to `severity="hard"` **only** when all hold:

1. ≥ `MIN_PAIRS_FOR_DIVERGENCE` observations for every pair among whitelisted models
   routinely co-assigned to generator roles.
2. D6 shows a held-out quality difference with a CI excluding zero.
3. A dry run over all 48 presets reports how many would be forced to re-route — the
   propagation-resistance precedent (0/49 presets cleared the floor) is the warning here.

If (3) shows widespread re-routing, **raise the floor or keep it soft**. Do not ship a
constraint that silently rewrites every preset.

---

## D8 — ADR-004 amendment

After D6 produces real numbers, add a "Measured vs. asserted" section to
[adr/004-cross-lab-routing.md](../adr/004-cross-lab-routing.md) recording which clauses
survived measurement. Amending before D6 would replace one unverified claim with another
— see [ENSEMBLE_DIVERSITY §7](../ENSEMBLE_DIVERSITY.md).

---

## Sequencing and effort

| WS | Depends on | Effort | Ship independently? |
|---|---|---|---|
| D0 | — | S | **Shipped** |
| D1 | — | S | Yes (pure, no wiring) |
| D2 | D1 | S | Yes |
| D3a | D0, D2 | M | Yes |
| D3b | D2 | M | Yes, default-off |
| D4 | D2 | M | Yes |
| D5 | D4 | S | Yes, soft = no-op |
| D6 | D3, D4 | M | Yes |
| D7 | D6 | S | **Gated — criteria above** |
| D8 | D6 | S | Yes |

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| ~~D0 raises budget-Delphi cost past target~~ | Closed | Measured: premium −34%/−26%, budget +49% input / −14% output, net ≈ neutral |
| Insufficient data forever — Delphi is a low-traffic method | **Medium-High** | D3b probe is the volume source; if Delphi traffic is negligible, D6 may never reach significance. **Accept this outcome rather than lowering `MIN_PAIRS`** |
| Divergence measured on Delphi estimates does not generalise to critique scoring | Medium | Store `source` on every observation; never pool `delphi_round1` and `shadow_scorer` pairs without checking they agree |
| Probe cost is unattributed | Medium | Route through `run_metering`; default rate 0.0 |
| Optimising for divergence degrades accuracy | **High** (the paper's own blind spot, §2) | Constraint is a floor on diversity, never an objective to maximise. Utility ranking still governs selection; diversity only vetoes |
