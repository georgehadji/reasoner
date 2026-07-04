# Multi-Perspective Pipeline — Model Characteristics Per Phase

> **Sources:** [`src/reasoner/phases/`](src/reasoner/phases/), [`src/reasoner/core/temperatures.py`](src/reasoner/core/temperatures.py), [`src/reasoner/application/flows/multi_perspective.py`](src/reasoner/application/flows/multi_perspective.py), [`src/reasoner/domain/preset_registry.py`](src/reasoner/domain/preset_registry.py)

---

## Pipeline Overview

The multi-perspective flow runs in 5 phases. Each LLM call targets a named **role**; the preset's routing table resolves the role to a specific model. Temperature and reasoning effort are per-role, not per-model — the same model may run at different temps depending on which role it's serving.

```
Phase 0   — Fusion (classification + decomposition)         temp=0.2, effort=minimal
Phase 1.5 — Evidence Search (web retrieval, optional)        temp=0.3, effort=medium
Phase 2   — Perspective Generation (4 parallel voices)       temp=1.0, effort=medium
Phase 3   — Critique & Scoring (judgment + pruning)          temp=0.3, effort=high
Phase 4   — Stress Testing (adversarial scenarios)           temp=0.5, effort=high
Phase 5   — Synthesis (consolidated final answer)            temp=0.5, effort=high
Phase 5b  — Post-Synthesis Verification (fact-check)         no temp/effort config
```

**Orphaned routing keys:** `perspective_cot` and `perspective_analysis` appear in every multi-perspective routing table but have zero consumers in all application, infrastructure, and phases code. They are valid `_KNOWN_ROUTING_ROLES` entries but are currently dead — no LLM call targets them ([`preset_core.py:33-34`](src/reasoner/domain/preset_core.py:33)).

---

## Phase 0 — Fusion (Pre-flight)

**One LLM call:** classification + decomposition in a single fusion prompt. The model must identify the task type and break the problem into a causal chain.

### fusion
| | |
|---|---|
| **Task** | Classify problem as analytical/strategic/creative/technical/predictive/hybrid, decompose into ≤5 causal steps, surface assumptions with epistemic labels, list failure modes |
| **Temperature** | 0.2 ([`temperatures.py:36`](src/reasoner/core/temperatures.py:36)) |
| **Reasoning effort** | Minimal ([`temperatures.py:59`](src/reasoner/core/temperatures.py:59)) |
| **Source** | [`phases/_universal.py:81`](src/reasoner/phases/_universal.py:81) (FUSION_SYSTEM + fusion_prompt) |
| **Ideal characteristics** | Fast JSON output with consistent structure. The cost of a misclassification here cascades to every downstream phase, but the task is simple enough that flash-tier models perform well. Creativity is not needed — determinism is. |
| **Budget assignment** | `qwen3.5-flash`, `deepseek-v4-flash` |

---

## Phase 1.5 — Evidence Search (Optional)

Not an LLM call — this phase generates search queries via the `primary` role and executes web searches against a configured search client. Results become `state.web_discovery_results` and feed into perspective generation and synthesis.

| | |
|---|---|
| **Source** | [`perspective_phases.py:28-67`](src/reasoner/application/flows/perspective_phases.py:28) |
| **Model role** | `primary` — generates search queries from ARTICLE_RETRIEVAL_PLAN_SYSTEM prompt |
| **Temperature** | 0.7 (primary fallback) ([`temperatures.py:48`](src/reasoner/core/temperatures.py:48)) |
| **Ideal characteristics** | Needs broad enough knowledge to form diverse, targeted queries. Overly specialized models may miss domain-adjacent angles. |

---

## Phase 2 — Perspective Generation (4 Parallel Voices)

The creative core. Each perspective is a **separate LLM call** with a distinct system prompt and persona. Calls execute in parallel via `asyncio.gather` ([`perspective_phases.py:155`](src/reasoner/application/flows/perspective_phases.py:155)). All four share `temp=1.0`, `effort=medium`.

### constructive
> *"Build the strongest, most comprehensive solution. Analyze from first principles, cite historical precedents where relevant, and address 2nd-order consequences. Minimum 4 paragraphs. JSON only."*

| | |
|---|---|
| **Prompt** | [`multi_perspective.py:12`](src/reasoner/phases/multi_perspective.py:12) |
| **Ideal model** | Strong multi-paragraph composition, can sustain a line of reasoning across several points. Benefits from training that emphasizes detailed exposition. Large context helps (all perspectives get the full problem context + web results). |
| **[DESIGN JUDGMENT]** | This is the most breadth-demanding voice. A model that excels on reasoning benchmarks but produces thin output will underperform here — content length and structural quality are the real metrics, not IQ-bench scores. |

### destructive
> *"Find every flaw in the proposed approach or subject matter. Focus exclusively on substantive weaknesses, risks, and incorrect assumptions. Do NOT criticize the prompt's language, grammar, formatting, or mixed languages."*

| | |
|---|---|
| **Prompt** | [`multi_perspective.py:13`](src/reasoner/phases/multi_perspective.py:13) |
| **Ideal model** | Willingness to disagree — this is the hardest-to-measure trait. Model sycophancy (agreeing with the user, hedging criticism, softening pushback) is invisible on standard benchmarks but destroys this role. |

### systemic
> *"Find 2nd/3rd-order effects."*

| | |
|---|---|
| **Prompt** | [`multi_perspective.py:14`](src/reasoner/phases/multi_perspective.py:14) |
| **Ideal model** | Broad training corpus spanning domains where indirect effects matter: economics, ecology, policy, technology diffusion. Needs to reason about feedback loops and emergent dynamics, not linear cause-and-effect. |

### minimalist
> *"Apply Occam's Razor. Simplest 80% solution."*

| | |
|---|---|
| **Prompt** | [`multi_perspective.py:15`](src/reasoner/phases/multi_perspective.py:15) |
| **Ideal model** | Resistance to over-explanation. Models trained to be thorough and safety-hedged will add caveats and expansions — the minimalist voice's value is in what it *omits*, not what it adds. |

### Perspective diversity invariant

**Enforced at runtime** ([`perspective_phases.py:80-107`](src/reasoner/application/flows/perspective_phases.py:80)) — if all four perspectives resolve to the same model or a single geopolitical bloc, a `phase_warning` event is emitted. The invariant comes from Buyl et al. (npj AI 2026): the creator's bloc is the dominant axis of ideological bias. Cross-company diversity within one bloc (DeepSeek + Qwen + StepFun, all 🇨🇳) does not buy ideological diversity. The routing table must assign **≥2 blocs, ≤2 models from any single bloc** to the four perspective roles.

---

## Phase 3 — Critique & Scoring (Judgment Layer)

