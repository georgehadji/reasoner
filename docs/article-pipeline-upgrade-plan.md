# Article Pipeline — Editorial Methodology Upgrade Plan

**Status:** In Progress  
**Last updated:** 2026-07-03  
**Scope:** `src/reasoner/application/flows/article*.py`, `src/reasoner/phases/article.py`, `src/reasoner/domain/preset_registry.py`, `src/reasoner/domain/preset_core.py`

---

## 1. Current State Summary

### ArticleFlow (what we have)

```
Retrieve Sources → Draft → Adversarial Verify (facts) → Refine → Synthesis
```

3 LLM calls + 1 refine pass. Single model handles drafting + editing. No structural review.

### WritingFlow (what we can learn from)

```
Source Retrieval → Outline → Draft → Fact-Check → Final Assembly → Synthesis
```

5 LLM calls. Has outline. Has fact-check. But still no structural critique or staged editing.

### What's defined but unused

`_KNOWN_ROUTING_ROLES` already contains article-specific roles that map to editorial methodology:

| Existing role | Editorial function | Used in flow? |
|---|---|---|
| `article_sot_skeleton` | Outline / argument map architect | ❌ |
| `article_decompose` | Research analyst / topic decomposition | ❌ |
| `article_critic` | Devil's advocate / structural critique | ❌ |
| `article_revise` | Developmental editor | ❌ |
| `article_humanize` | Style editor | ❌ |
| `article_verifier` | Fact checker | ❌ (uses `writing_factcheck` instead) |

These existing role keys save us from needing to add new ones to `_KNOWN_ROUTING_ROLES`. We just need to wire them up.

### What's missing entirely

| Editorial role | Nearest existing | Gap |
|---|---|---|
| Copy editor (grammar, consistency, formatting) | `article_assemble` | Does assembly but not dedicated proofing pass |
| Editorial audit (pre-submission checklist) | None | No final quality gate phase |
| Domain expert review | `article_decompose` | Decomposition exists but not as review |

---

## 2. Target Flow

```
Phase 1:  Evidence Collection     [existing, enhanced]
Phase 2:  Argument Map / Outline   [NEW to ArticleFlow — reuses article_sot_skeleton]
Phase 3:  First Draft              [existing, enhanced prompt]
Phase 4:  Fact Check + Claim Ledger [existing, enhanced]
Phase 5:  Structural Adversarial Review [NEW — article_critic]
Phase 6:  Developmental Edit       [NEW — article_revise]
Phase 7:  Style + Copy Edit        [NEW — article_humanize + article_assemble]
Phase 8:  Final Editorial Audit    [NEW — article_verifier repurposed]
Phase 9:  Synthesis                [existing]
```

9 phases → 9 LLM calls (vs 4 currently). Each phase targets a distinct role with its own model.

### Phase detail

#### Phase 1 — Evidence Collection (enhanced)

```
Role:       primary (sonar / sonar-pro)
Prompt:     article_retrieval_plan_prompt
Change:     Extract and store structured source metadata (author, date, publisher)
            alongside URLs for richer citation.
New field:  writing_state["source_metadata"] — list[{title, url, author, date, publisher, snippet}]
```

#### Phase 2 — Argument Map / Outline (NEW)

```
Role:       article_sot_skeleton
System:     ARTICLE_OUTLINE_SYSTEM (new prompt)
Prompt:     article_outline_prompt(state)
Output:     writing_state["outline"] — array of {section_title, key_points[], sources_used[], word_budget}
            writing_state["argument_map"] — Question→Problem→Explanations→Limitations→Insight→Evidence→Counterarguments→Implications→Conclusion
```

This is the user's Phase 3 methodology: before any prose is written, the model constructs the logical architecture of the article. The argument map is a structured JSON object that the draft phase consumes as scaffolding.

