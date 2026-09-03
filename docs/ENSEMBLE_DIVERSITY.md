# Ensemble Diversity in Reasoner's Model Routing

Research note. Maps *Diversity is the Strength of the AI Crowd* (Aitchison, Jeen,
Shevlane, Day — Mantic Technologies; ICML 2026 Workshop on Forecasting as a New
Frontier of Intelligence, arXiv:2606.29661v1) onto Reasoner's routing architecture,
and separates the parts that transfer from the parts that do not.

Status: **D0 is implemented** — the Delphi routing defect in §4 is fixed. Everything
else here is analysis only. The §4 defect description is deliberately kept in the
present tense of its discovery, because it is the evidence for the fix.
Code references verified against `main` @ `3ebeb5e` (2026-09-03).

Companion build plan: [plans/ensemble-diversity-measurement.md](plans/ensemble-diversity-measurement.md).
Amends: [adr/004-cross-lab-routing.md](adr/004-cross-lab-routing.md) — see §7.

---

## 1. What the paper actually establishes

**Setup.** 113 binary questions from the Metaculus AI Benchmark Q2 2025 tournament,
resolved May–July 2025. Five forecasters — *Gemini 3 Pro*, *GPT-5*, *Grok 4*,
*Kimi K2.5*, and *FT-gpt-oss-120b* (an RL fine-tune of `gpt-oss-120b` on a forecasting
training set disjoint from the test set) — each wrapped in identical retrieve-then-predict
scaffolding, 3 samples per model per question. Scored with the Metaculus baseline score
(uniform 50% earns 0 points, perfect foresight 100), a strictly proper rescaled log
score. Aggregation is a weighted mean clipped to `[0.05, 0.95]`.

The question asked is the one a router actually faces: **given a fixed sample budget,
which model forecasts should be combined?**

| Finding | Reported effect | Design implication |
|---|---|---|
| The optimal budget allocation never concentrates on one model | At *B*=5, `a*₅ = (FT: 2, Gemini: 1, GPT-5: 1, Grok 4: 1, Kimi: 0)` | "Spend the budget on the strongest model" is the wrong default |
| **Solo accuracy does not predict ensemble contribution** | *Grok 4* is least-replaceable (Δ ≈ 1.7 BP) while ranking only **third** in solo score | A router that ranks candidates by solo quality systematically under-weights the decorrelated model |
| Frontier models make tightly correlated predictions | *GPT-5* and *Kimi K2.5* sit at low JS divergence from *Gemini 3 Pro*; *Grok 4* and the fine-tune sit far out | **Vendor and geography are poor proxies for error correlation** — see §4 |
| Two frontier-cluster members are interchangeable | Δ_GPT-5 and Δ_Gemini each < 0.1 BP | Swapping one cluster member for another buys ≈ nothing |
| The gain comes from *leaving* the cluster | On the 3-way simplex, moving along the GPT-5–Gemini edge gains ≤ 0.6 BP over the better corner; moving toward the FT vertex gains ≈ 2.7 BP | Diversity is worth ~4.5× more than intra-cluster mixing here |
| Theory is settled, not novel | Krogh & Vedelsby (1994) ambiguity decomposition; Wood et al. (2023, *JMLR* 24(359)) extend it to Bregman losses, covering the log score | `ensemble error = mean member error − diversity` |
| Prior art on scale | Schoenegger et al. (2024, *Science Advances*) — 12 frontier models ≈ a tournament of ~900 human forecasters | Ensembling LLM forecasts already works; this paper is about *allocation* |

The theoretical contribution is nil — the ambiguity decomposition is 30 years old. The
contribution is **empirical**: the claim that categorical intuitions about which models
are "different" are measurably wrong.

---

## 2. What to trust, and what not to

The paper is a 4-page workshop note. Its weaknesses are load-bearing for anything we
build on it.