One LLM call evaluates all four candidates. Output is structured JSON with scores, steel_man arguments, and bias flags.

### scoring
| | |
|---|---|
| **Task** | Score each candidate on 4 dimensions (logical consistency, evidence support, failure resilience, feasibility, each 0-10). Apply confidence-vs-accuracy penalty. Steel-man each candidate. Flag biases. |
| **Prompt** | [`multi_perspective.py:73-92`](src/reasoner/phases/multi_perspective.py:73) (critique_prompt) |
| **Temperature** | 0.3 ([`temperatures.py:38`](src/reasoner/core/temperatures.py:38)) |
| **Reasoning effort** | High ([`temperatures.py:65`](src/reasoner/core/temperatures.py:65)) |
| **Ideal model** | Consistency across calls. The model must evaluate 4 candidates without anchoring on the first-read one, penalize false confidence, and output valid JSON every time — a single parse error kills the entire phase. |

### recovery_path (Phase 3.5, conditional)
| | |
|---|---|
| **Trigger** | Candidate scores with `confidence_vs_accuracy_penalty > 5.0` ([`perspective_phases.py:253`](src/reasoner/application/flows/perspective_phases.py:253)) |
| **Temperature** | 0.2 ([`temperatures.py:43`](src/reasoner/core/temperatures.py:43)) |
| **Reasoning effort** | Low ([`temperatures.py:77`](src/reasoner/core/temperatures.py:77)) |
| **Ideal model** | Mechanical fix-up — any reliable flash model. |

### Cross-bloc invariant (scoring)
**synthesis bloc ≠ scoring bloc.** Commented in the routing table ([`preset_registry.py:11-12`](src/reasoner/domain/preset_registry.py:11)). If synthesis is 🇨🇳, scoring must be 🇺🇸 or 🇪🇺, and vice versa. This ensures the final voice's evaluator does not share the same ideological training distribution.

---

## Phase 4 — Stress Testing

### stress_testing
| | |
|---|---|
| **Task** | Generate adversarial scenarios (optimal, constraint-violation, edge-case) for each top candidate. Assign survival rates. If `review_hypotheses` exists from VS critique, seed scenarios from the top-N highest-probability failure hypotheses ([`multi_perspective.py:101-116`](src/reasoner/phases/multi_perspective.py:101)). |
| **Temperature** | 0.5 ([`temperatures.py:39`](src/reasoner/core/temperatures.py:39)) |
| **Reasoning effort** | High ([`temperatures.py:69`](src/reasoner/core/temperatures.py:69)) |
| **Ideal model** | Adversarial creativity within plausible bounds. Needs domain-specific imagination — generic "supply chain collapse" scenarios are explicitly rejected by the prompt. Mid temperature balances novelty with realism. |

---

## Phase 5 — Synthesis

### synthesis
> *"Produce a definitive, professional synthesis with structured headings, inline citations, epistemic labels, action blueprint, and evidence."*

| | |
|---|---|
| **Prompt** | [`_universal.py:97-130`](src/reasoner/phases/_universal.py:97) (SYNTHESIS_SYSTEM + synthesis_prompt) |
| **Temperature** | 0.5 ([`temperatures.py:40`](src/reasoner/core/temperatures.py:40)) |
| **Reasoning effort** | High ([`temperatures.py:70`](src/reasoner/core/temperatures.py:70)) |
| **Context budget** | All candidates + web sources + stress test results — can exceed 64K tokens. |
| **Ideal model** | **[DESIGN JUDGMENT]** This is the most writing-intensive role. The synthesis model is chosen primarily for composition quality (clarity, structure, epistemic honesty) rather than reasoning benchmarks. A model that produces generic, hedging prose degrades the final output regardless of how well it "understands" the problem. |

### post_synthesis_verify
| | |
|---|---|
| **Task** | Generate 3-5 verification questions for key claims. Evaluate each independently. Flag unsupported/contradictory statements. |
| **Prompt** | [`_universal.py:228-241`](src/reasoner/phases/_universal.py:228) (post_synthesis_verify_prompt) |
| **Model** | `sonar` (Perplexity) — web-search augmented verification. Alternative prompt `POST_SYNTHESIS_VERIFY_SYSTEM_SONAR` enables live search ([`_universal.py:215-224`](src/reasoner/phases/_universal.py:215)). |
| **Ideal characteristics** | Must disagree with the synthesis model when warranted. Web-search capability is ideal — the model's own factual knowledge is not sufficient for independent verification. |

---

## Cross-Cutting Roles

### meta_evaluator
| | |
|---|---|
| **Temperature** | 0.3 ([`temperatures.py:42`](src/reasoner/core/temperatures.py:42)) |
| **Reasoning effort** | High ([`temperatures.py:68`](src/reasoner/core/temperatures.py:68)) |
| **Ideal model** | Reliable structured evaluator. Used in jury/debate flows for meta-judgment. Not invoked in standard multi-perspective. |

### verifier
| | |
|---|---|
| **Temperature** | 0.2 ([`temperatures.py:41`](src/reasoner/core/temperatures.py:41)) |
| **Reasoning effort** | High ([`temperatures.py:67`](src/reasoner/core/temperatures.py:67)) |
| **Ideal model** | Factual skepticism — needs to know its own knowledge boundaries. Not invoked in standard multi-perspective. |

---

## Quick-Reference Table

| Phase | Role | Temp | Effort | Primary Need |
|---|---|---|---|---|
| Pre-flight | fusion | 0.2 | minimal | Speed + JSON reliability |
| Perspectives | constructive | 1.0 | medium | Creative depth |
| | destructive | 1.0 | medium | Adversarial rigor (non-sycophantic) |
| | systemic | 1.0 | medium | Systems thinking |
| | minimalist | 1.0 | medium | Conciseness (resistance to over-explanation) |
| Critique | scoring | 0.3 | high | Calibrated, consistent judgment |
| | recovery_path | 0.2 | low | Mechanical fix-up |
| Stress Test | stress_testing | 0.5 | high | Domain-specific adversarial creativity |
| Synthesis | synthesis | 0.5 | high | Professional writing + evidence integration |
| Verify | post_synthesis_verify | — | — | Independent fact-checking (web-search) |
| Cross-cut | meta_evaluator | 0.3 | high | Structured evaluation |
| | verifier | 0.2 | high | Factual skepticism |
| **Dead key** | perspective_cot | — | — | No consumer in any layer |
| **Dead key** | perspective_analysis | — | — | No consumer in any layer |

---

# Recommended Model Assignments Per Phase

> **Source for all model data:** [`src/reasoner/infrastructure/llm/registry.py`](src/reasoner/infrastructure/llm/registry.py) — pricing, context window, capability annotations. Cross-bloc mapping from `_VENDOR_BLOC` ([`registry.py:435-441`](src/reasoner/infrastructure/llm/registry.py:435)). All costs per million tokens (input/output). [DESIGN JUDGMENT] markers indicate opinion, not measurement.

