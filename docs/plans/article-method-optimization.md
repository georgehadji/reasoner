# Article Method — Optimization & Perplexity Integration Plan

## Status

| Change | Status |
|---|---|
| Bug: `main.py` — `state.save()` / `PipelineState.load()` nonexistent methods | ✅ Applied |
| Bug: `models.py` — shim pointed to wrong class (`PipelineService` → `PipelineSerializationService`) | ✅ Applied |
| Bug: `article_phases.py` — missing `import asyncio` | ✅ Applied |
| Optimize `article-budget` preset routing | 🔲 To Do |
| Perplexity `sonar` integration for fact-check role | 🔲 To Do |
| New `article-budget-sonar` preset | 🔲 To Do |
| Validate changes | 🔲 To Do |

---

## Phase 1 — Optimize `article-budget` Preset Routing

**File:** `src/reasoner/domain/preset_registry.py`

**Current state (v3.4):**
```python
"article-budget": {
    "primary_id": "deepseek-v4-flash",
    "routing": {
        "synthesis":         "gpt-4o-mini",
        "article_critic":    "deepseek-v4-flash",
        "article_verifier":  "deepseek-v4-flash",
        "fusion":            "deepseek-v4-flash",
        "meta_evaluator":    "qwen3.7-plus",
        "scoring":           "deepseek-v4-flash",
        "stress_testing":    "ring-2.6-1t",
        "verifier":          "qwen3.7-plus",
    },
}
```
**Problem:** 5 of 6 roles fall back to `deepseek-v4-flash`. Each phase has different requirements and the budget tier has better phase-specific alternatives.

**Target:**
```python
"article-budget": {
    "method": "article",
    "primary_id": "deepseek-v4-flash",
    "routing": {
        "synthesis":          "qwen3.5-flash",        # was gpt-4o-mini: 2.3× cheaper, 8× more context
        "writing_draft":      "deepseek-v4-flash",    # explicit: best price/quality for long-form writing
        "writing_factcheck":  "qwen3.7-plus",         # was deepseek-v4-flash: stronger analytical reasoning
        "writing_assemble":   "deepseek-v4-flash",    # explicit: voice consistency with draft

        # Support roles
        "article_critic":     "deepseek-v4-flash",
        "article_verifier":   "qwen3.7-plus",         # was deepseek-v4-flash: match factcheck role
        "fusion":             "deepseek-v4-flash",
        "meta_evaluator":     "qwen3.7-plus",
        "scoring":            "deepseek-v4-flash",
        "stress_testing":     "ring-2.6-1t",
        "verifier":           "qwen3.7-plus",
    },
    "tags": ["budget", "writing", "article"],
},
```

### Phase 1 — Rationale per change

| Role | Old → New | Why |
|---|---|---|
| `synthesis` | `gpt-4o-mini` → `qwen3.5-flash` | 2.3× cheaper input, 8× more context (1M vs 128K). Excellent JSON compliance. Used as `meta_evaluator` across all budget presets already — proven reliability. |
| `writing_draft` | (fallback) → `deepseek-v4-flash` | Making explicit what was implicit. Best price/quality for creative 1M-ctx writing. No change in behaviour. |
| `writing_factcheck` | `deepseek-v4-flash` → `qwen3.7-plus` | Adversarial verification is an analytical task, not a creative one. `qwen3.7-plus` ($0.32/$1.28) has stronger reasoning for claim classification than `deepseek-v4-flash` ($0.09/$0.18). Worth the token premium for this accuracy-critical phase. |
| `writing_assemble` | (fallback) → `deepseek-v4-flash` | Explicit to pin voice consistency. Same model as draft. |
| `article_verifier` | `deepseek-v4-flash` → `qwen3.7-plus` | Match factcheck role for consistent verification quality. |

### Phase 1 — Validation

