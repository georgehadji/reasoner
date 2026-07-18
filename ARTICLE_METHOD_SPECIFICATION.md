# Article Method Specification

Complete deep-dive of the Article workflow: editorial pipeline for research-backed, source-grounded long-form content.

---

## 1. Article Method Overview

**Purpose**: Publication-grade editorial pipeline. Orchestrates evidence collection, structural planning, multi-pass drafting, adversarial fact-checking, developmental editing, final audit. Output: finished, citeable articles.

**When to Use**:
- User requests "Write an article about..." or "Draft a blog post"
- Content requires sources (web search, domain knowledge)
- Long-form output required (800-1200 words) with structured argument
- Output must include inline citations and claim verification

**Cost Baseline**:
- Budget: $0.40-0.60, 2-4 min, 8-12 LLM calls
- Premium: $1.20-1.80, 3-6 min, same phases, stronger models

---

## 2. Workflow Phases (Sequential)

| Phase | Role | Trigger | Input | Output |
|-------|------|---------|-------|--------|
| **Pre-Augment** | Optional | Deep question detected | Problem, debate/critique findings | Pre-research insights |
| **Retrieve Sources** | `primary` | Always | Problem + generated queries | URLs, metadata, snippets |
| **Outline/Argument Map** | `article_sot_skeleton` | Always | Sources, problem | Hierarchy, sections, title |
| **Draft** | `writing_draft` | Always | Sources, outline, (optional style brief) | 800-1200 word article |
| **Fact-Check** | `writing_factcheck` | Always | Article, sources | Verified claims ledger |
| **Structural Critique** | `article_critic` | Always | Article, outline, critique | Logic gaps, assumptions, rigor score |
| **Developmental Edit** | `article_revise` | Always | Article, critique feedback | Revised article |
| **Style + Copy Edit** | `article_humanize` + `writing_assemble` | Always | Article | Polished article |
| **Final Audit** | `article_verifier` | Always | Polished article | Audit checklist, score |
| **Synthesis** | `synthesis` | Always | All above | Article + metadata, claim labels |

**Control Flow**:
- Standard: retrieve → outline → draft → fact-check → critique → dev edit → style/copy → audit → synthesis
- If Final Audit fails (`passes_audit=false`): retry once (dev edit → style/copy → audit); abort if second audit also fails
- Phase skipping: none (article always runs all 9 phases + synthesis)

---

## 3. Augmentation (Optional, Pre-Pipeline)

**Trigger**: `is_deep_question()` detects philosophical, definitional, ethical, or conceptual questions

**Process**:
- Runs `debate` method + `iterative_critique` in parallel (independent budget, concurrent)
- Captures diverse perspectives on core tension
- Stores in `state.writing_state["pre_research_summary"]`

**Injection Point**:
- Subsequent phases (draft, critique, synthesis) receive augmentation context in system prompt
- "Consider the following perspectives gathered through debate: [pre_research_summary]"

**Cost**: Adds $0.20-0.40 to budget preset; skipped for factual questions

---

## 4. Retrieve Sources

**Search Strategy**:

1. **Query Generation**:
   - LLM generates 3-5 targeted search queries from problem
   - Queries: specific, answerable, covering different facets
   
2. **Backend Chain**:
   - Budget: Brave → Tavily → Perplexity
   - Premium: Brave LLM → Perplexity Deep → Tavily
   - Dispatches all queries in parallel
   
3. **Result Aggregation**:
   - Flatten by URL (dedup)
   - Extract: title, URL, author, date, publisher, snippet (≤500 chars)
   - Rank by relevance + source authority
   - Return top-16 results

**Constants**:
```
ARTICLE_MIN_SOURCE_COUNT = 8
ARTICLE_MAX_SOURCES_FOR_PROMPT = 16  (truncation for outline/draft phases)
ARTICLE_SEARCH_RESULTS_PER_QUERY = 6
ARTICLE_MIN_CLAIM_SUPPORT_RATIO = 0.5  (quality gate for fact-check)
```