## Budget Preset (`multi-perspective-budget`)

Constraints: models ≤ ~$0.50/M input, total run ~$5/1K runs, cross-bloc invariants enforced.

### Fusion
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `deepseek-v4-flash` | $0.09/$0.18 | 🇨🇳 | Best VFM reasoning, 1M ctx, fast — proven in this role |
| 2 | `gpt-5-nano` | $0.05/$0.40 | 🇺🇸 | Cheapest OpenAI, reliable JSON, 400K ctx |
| 3 | `qwen3.5-flash` | $0.065/$0.26 | 🇨🇳 | Cheapest Qwen, 1M ctx, fast & reliable |

### Constructive (creative depth + multi-paragraph composition)
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `qwen3.7-plus` | $0.32/$1.28 | 🇨🇳 | Best Qwen VFM, 1M ctx, strong multi-paragraph writing. **[DESIGN JUDGMENT]** Superior to v3 for structured argumentation at similar price range. |
| 2 | `deepseek-v3` | $0.12/$0.50 | 🇨🇳 | Strong reasoning at budget price, 1M ctx — current routing choice |
| 3 | `gpt-5-mini` | $0.25/$2.00 | 🇺🇸 | Stronger than gpt-4o-mini, 400K ctx — if US bloc needed |

### Destructive (adversarial, non-sycophantic)
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `ring-2.6-1t` | $0.075/$0.625 | 🇨🇳 | 1T total / 63B active thinking model — trained to reason adversarially. Current routing. |
| 2 | `hermes-4-70b` | $0.13/$0.40 | 🇺🇸 | Nous Research critic-specialized model, strong at finding flaws. **[DESIGN JUDGMENT]** Likely more genuinely adversarial than general-purpose models, but untested in this pipeline. |
| 3 | `qwen3-coder-next` | $0.11/$0.80 | 🇨🇳 | Open-weight coder — logical precision may translate to good flaw-finding |

### Systemic (broad domain knowledge, 2nd/3rd-order effects)
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `qwen3.7-plus` | $0.32/$1.28 | 🇨🇳 | Broad training across domains, 1M ctx. Stronger reasoning than gpt-4o-mini for systems-thinking tasks. |
| 2 | `gpt-4o-mini` | $0.15/$0.60 | 🇺🇸 | Proven reliable, Western data bias provides different perspective from CN models |
| 3 | `seed-2.0-mini` | $0.10/$0.40 | 🇨🇳 | ByteDance, good generalist at very low cost |

### Minimalist (conciseness, Occam's razor)
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `ministral-8b` | $0.075/$0.20 | 🇫🇷 | Mistral models excel at conciseness — the French/European training distribution produces notably terse output. Current routing. |
| 2 | `qwen3.5-flash` | $0.065/$0.26 | 🇨🇳 | Cheap, fast, direct. Good minimalist if EU bloc unavailable. |
| 3 | `gpt-5-nano` | $0.05/$0.40 | 🇺🇸 | Cheapest OpenAI — 400K ctx, adequate for short-form role |

### Scoring (calibrated judgment, temp=0.3, effort=high)
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `qwen3.7-plus` | $0.32/$1.28 | 🇨🇳 | 1M ctx, strong structured evaluation. **[DESIGN JUDGMENT]** Better multi-dimensional scoring than gpt-4o-mini for the 4-axis rubric. |
| 2 | `gpt-4o-mini` | $0.15/$0.60 | 🇺🇸 | Proven reliable evaluator. Current routing. Cross-bloc from 🇨🇳 synthesis. |
| 3 | `hermes-4-70b` | $0.13/$0.40 | 🇺🇸 | Critic-specialized, 131K ctx. **[DESIGN JUDGMENT]** May produce more honest scores than general-purpose models. |
| **Cross-bloc check** | Must differ from synthesis: | | | With synthesis=🇨🇳, scoring=🇺🇸 ✅ |

### Stress Testing (adversarial creativity, temp=0.5, effort=high)
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `ring-2.6-1t` | $0.075/$0.625 | 🇨🇳 | Thinking model, strong adversarial capability. Current routing. |
| 2 | `qwen3.7-plus` | $0.32/$1.28 | 🇨🇳 | Broad domain knowledge generates more varied failure modes |
| 3 | `deepseek-v4-flash` | $0.09/$0.18 | 🇨🇳 | Creative at mid temp, 1M ctx |

### Synthesis (professional writing, temp=0.5, effort=high)
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `qwen3.7-plus` | $0.32/$1.28 | 🇨🇳 | 1M ctx handles all candidates + sources. Strong structured writing. Current routing (via qwen3-max alias). |
| 2 | `gpt-4o-mini` | $0.15/$0.60 | 🇺🇸 | Proven synthesis quality. If synthesis=🇺🇸, scoring must be 🇨🇳 — swap scoring to qwen3.7-plus or deepseek-v4-flash. |
| 3 | `deepseek-v3` | $0.12/$0.50 | 🇨🇳 | Strong writing, 1M ctx. Inferior to qwen3.7-plus for structured output but cheaper. |

### Post-Synthesis Verify
| Rank | Model | Bloc | Rationale |
|---|---|---|---|
| **1** | `sonar` | 🇺🇸 | Perplexity web-search verification. Current routing. |

### Meta Evaluator
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `qwen3.5-flash` | $0.065/$0.26 | 🇨🇳 | Fast, reliable structured evaluation. Current routing. |

### Verifier
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `qwen3.5-flash` | $0.065/$0.26 | 🇨🇳 | Fast + reliable. Current routing. |
| 2 | `deepseek-v4-flash` | $0.09/$0.18 | 🇨🇳 | Stronger reasoning for verification if consistency issues arise |

---

## Premium Preset (`multi-perspective-premium`)

Constraints: best-in-class per role, cost secondary, cross-bloc invariants enforced.

### Fusion
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `deepseek-v4-pro` | $0.435/$0.87 | 🇨🇳 | Strong reasoning, 1M ctx — current routing |
| 2 | `claude-sonnet` | $2/$10 | 🇺🇸 | Best structured output, reliable at deterministic tasks |
| 3 | `gpt-5` | $1.25/$10 | 🇺🇸 | Strong alternative, 400K ctx |

### Constructive (creative depth + multi-paragraph composition)
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `claude-sonnet` | $2/$10 | 🇺🇸 | Best writing quality at reasonable cost. 1M ctx. Current routing. **[DESIGN JUDGMENT]** Claude's prose style delivers the most nuanced, well-structured constructive arguments. |
| 2 | `gpt-5.5` | $5/$30 | 🇺🇸 | AI² Intel 54.8, frontier writing — but 6× cost of Claude for marginal prose gain |
| 3 | `claude-fable-5` | $10/$50 | 🇺🇸 | Ultra-premium creative/synthesis. Best prose quality available. |
| 4 | `gpt-5` | $1.25/$10 | 🇺🇸 | Strong value alternative, 400K ctx |