**Prompt design:** The system prompt should instruct the model to:
1. Identify the central question
2. Map the problem space
3. Catalog current explanations
4. Identify their limitations
5. Articulate the new insight the article contributes
6. Map evidence sources to each section
7. Anticipate counterarguments
8. Trace implications
9. Structure a conclusion

The output is NOT prose — it's a JSON argument blueprint.

#### Phase 3 — First Draft (enhanced)

```
Role:       writing_draft
System:     ARTICLE_DRAFT_SYSTEM (enhanced)
Prompt:     article_draft_prompt (enhanced — consumes argument map)
Change:     Draft prompt now receives the argument map as scaffolding.
            Model writes within the pre-built structure rather than inventing structure.
```

The draft prompt will inject the argument map between style brief and sources:

```
Assignment: <topic>
Argument Blueprint (write within this structure):
  Question: ...
  Problem: ...
  ...
Sources: <evidence>
```

#### Phase 4 — Fact Check + Claim Ledger (enhanced)

```
Role:       writing_factcheck (sonar / sonar-pro)
System:     ARTICLE_VERIFY_SYSTEM (enhanced)
Prompt:     article_verify_prompt (enhanced)
Change:     Output now includes structured claim ledger per the user's specification.
New output: "claim_ledger": [{claim, supporting_source, verification_status: "verified"|"supported"|"speculative"}]
            Existing verified_claims array kept for backward compatibility.
```

The claim ledger maps to the user's Phase 7: a table of claims, supporting sources, and verification status.

#### Phase 5 — Structural Adversarial Review (NEW)

```
Role:       article_critic
System:     ARTICLE_CRITIC_SYSTEM (new prompt)
Prompt:     article_critic_prompt(state)
Output:     writing_state["structural_critique"] — {
                implicit_assumptions[], 
                ignored_counterarguments[], 
                logical_gaps[], 
                speculative_leaps[],
                misunderstanding_risks[],
                overall_rigor_score
            }
```

This is the user's Phase 6: before publication, deliberately search for failure modes. The prompt asks:

> "Which claims lack evidence? What assumptions remain implicit? How would a domain expert critique this? Which counterarguments have been ignored? Where does the reasoning rely on speculation? What could be misunderstood?"

The critic is NOT checking facts (Phase 4 does that). It's checking **logic, structure, and completeness**. A good structural critic will flag:
- The article asserts X but X depends on unstated assumption Y
- The article ignores the standard counterargument Z
- The transition from section A to B assumes a causal link that isn't established
- A reader unfamiliar with domain jargon would misinterpret paragraph P

#### Phase 6 — Developmental Edit (NEW)

```
Role:       article_revise
System:     ARTICLE_DEVELOPMENTAL_EDIT_SYSTEM (new prompt)
Prompt:     article_developmental_edit_prompt(state)
Output:     writing_state["final_article"] (revised draft)
```

This is the user's Phase 5 "separate drafting from editing." The developmental edit focuses on:
1. **Argument and structure** — fix logical gaps flagged by the critic
2. **Evidence and citations** — shore up weak claims flagged by fact-check
3. **Narrative flow** — smooth transitions, remove redundancies
4. **Technical accuracy** — incorporate domain corrections

This is a SUBSTANTIVE edit, not a cosmetic one. The model is free to restructure paragraphs, add qualifying statements, and remove unsupported claims. It should NOT change voice or style — that's Phase 7.

#### Phase 7 — Style + Copy Edit (NEW)

```
Role:       article_humanize   (style edit)
Role:       writing_assemble   (copy edit + final assembly)
System:     ARTICLE_STYLE_EDIT_SYSTEM (new prompt)
            ARTICLE_COPY_EDIT_SYSTEM (new prompt)
Output:     writing_state["final_article"] (twice-edited draft)
```

This is split into two passes:
1. **Style edit** (article_humanize): Refine readability while preserving author voice. Adjust sentence rhythm, vocabulary register, paragraph pacing. Match target publication conventions.
2. **Copy edit** (writing_assemble): Correct grammar, consistency, formatting. Add ## Sources section. Normalize citations. This is mechanical — a cheaper model can handle it.