**Fallback**:
- If no sources retrieved: set `insufficient_evidence=true`, log warning, proceed with general knowledge (mark unverified claims `[UNVERIFIED]`)

**Output**:
```python
state.writing_state["retrieved_sources"] = [
    {"url": "...", "title": "...", "snippet": "...", "date": "...", "authority_score": 0.85},
    ...
]
state.writing_state["source_metadata"] = {source counts, date ranges, publisher list}
```

---

## 5. Outline & Argument Map

**Purpose**: Logical blueprint *before* drafting. Ensures structural coherence, evidence alignment.

**Structure**:
```json
{
  "suggested_title": "string",
  "central_question": "What is the core question this article answers?",
  "argument_map": {
    "problem": "Why this matters now",
    "current_explanations": ["view A", "view B"],
    "limitations": ["what current views miss"],
    "new_insight": "What this article uniquely contributes",
    "evidence_sources": ["url1", "url2"],
    "counterarguments": ["objection X", "objection Y"],
    "implications": ["what follows from this insight"],
    "conclusion_type": "call_to_action | forward_looking | synthesis"
  },
  "outline": [
    {
      "section_title": "Section Name",
      "key_points": ["point A", "point B"],
      "sources_to_cite": ["url"],
      "estimated_word_count": 250
    },
    ...
  ],
  "total_word_count_target": 1200
}
```

**Editorial Constraints** (enforced in prompt):
- Central question must be answerable from sources (not speculation)
- New insight differs from current explanations (not restatement)
- Counterarguments required (rigor, not echo chamber)
- Implications tied to evidence (not speculation)
- Section word counts sum to target (800-1200)

**Output**:
```python
state.writing_state["argument_map"] = {...}
state.writing_state["outline"] = [...]
state.writing_state["suggested_title"] = "..."
```

---

## 6. Draft Generation

**Input**:
- Sources (top-16 + snippets)
- Argument map + outline
- Pre-research insights (if augmented)
- Optional style brief: `{"author": "Malcolm Gladwell", "publication": "The New Yorker"}`

**Directives** (in prompt):
1. Open with specific anecdote/scene/fact (not generic statement)
2. Inline citations for every factual claim: `[Source Title](URL)`
3. Mark unverified claims: `[UNVERIFIED]`
4. Incorporate pre-research perspectives (if augmented)
5. Close with forward-looking or thought-provoking conclusion
6. Target: 800-1200 words
7. End with `## Sources` section (all cited URLs)

**Voice Preservation**:
- If style brief provided: "Emulate [author]'s sentence rhythm, vocabulary, narrative devices"
- Preference: preserve original voice over perfect grammar (revised in style edit)

**Output**:
```python
state.writing_state["final_article"] = "# Article Title\n\n..."  # markdown
```

---

## 7. Fact-Check Phase

**Adversarial Verification** (anti-hallucination):
- LLM acts as rigorous fact-checker (not cheerleader)
- Assumption: author may have hallucinated stats, misattributed quotes, overgeneralized
- Verify: claims from provided sources *only* (or via live web search if using Sonar)

**Two Paths**:
1. **Standard** (Budget): Check claims against provided sources
2. **Sonar** (Premium): Independent live web search verification

**Claim Verification Logic**:
- Extract all factual claims from article (≤50)
- For each claim: find supporting evidence in sources
- Verdict: `supported | partially_supported | unsupported`
- Source must directly support or quote-match (not inference)

**Output**:
```json
{
  "verified_claims": [
    {
      "claim": "exact quote from article",
      "verdict": "supported | partially_supported | unsupported",
      "source_url": "url or null",
      "note": "brief explanation"
    },
    ...
  ],
  "metrics": {
    "total_claims": 42,
    "supported": 28,
    "partially_supported": 9,
    "unsupported": 5,
    "claim_support_ratio": 0.667
  },
  "gaps": ["topic lacking evidence"],
  "high_risk_sentences": ["sentence 1", "sentence 2"],
  "claim_ledger": [
    {"claim": "...", "source": "url", "status": "verified | supported | speculative | unsupported"}
  ]
}
```