### Destructive (adversarial, non-sycophantic)
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `grok-4.3` | $1.25/$2.50 | 🇺🇸 | τ²-Bench 97.7% adversarial, configurable reasoning. **[DESIGN JUDGMENT]** Grok models consistently push back harder than Claude/GPT — ideal for destructive. |
| 2 | `deepseek-v4-pro` | $0.435/$0.87 | 🇨🇳 | Current routing. Strong reasoning, lower cost. |
| 3 | `grok-4.20` | $1.25/$2.50 | 🇺🇸 | 2M ctx, reasoning — slightly broader than 4.3. Same price. |

### Systemic (broad domain knowledge, 2nd/3rd-order effects)
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `grok-4.20` | $1.25/$2.50 | 🇺🇸 | 2M ctx — can ingest entire problem domains. Broadest training of any model under $5/M. |
| 2 | `qwen3.7-max` | $1.25/$3.75 | 🇨🇳 | 1M ctx, flagship agent. Current routing. |
| 3 | `claude-sonnet` | $2/$10 | 🇺🇸 | Excellent systems thinking, 1M ctx |

### Minimalist (conciseness, Occam's razor)
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `mistral-large-3` | ~$2/$6 (est.) | 🇪🇺 | Mistral flagship — concise, direct, European training distribution. Current routing. |
| 2 | `claude-haiku` | $1/$5 | 🇺🇸 | Fast, distilled Anthropic — excellent conciseness |
| 3 | `claude-sonnet` | $2/$10 | 🇺🇸 | Strong conciseness when instructed (overkill for this role but reliable) |

### Scoring (calibrated judgment, temp=0.3, effort=high)
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `qwen3-max-thinking` | $0.78/$3.90 | 🇨🇳 | Dedicated deep multi-step reasoning — ideal for 4-axis rubric evaluation. Current routing. |
| 2 | `grok-4.3` | $1.25/$2.50 | 🇺🇸 | Strong adversarial judgment, complements 🇨🇳 synthesis |
| 3 | `gpt-5` | $1.25/$10 | 🇺🇸 | Reliable structured evaluation |
| **Cross-bloc check** | Must differ from synthesis: | | | With synthesis=🇺🇸, scoring=🇨🇳 ✅ |

### Stress Testing (adversarial creativity, temp=0.5, effort=high)
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `grok-4.3` | $1.25/$2.50 | 🇺🇸 | τ²-Bench 97.7%, configurable reasoning effort, best adversarial creativity. Current routing. |
| 2 | `deepseek-v4-pro` | $0.435/$0.87 | 🇨🇳 | Strong alternative at 3× lower cost |
| 3 | `claude-sonnet` | $2/$10 | 🇺🇸 | Creative at mid temp, broad world knowledge for varied scenarios |

### Synthesis (professional writing, temp=0.5, effort=high)
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `gpt-5.5` | $5/$30 | 🇺🇸 | AI² Intel 54.8, frontier writing, 1M ctx. Current routing. **[DESIGN JUDGMENT]** Best prose quality of any model under $10/M input. |
| 2 | `claude-fable-5` | $10/$50 | 🇺🇸 | Ultra-premium creative/synthesis — best absolute prose quality, but 2× cost of gpt-5.5 |
| 3 | `claude-sonnet` | $2/$10 | 🇺🇸 | Excellent writing at much lower cost. If gpt-5.5 budget is a concern, this is the fallback. |
| 4 | `gpt-5` | $1.25/$10 | 🇺🇸 | Budget premium option, 400K ctx — may truncate on large synthesis prompts |

### Post-Synthesis Verify
| Rank | Model | Bloc | Rationale |
|---|---|---|---|
| **1** | `sonar-pro` | 🇺🇸 | Perplexity with high context search, fact-checking. Current routing. |
| 2 | `sonar-reasoning-pro` | 🇺🇸 | Adds reasoning depth to verification |

### Meta Evaluator
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `minimax-m3` | $0.30/$1.20 | 🇨🇳 | AI² Intel 44.4, 1M ctx, multimodal — 3× cheaper than qwen3.7-max for same class. Current routing. |
| 2 | `qwen3.7-max` | $1.25/$3.75 | 🇨🇳 | Stronger individual quality, 3× the cost |

### Verifier
| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `grok-4.20` | $1.25/$2.50 | 🇺🇸 | 2M ctx, lowest hallucination rate — best factual verification. Current routing. |
| 2 | `qwen3-max-thinking` | $0.78/$3.90 | 🇨🇳 | Deep multi-step reasoning for claim verification |

---

## Cross-Bloc Summary

### Budget
| Role | Recommended | Bloc |
|---|---|---|
| constructive | `deepseek-v3` or `qwen3.7-plus` | 🇨🇳 |
| destructive | `ring-2.6-1t` | 🇨🇳 |
| systemic | `qwen3.7-plus` or `gpt-4o-mini` | 🇨🇳 or 🇺🇸 |
| minimalist | `ministral-8b` | 🇫🇷 |
| synthesis | `qwen3.7-plus` | 🇨🇳 |
| scoring | `gpt-4o-mini` | 🇺🇸 |
| **Invariant check** | **A:** synthesis≠scoring 🇨🇳≠🇺🇸 ✅ | **B:** 2🇨🇳+1🇺🇸+1🇫🇷 (≤2🇨🇳) ✅ |

### Premium
| Role | Recommended | Bloc |
|---|---|---|
| constructive | `claude-sonnet` | 🇺🇸 |
| destructive | `grok-4.3` | 🇺🇸 |
| systemic | `grok-4.20` or `qwen3.7-max` | 🇺🇸 or 🇨🇳 |
| minimalist | `mistral-large-3` | 🇪🇺 |
| synthesis | `gpt-5.5` | 🇺🇸 |
| scoring | `qwen3-max-thinking` | 🇨🇳 |
| **Invariant check** | **A:** synthesis≠scoring 🇺🇸≠🇨🇳 ✅ | **B:** 2🇺🇸+1🇨🇳+1🇪🇺 (≤2🇺🇸) ✅ |

### Key Changes From Current Routing

| Tier | Role | Current | Recommended | Delta |
|---|---|---|---|---|
| Budget | constructive | `deepseek-v3` | `qwen3.7-plus` | Stronger writing, $0.20/M more |
| Budget | systemic | `gpt-4o-mini` | `qwen3.7-plus` | Stronger systems thinking |
| Budget | scoring | `gpt-4o-mini` | keep | Proven, reliable |
| Premium | destructive | `deepseek-v4-pro` | `grok-4.3` | Higher adversarial quality |
| Premium | systemic | `qwen3.7-max` | `grok-4.20` (optional) | 2M ctx, broader domain knowledge |