- Run `python -m reasoner.main --list-presets` — confirm `article-budget` shows updated routing
- Run article-budget pipeline with a test topic — confirm all phases complete
- Check phase_logs for model assignments — confirm roles are routing correctly
- Compare claim_support_ratio against previous runs (should improve with qwen3.7-plus factcheck)

---

## Phase 2 — Perplexity Sonar Integration

### 2a — Add `writing_factcheck_sonar` role support to `article-budget`

**File:** `src/reasoner/domain/preset_registry.py`

Add a new preset that uses Perplexity sonar for the fact-check phase:

```python
"article-budget-sonar": {
    "method": "article",
    "primary_id": "deepseek-v4-flash",
    "routing": {
        "synthesis":          "qwen3.5-flash",
        "writing_draft":      "deepseek-v4-flash",
        "writing_factcheck":  "sonar",               # ← Perplexity: live web verification + citations
        "writing_assemble":   "deepseek-v4-flash",

        # Support roles
        "article_critic":     "deepseek-v4-flash",
        "article_verifier":   "sonar",               # ← Perplexity: cross-model source verification
        "fusion":             "deepseek-v4-flash",
        "meta_evaluator":     "qwen3.7-plus",
        "scoring":            "deepseek-v4-flash",
        "stress_testing":     "ring-2.6-1t",
        "verifier":           "qwen3.7-plus",
    },
    "tags": ["budget", "writing", "article", "sonar", "verified"],
},
```

### 2b — Add `primary` role to use Perplexity for native source retrieval

**File:** `src/reasoner/domain/preset_registry.py`

```python
"article-budget-sonar": {
    ...
    "routing": {
        ...
        "primary":            "sonar",               # ← replaces external search pipeline with native Perplexity search
        ...
    },
}
```

**Impact:** The `run_article_retrieve_sources_phase` function (`article_phases.py:18-57`) will invoke `sonar` for the `primary` role. The sonar model's built-in web search (configured with `search_recency_filter: "year"` and domain filters) will:
1. Generate search queries internally (no separate query-planning LLM call needed)
2. Search the web
3. Return cited, sourced content

**Caveat:** The current phase code expects JSON with `{"queries": [...]}` format. Since sonar returns natural-language sourced text, not JSON query lists, the `extract_json()` call at line 28 of `article_phases.py` will fail gracefully (it already has exception handling). The fallback would be empty queries → empty source list → draft proceeds without sources.

**Mitigation:** The `run_article_retrieve_sources_phase` function should be modified to detect when a sonar model is in use and bypass the query-plan-then-search flow in favour of parsing sonar's inline citations directly. This is the **Phase 2c work item**.

### 2c — Modify `article_phases.py` to support Perplexity native search

**File:** `src/reasoner/application/flows/article_phases.py`

**Current flow:**
1. Call LLM with role=`primary` → get JSON `{"queries": [...]}`
2. `asyncio.gather` searches across all queries via external search client
3. Flatten and dedupe results into `state.writing_state["retrieved_sources"]`

**Target flow (when role routes to a sonar model):**
1. Call LLM with role=`primary` → sonar returns natural-language text with inline citations
2. Parse sonar's response to extract `[Source Title](URL)` citations
3. Optionally: extract the factual content between citations for source context
4. Populate `state.writing_state["retrieved_sources"]` from parsed citations