**Design decision:** The style edit uses `article_humanize` because humanization is fundamentally about making AI-generated text read like human prose — matching the user's "match the publication" guidance. The copy edit reuses `writing_assemble` because it already handles source normalization and final assembly.

#### Phase 8 — Final Editorial Audit (NEW)

```
Role:       article_verifier
System:     ARTICLE_FINAL_AUDIT_SYSTEM (new prompt)
Prompt:     article_final_audit_prompt(state)
Output:     writing_state["editorial_audit"] — {
                thesis_advancement,      // does every paragraph advance the thesis?
                claim_support_ratio,     // are all significant claims supported?
                internal_consistency,    // is reasoning consistent throughout?
                transition_quality,      // are transitions smooth?
                redundancy_removed,      // is redundant material gone?
                citation_accuracy,       // are citations correct?
                policy_compliance,       // does it comply with AI-use policy?
                issues: [{section, severity, description, fix_suggestion}]
            }
```

This is the user's Phase 9 final editorial audit. It's a structured checklist applied to the final draft. The verifier role (originally intended for claim verification) is repurposed here for holistic audit.

If the audit score is below threshold, the article loops back to the developmental edit phase (maximum 1 retry).

#### Phase 9 — Synthesis (unchanged)

```
Role:       synthesis
System:     SYNTHESIS_SYSTEM (existing)
Prompt:     synthesis_prompt (existing)
```

The final synthesis call wraps the article in the standard pipeline output format. Unchanged from current.

---

## 3. Model Routing

### Budget Preset (`article-budget`)

| Phase | Role | Model | Lab | Cost (in/out per M) | Rationale |
|---|---|---|---|---|---|
| Evidence | `primary` | `sonar` | 🇺🇸 Perplexity | — | Native web search + live citations |
| Outline | `article_sot_skeleton` | `deepseek-v4-flash` | 🇨🇳 DeepSeek | $0.09/$0.18 | Fast structured planning, 1M ctx |
| Draft | `writing_draft` | `deepseek-v3` | 🇨🇳 DeepSeek | $0.12/$0.50 | Strong long-form writing at VFM price |
| Fact Check | `writing_factcheck` | `sonar` | 🇺🇸 Perplexity | — | Live web verification |
| Structural Critic | `article_critic` | `hermes-4-70b` | 🇺🇸 Nous | $0.13/$0.40 | Critic-specialized, adversarial |
| Dev Edit | `article_revise` | `deepseek-v3` | 🇨🇳 DeepSeek | $0.12/$0.50 | Same model family as draft for voice consistency |
| Style Edit | `article_humanize` | `qwen3.7-plus` | 🇨🇳 Qwen | $0.32/$1.28 | Strong editorial refinement |
| Copy Edit | `writing_assemble` | `deepseek-v4-flash` | 🇨🇳 DeepSeek | $0.09/$0.18 | Mechanical, fast |
| Audit | `article_verifier` | `qwen3.7-plus` | 🇨🇳 Qwen | $0.32/$1.28 | Structured checklist evaluation |
| Synthesis | `synthesis` | `qwen3-max` | 🇨🇳 Qwen | $0.32/$1.28 | Cross-bloc from scoring |

**Cross-lab diversity:** 5 labs (Perplexity, DeepSeek, Nous, Qwen) × 3 blocs (US, CN, FR)  
**Cross-bloc invariant:** Synthesis🇨🇳 ≠ Scoring(same as other budget presets) — verified via scoring role unchanged in this preset.

### Premium Preset (`article-premium`)