---

# Cross-Lab Diversity & Echo Chamber Avoidance

> **[DESIGN JUDGMENT]** This section is analytical rather than measured. The claims about training-data overlap and architectural divergence are inferred from public information about model provenance, not from A/B measurements in this pipeline.

## The Echo Chamber Problem

The multi-perspective pipeline's value proposition is **genuinely different perspectives converging on truth**. If the four perspectives are produced by models that share training data distributions, safety-tuning approaches, or architectural constraints, the "diversity" is cosmetic — the models will produce structurally similar outputs that differ in phrasing but converge on the same reasoning patterns.

**Five axes of divergence matter:**

| Axis | What varies | Echo chamber risk when aligned |
|---|---|---|
| **Bloc** | 🇺🇸/🇨🇳/🇪🇺 training origin | Buyl et al. (2026): creator's ideology is the dominant bias axis |
| **Lab** | Company-specific data pipelines, RLHF, safety tuning | Two CN labs may share web crawl data, filtering policies |
| **Architecture** | MoE vs dense, thinking vs standard, tokenizer | Same architecture → similar attention patterns → similar reasoning |
| **Alignment style** | Heavily safety-tuned (Claude, GPT) vs lightly filtered (Grok, some CN) | Safety-tuning suppresses specific viewpoints, creates blind spots |
| **Training data** | Recency, language mix, domain emphasis | Convergent training → convergent world knowledge |

## Budget Tier: Cross-Lab + Echo Chamber Analysis

### Current Routing (post bloc-adjusted change)

| Role | Model | Lab | Bloc | Architecture | Alignment |
|---|---|---|---|---|---|
| constructive | `deepseek-v3` | DeepSeek | 🇨🇳 | MoE, 1M ctx, standard | Moderate CN filtering |
| destructive | `ring-2.6-1t` | inclusionAI (Ant) | 🇨🇳 | **Thinking** (1T/63B active) | CN think-tank style |
| systemic | `gpt-4o-mini` | OpenAI | 🇺🇸 | Dense, 16K ctx | Conservative safety-tuning |
| minimalist | `ministral-8b` | Mistral | 🇫🇷 | Compact dense, 262K ctx | European, lightly filtered |

### Echo Chamber Assessment

**Strength:** Constructive (DeepSeek MoE, standard) and destructive (inclusionAI, thinking model) use fundamentally different architectures. The thinking process generates intermediate reasoning tokens that a standard model never produces — this creates a genuine cognitive divergence that bloc-alignment alone doesn't capture. Even trained on overlapping Chinese web data, the thinking-vs-standard architectural gap produces noticeably different outputs.

**Weakness:** Both constructive and destructive are trained on Chinese web data distributions. Their world knowledge, case studies, historical references, and policy frameworks will have significant overlap. The two "opposing" perspectives may cite the same examples, reference the same precedents, and converge on similar blind spots (e.g., underweighting Western regulatory frameworks, overindexing on state-capacity solutions).

**Verdict:** **Acceptable but not ideal.** The architectural divergence partially mitigates the data-distribution overlap. For a truly echo-chamber-resistant budget setup, one of the two CN perspective roles should be swapped to a non-CN model.

### Optimal Echo-Chamber-Avoiding Budget Routing

| Role | Model | Lab | Bloc | Architecture | Why |
|---|---|---|---|---|---|
| constructive | `deepseek-v3` | DeepSeek | 🇨🇳 | MoE, 1M ctx | Strong multi-paragraph, CN training |
| destructive | `hermes-4-70b` | Nous Research | 🇺🇸 | Dense, critic-specialized | **US lab, US data, trained to critique** — maximal divergence from CN constructive |
| systemic | `qwen3.7-plus` | Qwen | 🇨🇳 | MoE, 1M ctx | Different CN lab from DeepSeek, broad training |
| minimalist | `ministral-8b` | Mistral | 🇫🇷 | Compact dense, terse | European — unique training distribution |

**Invariant check:** 2🇨🇳 (DeepSeek + Qwen) + 1🇺🇸 (Nous) + 1🇫🇷 (Mistral) ✅

| Metric | Current | Optimal |
|---|---|---|
| constructive ↔ destructive divergence | Medium (architecture only) | **High** (bloc + architecture + alignment style) |
| Destructive model cost | $0.075/$0.625 | $0.13/$0.40 |
| Destructive context | 1M ctx (ring) | 131K ctx (hermes) |
| Tradeoff | Favors cost + ctx | Favors echo-chamber resistance |

**Risk:** Hermes-4-70b has only 131K context vs ring-2.6-1t's 1M. The destructive prompt includes problem text + web results — 131K should be adequate but may clip on very long problems with many web sources. Monitor empty/truncated destructive outputs before committing.

### synthesis ↔ scoring echo chamber

Current: synthesis=`qwen3-max` (→qwen3.7-plus) 🇨🇳, scoring=`gpt-4o-mini` 🇺🇸

**Cross-bloc, different labs, different architectures** — excellent. The Qwen synthesis gets scored by an OpenAI evaluator, meaning the critic does not share the composer's training distribution or alignment bias. This is the strongest single anti-echo-chamber measure in the budget preset.

---

## Premium Tier: Cross-Lab + Echo Chamber Analysis

### Current Routing

| Role | Model | Lab | Bloc | Architecture | Alignment |
|---|---|---|---|---|---|
| constructive | `claude-sonnet` | Anthropic | 🇺🇸 | Dense, Constitutional AI | Heavily safety-tuned |
| destructive | `deepseek-v4-pro` | DeepSeek | 🇨🇳 | MoE, heavy reasoning | Moderate CN filtering |
| systemic | `qwen3.7-max` | Qwen | 🇨🇳 | Large MoE, 1M ctx | CN flagship |
| minimalist | `mistral-large-3` | Mistral | 🇪🇺 | Dense, terse | European, light filtering |

### Echo Chamber Assessment

**Strength:** Constructive (Anthropic, US, Constitutional AI, safety-tuned) and destructive (DeepSeek, CN, reasoning-heavy, less filtered) are nearly **maximally divergent** — different blocs, different labs, different architectures, different alignment philosophies, different training data. These two SHOULD produce genuinely opposing views. This is the best constructive↔destructive divergence of any preset in the system.

**Strength:** Synthesis (gpt-5.5, US) and scoring (qwen3-max-thinking, CN) are cross-bloc with different architectures (standard vs reasoning). GPT-5.5's synthesis gets evaluated by Qwen's reasoning model — no shared training distribution.