| Concern | Severity | Assessment |
|---|---|---|
| **The optimum is selected in-sample.** All 101 valid *B*=5 allocations are scored on the test set, the argmax is taken, and replaceability Δ_m is then computed on that same set. No held-out split, no nested CV | **High** | Classic winner's curse. The reported margin over uniform allocation is inflated by an unquantified amount. **UNKNOWN** how much of Δ_Grok ≈ 1.7 BP survives out-of-sample |
| **No confidence intervals.** N=113, R=3 | **High** | The authors retreat to "the ranking is the robust result, magnitudes indicative". Under in-sample selection that defence is backwards — the *ranking* is what selection distorts first |
| **JS divergence cannot separate complementary error from noise** | Medium | The decomposition's two terms are coupled: a miscalibrated model maximises diversity and destroys accuracy. The title elides the joint constraint. Their own data is fine (Grok scores comparably) but the *prescription* as stated does not carry |
| **ε = 0.05 clipping is an intervention, not a detail** | Medium | Bounding to [0.05, 0.95] caps log-score penalties on near-certain questions, compressing between-model differences. Robustness is asserted, not shown |
| **The FT model's top weight is an accuracy result** | Medium | It was RL-trained on same-distribution Metaculus questions. Its JS distance from the cluster is confounded with that training |
| Single tournament, single quarter, binary questions only | Medium | Correlation structure among frontier LLMs is time-varying and likely domain-dependent |

**What we should carry forward — INFERENCE, at moderate confidence:**

1. Error correlation between models is real, large, and **not predicted by vendor identity**.
2. Ranking by solo quality under-weights decorrelated members. This is a *structural*
   claim about optimisation, backed by 30-year-old theory, not by N=113.

**What we should not carry forward:**

3. The specific model rankings, the 1.7 BP figure, or `a*₅` itself. These are one
   in-sample fit on one tournament with models we do not run.

The correct response to this paper is therefore **not** to adopt its numbers. It is to
**measure the same quantity on our own traffic** — which is what the companion plan does.

---

## 3. Reasoner's exposure map

Diversity matters only where several models' outputs are *combined*. Reasoner's
combination points, scored on whether the paper's argument applies:

| Surface | Same item scored? | Distinct models? | Comparable scalar? | Diversity enforced? | Measured? |
|---|---|---|---|---|---|
| **Delphi round 1** — 4 "independent forecasters" | ✅ identical prompt | ❌ **all resolve to `primary`** (§4) | ✅ `estimate_value` | ❌ not in `_GENERATOR_ROLES` | ❌ |
| Phase 2 perspectives | ❌ different lenses by design | ✅ per-role routing | ❌ free text | ✅ bloc + no-repeat-lab | ❌ |
| Phase 3 critique scoring | n/a — a single `scoring` role scores every candidate | ❌ one scorer per run | ✅ 0–10 per candidate | ✅ synthesis bloc ≠ scoring bloc | ❌ |
| Critique sub-agents (`bias`, `logic`, `evidence`, `counterfactual`) | ❌ different lenses | ✅ own `ROLE` each | partial | — | ❌ |
| Jury generator / critic / verifier / meta-evaluator | ❌ different roles | ✅ | ✅ | ✅ | ❌ |

Two observations follow.

**Nothing is measured.** Every diversity guarantee in the codebase is *categorical* —
asserted from vendor and bloc metadata, never verified against output. That is precisely
the assumption the paper falsifies.

**The only clean measurement substrate is Delphi round 1** — and it is currently
mis-wired. Everything else either scores different items (perspectives, sub-agent lenses)
or uses a single model (Phase 3 scoring), so no pairwise divergence can be computed from
existing telemetry. `LLMCallTelemetry.critique_score`
([telemetry.py:44](../src/reasoner/domain/telemetry.py)) is per-call; no two calls in a
run score the same object. **Paired observations do not exist and must be created.**

---

## 4. The Delphi finding — the paper's failure mode, in production

**VERIFIED.** `run_delphi_round1_phase` fans out four calls with
`role=f"expert_{i+1}"` on the same prompt
([delphi_phases.py:15-26](../src/reasoner/application/flows/delphi_phases.py)).
`expert_1`–`expert_4` are declared valid routing roles
([preset_core.py:42-46](../src/reasoner/domain/preset_core.py), marked "Sprint 3 — B5")
and are mapped to the `generate` task class for ACR
([role_requirements.py:278-281](../src/reasoner/application/services/role_requirements.py)).

But **no preset defines them.** `delphi-budget` and `delphi-premium`
([preset_registry.py:380-410](../src/reasoner/domain/preset_registry.py)) route
`synthesis`, `fusion`, `meta_evaluator`, `scoring`, `stress_testing`, `verifier` and
`post_synthesis_verify` — and no `expert_*` key. `ProviderRouter.resolve` falls through
to the primary for any unmapped role
([router.py:349-354](../src/reasoner/infrastructure/llm/router.py); the class docstring
at line 279 states this explicitly).

