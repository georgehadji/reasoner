# Methods & Presets That Would Benefit From Web Research

## Tier 1 — Already Have Search (2 methods)

| Method | Presets | Current Search | Status |
|---|---|---|---|
| **article** | `article-budget`, `article-premium` | `primary: sonar/sonar-pro` for source retrieval + `writing_factcheck: sonar/sonar-pro` for live verification + `get_search_client_for_method` fallback | ✅ Complete |
| **research** | `research-budget`, `research-premium` | `deep_read: sonar-pro-search/sonar-reasoning-pro`, `scoring: sonar-deep-research`, + `get_search_client_for_method` | ✅ Complete |

---

## Tier 2 — HIGH Benefit (3 methods)

Methods where web search would **fundamentally transform** output quality from LLM-internal-guessing to evidence-backed reasoning.

### 🔴 scientific (`scientific-budget`, `scientific-premium`)

**Phases:** Hypothesize → Falsification Tests → Stress Testing → Synthesis

**Why HIGH:** Scientific reasoning is inherently evidence-based. Currently, hypotheses are generated from LLM training data with no awareness of actual published research. Falsification tests are invented scenarios, not real experimental results.

**Where to add search:**
| Phase | File:Line | What to search for | Role to use |
|---|---|---|---|
| Hypothesize | `dialectical_phases.py:75` | Existing research/literature on the problem domain | `deep_read` |
| Falsification Tests | `dialectical_phases.py:83` | Real experimental results, published counter-evidence | `deep_read` |

**Implementation:** Add a pre-search step before the hypothesize phase. Search for "[problem] research papers", "[problem] experimental results", "[problem] conflicting findings". Inject top results as context into the hypothesis generation prompt.

**Estimated impact:** Transforms from "LLM invents plausible-sounding hypotheses" to "LLM reasons from real published evidence."

---

### 🔴 coding (`coding-budget`, `coding-premium`)

**Phases:** Spec Analysis → Code Generation → Security Review → Test Generation → Final Assembly

**Why HIGH:** Code generation without awareness of library APIs, version-specific syntax, known vulnerabilities, or existing solutions produces hallucinated function calls and outdated patterns.

**Where to add search:**
| Phase | File:Line | What to search for | Role to use |
|---|---|---|---|
| Spec Analysis | `coding_phases.py` (run_coding_spec_phase) | Existing implementations, library docs, best practices | `deep_read` |
| Security Review | `coding_phases.py` (run_coding_review_phase) | Known CVEs for dependencies, OWASP patterns, security advisories | `sonar` |

**Implementation:** Before spec analysis, search for the relevant library documentation. Before security review, search for known vulnerability patterns for the tech stack.

**Estimated impact:** Reduces hallucinated APIs by grounding in real documentation. Security review gains awareness of actual known vulnerabilities.

---

### 🔴 pre-mortem (`pre-mortem-budget`, `pre-mortem-premium`)

**Phases:** Failure Narrative → Root Cause → Early Warning Signals → Hardened Redesign → Synthesis

**Why HIGH:** Pre-mortem analysis is dramatically stronger when informed by real-world case studies of similar failures. "What could go wrong?" becomes "What DID go wrong in comparable situations?"

**Where to add search:**
| Phase | File:Line | What to search for | Role to use |
|---|---|---|---|
| Failure Narrative | `dialectical_phases.py:121` | Real case studies of similar project/product failures | `deep_read` |
| Early Warning Signals | `dialectical_phases.py:145` | Known early indicators from real incidents | `sonar` |

**Implementation:** Before the failure narrative, search for "[domain] project failure case study", "[technology] outage postmortem". Inject as context.

**Estimated impact:** Failure narratives become anchored in real events rather than imagined scenarios. Early warning signals become evidence-backed.

---

## Tier 3 — MEDIUM Benefit (7 methods)

Methods where web search would **meaningfully improve** quality but the method works adequately without it.

### 🟡 multi-perspective (`multi-perspective-budget`, `multi-perspective-ultra-budget`, `multi-perspective-premium`)

**Most-used method.** 4 perspectives generated from pure LLM knowledge. Adding search:

| Phase | What to search for |
|---|---|
| Perspectives generation | Domain-specific facts and data relevant to each perspective angle |
| Critique & Scoring | Real evidence to validate/invalidate each perspective's claims |

**Impact:** Perspectives gain factual grounding. Scoring becomes evidence-based rather than purely consistency-based. This is the highest-traffic method — any improvement here touches the most users.

---

### 🟡 debate (`debate-budget`, `debate-premium`)

**Phases:** Opening → Rebuttal → Cross-Examine → Judge → Synthesis

| Phase | What to search for |
|---|---|
| Opening statements | Evidence supporting each side's position |
| Rebuttals | Counter-evidence, fact-checks of opponent's claims |
| Judging | Web verification of disputed factual claims |

**Impact:** Transforms from rhetoric-only debate to evidence-backed argumentation. The judge can verify claims rather than relying on internal consistency.

---