| Phase | Role | Model | Lab | Cost (in/out per M) | Rationale |
|---|---|---|---|---|---|
| Evidence | `primary` | `sonar-pro` | 🇺🇸 Perplexity | — | High-context search |
| Outline | `article_sot_skeleton` | `claude-sonnet` | 🇺🇸 Anthropic | $2/$10 | Best planning/outlining |
| Draft | `writing_draft` | `claude-sonnet` | 🇺🇸 Anthropic | $2/$10 | Best long-form prose |
| Fact Check | `writing_factcheck` | `sonar-pro` | 🇺🇸 Perplexity | — | Live web verification |
| Structural Critic | `article_critic` | `grok-4.3` | 🇺🇸 xAI | $1.25/$2.50 | τ²-Bench 97.7% adversarial |
| Dev Edit | `article_revise` | `gpt-5` | 🇺🇸 OpenAI | $1.25/$10 | Strong editorial refinement |
| Style Edit | `article_humanize` | `claude-sonnet` | 🇺🇸 Anthropic | $2/$10 | Voice-preserving refinement |
| Copy Edit | `writing_assemble` | `gpt-4o-mini` | 🇺🇸 OpenAI | $0.15/$0.60 | Mechanical, cheap |
| Audit | `article_verifier` | `qwen3.7-max` | 🇨🇳 Qwen | $1.25/$3.75 | Cross-bloc evaluation |
| Synthesis | `synthesis` | `gpt-5.5` | 🇺🇸 OpenAI | $5/$30 | Frontier writing |

**Cross-lab diversity:** 6 labs (Perplexity, Anthropic, xAI, OpenAI, Qwen) × 2 blocs  

---

## 4. New Prompts Required

All new prompts go in `src/reasoner/phases/article.py`.

| System prompt constant | Purpose |
|---|---|
| `ARTICLE_OUTLINE_SYSTEM` | Argument map architect — constructs logical blueprint, not prose |
| `ARTICLE_CRITIC_SYSTEM` | Devil's advocate — finds structural weaknesses, implicit assumptions, ignored counterarguments |
| `ARTICLE_DEVELOPMENTAL_EDIT_SYSTEM` | Developmental editor — fixes structure, evidence, flow; preserves voice |
| `ARTICLE_STYLE_EDIT_SYSTEM` | Style editor — refines readability while matching publication conventions |
| `ARTICLE_COPY_EDIT_SYSTEM` | Copy editor — grammar, consistency, formatting, source normalization |
| `ARTICLE_FINAL_AUDIT_SYSTEM` | Final auditor — structured checklist evaluation of the complete article |

| Prompt function | Purpose |
|---|---|
| `article_outline_prompt(state)` | Injects topic, sources, style brief → produces argument map JSON |
| `article_critic_prompt(state)` | Injects draft, argument map, fact-check results → produces structural critique |
| `article_developmental_edit_prompt(state)` | Injects draft, critique, fact-check results → produces revised draft |
| `article_style_edit_prompt(state)` | Injects revised draft, style brief → produces stylistically refined draft |
| `article_copy_edit_prompt(state)` | Injects styled draft → produces final copy with normalized citations |
| `article_final_audit_prompt(state)` | Injects final draft → produces structured audit JSON |

---

## 5. Flow Code Changes

### `src/reasoner/application/flows/article.py`

```python
class ArticleFlow(WorkflowStrategy):
    def get_phases(self, state: PipelineState) -> List[PhaseStep]:
        return [
            PhaseStep(2,  "Evidence Collection",     run_article_retrieve_sources_phase, _ser_2),
            PhaseStep(3,  "Argument Map / Outline",   run_article_outline_phase,         _ser_2),     # NEW
            PhaseStep(4,  "First Draft",              run_article_draft_phase,            _ser_3),
            PhaseStep(5,  "Fact Check + Claim Ledger",run_article_adversarial_verify_phase, _ser_4),
            PhaseStep(6,  "Structural Review",        run_article_structural_review_phase,_ser_4),     # NEW
            PhaseStep(7,  "Developmental Edit",       run_article_developmental_edit_phase,_ser_4),    # NEW
            PhaseStep(8,  "Style + Copy Edit",        run_article_style_copy_edit_phase,  _ser_5),     # NEW
            PhaseStep(9,  "Final Audit",              run_article_final_audit_phase,      _ser_5),     # NEW
            PhaseStep(10, "Synthesis",                run_synthesis_phase,                _ser_5),
        ]
```