**Weakness:** Systemic (qwen3.7-max) and destructive (deepseek-v4-pro) are both 🇨🇳. But they serve different roles — systemic analyzes 2nd/3rd-order effects while destructive attacks the proposed solution. Different prompts, different tasks, different companies (Qwen ≠ DeepSeek). **Low echo-chamber risk in practice.**

**Verdict:** **Excellent.** The premium preset already achieves strong echo-chamber resistance through maximum constructive↔destructive divergence and cross-bloc synthesis↔scoring separation. No changes recommended.

### Optional enhancement: swap systemic to Grok

If maximum divergence is desired across ALL four perspective roles:

| Role | Swap from → to | Gain | Cost |
|---|---|---|---|
| systemic | `qwen3.7-max` → `grok-4.20` | 2M ctx, 🇺🇸 training, different alignment style from all others | Same price ($1.25/$2.50), different architecture |

This gives: constructive=Anthropic 🇺🇸, destructive=DeepSeek 🇨🇳, systemic=xAI 🇺🇸, minimalist=Mistral 🇪🇺 → 2🇺🇸+1🇨🇳+1🇪🇺 (≤2 US, same invariant, different labs within US bloc).

**Invariant check:** 2🇺🇸 (Anthropic + xAI, different companies) + 1🇨🇳 + 1🇪🇺 ✅

---

## Echo Chamber Risk Matrix

How much will two perspectives genuinely diverge? Qualitative assessment:

| constructive paired with | Divergence | Why |
|---|---|---|
| `ring-2.6-1t` (inclusionAI 🇨🇳, thinking) | Medium | Same bloc, different architecture |
| `hermes-4-70b` (Nous 🇺🇸, critic) | **High** | Different bloc, lab, architecture, alignment |
| `deepseek-v4-pro` (DeepSeek 🇨🇳) | Low | Same lab, same architecture family — worst case |
| `claude-sonnet` (Anthropic 🇺🇸) | **High** | Different bloc, lab, alignment style |
| `grok-4.3` (xAI 🇺🇸) | **High** | Different bloc, lab, alignment style; Grok pushes back harder than Claude |

| destructive paired with | Divergence from constructive |
|---|---|
| `hermes-4-70b` + `deepseek-v3` | **High** — US critic vs CN constructive |
| `grok-4.3` + `claude-sonnet` | **High** — xAI adversarial vs Anthropic safety-tuned |
| `deepseek-v4-pro` + `claude-sonnet` | **High** — CN reasoning vs US Constitutional AI |
| `ring-2.6-1t` + `deepseek-v3` | Medium — both CN, architectural divergence only |

## Applied Configuration (2026-07-03)

The anti-echo-chamber budget configuration has been applied to `preset_registry.py`. Premium was already optimal and is unchanged.

### Budget — Applied

```
constructive:  deepseek-v3        🇨🇳 DeepSeek      (MoE, 1M ctx, CN data)
destructive:   hermes-4-70b       🇺🇸 Nous Research  (dense, critic-specialized, US data)
systemic:      qwen3.7-plus       🇨🇳 Qwen           (MoE, 1M ctx, broad training)
minimalist:    ministral-8b       🇫🇷 Mistral        (compact dense, terse, EU data)
synthesis:     qwen3-max          🇨🇳 Qwen           (→ qwen3.7-plus)
scoring:       gpt-4o-mini        🇺🇸 OpenAI         (cross-bloc from synthesis)
```

**Invariants:** A: 🇨🇳(Qwen)≠🇺🇸(OpenAI) ✅ · B: 2🇨🇳+1🇺🇸+1🇫🇷 ✅  
**Divergence axes:** 3 blocs, 5 labs, 3 architectures, 4 alignment styles  
**constructive↔destructive divergence:** Maximum (CN MoE standard vs US dense critic)  

### Premium — Unchanged

```
constructive:  claude-sonnet      🇺🇸 Anthropic      (Constitutional AI, safety-tuned)
destructive:   deepseek-v4-pro    🇨🇳 DeepSeek       (MoE, heavy reasoning, less filtered)
systemic:      qwen3.7-max        🇨🇳 Qwen           (large MoE, broad training)
minimalist:    mistral-large-3    🇪🇺 Mistral        (dense, terse, European)
synthesis:     gpt-5.5            🇺🇸 OpenAI         (frontier writing)
scoring:       qwen3-max-thinking 🇨🇳 Qwen           (cross-bloc from synthesis)
```

**Invariants:** A: 🇺🇸(OpenAI)≠🇨🇳(Qwen) ✅ · B: 1🇺🇸+2🇨🇳+1🇪🇺 ≤2 ✅  
**constructive↔destructive divergence:** Maximum (US Constitutional AI vs CN reasoning MoE)  
**No changes needed.** Already optimal for echo-chamber resistance.

---

# Article Method — Model Recommendations Per Phase

> **Source:** [`src/reasoner/infrastructure/llm/registry.py`](src/reasoner/infrastructure/llm/registry.py) for all model data. **[DESIGN JUDGMENT]** on prose quality and editorial judgment is opinion, not measurement.

## Phase Characteristics

| Phase | Role | Temp | Effort | Primary Need |
|---|---|---|---|---|
| Evidence | `primary` | 0.7 | medium | Live web search with citations |
| Outline | `article_sot_skeleton` | 0.3 | low | Structured JSON planning |
| Draft | `writing_draft` | 0.7 | medium | **Long-form prose writing** — most important phase |
| Fact Check | `writing_factcheck` | 0.3 | high | Live adversarial verification |
| Structural Review | `article_critic` | 0.1 | high | Logic critique, counterarguments |
| Dev Edit | `article_revise` | 0.2 | high | Substantive revision, voice preservation |
| Style Edit | `article_humanize` | 0.7 | medium | Readability, rhythm, publication match |
| Copy Edit | `writing_assemble` | 0.2 | low | Mechanical — grammar, consistency |
| Final Audit | `article_verifier` | 0.3 | high | Structured checklist evaluation |
| Synthesis | `synthesis` | 0.5 | high | Final output formatting |

## Budget Tier (`article-budget`)

**Cost target:** ≤ ~$0.50/M input per model, ~$0.005-0.01 per article total.

### Evidence Collection — `primary`

| Rank | Model | Cost (in/out per M) | Bloc | Rationale |
|---|---|---|---|---|
| **1** | `sonar` | — | 🇺🇸 | Perplexity live web search. Native citations, real URLs. Current routing. |

### Argument Map / Outline — `article_sot_skeleton`