`ACR_MODE` defaults to `"shadow"` — "No impact on actual routing. Default — safe for
production" ([adaptive_routing.py:62-63](../src/reasoner/application/services/adaptive_routing.py),
[settings.py:401](../src/reasoner/core/settings.py)) — so the static preset governs.

**Consequence:** all four Delphi "independent experts" are the same model —
`qwen3.5-flash` on budget, `claude-sonnet` on premium. The panel is four temperature
samples from one model. The prompt tells each one "You are Expert *N* of 4 independent
forecasters… Do NOT anchor to any consensus"
([delphi.py:20-32](../src/reasoner/phases/delphi.py)), and the aggregation phase then
computes a median, an IQR and an outlier over those four samples as though they were
independent panellists.

This is exactly the allocation the paper argues against — the entire budget drawn from
one model — implemented in a method tagged `"forecasting"`, on the paper's own task.
The spread the aggregator reports is sampling noise, not disagreement, so the IQR
understates real uncertainty and the "outlier expert" is an artefact.

`BlocDiversityConstraint` cannot catch this: `_GENERATOR_ROLES`
([bloc_diversity.py:22-27](../src/reasoner/infrastructure/llm/constraints/bloc_diversity.py))
lists the perspective, debate and generator roles but **not** `expert_*`. Rule 4 ("no
two generator roles resolve to the identical underlying model") is written for exactly
this failure and never fires here.

### 4.1 Fixed (D0)

Both Delphi presets now route four distinct models, and `expert_1..4` were added to
`_GENERATOR_ROLES` so rule 4 covers the panel it was written for.

| Slot | `delphi-budget` | `delphi-premium` |
|---|---|---|
| `expert_1` | `gpt-oss-120b` 🇺🇸 OpenAI | `gpt-5.6-terra` 🇺🇸 OpenAI |
| `expert_2` | `ministral-3b` 🇪🇺 Mistral | `gemini-pro-real` 🇺🇸 Google |
| `expert_3` | `mimo-v2.5` 🇨🇳 Xiaomi | `qwen3-max-thinking` 🇨🇳 Qwen |
| `expert_4` | `llama-4-scout` 🇺🇸 Meta | `mistral-large-3` 🇪🇺 Mistral |

Both panels span 3 blocs and 4 labs, with ≤2 slots per bloc.

**The cost objection did not survive measurement.** Per `PRICING_DB` (the billing
source of truth — several registry price comments disagree with it and are wrong),
against the single model each panel previously collapsed onto:

| | input | output |
|---|---|---|
| `delphi-budget` vs 4× `qwen3.5-flash` | +49% | **−14%** |
| `delphi-premium` vs 4× `claude-sonnet` | **−34%** | **−26%** |

Premium is strictly cheaper. Budget is output-cheaper and input-dearer, and round-1
generation is output-dominated, so the net is roughly neutral — no budget-tier
exemption was needed. Regression coverage:
`tests/unit/test_delphi_expert_routing.py`.

---

## 5. What transfers to Reasoner, and what does not

The paper measures divergence between **scalar probability forecasts**. That constrains
transfer sharply.

**Transfers cleanly** — same mathematical object:
- Delphi round-1 `estimate_value` (numeric, same question, already median/IQR-aggregated).
- Phase 3 critique scores (0–10 per candidate), *if* two models ever score the same
  candidate set — which today they do not.

**Does not transfer** — Phase 2 perspective generation. Perspectives are free text and
are deliberately assigned *different lenses* (constructive / destructive / systemic /
minimalist), so there is no shared scalar to correlate. The paper's own footnote 1
concedes the point from the other direction: "the reasoning traces that produce them may
differ" even when the probabilities agree. Two models with near-identical forecast
distributions may still write genuinely different analyses.

**HYPOTHESIS, untested:** semantic-embedding divergence between perspective texts is the
analogous quantity for Phase 2. Reasoner already has embedding search in the Neuro L3
tier, so the machinery exists. This note does **not** claim the paper supports it — it
does not.

**A caveat that cuts against the whole programme.** Phase 3 uses critique scores only to
*rank* candidates (`state.candidates.sort(...)`,
[perspective_phases.py:283-284](../src/reasoner/application/flows/perspective_phases.py)).
Two scorers that disagree on absolute scores but agree on ordering are, for our purposes,
identical — while JS divergence would call them diverse. **Rank agreement, not
distributional divergence, is the decision-relevant metric for Phase 3.** The plan
therefore logs both.

---

## 6. Implications, ranked by expected value

| # | Implication | Confidence | Cost |
|---|---|---|---|
| 1 | ~~Route Delphi's four experts to four distinct models~~ — **shipped (§4.1)** | **VERIFIED** defect, now fixed | Done |
| 2 | **Measure pairwise divergence on our own traffic** rather than importing the paper's rankings | INFERENCE — the paper's own weaknesses (§2) argue for this | Medium |
| 3 | **Treat solo-quality ranking as a known bias** in `UtilityScorer`; diversity is pairwise and belongs in the constraint layer, not the utility scalar | INFERENCE, backed by the decomposition | Low (design) |
| 4 | Re-examine the geopolitical bloc partition once measured data exists | HYPOTHESIS — see §4 caveat below | Deferred |
| 5 | Embedding-divergence for Phase 2 perspectives | HYPOTHESIS, unsupported by this paper | Deferred |

**On implication 4 — do not act on it yet.** `bloc_of`
([registry.py:663-668](../src/reasoner/infrastructure/llm/registry.py)) partitions models
US / CN / EU / OTHER. Under the paper's Figure 1, that partition disagrees with measured
correlation on exactly the two models that matter: *Kimi K2.5* (`moonshotai` → `"CN"`)
clusters *with* the US frontier models, while *Grok 4* (`x-ai` → `"US"`) is the outlier.
So the geopolitical axis would call Kimi the diversity win and Grok interchangeable —
backwards on both counts, **if** the paper's clustering generalises.

That "if" is doing real work. Re-partitioning `_VENDOR_BLOC` from a single in-sample
N=113 result would be exactly the error §2 warns about. The bloc partition also serves a
second purpose — training-data provenance and supply-chain independence — which measured
output correlation does not capture and should not override. **Recommendation: keep the
bloc constraint, add a measured constraint alongside it, and revisit only when our own
divergence matrix has meaningful sample counts.**

---

## 7. Relationship to ADR-004

[ADR-004](adr/004-cross-lab-routing.md) records the cross-lab decision. Two of its
clauses are affected:

- **Clause 3** ("Phase 2 must use ≥3 different labs in Budget, ≥4 in Premium") counts
  *labs*, and the paper's finding is that lab count is not the quantity of interest.
  The clause is not wrong — lab diversity is a reasonable prior in the absence of
  measurement — but it is **unverified**, and Delphi (§4) shows the counting is not
  applied uniformly across methods.
- **Clause 4** ("the scorer must be from a different ecosystem than the dominant
  generator") is the clause the paper most directly supports, for the reason it gives:
  a scorer correlated with the generator adds little independent signal.

ADR-004 should be amended with a "Measured vs. asserted" section once the plan's D4
lands, not before. Amending it now would replace one unverified claim with another.

---

## 8. References

- Aitchison, M., Jeen, S., Shevlane, T., Day, B. *Diversity is the Strength of the AI
  Crowd.* ICML 2026 Workshop on Forecasting as a New Frontier of Intelligence.
  arXiv:2606.29661v1.
- Krogh, A., Vedelsby, J. *Neural network ensembles, cross validation, and active
  learning.* NeurIPS 1994. — the ambiguity decomposition.
- Wood, D., Mu, T., Webb, A. M., Reeve, H. W. J., Luján, M., Brown, G. *A unified theory
  of diversity in ensemble learning.* JMLR 24(359):1–49, 2023. — extends the
  decomposition to Bregman losses, including the log score.
- Schoenegger, P., Tuminauskaite, I., Park, P. S., Bastos, R. V. S., Tetlock, P. E.
  *Wisdom of the silicon crowd: LLM ensemble prediction capabilities rival human crowd
  accuracy.* Science Advances 10(45), 2024.
- Halawi, D., Zhang, F., Yueh-Han, C., Steinhardt, J. *Approaching human-level
  forecasting with language models.* NeurIPS 2024. arXiv:2402.18563.
- Gneiting, T., Raftery, A. E. *Strictly proper scoring rules, prediction, and
  estimation.* JASA 102(477):359–378, 2007.

**Citation provenance.** The five supporting references above are established prior work
and are cited here as the paper cites them. The primary paper itself
(arXiv:2606.29661v1) was supplied as a local document and has **not** been independently
retrieved or verified against arXiv — treat its reported figures as
*as-reported*, consistent with the reliability assessment in §2.