**Quality Gate**:
- If `claim_support_ratio < 0.5`: set `insufficient_evidence=true`, log gaps
- Gate doesn't block flow; gaps noted for downstream phases

**Stored**:
```python
state.writing_state["verification"] = {...}
state.writing_state["claim_ledger"] = [...]
state.writing_state["metrics"] = {...}
state.writing_state["gaps_noted"] = [...]
```

---

## 8. Structural Adversarial Critique

**Purpose**: Devil's advocate—logic & rigor, not fact-checking or grammar.

**Scope** (merciless):
- Which claims lack *evidence quality* (not just citation count)?
- Unstated assumptions? Hidden premises?
- Obvious counterarguments ignored or weakly addressed?
- Speculative leaps beyond evidence?
- Terms used non-standardly?
- Reader misunderstanding risks?
- Circular reasoning?

**Output**:
```json
{
  "implicit_assumptions": [
    {"assumption": "...", "section": "Intro", "risk": "high|medium|low"},
    ...
  ],
  "ignored_counterarguments": [
    {"argument": "...", "relevance": "high|medium|low"},
    ...
  ],
  "logical_gaps": [
    {"gap": "Claims X, then jumps to Y without bridge", "severity": "high|medium|low"},
    ...
  ],
  "speculative_leaps": [
    "sentence extrapolating beyond sources"
  ],
  "misunderstanding_risks": [
    "sentence reader could misinterpret X as Y"
  ],
  "overall_rigor_score": 0.75
}
```

**Stored**:
```python
state.writing_state["structural_critique"] = {...}
```

---

## 9. Developmental Edit

**Input**:
- Draft article
- Structural critique
- Original argument map
- Fact-check ledger

**Priorities** (in order):
1. **Argument**: Fix logical gaps, shore up weak reasoning, address ignored counterarguments
2. **Evidence**: Strengthen weak claims (add citations); remove unsupported claims
3. **Narrative Flow**: Smooth transitions, remove redundancies, ensure each ¶ advances thesis
4. **Accuracy**: Correct technical inaccuracies; do NOT invent new facts

**Constraints**:
- Preserve author's voice, sentence rhythm, vocabulary register (style edit handles refinement later)
- Restructure paragraphs as needed, add qualifying language
- Do NOT change structural choices made by author

**Output**:
```python
state.writing_state["final_article"] = "# Article Title\n\n... (revised)"
```

---

## 10. Style & Copy Edit

**Dual-Pass Sequential Pipeline**:

**Pass 1: Style Edit** (`article_humanize` role):
- Vary sentence length/structure for rhythm
- Replace generic/hedging phrases with confident language
- Adjust vocabulary register to target publication
- Break up long/monotonous paragraphs
- Fix word repetition, awkward phrasing
- **Preserve**: voice, argument intent, all facts, all citations

**Pass 2: Copy Edit** (`writing_assemble` role):
- Grammar, punctuation, spelling (Oxford comma, em-dashes, etc.)
- Inconsistent terminology/formatting
- Citation format consistency (all `[Title](URL)`)
- Run-on sentences, comma splices
- Subject-verb agreement, tense consistency
- Formatting: headings, bold, italics
- **Do NOT change**: sentence structure, word choice, factual content

**Output**:
```python
state.writing_state["final_article"] = "# Article Title\n\n... (polished)"
```

---

## 11. Final Editorial Audit

**Pre-Publication Structured Checklist**. Scores 7 dimensions (0.0-1.0 each).

| Dimension | Definition | Pass Threshold |
|-----------|-----------|---|
| **Thesis Advancement** | Every paragraph advances central thesis | ≥0.6 |
| **Claim Support** | All significant claims supported by evidence | ≥0.6 |
| **Internal Consistency** | Reasoning logically consistent throughout | ≥0.6 |
| **Transition Quality** | Smooth, logical transitions between sections | ≥0.6 |
| **Redundancy Removed** | No redundant material remains | ≥0.6 |
| **Citation Accuracy** | All citations correctly formatted, in ## Sources | ≥0.6 |
| **Policy Compliance** | Complies with AI-use disclosure, TOC, etc. | ≥0.6 |