| Rank | Model | Cost (in/out per M) | Context | Rationale |
|---|---|---|---|---|
| **1** | `deepseek-v4-flash` | $0.09/$0.18 | 1M | Fast structured JSON. Cheapest 1M-ctx model with reliable planning. Current routing. |
| 2 | `qwen3.5-flash` | $0.065/$0.26 | 1M | Cheaper alternative. Slightly weaker at structured argumentation. |
| 3 | `qwen3.7-plus` | $0.32/$1.28 | 1M | Stronger argument mapping — worth the cost if outline quality is bottleneck. |

### First Draft — `writing_draft` ⭐ **highest-impact phase**

| Rank | Model | Cost (in/out per M) | Context | Rationale |
|---|---|---|---|---|
| **1** | `qwen3.7-plus` | $0.32/$1.28 | 1M | **[DESIGN JUDGMENT]** Best VFM prose writer under $0.50/M. 1M ctx handles all sources + argument map. Noticeably better paragraph structure, transitions, and voice consistency than deepseek-v4-flash. |
| 2 | `deepseek-v3` | $0.12/$0.50 | 1M | Strong reasoning at budget price. Good prose quality. Current for constructive elsewhere. |
| 3 | `deepseek-v4-flash` | $0.09/$0.18 | 1M | Current routing. Serviceable but weakest prose of the three. |

**Recommendation:** Upgrade to `qwen3.7-plus`. The draft is the single most consequential LLM call — every downstream phase (fact check, structural review, dev edit, style, copy, audit, synthesis) depends on its output. +$0.23/M for dramatically better prose is the highest-ROI upgrade in the budget tier.

### Fact Check + Claim Ledger — `writing_factcheck`

| Rank | Model | Rationale |
|---|---|---|
| **1** | `sonar` | Perplexity live web verification. Current routing. |

### Structural Adversarial Review — `article_critic`

| Rank | Model | Cost (in/out per M) | Context | Rationale |
|---|---|---|---|---|
| **1** | `hermes-4-70b` | $0.13/$0.40 | 131K | Nous Research critic-specialized. Current routing. Best adversarial model under $0.20/M. |
| 2 | `ring-2.6-1t` | $0.075/$0.625 | 1M | InclusionAI thinking model. 1M ctx handles full draft. Slightly cheaper, different adversarial style. |
| 3 | `deepseek-v4-flash` | $0.09/$0.18 | 1M | Serviceable but less adversarial by nature. |

### Developmental Edit — `article_revise`

| Rank | Model | Cost (in/out per M) | Context | Rationale |
|---|---|---|---|---|
| **1** | `deepseek-v3` | $0.12/$0.50 | 1M | Same model family as qwen3.7-plus draft — good for voice-consistent revision. Current routing. |
| 2 | `qwen3.7-plus` | $0.32/$1.28 | 1M | Stronger editorial judgment. Use if draft model is also qwen3.7-plus (self-revision works). |
| 3 | `deepseek-v4-flash` | $0.09/$0.18 | 1M | Budget fallback — weaker editorial judgment but functional. |

### Style Edit — `article_humanize`

| Rank | Model | Cost (in/out per M) | Context | Rationale |
|---|---|---|---|---|
| **1** | `qwen3.7-plus` | $0.32/$1.28 | 1M | Strong editorial refinement. Handles publication style matching and rhythm. Current routing. |
| 2 | `deepseek-v3` | $0.12/$0.50 | 1M | Decent style work at lower cost. Less refined than qwen3.7-plus. |
| 3 | `gpt-4o-mini` | $0.15/$0.60 | 128K | OpenAI prose quality, but limited context window. |

### Copy Edit — `writing_assemble`

| Rank | Model | Cost (in/out per M) | Context | Rationale |
|---|---|---|---|---|
| **1** | `qwen3.5-flash` | $0.065/$0.26 | 1M | Cheapest 1M-ctx model. Mechanical tasks don't need strong reasoning — just grammar and consistency. Saves $0.025/M vs current. |
| 2 | `deepseek-v4-flash` | $0.09/$0.18 | 1M | Current routing. Slightly more expensive than qwen3.5-flash for no mechanical gain. |
| 3 | `gpt-5-nano` | $0.05/$0.40 | 400K | Cheapest OpenAI. 400K ctx adequate for final draft. |

### Final Audit — `article_verifier`

| Rank | Model | Cost (in/out per M) | Context | Rationale |
|---|---|---|---|---|
| **1** | `qwen3.5-flash` | $0.065/$0.26 | 1M | Checklist evaluation is a structured scoring task — doesn't need strong reasoning. Current uses qwen3.7-plus at 5× the cost. |
| 2 | `qwen3.7-plus` | $0.32/$1.28 | 1M | Current routing. Overqualified for checklist scoring. |
| 3 | `gpt-4o-mini` | $0.15/$0.60 | 128K | OpenAI evaluator — good for US-bloc diversity. |

### Synthesis — `synthesis`

| Rank | Model | Cost (in/out per M) | Rationale |
|---|---|---|---|
| **1** | `gpt-4o-mini` | $0.15/$0.60 | Proven synthesis. Cross-bloc from CN-heavy phases. Current routing. |

### Budget — Optimal Routing

```
primary:               sonar              🇺🇸 Perplexity   web search
article_sot_skeleton:  deepseek-v4-flash  🇨🇳 DeepSeek     structured planning
writing_draft:         qwen3.7-plus       🇨🇳 Qwen         ⭐ upgraded prose
writing_factcheck:     sonar              🇺🇸 Perplexity   live verification
article_critic:        hermes-4-70b       🇺🇸 Nous         adversarial review
article_revise:        deepseek-v3        🇨🇳 DeepSeek     voice-consistent editing
article_humanize:      qwen3.7-plus       🇨🇳 Qwen         style refinement
writing_assemble:      qwen3.5-flash      🇨🇳 Qwen         mechanical copy (cheaper)
article_verifier:      qwen3.5-flash      🇨🇳 Qwen         checklist audit (cheaper)
synthesis:             gpt-4o-mini        🇺🇸 OpenAI       final output
```

**Changes from current:** 3 (draft upgrade, copy downgrade to cheaper, audit downgrade to cheaper). Net cost: +$0.23/M (draft) − $0.025/M (copy) − $0.255/M (audit) = **−$0.05/M net savings with better draft quality.**

---

## Premium Tier (`article-premium`)

**Cost target:** Best-in-class per role, secondary consideration.

### Evidence Collection — `primary`

| Rank | Model | Rationale |
|---|---|---|
| **1** | `sonar-pro` | Perplexity high-context search. Current routing. |

### Argument Map / Outline — `article_sot_skeleton`

| Rank | Model | Cost (in/out per M) | Context | Rationale |
|---|---|---|---|---|
| **1** | `claude-sonnet` | $2/$10 | 1M | Best planning/outlining. Structured argumentation with exceptional clarity. Current routing. |
| 2 | `gpt-5.5` | $5/$30 | 1M | Stronger raw intelligence but 2.5× cost for marginal outline improvement. |
| 3 | `gpt-5` | $1.25/$10 | 400K | Strong alternative at lower cost. Limited context may clip on large source sets. |

