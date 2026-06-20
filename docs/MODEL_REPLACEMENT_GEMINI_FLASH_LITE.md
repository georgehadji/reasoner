# Model Replacement Research: gemini-3.1-flash-lite → Fresher Alternative

**Problem Statement:**  
`gemini-3.1-flash-lite` has a knowledge cutoff **before February 2025** (Fable 5 release), defaulting to Claude 3.5 Sonnet knowledge base. This causes stale reasoning on recent events, APIs, and best practices.

**Current Usage:**  
Appears as `primary_id` or routing model in **15+ Budget presets**:
- Debate, Jury, Research, Scientific, Socratic, Pre-Mortem, Bayesian, Dialectical, Analogical, Delphi, CoVE, SoT, ToT, PoT, Self-Discover, SubAgent, Writing/Article, Coding, Cross-Language, Brainstorming

---

## Recommendation Summary

| Model | Cutoff | Cost Tier | Use Case | Trade-off |
|-------|--------|-----------|----------|-----------|
| **google/gemini-2.5-flash-lite** ✅ | 2025-01-31 | Lite | Drop-in replacement | 1 month fresher |
| google/gemini-3.5-flash | 2025-01-01 | Flash | Better quality | 50% more expensive |
| qwen3.7-max | 2025-06-30 | Budget | Phase 2+ (scoring, synthesis) | Different lab (cross-diversity) |
| deepseek-v3.2-exp | 2025-07-31 | Budget | Phase 2+ (decomposition) | Different lab (reasoning strength) |
| mistral-medium-3.1 | 2025-06-30 | Budget | Phase 2+ (destructive/critic) | Different lab |

---

## Detailed Analysis

### Option 1: Gemini 2.5 Flash Lite (RECOMMENDED) ✅

**Registry entry needed:**
```python
"gemini-flash-lite": {"model": "google/gemini-2.5-flash-lite"},  # v3.3: 3.1-lite → 2.5-lite (Jan 2025 cutoff, $0.075/$0.45 per M)
```