**Output**:
```json
{
  "audit": {
    "thesis_advancement": 0.9,
    "claim_support": 0.85,
    "internal_consistency": 0.88,
    "transition_quality": 0.92,
    "redundancy_removed": 0.95,
    "citation_accuracy": 0.98,
    "policy_compliance": 1.0
  },
  "issues": [
    {
      "section": "Intro",
      "severity": "high|medium|low",
      "description": "Opening example doesn't connect to thesis",
      "fix_suggestion": "Lead with cited statistic instead"
    }
  ],
  "audit_score": 0.91,
  "passes_audit": true
}
```

**Pass Criteria**:
- `passes_audit=true` iff all dimensions ≥0.6 **AND** `audit_score ≥ 0.6`
- If false: **single retry** (Developmental Edit → Style/Copy → Final Audit again)
- If second audit also fails: article ships as-is with `passes_audit=false` in metadata

**Stored**:
```python
state.writing_state["editorial_audit"] = {...}
```

---

## 12. Synthesis

**Aggregation**: Combine article + all metadata into `FinalSolution`.

**Process**:
1. Extract critical insights from audit + critique
2. Label all key claims using claim_ledger: `verified | supported | speculative | unsupported`
3. Compute metadata:
   - `word_count`: Length of final_article
   - `sources_used_count`: Distinct URLs in ## Sources
   - `claims_verified_count`: # with status=verified
   - `total_claims_audited`: # from ledger
   - `claim_support_ratio`: supported/total
4. Build action blueprint: "Read full article for in-depth analysis"

**Output** (stored in `state.core.final_solution`):
```json
{
  "core_solution": "# [Article Title]\n\n[Full article markdown]",
  "critical_insights": [
    {
      "insight": "Insight A",
      "evidence": "From [Source Name]",
      "label": "verified"
    }
  ],
  "action_blueprint": [
    {
      "step": "Read full article",
      "rationale": "Comprehensive analysis with citations"
    }
  ],
  "open_questions": [
    {
      "question": "How does X scale to Y?",
      "why_matters": "Critical for implementation"
    }
  ],
  "claim_labels": {
    "claim_key_1": "verified",
    "claim_key_2": "supported",
    ...
  },
  "meta_audit": {
    "models_used": ["sonar", "claude-sonnet", "gpt-4o-mini", ...],
    "total_tokens": 45000,
    "total_cost_usd": 0.52,
    "duration_seconds": 187,
    "sources_used": 9,
    "word_count": 1087,
    "audit_score": 0.91,
    "passes_audit": true
  }
}
```

---

## 13. Model Routing

**Budget Preset** (`article-budget`):

| Role | Model | Bloc | Cost | Purpose |
|------|-------|------|------|---------|
| `primary` | sonar | 🇪🇺 | $0.15/run | Native web search |
| `article_sot_skeleton` | gpt-4o-mini | 🇺🇸 | $0.05 | Outline generation |
| `writing_draft` | claude-sonnet | 🇺🇸 | $0.20 | Long-form prose (1M context) |
| `writing_factcheck` | sonar | 🇪🇺 | $0.10 | Live verification |
| `article_critic` | hy3 (Tencent) | 🇨🇳 | $0.08 | Adversarial logic review |
| `article_revise` | deepseek-v4-flash | 🇨🇳 | $0.10 | Developmental edit |
| `article_humanize` | claude-sonnet | 🇺🇸 | $0.15 | Style preservation |
| `writing_assemble` | gpt-4o-mini | 🇺🇸 | $0.05 | Copy edit |
| `article_verifier` | hy3 (Tencent) | 🇨🇳 | $0.08 | Final audit |

**Premium Preset** (`article-premium`):