### First Draft — `writing_draft` ⭐

| Rank | Model | Cost (in/out per M) | Context | Rationale |
|---|---|---|---|---|
| **1** | `claude-sonnet` | $2/$10 | 1M | **[DESIGN JUDGMENT]** Best long-form prose writer overall. Claude's narrative voice, paragraph rhythm, and stylistic range are superior to GPT-5.5 for article-length composition, even though GPT-5.5 scores higher on reasoning benchmarks. Current routing. |
| 2 | `gpt-5.5` | $5/$30 | 1M | Frontier intelligence, excellent prose. 2.5× cost of Claude for marginal writing gain. |
| 3 | `claude-fable-5` | $10/$50 | 1M | Ultra-premium creative — best absolute prose. 5× cost for boutique quality. |

### Fact Check + Claim Ledger — `writing_factcheck`

| Rank | Model | Rationale |
|---|---|---|
| **1** | `sonar-pro` | Perplexity high-context live verification. Current routing. |

### Structural Adversarial Review — `article_critic`

| Rank | Model | Cost (in/out per M) | Context | Rationale |
|---|---|---|---|---|
| **1** | `grok-4.3` | $1.25/$2.50 | 1M | τ²-Bench 97.7% adversarial, configurable reasoning. Best adversarial model available. Current routing. |
| 2 | `grok-4.20` | $1.25/$2.50 | 2M | Same price, 2M ctx — can ingest full draft + sources. Slightly broader reasoning. |
| 3 | `claude-sonnet` | $2/$10 | 1M | Excellent critic when instructed adversarially, but doesn't match Grok's natural adversarial tendency. |

### Developmental Edit — `article_revise`

| Rank | Model | Cost (in/out per M) | Context | Rationale |
|---|---|---|---|---|
| **1** | `claude-sonnet` | $2/$10 | 1M | Better editorial judgment than gpt-5. Claude's prose revision preserves voice while fixing substance — the hardest editorial skill. Same model as draft ensures voice consistency. |
| 2 | `gpt-5` | $1.25/$10 | 400K | Current routing. Strong editorial judgment. 400K ctx may be tight for full article + feedback. |
| 3 | `gpt-5.5` | $5/$30 | 1M | Overkill for editing — 2.5× cost of Claude for marginal editorial gain. |

**Recommendation:** Upgrade to `claude-sonnet`. Same model as draft = best voice preservation. $2 vs $1.25 is a small premium for the most important editing phase.

### Style Edit — `article_humanize`

| Rank | Model | Cost (in/out per M) | Context | Rationale |
|---|---|---|---|---|
| **1** | `claude-sonnet` | $2/$10 | 1M | Best voice-preserving refinement. Handles rhythm, publication matching, and tonal adjustment without flattening. Current routing. |

### Copy Edit — `writing_assemble`

| Rank | Model | Cost (in/out per M) | Rationale |
|---|---|---|---|---|
| **1** | `gpt-4o-mini` | $0.15/$0.60 | Cheap, reliable. Mechanical copy editing doesn't need premium models. Current routing. |

### Final Audit — `article_verifier`

| Rank | Model | Cost (in/out per M) | Context | Rationale |
|---|---|---|---|---|
| **1** | `qwen3.7-max` | $1.25/$3.75 | 1M | Cross-bloc evaluation of US-heavy pipeline. Current routing. |
| 2 | `qwen3-max-thinking` | $0.78/$3.90 | 262K | Dedicated reasoning for structured evaluation. Cheaper but smaller context. |

### Synthesis — `synthesis`

| Rank | Model | Cost (in/out per M) | Rationale |
|---|---|---|---|---|
| **1** | `gpt-5.5` | $5/$30 | Frontier writing. AI² Intel 54.8. Current routing. |
| 2 | `claude-sonnet` | $2/$10 | Excellent synthesis at 40% of the cost. |

### Premium — Optimal Routing

```
primary:               sonar-pro          🇺🇸 Perplexity   high-context search
article_sot_skeleton:  claude-sonnet      🇺🇸 Anthropic    best planning
writing_draft:         claude-sonnet      🇺🇸 Anthropic    best prose ⭐
writing_factcheck:     sonar-pro          🇺🇸 Perplexity   live verification
article_critic:        grok-4.3           🇺🇸 xAI          adversarial
article_revise:        claude-sonnet      🇺🇸 Anthropic    ⭐ upgraded (voice-consistent)
article_humanize:      claude-sonnet      🇺🇸 Anthropic    style refinement
writing_assemble:      gpt-4o-mini        🇺🇸 OpenAI       mechanical copy
article_verifier:      qwen3.7-max        🇨🇳 Qwen         cross-bloc audit
synthesis:             gpt-5.5            🇺🇸 OpenAI       frontier writing
```

**Changes from current:** 1 (dev edit upgrade from gpt-5 to claude-sonnet). +$0.75/M for voice-consistent editorial judgment.

---

## Cross-Lab Diversity (Article)

### Budget

| Lab | Roles | Bloc |
|---|---|---|
| Perplexity | primary, factcheck | 🇺🇸 |
| DeepSeek | outline, dev edit | 🇨🇳 |
| Qwen | draft, style, copy, audit | 🇨🇳 |
| Nous Research | critic | 🇺🇸 |
| OpenAI | synthesis | 🇺🇸 |

**5 labs, 2 blocs.** CN-heavy but with US adversarial critic + US synthesis final voice. Acceptable for budget tier.

### Premium

| Lab | Roles | Bloc |
|---|---|---|
| Perplexity | primary, factcheck | 🇺🇸 |
| Anthropic | outline, draft, dev edit, style | 🇺🇸 |
| xAI | critic | 🇺🇸 |
| OpenAI | copy, synthesis | 🇺🇸 |
| Qwen | audit | 🇨🇳 |

**5 labs, 2 blocs.** US-heavy with cross-bloc CN audit. The critic (xAI Grok) provides genuine adversarial diversity within the US bloc — Grok's unfiltered style diverges from Anthropic's Constitutional AI.

### Echo Chamber Risk (Article)

The article pipeline has **lower echo-chamber risk than multi-perspective** because each phase consumes DIFFERENT input rather than answering the same question. The outline architect, draft writer, structural critic, and copy editor all operate on distinct artifacts — they can't converge on the same output even if they share training distributions.

**One risk to watch:** If `claude-sonnet` handles outline + draft + dev edit + style (4 phases in premium), the article inherits a single model's prose conventions and cognitive patterns. This is a voice-consistency FEATURE, not a bug — but worth monitoring for stylistic uniformity across the four Claude-dependent phases.