The `style + copy edit` is a single `PhaseStep` function that makes two sequential LLM calls internally — one for style (`article_humanize`), one for copy (`writing_assemble`). This keeps the flow manageable (10 phases) while preserving the editorial separation.

### `src/reasoner/application/flows/article_phases.py`

New functions:

| Function | Role | Description |
|---|---|---|
| `run_article_outline_phase` | `article_sot_skeleton` | Builds argument map + outline JSON |
| `run_article_structural_review_phase` | `article_critic` | Adversarial structural critique |
| `run_article_developmental_edit_phase` | `article_revise` | Argument/structure/flow revision |
| `run_article_style_copy_edit_phase` | `article_humanize` → `writing_assemble` | Sequential style then copy passes |
| `run_article_final_audit_phase` | `article_verifier` | Structured checklist audit |

Enhanced existing function:
- `run_article_draft_phase` — now consumes `writing_state["outline"]` and `writing_state["argument_map"]` from Phase 2
- `run_article_adversarial_verify_phase` — now outputs structured claim ledger in addition to existing format

---

## 6. Preset Registry Changes

### `article-budget` — New routing entries

```
"article_sot_skeleton": "deepseek-v4-flash",  # 🇨🇳 DeepSeek — fast structured planning, 1M ctx
"article_critic":       "hermes-4-70b",       # 🇺🇸 Nous Research — critic-specialized adversarial review
"article_revise":       "deepseek-v3",        # 🇨🇳 DeepSeek — voice-consistent developmental editing
"article_humanize":     "qwen3.7-plus",       # 🇨🇳 Qwen — editorial refinement, style matching
"article_verifier":     "qwen3.7-plus",       # 🇨🇳 Qwen — structured final audit
```

### `article-premium` — New routing entries

```
"article_sot_skeleton": "claude-sonnet",      # 🇺🇸 Anthropic — best planning/outlining
"article_critic":       "grok-4.3",           # 🇺🇸 xAI — strongest adversarial reasoning
"article_revise":       "gpt-5",              # 🇺🇸 OpenAI — strong editorial judgment
"article_humanize":     "claude-sonnet",      # 🇺🇸 Anthropic — best voice-preserving refinement
"article_verifier":     "qwen3.7-max",        # 🇨🇳 Qwen — cross-bloc final audit
```

Also fill in the currently-missing routes:
```
"writing_draft":     "claude-sonnet",         # (already in primary_id fallback, but explicit)
"writing_assemble":  "gpt-4o-mini",           # cheap, reliable copy edit
"writing_outline":   "claude-sonnet",         # alias for consistency with WritingFlow preset naming
```

---

## 7. Implementation Steps

### Step 1 — New prompts (`src/reasoner/phases/article.py`)
| Action | Risk |
|---|---|
| Add `ARTICLE_OUTLINE_SYSTEM` + `article_outline_prompt(state)` | Low — pure prompt, no flow impact |
| Add `ARTICLE_CRITIC_SYSTEM` + `article_critic_prompt(state)` | Low |
| Add `ARTICLE_DEVELOPMENTAL_EDIT_SYSTEM` + `article_developmental_edit_prompt(state)` | Low |
| Add `ARTICLE_STYLE_EDIT_SYSTEM` + `article_style_edit_prompt(state)` | Low |
| Add `ARTICLE_COPY_EDIT_SYSTEM` + `article_copy_edit_prompt(state)` | Low |
| Add `ARTICLE_FINAL_AUDIT_SYSTEM` + `article_final_audit_prompt(state)` | Low |
| Enhance `article_draft_prompt` to consume argument map | Med — affects existing prompt |
| Enhance `article_verify_prompt` to output claim ledger | Med — affects existing prompt |