**Implementation sketch:**
```python
async def run_article_retrieve_sources_phase(state, services, domain=None):
    services.log("WRITING", "Retrieving targeted sources for article...", state)
    try:
        raw_plan, meta = await services.call_llm(
            role="primary",
            system_prompt=phases.ARTICLE_RETRIEVAL_PLAN_SYSTEM,
            user_prompt=phases.article_retrieval_plan_prompt(state),
            state=state
        )

        # Detect Perplexity model: sonar returns cited prose, not JSON
        model_used = meta.get("model", "") if meta else ""
        is_sonar = "sonar" in model_used.lower() or "perplexity" in model_used.lower()

        if is_sonar:
            # Parse inline [Title](URL) citations from sonar's response
            import re
            citations = re.findall(r'\[([^\]]+)\]\((https?://[^\)]+)\)', raw_plan)
            sources = [
                {"title": title, "url": url, "snippet": ""}
                for title, url in citations
            ]
            # Also try to extract sonar's returned_sources if available
            if hasattr(meta, 'get') and meta.get("citations"):
                for c in meta["citations"]:
                    if c.get("url") not in {s["url"] for s in sources}:
                        sources.append({
                            "title": c.get("title", ""),
                            "url": c.get("url", ""),
                            "snippet": c.get("snippet", ""),
                        })
        else:
            # Standard flow: extract JSON queries → search externally
            plan = extract_json(raw_plan)
            queries = plan.get("queries", [])[:5]
            # ... existing asyncio.gather search flow ...

        state.writing_state["retrieved_sources"] = sources
        if not sources:
            state.writing_state["insufficient_evidence"] = True
            services.log("WRITING", "No sources found. Triggering insufficient evidence gate.", state)
    except Exception as e:
        services.log("WRITING", f"Source retrieval failed: {e}", state)
```

**Note:** The Perplexity OpenAI-compatible provider returns `citations` in the response metadata when `return_sources: True` is in `extra_body`. However, OpenRouter may not pass all metadata through to the `call_llm` return value. An alternative is to rely on the text-based inline citation parsing (the regex approach), which works with any model's output format.

### 2d — (Optional) Prompt adaptation for sonar fact-checking

**File:** `src/reasoner/phases/article.py`

When `writing_factcheck` uses sonar, the verification prompt should instruct it to **use its live web search** rather than relying only on provided sources:

```python
ARTICLE_VERIFY_SYSTEM_SONAR = (
    "You are a rigorous fact-checker at a top publication with live web search capability. "
    "Your job is to identify every factual claim in the article draft that cannot be verified. "
    "Use your web search to independently verify each claim against current sources. "
    "Be adversarial: assume the author may have hallucinated statistics, misattributed quotes, "
    "or overgeneralised from limited evidence. "
    + JSON_ONLY_FOOTER
)
```

**Alternatively** (simpler, no prompt change): The current system prompt already works with sonar — sonar will naturally use web search to ground its verification, since that's its default behaviour. The only change needed is in the preset routing.

---

## Phase 3 — `article-premium` Audit

### 3a — Check premium preset for same improvement opportunities

**Current `article-premium`:** All writing roles fall back to `claude-sonnet`. The only explicit routing is `synthesis` → `gpt-5.5`. This is deliberate — `claude-sonnet` is an excellent writer and doesn't need per-phase diversification the way budget does.

**Recommendation:** Add explicit `writing_factcheck: "sonar-pro"` to premium preset for the same reason as budget — live web verification is a step-change improvement over static source checking, and premium users expect the best.

```python
"article-premium": {
    ...
    "routing": {
        ...
        "writing_factcheck":  "sonar-pro",          # ← Perplexity: live web verification at premium quality
        ...
    },
}
```

### 3b — Cross-bloc diversity check

Current budget preset: synthesis (`gpt-4o-mini` → `qwen3.5-flash`, both 🇨🇳 after change) vs scoring (`deepseek-v4-flash`, 🇨🇳). **No cross-bloc.** The invariant enforced by `test_preset_bloc_diversity.py` is that `synthesis bloc ≠ scoring bloc`. Both being 🇨🇳 would fail validation.

**Fix:** Either:
- Keep `synthesis` as `gpt-4o-mini` (🇺🇸 OpenAI) — simplest, no preset change needed for synthesis
- Or change `scoring` to a 🇺🇸 model (e.g., `gpt-oss-20b` at $0.029/$0.14)

