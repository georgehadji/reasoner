# Model Capability per Preset Phase — August 2026

Research pass over all **50 presets × 47 routed models**, matching each routing role's
actual demand (token budget, temperature, context pressure, output type) against
current public capability evidence.

Sources: Artificial Analysis Intelligence Index v4.1.1 (Aug 2026 snapshot), Vectara
HHEM-2.3 hallucination leaderboard, SWE-bench Verified/Pro, EQ-Bench Creative Writing,
Perplexity SimpleQA/Search Arena, vendor benchmark cards. Prices verified against the
bundled catalogue (`domain/openrouter_models.json`, fetched 2026-08-16) and, where they
disagreed, against live OpenRouter model pages.

> **Status — applied 2026-08-18.** Tier A (all 5), Tier B (#6, #7, #10) and the
> mechanical Tier C swap (`article_critic`) are live in `domain/preset_registry.py`;
> the stale price comments in §5 are corrected in `infrastructure/llm/registry.py`.
> Verified: 0 bloc-diversity violations across 50 presets, all aliases resolve,
> `validate_presets.py` reports the same 4 pre-existing `unknown method` errors and no
> new ones; `pytest tests/unit/test_preset_bloc_diversity.py tests/test_presets.py
> tests/test_preset_validation.py tests/test_api_presets_models.py
> tests/test_article_presets.py` → **103 passed, 51 skipped**.
>
> Side fix: `test_all_preset_models_have_lab_entries` needed `qwen3.8-max` added to
> `harness_guard._MODEL_LABS`. That test was **already red** before this change —
> `kat-coder-air-v2.5` and `kat-coder-pro-v2.5` (coding-budget cascade, untouched here)
> were missing too. All three added, plus `kat-coder-pro-v2`.
>
> Note for anyone running the suite: `pytest.ini` hardcodes `-n auto --dist loadscope`,
> which on this box exhausts system handles (`OSError: WinError 1450`) and hangs for
> 20+ min. Pass `-n 0`; the same set then runs in 35s.
>
> **Not applied** (real cost/behaviour changes, need a call): `writing_draft` →
> `claude-fable-5` ($10/$50) and premium `primary` → `qwen3.8-max`.
>
> Two deviations from the recommendations as written, both to avoid a
> single model holding three critique roles in one preset:
> `coding-premium` `scoring` → `qwen3.8-max` (not `glm-5.2`, which already holds
> `meta_evaluator` and `verifier` there); premium `meta_evaluator` keeps `minimax-m3`
> per the §4 bloc note, since `scoring` took the CN slot with `glm-5.2`.

---

## 1. Headline finding

**The presets route to a previous generation.** The registry declares 222 aliases;
presets use 47. Every current-generation frontier model is registered and reachable but
routed to by **zero** presets:

`claude-opus-5` · `claude-fable-5` · `gpt-5.6-{sol,terra,luna}` (+ `-pro` siblings) ·
`gpt-5.5` · `grok-4.6` · `grok-4.20` · `gemini-3.7-flash` · `qwen3.8-max` · `kimi-k3` ·
`gemini-2.5-flash-lite` · `hermes-4-405b` · `inkling`

Meanwhile the four highest-traffic slots run on models that the Aug 2026 index scores at
the bottom of the routable set:

| Role | Slots | Current | AA Index | Best routable alternative | AA Index |
|---|---|---|---|---|---|
| `synthesis` | 41 | `gpt-4o-mini` | **6.7** | `gpt-5.6-luna` / `gemini-3.7-flash` | 51.2 / 56.0 |
| `stress_testing` | 20 (prem) | `grok-4.3` | **37.6** | `grok-4.6` / `grok-4.20` | 60.9 / 48 |
| `verifier` | 18 (prem) | `grok-4.3` | **37.6** | `grok-4.20` | 48 |
| `scoring` | 20 (prem) | `qwen3-max-thinking` | **~32** (est.) | `glm-5.2` | 52.6 |
| `deep_read` | 19 | `gemini-3.1-pro-preview` | **47.7** | `gemini-3.7-flash` | 56.0 |

`gpt-4o-mini` is the worst case: it is the **final user-facing voice in 41 of 50
presets**, it carries the largest output budget in the pipeline (`synthesis` = 32,768
tokens, 32× every critique role), and it has the **smallest context window on the premium
path** — 128K where every other premium model is 1M+.

---

## 2. What each role actually demands

Derived from `PHASE_TOKEN_BUDGETS` (`core/constants_limits.py`), `docs/Temperature
Values.txt`, and the phase prompt modules. This is what "most capable" has to mean
per role — a role that emits 1,024 tokens of structured JSON has nothing in common with
one that emits 32K of prose.

| Role | Out budget | Temp | Dominant demand | Cost driver |
|---|---|---|---|---|
| `synthesis` | **32768** | 0.5 | Long-form faithful prose, must ingest every prior phase | **output** |
| `coding_assemble` | 16384 | — | Whole-file code emission | output |
| `coding_generate` / `coding_tests` | 8192 | — | Code correctness | output |
| `coding_spec` / `coding_review` | 4096 | — | Spec precision / defect recall | balanced |
| `research` | 4096 | — | Grounded retrieval + citation | balanced |
| `destructive` | 2560 | 1.0 | Adversarial idea generation, diversity | balanced |
| `deep_read` | 2048 | — | **Long-context retrieval fidelity** | **input** |
| `fusion`, generators, `jury_generator` | 1536 | 1.0 | Divergent generation | balanced |
| `scoring`, `critique`, `stress_testing`, `verifier` | **1024** | 0.3–0.5 | Read a lot, emit short structured judgement | **input** |
| `prism_classify`, `search_disambiguation` | 256 | 0.3 | Cheap classification | input |

Two consequences that the current registry does not reflect:

1. **`synthesis` is the only role where output price dominates.** At the full 32K budget,
   output cost per run is $0.020 (`gpt-4o-mini`) → $0.039 (`gpt-5.6-luna`) → $0.061
   (`gemini-3.7-flash`) → $0.33 (`claude-sonnet-5`). The gap between the worst and best
   *routable* synthesis model is ~2¢/run — for a 44-point Intelligence Index swing.
2. **`scoring`/`verifier`/`meta_evaluator` are input-heavy and output-trivial.** Paying
   $3.90/M output for `qwen3-max-thinking` on a 1,024-token budget buys almost nothing;
   the binding constraint there is judge agreement and position-bias resistance, not
   generation quality.

---

## 3. Capability evidence

### 3.1 General reasoning — AA Intelligence Index v4.1.1, Aug 2026

Routable models only, ranked:

| Model | Index | $/M in | $/M out | Ctx | Routed today? |
|---|---|---|---|---|---|
| `claude-opus-5` | 63.0 | 5 | 25 | 1M | — |
| `claude-fable-5` | 62.1 | 10 | 50 | 1M | — |
| `grok-4.6` | 60.9 | 2 | 6 | 500K | — |
| `kimi-k3` | 59.7 | 3 | 15 | 1M | — |
| `gpt-5.6-sol` | 58.9 | 5 | 30 | 1.05M | — |
| `qwen3.8-max` | 58.1 | 2 | 6 | 1M | — |
| `gpt-5.5` | 56.3 | 5 | 30 | 1M | — |
| **`gemini-3.7-flash`** | **56.0** | **0.375** | **1.875** | **1M** | — |
| `grok-4.5` | 55.8 | 2 | 6 | 500K | — |
| `claude-sonnet-5` | 55.3 | 2 | 10 | 1M | ✅ 20× primary |
| `gpt-5.6-terra` | 55.0 | 1 | 6 | 1.05M | — |
| `deepseek-v4-pro` | 53.2 | 0.66 | 1.98 | 1.05M | ✅ 23× fusion |
| `glm-5.2` | 52.6 | 0.476¹ | 1.496¹ | 1M | ✅ 4 slots |
| `deepseek-v4-flash` | 51.8 | 0.08 | 0.16 | 1.05M | ✅ 25× fusion |
| `gemini-3.6-flash` | 51.6 | 0.75 | 3.75 | 1M | — |
| `gpt-5.6-luna` | 51.2 | 0.20¹ | 1.20¹ | 1.05M | — |
| `grok-4.20` | 48 | 1.25 | 2.50 | **2M** | — |
| `gemini-3.1-pro-preview` | 47.7 | 2 | 12 | 1M | ✅ 19× deep_read |
| `qwen3.7-max` | 46.7 | 1.48 | 4.42 | 1M | ✅ 3 slots |
| `minimax-m3` | 45.4 | 0.30 | 1.20 | 1M | ✅ 19× meta_eval |
| `kimi-k2-6` | 45.1 | 0.56 | 2.36 | 262K | ✅ 1 slot |
| `grok-4.3` | **37.6** | 1.25 | 2.50 | 1M | ✅ **42 slots** |
| `qwen3-max-thinking` | ~32 (est.) | 0.78 | 3.90 | 262K | ✅ **21 slots** |
| `ring-2.6-1t` | 31 | 0.075 | 0.625 | 262K | ✅ 23× stress |
| `mistral-large-3` | 15.9 | 0.50 | 1.50 | 262K | ✅ 4 slots |
| `gpt-4o-mini` | **6.7** | 0.15 | 0.60 | 128K | ✅ **44 slots** |

¹ live OpenRouter page; disagrees with the bundled snapshot — see §5.

Not on the index: `claude-haiku-4.5`, `qwen3.5-flash`, `qwen3.7-flash`, `hy3`, `sonar*`.

### 3.2 Role-specific evidence

**Long-context retrieval (`deep_read`).** RULER puts effective context at 50–65% of
advertised for most models; MRCR v2 shows a 30–60 point retrieval drop between 200K and
1M for every frontier model tested. `grok-4.20` is the exception with independently
described *tested* reliable retrieval across the full 2M window. For the 2,048-token
`deep_read` budget the input side is what matters, so `gemini-3.7-flash` (1M, $0.375)
dominates the incumbent `gemini-3.1-pro-preview` (1M, $2.00) on both index (+8.3) and
price (−81% in, −84% out), same US/Google bloc → invariants untouched.

**Hallucination / grounded verification (`verifier`, `post_synthesis_verify`,
`article_verifier`).** `grok-4.20` set a record 78% non-hallucination rate on AA
Omniscience — xAI explicitly traded raw index for reliability, which is exactly the
`verifier` job description and makes the index gap to `grok-4.6` irrelevant *for this
role*. On the Vectara HHEM summarization-faithfulness leaderboard the standout routable
model is `gemini-2.5-flash-lite` at **3.3% hallucination** (rank 3 of all models) at
$0.10/$0.40 — a far better budget verifier than the incumbent `qwen3.5-flash`. Caveat:
HHEM measures faithfulness-when-grounded, not verification skill; it is the right proxy
for "won't invent facts while checking", not for "will catch a subtle error".

⚠ `deepseek-v4-flash` — currently `fusion` in 25 presets and `scoring` in 20 — is
reported at the **highest hallucination rate measured (96%) on AA-Omniscience** knowledge
questions. That benchmark is closed-book recall, and `fusion`/`scoring` are grounded
tasks, so this is not disqualifying. It does argue against using it anywhere the model
must supply facts from its own weights.

**Judge quality (`scoring`, `meta_evaluator`, `article_critic`).** The 2026 large-scale
judge audit (21 judges, ~541K judgements) found raw agreement overstates chance-corrected
discrimination by 33–41pp, judge rankings move up to 14 positions across benchmarks, and
severe position bias coexists with high test–retest reliability. Practical reading: judge
choice should not be made on index alone, and `scoring` deserves a deliberate rubric +
position-swap rather than a bigger model. Claude Sonnet-class and GPT-5-class models sit
at the top for subjective rubrics with rich reasoning. `qwen3-max-thinking` at ~32 index
and $3.90/M output is the weakest justified choice in the premium block.

**Adversarial stress (`stress_testing`, `destructive`).** No public benchmark ranks
"finding flaws in a proposal" — red-teaming is explicitly a private-dataset problem in
2026. Best available proxies are agentic/adversarial suites. `ring-2.6-1t` scores poorly
on the general index (31) but posts AIME 2026 95.83, GPQA Diamond 88.27, and PinchBench
87.60 in agent mode, beating GPT-5.4 and Gemini 3.1 Pro on the latter — it is a
defensible budget stress-tester despite the headline number. Premium `grok-4.3` (37.6)
has no such defence; `grok-4.6` at 60.9 for $2/$6 or `grok-4.20` at 48 for the *identical*
$1.25/$2.50 both dominate it.

**Coding (`coding_*`).** SWE-bench Verified: `claude-fable-5` 95.0%, `deepseek-v4-pro`
80.6% (top open-weight), `deepseek-v4-flash` 79.0%, `claude-haiku-4.5` 73.3%. Verified is
near-ceiling and weakly discriminative; SWE-bench Pro separates better — Fable 5 80.3,
Opus 5 79.2, `qwen3.8-max` 67.7. The budget coding cascade (`qwen3-coder-flash` →
`kat-coder-pro-v2.5` → `laguna-xs-2.1` → …) is well-constructed and cross-lab; its
weakness is `coding_review` on `deepseek-v4-flash`, where defect recall matters more than
generation.

**Creative / long-form (`writing_draft`, `article_humanize`, `synthesis`).** EQ-Bench
Creative Writing Elo: `claude-opus-5` 2430, `kimi-k3` 2340, `gpt-5.6-sol` 2092.
`claude-fable-5` holds the highest tracked Arena Elo (1508) for long-form writing,
editing and tone-matching. The article presets already route `writing_draft` and
`article_humanize` to `claude-sonnet-5`, which is the right *family* — `claude-fable-5`
is the same family's writing specialist and is registered but unused.

**Web-grounded (`post_synthesis_verify`, `research` primary, `writing_factcheck`).**
`sonar-pro` SimpleQA F 0.858 vs `sonar` 0.773; `sonar-pro` has the lowest citation
hallucination rate among AI search platforms (37% CJR vs 67% ChatGPT Search). The
budget/premium split (`sonar` 26×, `sonar-pro` 24×) is evidence-aligned and needs no
change. One exception below.

---

## 4. Recommendations per role

Ranked by leverage (slots × capability delta). Bloc column confirms the two enforced
invariants (A: synthesis bloc ≠ scoring bloc; B: generators span ≥2 blocs) still hold.

### Tier A — high leverage, evidence-backed

| # | Role · slots | From | To | Why | Bloc |
|---|---|---|---|---|---|
| 1 | `synthesis` · 41 | `gpt-4o-mini` (6.7, 128K) | **`gpt-5.6-luna`** (51.2, 1.05M) | +44.5 index, 8× context, current gen. Costs +$0.02/run at full 32K output. | US→US ✅ |
| 2 | `deep_read` · 19 | `gemini-3.1-pro-preview` (47.7, $2/$12) | **`gemini-3.7-flash`** (56.0, $0.375/$1.875) | +8.3 index **and** −81%/−84% price, same 1M ctx, same bloc, 340 tok/s | US→US ✅ |
| 3 | `stress_testing` · 20 (prem) | `grok-4.3` (37.6) | **`grok-4.6`** (60.9, $2/$6) | +23.3 index on the adversarial role; xAI's current flagship | US→US ✅ |
| 4 | `verifier` · 18 (prem) | `grok-4.3` (37.6, 1M) | **`grok-4.20`** (48, 2M) | +10.4 index, **identical price**, 2× ctx, record 78% non-hallucination — the role's actual metric | US→US ✅ |
| 5 | `scoring` · 20 (prem) | `qwen3-max-thinking` (~32, $0.78/$3.90) | **`glm-5.2`** (52.6, $0.476/$1.496) | +20 index, −39% in / −62% out, keeps CN bloc so invariant A survives | CN→CN ✅ |

### Tier B — solid, smaller deltas

| # | Role · slots | From | To | Why |
|---|---|---|---|---|
| 6 | `verifier` · 20 (budget) | `qwen3.5-flash` ($0.065/$0.26) | **`gemini-2.5-flash-lite`** ($0.10/$0.40) | 3.3% HHEM hallucination — 3rd best measured; verification is the one role where faithfulness beats price |
| 7 | `meta_evaluator` · 20 (budget) | `qwen3.5-flash` ($0.065/$0.26) | **`qwen3.7-flash`** ($0.03/$0.13) | −54% price, newer gen, same 1M ctx, gains vision. Cheapest safe upgrade in the registry |
| 8 | `meta_evaluator` · 19 (prem) | `minimax-m3` (45.4) | **`gemini-3.7-flash`** (56.0) | +10.6 index at ~1.25× input price; but see bloc note below |
| 9 | `stress_testing` · 23 (budget) | `ring-2.6-1t` | *keep* | Index 31 is misleading; agent-mode benchmarks justify it at $0.075/$0.625 |
| 10 | `deep_read` · 1 (`research-budget`) | `sonar-pro-search` ($3/$15) | **`sonar`** ($1/$1) | The registry comment claims "$1/$1 per M" — that is `sonar`'s price. `research-budget` is currently routing to the joint most expensive model in the catalogue |

⚠ **Bloc note on #8:** premium `meta_evaluator` is the only CN model in several premium
presets besides `scoring`. Moving it to Google makes the premium block US-heavy. Invariant
A (synthesis vs scoring) still holds, and `meta_evaluator` is not in the enforced
generator set — but the *spirit* of the cross-bloc design argues for keeping it CN.
`glm-5.2` (52.6) is the better CN-preserving choice if #5 uses something else, otherwise
keep `minimax-m3`.

### Tier C — worth doing, narrow scope

| Role | From | To | Why |
|---|---|---|---|
| `writing_draft`, `article_humanize` (article-premium) | `claude-sonnet-5` | `claude-fable-5` | Highest tracked long-form/tone-matching Arena Elo (1508); same family, same bloc. $10/$50 confines this to the premium article path only |
| `article_critic` (premium) | `grok-4.3` | `grok-4.6` | Same swap as #3, critique role |
| `coding_review` (both tiers) | `deepseek-v4-flash` | `qwen3.8-max` (prem) / keep cascade (budget) | Review is defect-recall, not generation; SWE-bench Pro 67.7 vs the flash tier |
| `fusion` · 25 (budget) | `deepseek-v4-flash` | *keep* | 51.8 index at $0.08/$0.16 is the best value in the entire catalogue |
| `primary` · 20 (prem, alias `gemini-pro`) | → `claude-sonnet-5` (55.3) | consider `qwen3.8-max` (58.1, $2/$6) | Same price, +2.8 index, and it breaks the `gemini-pro`/`claude-sonnet` alias collision noted below |

### Leave alone

`sonar`/`sonar-pro` split (evidence-aligned), budget coding cascade (well-designed,
cross-lab), `ministral-8b` minimalist generator (role is deliberately small-model),
`hy3` (anti-hallucination design fits `article_verifier`/`article_critic` at $0.132/$0.528).

---

## 5. Data-integrity problems found

**Prices in the registry comments, the bundled catalogue, and live OpenRouter disagree —
three-way, on models that drive routing decisions.**

| Model | Registry comment | Bundled catalogue (08-16) | Live OpenRouter | Consequence |
|---|---|---|---|---|
| `glm-5.2` | $0.95/$3.00 | $1.19/$3.74 | **$0.476/$1.496** | `docs/openrouter-catalogue-2026-08.md` claims $0.308/$0.968 — a **fourth** number. Its "3× cheaper than documented" argument reaches the right conclusion from wrong data |
| `gpt-5.6-luna` | $0.10/$0.60 | **$0.20/$1.20** | $0.20/$1.20 (after an 80% drop) | The same doc bills the synthesis swap as "−33% input". It is actually **+33% input, +100% output** — still worth doing for +44.5 index, but not on cost grounds |
| `deepseek-v4-pro` | $0.435/$0.87 | **$0.66/$1.98** | — | 23 preset slots priced against a stale figure |
| `gemini-3.7-flash` | — | $0.375/$1.875 | $0.375/$1.875 (50% promo, ends 2026-12-31) | ✅ agrees — but the discount expires; recommendation #2 survives at list price ($0.75/$3.75) on index alone |

`PRICING_DB` loads the bundled snapshot, so `budget_ceiling`, `utility_scorer`, credit
metering and the `/estimate` endpoint are all currently wrong for `glm-5.2` (2.5× over)
and `gpt-5.6-luna`. Re-running `scripts/update_openrouter_catalogue.py` fixes the
snapshot; the comments need hand-editing or, better, generation from the catalogue.

**Two other defects:**

- `iterative-critique-budget` tags `ring-2.6-1t` as `# InclusionAI 🇺🇸`. inclusionAI is
  Ant Group — `bloc_of()` correctly returns **CN**, so the invariant checks are fine and
  only the comment lies. Still worth fixing: the comments are what a human reads when
  editing routing.
- The `gemini-pro` → `anthropic/claude-sonnet-5` alias collision (already noted in the
  Aug catalogue doc) means `multi-perspective-premium` runs `primary_id`,
  `perspective_cot`, `perspective_analysis` and `constructive` on one identical served
  model. `BlocDiversityConstraint` rule 4 only checks identical-model collisions among
  `_GENERATOR_ROLES`, and `primary`/`perspective_cot` are outside that set, so it passes
  validation. Recommendation Tier C (`primary` → `qwen3.8-max`) resolves it as a
  side-effect.

---

## 6. Method

- Role inventory computed directly from `domain/preset_registry.py` (50 presets, 47
  distinct aliases, 60 routing roles) joined against `bloc_of()` / `resolved_model_of()`
  so alias indirection (`gemini-pro` → Anthropic, `gemini-flash-lite` → Qwen) is resolved
  rather than assumed.
- Demand profile from `PHASE_TOKEN_BUDGETS`, `docs/Temperature Values.txt`, and phase
  prompt modules — capability is judged against what the role emits, not in general.
- Capability from public Aug-2026 benchmarks; where a role has no public benchmark
  (adversarial critique) that is stated rather than papered over with a proxy.
- Every recommendation checked against invariants A and B before inclusion.

**Not verified here:** no model was run. These are benchmark-and-price recommendations;
several incumbents were chosen for empirical reasons the registry records inline
(`claude-sonnet` dropped from `article_revise` after "2/3 empty responses";
`gpt-5.1-codex-mini` demoted for intermittent empty content). Those observations outrank
any index score and should be re-tested, not overridden on paper.