| Role | Model | Bloc | Cost | Purpose |
|------|-------|------|------|---------|
| `primary` | sonar-pro | 🇪🇺 | $0.40 | Higher-context web search |
| `article_sot_skeleton` | claude-sonnet | 🇺🇸 | $0.15 | Structural alignment (1M context) |
| `writing_draft` | claude-sonnet | 🇺🇸 | $0.20 | Best long-form (1M context) |
| `writing_factcheck` | sonar-pro | 🇪🇺 | $0.25 | Deep live verification |
| `article_critic` | grok-4.3 (xAI) | 🇺🇸 | $0.30 | Adversarial reasoning (97.7% τ²-Bench) |
| `article_revise` | deepseek-v4-pro | 🇨🇳 | $0.25 | Cross-bloc dev edit (1.6T MoE) |
| `article_humanize` | claude-sonnet | 🇺🇸 | $0.15 | Voice preservation |
| `writing_assemble` | gpt-4o-2024-11-20 | 🇺🇸 | $0.10 | Copy edit |
| `article_verifier` | qwen3.7-max | 🇨🇳 | $0.20 | Cross-bloc audit (1M context) |

**Bloc Diversity**:
- Budget: US (Claude, GPT) + EU (Sonar) + CN (DeepSeek, Tencent) mix
- Premium: Deliberate cross-bloc (Anthropic→xAI→DeepSeek→Qwen) to resist consensus distortion

**Fallback Chain**:
- Primary → cross-bloc equivalent → OpenRouter

---

## 14. Configuration & Constants

**Token Budgets**:
```python
PHASE_TOKEN_BUDGETS = {
    "default_llm_role": 1536,
    "synthesis": 32768  # shared across all methods
}
```
(Articles use default budgets; synthesis allows full article + metadata integration)

**Timeout Settings**:
```python
PHASE_TIMEOUTS = {
    "Retrieve Sources": 240.0,  # Web search can be slow
    "Synthesis": 240.0
}
```

**Quality Gates**:
- `ARTICLE_MIN_SOURCE_COUNT = 8`
- `ARTICLE_MAX_SOURCES_FOR_PROMPT = 16` (truncation to fit token budget)
- `ARTICLE_MIN_CLAIM_SUPPORT_RATIO = 0.5` (fact-check quality gate)

**Temperature**: Not explicitly configured per-phase; uses provider defaults

---

## 15. State Management

**PipelineState Integration**:

```python
state.writing_state = {
    # Retrieval
    "retrieved_sources": [
        {"url": "...", "title": "...", "snippet": "...", "date": "...", "authority_score": 0.85}
    ],
    "source_metadata": {...},
    
    # Outline
    "argument_map": {...},
    "outline": [...],
    "suggested_title": "...",
    
    # Drafting & Revision
    "final_article": "# Article Title\n\n...",  # Mutated through phases 3-8
    
    # Verification
    "verification": {...},
    "claim_ledger": [...],
    "metrics": {"claim_support_ratio": 0.667, ...},
    "gaps_noted": ["topic X needs more evidence"],
    
    # Critique
    "structural_critique": {...},
    
    # Audit
    "editorial_audit": {...},
    
    # Flags
    "insufficient_evidence": bool,
    "pre_research_summary": "...",  # (if augmented)
    "style_brief": {"author": "...", "publication": "..."},  # (optional)
}
```

**Key Mutations**:
- Phase 2 (outline): populates `argument_map`, `outline`, `suggested_title`
- Phase 3 (draft): **sets** `final_article` to draft markdown
- Phase 4 (fact-check): populates `verification`, `claim_ledger`, `metrics`
- Phase 5 (critique): populates `structural_critique`
- Phase 6 (dev edit): **mutates** `final_article` (revised version)
- Phase 7 (style/copy): **mutates** `final_article` (polished version)
- Phase 8 (audit): populates `editorial_audit`

---

## 16. Error Handling