### 🟡 jury (`jury-budget`, `jury-premium`)

**Phases:** Generation Pool → Critic Pool → Verification & Meta → Weighted Ranking → Synthesis

| Phase | What to search for |
|---|---|
| Verification & Meta | Independent fact-checking of generator claims |
| Critic Pool | Real evidence to support/refute critiques |

**Impact:** The verification phase currently checks claims against nothing. Adding search makes it actually verify.

---

### 🟡 bayesian (`bayesian-budget`, `bayesian-premium`)

**Phases:** Priors → Likelihood → Posterior → Sensitivity → Synthesis

| Phase | What to search for |
|---|---|
| Priors | Real base rates and prior probabilities from published data |
| Likelihood | Real-world evidence to inform likelihood estimates |

**Impact:** Prior probabilities become data-informed rather than LLM-invented. Currently the "priors" are just the model's best guess at what a prior should be.

---

### 🟡 analogical (`analogical-budget`, `analogical-premium`)

**Phases:** Abstraction → Domain Search → Mapping → Transfer → Synthesis

| Phase | What to search for |
|---|---|
| Domain Search | **Real** cross-domain analogs via web search (currently LLM-only) |

**Impact:** Despite its name, "Domain Search" is pure LLM — it asks the model to recall domains from training data. Adding actual web search would find real, specific examples the model hasn't memorized.

---

### 🟡 writing (`writing-budget`, `writing-premium`)

**Phases:** Outline → Draft → Fact-Check → Final Assembly → Synthesis

| Phase | What to search for |
|---|---|
| Fact-Check | Web verification of factual claims (currently checks against nothing) |
| Draft | Source retrieval for evidence-backed writing |

**Impact:** The fact-check phase marks a role as `critical=True` but has nothing to check against. Adding search makes it actually verify. The article method already solved this — writing should follow the same pattern.

---

### 🟡 brainstorming (`brainstorming-budget`, `brainstorming-premium`)

**Phases:** VS Idea Generation → Cluster & Score

| Phase | What to search for |
|---|---|
| Idea Generation | Existing solutions, prior art, what competitors have tried |

**Impact:** Prevents reinventing existing ideas. "Novel" ideas from the LLM are often things already built — search would flag this.

---

## Tier 4 — LOW Benefit (7 methods)

Methods where web search adds marginal value. These methods are about reasoning structure, not factual content.

| Method | Presets | Why LOW |
|---|---|---|
| **socratic** | `socratic-budget/premium` | Socratic method is about logical questioning, not factual retrieval |
| **dialectical** | `dialectical-budget/premium` | Thesis/antithesis/aufhebung is purely structural reasoning |
| **delphi** | `delphi-budget/premium` | Forecasting is about expert opinion synthesis, not fact lookup |
| **iterative-critique** | `iterative-critique-budget/premium` | Adversarial debate loop — structural, not evidential |
| **CoVE** | `cove-budget/premium` | Chain-of-Verification self-checks — adding search would help but the method is designed for self-consistency |
| **SoT / ToT / PoT / Self-Discover** | all budget/premium pairs | Tree/graph search over reasoning paths — structural |
| **cross-language** | `cross-language-budget/premium` | Pure translation — no reasoning to ground |

These methods are **not exempt from search** — they'd all benefit from having a search step. But the benefit is marginal compared to the HIGH tier methods where search fundamentally transforms the output.

---

## Cross-Cutting: Post-Synthesis Verification (ALL methods)

Every method runs `_phase_post_synthesis_verify` after synthesis. It calls `role="post_synthesis_verify"` to check the final solution. Currently this role is **not routed in ANY preset** and the verification prompt has **no evidence context**.

**Fix:** Add `post_synthesis_verify: "sonar"` (budget) / `post_synthesis_verify: "sonar-pro"` (premium) to every preset. Update `POST_SYNTHESIS_VERIFY_SYSTEM` to instruct live web verification. This one change improves every single pipeline run.

---

## Summary Table

| Priority | Methods | Presets | Search Phase | Est. Impact |
|---|---|---|---|---|
| ✅ Done | article, research | 4 presets | Source retrieval + verification | — |
| 🔴 HIGH | scientific, coding, pre-mortem | 6 presets | Hypothesis grounding, API doc search, case study retrieval | Transformative |
| 🟡 MEDIUM | multi-perspective, debate, jury, bayesian, analogical, writing, brainstorming | 15 presets | Evidence for claims, real priors, web domain search, prior art | Significant |
| 🟢 LOW | socratic, dialectical, delphi, iterative-critique, CoVE, SoT, ToT, PoT, Self-Discover, cross-language | 20 presets | Optional verification | Marginal |
| 🔴 ALL | post-synthesis verify | **50 presets** | Live web verification of final output | Pervasive |

The single highest-ROI change: add `post_synthesis_verify: "sonar"` to every budget preset and `post_synthesis_verify: "sonar-pro"` to every premium preset. One routing entry × 50 presets = every pipeline run gets live web verification of its final answer.