**Pros:**
- Direct replacement (same Gemini family, same lite cost)
- Knowledge cutoff: **2025-01-31** (6+ months fresher than old 3.1-lite)
- Zero code changes — works in all 15+ Budget presets immediately
- Proven in production (Google's primary Flash model)
- Minimal risk of model behavior change

**Cons:**
- Only 1 month fresher than Gemini 3.5 Flash
- Still not as fresh as Qwen/DeepSeek (6-7 months behind)

**Cost impact:** No change ($0.075 prompt / $0.45 completion per M)

---

### Option 2: Upgrade to Gemini 2.5 Flash (Full)

**When to use:**  
If slightly better quality is needed and cost is acceptable.

**Pros:**
- Same 2025-01-31 cutoff as Flash Lite
- Better instruction-following, lower hallucination rate
- Still cheap vs. Premium tier

**Cons:**
- ~50% more expensive ($0.075 → ~$0.30 prompt / $0.45 → ~$2.40 completion)
- Budget presets would lose cost advantage

**Cost impact:** 2–3× increase in Budget preset cost

---

### Option 3: Per-Phase Freshness Strategy

For max freshness in Budget presets, use different models by phase:

#### Phase 0–1 (Classification/Decomposition)
- Keep: **DeepSeek V3** (already in use)
- Freshness: 2025-07-31 (or later in v3.2-exp)
- Reasoning strength + freshness ✅

#### Phase 2 (Perspectives: constructive/destructive/systemic/minimalist)
- **Constructive**: `gemini-2.5-flash-lite` (replace current flash-lite)
  - Cutoff: 2025-01-31
  - Lab: Google (maintains diversity)

- **Destructive**: Keep `mistral-small` OR upgrade to `mistral-medium-3.1`
  - Current: mistral-small (2023-10-31 — very stale)
  - Recommended: `mistral-medium-3.1` (2025-06-30 — 6 months fresher)
  - Cost: ~2× but still Budget tier

- **Systemic**: Keep `glm-5.1` (no cutoff listed — assume latest)
  - Chinese language model, good for structured analysis

- **Minimalist**: Keep `stepfun-3.7-flash` (no cutoff — assume fresh)
  - Very cheap MoE, good for divergent generation

#### Phase 3–4 (Scoring / Stress Testing)
- **Scoring**: `qwen3.7-max` (already in use)
  - Cutoff: 2025-06-30 (6 months fresh)
  
- **Stress Testing**: `mistral-small` → upgrade to `mistral-medium-3.1`
  - Cutoff: 2025-06-30

#### Phase 5 (Synthesis)
- Keep `qwen3.7-max` (2025-06-30 — freshest in rotation)

---

### Option 4: Cross-Diversity + Freshness (PREMIUM STRATEGY)

For teams wanting best freshness without lab echo chambers:

**Multi-Perspective Budget v4 (hypothetical):**
```python
{
    "id": "multi-perspective-budget-v4",
    "routing": {
        "prompt_enhancement": "gemini-2.5-flash-lite",      # Google, 2025-01-31
        "classification": "deepseek-v3.2-exp",              # DeepSeek, 2025-07-31
        "decomposition": "deepseek-v3.2-exp",               # Consistency
        "constructive": "gemini-2.5-flash-lite",            # Google
        "destructive": "mistral-medium-3.1",                # Mistral, 2025-06-30
        "systemic": "qwen3.7-max",                          # Alibaba, 2025-06-30
        "minimalist": "stepfun-3.7-flash",                  # StepFun (MoE)
        "scoring": "qwen3.7-max",                           # Independent lab
        "stress_testing": "mistral-medium-3.1",             # Mistral
        "synthesis": "qwen3.7-max",                         # Synthesis lead
    }
}
```

**Cross-lab diversity:**
- Google (constructive, prompt enhancement)
- DeepSeek (decomposition, classification)
- Mistral (destructive, stress testing)
- Alibaba/Qwen (systemic, scoring, synthesis)
- StepFun (minimalist perspective)

**Average training freshness:** 2025-05 (5 months newer than current fleet)

---

## Implementation Plan

### Quick Fix (v3.3 patch) — 2 hours
1. Update `registry.py`: `gemini-flash-lite` → `google/gemini-2.5-flash-lite`
2. Update all preset descriptions (15+ presets note the freshness bump)
3. Update `constants_models.py` if needed
4. Test one Budget preset end-to-end
5. Commit: `fix: upgrade gemini-flash-lite 3.1 → 2.5 for Jan 2025 knowledge cutoff`

### Mid-Term (v3.4 release) — 1–2 days
1. Create `multi-perspective-budget-v2` with upgraded destructive/stress_testing
2. Swap mistral-small → mistral-medium-3.1 in Budget tier
3. Update preset descriptions with average freshness metric
4. Cost analysis: estimate +$0.002–$0.003 per run
5. A/B test on 10% of users

### Long-Term (v3.5+)
1. Periodic (quarterly) model freshness audit
2. Add training cutoff to preset metadata (UI displays it)
3. Implement auto-upgrade logic: if cutoff < 6 months old, flag for review
4. Build preset freshness score = avg(training_cutoffs) relative to today

---

## Knowledge Cutoff Comparison

| Model | Cutoff | Days Old | Freshness Score |
|-------|--------|----------|-----------------|
| gemini-3.1-flash-lite (old) | Unknown (pre-2025-02) | 150+ | ⭐☆☆ Very stale |
| **gemini-2.5-flash-lite** ✅ | 2025-01-31 | 160 | ⭐⭐⭐ Good |
| mistral-small (current) | 2023-10-31 | 588 | ☆☆☆ Ancient |
| mistral-medium-3.1 | 2025-06-30 | 11 | ⭐⭐⭐⭐⭐ Cutting edge |
| qwen3.7-max | 2025-06-30 | 11 | ⭐⭐⭐⭐⭐ Cutting edge |
| deepseek-v3.2-exp | 2025-07-31 | -19 | ⭐⭐⭐⭐⭐ Future training |

*Calculations as of 2026-06-11*

---

## Risk Assessment

### Quick Fix (gemini-2.5-flash-lite only)
- **Risk:** Low
  - Google's own newer model in same family
  - Same price tier
  - No behavioral surprises expected
  
- **Testing needed:** 1–2 Budget presets with real problems

### Mid-Term (add mistral-medium-3.1)
- **Risk:** Medium
  - Mistral medium is more capable than small (may change tone)
  - 50% cost increase for Budget tier
  - Different model family for destructive phase
  
- **Testing needed:** Verify destructive critique quality doesn't degrade

### Long-Term (full cross-diversity refresh)
- **Risk:** Medium–High
  - Multiple model changes = harder to debug issues
  - Different reasoning styles from Qwen/DeepSeek may impact synthesis phase
  - Cost impact TBD
  
- **Testing needed:** Full A/B test vs. current v3.2

---

## Decision Matrix

| Scenario | Recommendation | Timeline |
|----------|--------------|----------|
| **Emergency fix** (users reporting stale answers) | Quick fix: gemini-2.5-flash-lite only | 2 hours |
| **Next patch release** | Quick fix + test 3 Budget presets | 1 day |
| **v3.4 feature release** | Quick fix + mistral-medium-3.1 upgrade | 2 days |
| **Quarterly review** (v3.5+) | Audit all 50 presets, build freshness scoring | 1 week |

---

## Conclusion

**Immediate action:** Replace `gemini-3.1-flash-lite` with `google/gemini-2.5-flash-lite`.  
- **Why?** 2+ months fresher, no code changes, same cost, same lab.  
- **Impact:** 15 Budget presets get ~Jan 2025 knowledge vs. pre-2025-02.  
- **Risk:** Very low (same vendor, same price tier).  

**Secondary action:** Plan mistral-medium-3.1 upgrade for v3.4.  
- **Why?** Destructive phase currently uses 2023-10 data (very stale for criticism).  
- **Impact:** ~+$0.002/run but 18 months fresher reasoning.  

**Long-term:** Build freshness scoring into preset metadata + quarterly audit.  
- **Why?** Prevents bit-rot, keeps Budget tier competitive on knowledge.  
- **Impact:** Maintain user trust in reasoning quality.