### Step 2 — New phase functions (`src/reasoner/application/flows/article_phases.py`)
| Action | Risk |
|---|---|
| Add `run_article_outline_phase` | Low — new code, no existing callers |
| Add `run_article_structural_review_phase` | Low |
| Add `run_article_developmental_edit_phase` | Low |
| Add `run_article_style_copy_edit_phase` (2 sequential calls) | Low |
| Add `run_article_final_audit_phase` | Low |
| Enhance `run_article_draft_phase` to pass argument map | Med |
| Enhance `run_article_adversarial_verify_phase` to store claim ledger | Med |

### Step 3 — Update ArticleFlow (`src/reasoner/application/flows/article.py`)
| Action | Risk |
|---|---|
| Replace `get_phases()` with 10-phase sequence | High — structural change |
| Import new phase functions | Low |

### Step 4 — Update presets (`src/reasoner/domain/preset_registry.py`)
| Action | Risk |
|---|---|
| Add new routing entries to `article-budget` | Med — preset validation |
| Add new routing entries to `article-premium` | Med |
| Run `python scripts/validate_presets.py` | — verification |

### Step 5 — Update methods_and_presets.md
| Action | Risk |
|---|---|
| Reflect new phase count and roles in article presets table | Low |

### Step 6 — Verify
| Action |
|---|
| `python scripts/validate_presets.py` — all presets must pass |
| `pytest tests/unit/test_article_*.py` — existing tests must still pass (if any) |
| Manual: run an article with the budget preset and verify phase sequencing |

---

## 8. Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| **Phase explosion** — 9 LLM calls increases latency 2.25× and cost proportionally | P2 | Each phase uses cheaper budget models where possible (deepseek-v4-flash for outline/copy, gpt-4o-mini for audit). Premium users accept higher cost. Add `skip_*` config flags for opt-out. |
| **Prompt regression** — enhancing existing draft/verify prompts could degrade current quality | P1 | Preserve existing prompt structure. Add argument map as an optional injection — if outline phase fails, draft falls back to current behavior. |
| **Existing article presets break** — adding new routing keys changes preset validation | P0 | Run validator before and after. All new roles use existing `_KNOWN_ROUTING_ROLES` keys — no new constants needed. |
| **ArticleFlow vs WritingFlow divergence** — two flows diverge in quality | P2 | WritingFlow should eventually be upgraded to match, but out of scope for this plan. |
| **Token budget** — argument map + outline + draft + critique + edit stages may exceed context | P1 | Each phase trims input to relevant subset. Argument map is JSON (compact). Critique receives summary, not full sources. |

---

## 9. Open Questions

1. **Style brief corpus analysis** — the user's Phase 8 recommends analyzing 20-50 articles from the target publication. This is impractical to automate in a single pipeline run. Should we defer this to a pre-processing step (user uploads or provides publication name → we fetch and analyze), or leave it as manual guidance?

2. **Retry loop for audit failures** — the plan says "1 retry if audit score below threshold." Should this be configurable per preset?

3. **Should WritingFlow be upgraded to match?** — WritingFlow (outline → draft → fact-check → assemble) currently has 5 phases vs ArticleFlow's proposed 10. Should both flows converge on the same editorial architecture, or is WritingFlow intentionally lighter for faster turnaround?

4. **Human-in-the-loop hooks** — the user's methodology emphasizes human-led phases (idea development, final approval). Should we add explicit "pause for human review" hooks in the pipeline, or are these out of scope for the automated flow?

5. **Cost per article** — 9 LLM calls at budget tier is roughly $0.005-0.01 per article. At premium, $0.05-0.10. Are these acceptable cost targets?