| Error | Detection | Recovery |
|-------|-----------|----------|
| No sources retrieved | `len(sources)=0` | Set `insufficient_evidence=true`, proceed (mark claims `[UNVERIFIED]`) |
| Outline parse error | JSON exception | Log error, use empty dict fallback |
| Draft generation error | LLM timeout/malformed | Use cached outline as fallback; proceed |
| Fact-check parse error | JSON exception | Log error, skip claim_ledger creation |
| Low claim support | `ratio < 0.5` | Note in `gaps_noted`, continue (not fatal) |
| Structural critique error | JSON exception | Log error, skip critique (proceed to dev edit) |
| Dev edit failure | LLM error/timeout | Skip to style edit |
| Style edit failure | LLM error/timeout | Skip to copy edit |
| Copy edit failure | LLM error/timeout | Proceed to audit with pre-style draft |
| Final audit fails | `passes_audit=false` | **Retry once**: dev edit → style/copy → audit; abort if fails again |

**No Cascading Failures**:
- Each phase produces JSON; parse errors are non-fatal (emit warning, use fallback)
- Worst case: basic diagnostic article ships (never empty)

---

## 17. Output Format & Metadata

**Final Article** (in `state.core.final_solution.core_solution`):

```markdown
# Article Title

Opening anecdote or specific fact...

## Section 1
Evidence-backed content with inline citations: [Source Name](https://url).

## Section 2
...

## Conclusion
Forward-looking synthesis tied to thesis.

## Sources
- [Source Name 1](https://url1)
- [Source Name 2](https://url2)
...
```

**Metadata** (in `state.core.final_solution.meta_audit`):
```json
{
  "word_count": 1087,
  "sources_used": 9,
  "sources_used_count": 9,
  "claims_verified_count": 28,
  "total_claims_audited": 42,
  "claim_support_ratio": 0.667,
  "audit_score": 0.91,
  "passes_audit": true,
  "duration_seconds": 187,
  "total_cost_usd": 0.52,
  "total_tokens": 45000,
  "models_used": ["sonar", "gpt-4o-mini", "claude-sonnet", "hy3", "deepseek-v4-flash"]
}
```

**Claim Labels** (in `state.core.final_solution.claim_labels`):
```python
{
  "claim_key_1": "verified",      # directly confirmed
  "claim_key_2": "supported",     # evidence-based (not verbatim)
  "claim_key_3": "speculative",   # hypothesis/opinion
  "claim_key_4": "unsupported"    # no source found
}
```

**Critical Insights** (extracted from audit):
```json
[
  {
    "insight": "Key finding from article",
    "evidence": "Backed by [Source Name]",
    "label": "verified"
  }
]
```

---

## 18. Performance Baseline

| Metric | Budget | Premium |
|--------|--------|---------|
| Avg Cost | $0.40-0.60 | $1.20-1.80 |
| Avg Duration | 2-4 min | 3-6 min |
| Word Count | 800-1200 | 850-1250 |
| Claim Support Ratio | 65-75% | 75-85% |
| Audit Score | 0.75-0.85 | 0.85-0.95 |
| Sources Used | 6-8 | 8-10 |

---

## 19. Key Invariants

1. **Every phase mutates `state.writing_state["final_article"]`** except retrieval, outline, verification, critique (which populate separate fields; dev edit + style/copy overwrite draft)

2. **Sonar models get special prompts** (`ARTICLE_VERIFY_SYSTEM_SONAR`) leveraging live search; standard verification uses only provided sources

3. **Pre-research augmentation is optional** (triggered by `is_deep_question()`); non-deep questions skip directly to retrieval

4. **Retry is single-shot** on final audit failure; if second audit also fails, article ships as-is with `passes_audit=false`

5. **All roles route through preset registry** — zero hardcoded model selection in phase logic; full flexibility for A/B testing

6. **Editorial audit is not fact-checking** — it checks logic, coherence, rigor, claims advancement; fact-check phase is separate

7. **Sources must be cited** inline with markdown `[Title](URL)` format; all URLs collected into ## Sources section at end

---

## Conclusion

Article method: 9-phase editorial pipeline producing research-backed, citeable long-form content. Every output has transparent source attribution, claim-level confidence labels, and structured audit trail. Bloc-diverse routing (budget/premium tiers) ensures cross-cultural reasoning rigor.