**Decision:** Keep `synthesis: "gpt-4o-mini"` unchanged for bloc diversity. The $0.002/article saving from switching to `qwen3.5-flash` is not worth breaking the cross-bloc invariant. The `qwen3.5-flash` swap for synthesis should only be applied if `scoring` is also moved to a 🇺🇸 model.

---

## Phase 4 — Testing & Validation

### 4a — Preset validation

```bash
python src/reasoner/main.py --list-presets
# Confirm article-budget and article-budget-sonar appear
```

```bash
python scripts/validate_presets.py
# Should pass all checks including cross-bloc diversity
```

```bash
pytest tests/unit/test_preset_bloc_diversity.py -v
# Should pass
```

### 4b — Pipeline smoke tests

```bash
# Test optimized budget
python -c "
import sys, os
sys.path.insert(0, 'src')
import asyncio, argparse
from reasoner.main import main

args = argparse.Namespace(
    preset='article-budget', top_k=2, sequential=False, quiet=False,
    force_pipeline=False, output='', save_state='', resume='',
    list_presets=False, list_models=False, enhance_prompt=False,
    source_type='general', domain='', problem_file='', routing='',
    problem='Write a 500-word article about renewable energy trends in 2026.'
)
asyncio.run(main(args))
"
```

```bash
# Test sonar budget (requires OPENROUTER_API_KEY and PERPLEXITY_API_KEY)
python -c "
import sys, os
sys.path.insert(0, 'src')
import asyncio, argparse
from reasoner.main import main

args = argparse.Namespace(
    preset='article-budget-sonar', top_k=2, sequential=False, quiet=False,
    force_pipeline=False, output='', save_state='', resume='',
    list_presets=False, list_models=False, enhance_prompt=False,
    source_type='general', domain='', problem_file='', routing='',
    problem='Write a 500-word article about renewable energy trends in 2026.'
)
asyncio.run(main(args))
"
```

### 4c — Quality comparison

Run all three presets on the same topic and compare:
1. `article-budget` (optimized) — baseline
2. `article-budget-sonar` (sonar-enhanced) — live fact-checking
3. `article-premium` (unchanged) — gold standard

Compare: claim_support_ratio, article word count, prose quality, factuality of claims, total pipeline time, total cost.

---

## Implementation Order

1. **Step 1**: Update `article-budget` routing in `preset_registry.py` (Phase 1)
2. **Step 2**: Run `validate_presets.py` + bloc diversity tests
3. **Step 3**: Add `article-budget-sonar` preset in `preset_registry.py` (Phase 2a)
4. **Step 4**: Modify `article_phases.py` for sonar citation parsing (Phase 2c)
5. **Step 5**: Run validation suite again
6. **Step 6**: Smoke-test article-budget with real pipeline
7. **Step 7**: Smoke-test article-budget-sonar with real pipeline
8. **Step 8**: Optional — add `writing_factcheck: "sonar-pro"` to article-premium

---

## Risk Register

| Risk | Severity | Mitigation |
|---|---|---|
| `qwen3.5-flash` synthesis produces lower-quality JSON than `gpt-4o-mini` | Medium | Keep `gpt-4o-mini` for bloc diversity (Phase 3b). Only swap synthesis if scoring is also rebalanced. |
| `qwen3.7-plus` factcheck is slower than `deepseek-v4-flash` | Low | Fact-check is a quality-critical phase; latency tradeoff is acceptable. |
| `sonar` inline citation parsing is unreliable (regex-based) | Medium | Fall back to existing external search flow when sonar parsing produces <3 sources. |
| OpenRouter doesn't pass Perplexity `citations` metadata through to `call_llm` | Medium | The regex fallback (parsing `[Title](URL)` from response text) is model-agnostic and works with any output. |
| Cross-bloc diversity check fails on updated preset | High | Either keep `synthesis: "gpt-4o-mini"` or rebalance `scoring` to a 🇺🇸 model. See Phase 3b. |
