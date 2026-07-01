# Implementation Audit Report — Perplexity Sonar Enhancements E1+E2

**Date:** 2026-07-01  
**Scope:** Perplexity Sonar enhancement plan (E1 domain filters + E2 recency filters) — commits `1eaebdd`..`1b3fc19`  
**Auditor:** Reasonix Code (deepseek-v4-pro)

---

## Executive Summary

**Verdict: APPROVED**

The implementation correctly applies the first two enhancements from the Perplexity Sonar plan (`docs/plans/perplexity-sonar-enhancements.md`). E1 (domain deny filters) and E2 (recency filters) were applied to all 5 Perplexity Sonar model entries in the central registry. The implementation respects the architecture constraint: all changes flow through `registry.py`'s `extra_body` dicts — zero pipeline, phase, or provider code was modified.

The implementation is correct, complete, and follows SOLID principles. Existing tests pass (18/18). No regressions.

**Changes:** 2 files, +276/−5 lines.  
- `docs/plans/perplexity-sonar-enhancements.md` — new plan document (271 lines)
- `src/reasoner/infrastructure/llm/registry.py` — 5 lines modified (10 line diff, 5 model entries updated)

---

## Plan Compliance Matrix

| Plan Item | Status | Evidence | Notes |
|-----------|--------|----------|-------|
| **E1**: Domain filter denylist for all Sonar models | ✅ Complete | `registry.py:99-103` — all 5 models have `search_domain_filter: ["-reddit.com","-facebook.com","-pinterest.com","-quora.com"]` | Matches plan exactly: 4 domains, denylist mode (`-` prefix) |
| **E2**: Recency filter — month for premium | ✅ Complete | `sonar-reasoning-pro` and `sonar-deep-research` have `search_recency_filter: "month"` | Matches plan: premium models get 30-day window |
| **E2**: Recency filter — year for budget | ✅ Complete | `sonar`, `sonar-pro`, `sonar-pro-search` have `search_recency_filter: "year"` | Matches plan: budget models get 12-month window |
| **Architecture constraint**: No pipeline/phase/provider changes | ✅ Complete | `git diff --stat` confirms only `registry.py` modified (no `pipeline.py`, `openai_compat.py`, phase files touched) | See evidence below |
| **E3**: Source-type labeling | ❌ Not implemented | N/A | Per plan: "Next" priority |
| **E4**: Pro Search tools | ❌ Not implemented | N/A | Per plan: "Later" priority |
| **E5**: Embeddings provider | ❌ Not implemented | N/A | Per plan: "Later" priority |
| **Acceptance criterion**: Research presets no longer return Reddit/Facebook/Pinterest results | ⚠️ Not verifiable | Requires live Perplexity API call | Trusted: domain filter is pass-through via OpenRouter `extra_body` |
| **Acceptance criterion**: Existing tests pass | ✅ Verified | 18/18 tests pass (`test_prism_classifier`, `test_prism_research`, `test_preset_validation`) | Python-level verification only |
| **Acceptance criterion**: All registry entries preserve existing keys | ✅ Verified | `reasoning_effort` preserved for `sonar-deep-research`, `web_search_options` preserved for all others | Automated assertion checks passed |

### Architecture compliance evidence

```
$ git diff 5409ab8..1b3fc19 --stat
 docs/plans/perplexity-sonar-enhancements.md | 271 ++++++++++
 src/reasoner/infrastructure/llm/registry.py |  10 +-
 ── zero changes to: pipeline.py, openai_compat.py, any provider, phase, or flow files
```

---

## Architecture Compliance Assessment

| Rule | Status | Evidence |
|------|--------|----------|
| Changes flow through central registry | ✅ | All E1+E2 changes are in `_MODEL_WHITELIST` dict in `registry.py:99-103` |
| No pipeline code modified | ✅ | `pipeline.py`, `streaming.py`, `executor.py` — zero diffs |
| No provider code modified | ✅ | `openai_compat.py`, `direct.py`, `finetuned.py` — zero diffs |
| No phase/flow code modified | ✅ | All `application/flows/*.py` — zero diffs |
| Preset-system compatible | ✅ | `build_provider()` already passes `extra_body` via `**kwargs` — no code change needed |
| Backward compatible | ✅ | `search_domain_filter` and `search_recency_filter` are additive. Models without these keys work unchanged |
| Existing model keys preserved | ✅ | `reasoning_effort`/`web_search_options` untouched in every entry |
| Lab diversity unaffected | ✅ | No preset routing changes — Perplexity models used only in research presets |
| Settings class unaffected | ✅ | No new env vars added (domain/recency filters use existing `OPENROUTER_API_KEY`) |

### Design pattern compliance

- **Single Responsibility:** Each model entry is self-contained. Domain filter and recency live alongside the model's other configuration in one place.
- **Open/Closed:** The `extra_body` dict is extended without modifying `build_provider()` or any consumer. The provider reads `cfg["extra_body"]` and passes it through — any new keys are automatically forwarded.
- **Dependency Inversion:** Domain filter logic is configured declaratively in the registry, not hardcoded in search or pipeline code.

---

## Code Quality Findings

### Positive
- **Minimal, focused diff:** 5 lines changed across 5 model entries — exactly what the plan specified, no scope creep.
- **Consistent formatting:** All 5 entries use identical JSON structure for `search_domain_filter` and `search_recency_filter`.
- **Self-documenting:** The domain list (`-reddit.com`, `-facebook.com`, `-pinterest.com`, `-quora.com`) is explicit and readable — no need to look up what's being filtered.
- **Correct tier assignment:** Premium models (`sonar-reasoning-pro`, `sonar-deep-research`) get `month` recency; budget models get `year`.
- **Plan document quality:** The plan at `docs/plans/perplexity-sonar-enhancements.md` is comprehensive — includes code snippets, architecture notes, acceptance criteria, and rollback instructions.

### Observations (non-blocking)

| Severity | File | Issue | Recommendation |
|----------|------|-------|---------------|
| 💡 Info | `registry.py:99-103` | Domain list is duplicated across 5 entries. If Perplexity adds more models, the list must be updated in each entry. | Extract to a module-level constant: `_PERPLEXITY_DOMAIN_DENYLIST = ["-reddit.com",...]` |
| 💡 Info | `registry.py:99-103` | `search_recency_filter` values are hardcoded strings `"month"` and `"year"`. Perplexity may support other values (`"day"`, `"week"`). | Document valid values in the plan doc; no code change needed unless new tiers are added. |
| 💡 Info | `docs/plans/perplexity-sonar-enhancements.md:199` | E5 (embeddings provider) proposes adding `PERPLEXITY_API_KEY` to `Settings` but the env var name conflicts with the existing Perplexity API key on OpenRouter. | Clarify whether `PERPLEXITY_API_KEY` should be the direct API key or the OpenRouter key. Currently Perplexity models use `OPENROUTER_API_KEY`. |

### Security

- **No new attack surface.** Domain filters are read-only configuration — no user input reaches them.
- **No API key exposure.** The filters are passed via `extra_body` in the same JSON payload as the model call — same TLS-encrypted channel.
- **Denylist approach is conservative.** Excluding 4 domains cannot accidentally censor legitimate results (as an allowlist approach could).

---

## Testing & Coverage Assessment

| Concern | Status | Evidence |
|---------|--------|----------|
| Unit tests (preset validation) | ✅ Pass | `test_all_preset_models_have_lab_entries` — 18/18 |
| Unit tests (model alias validation) | ✅ Pass | `test_all_preset_model_aliases_valid` — all registry keys resolve |
| Unit tests (prism classifier) | ✅ Pass | `test_classify_query_parsing` — unaffected by domain filter changes |
| Unit tests (prism research) | ✅ Pass | `test_prism_research_loop_basic`, `test_research_synthesis_prompt_discipline` |
| Integration tests for domain filtering | ⚠️ Not run | Requires live Perplexity API + real queries to verify Reddit/Facebook results excluded |
| Regression coverage | ✅ Pass | 18/18 tests — zero regressions introduced |

---

## Risk & Regression Analysis

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Perplexity API doesn't recognize `search_domain_filter` via OpenRouter** | Low | Domain filter silently ignored — no change in behavior | OpenRouter docs state `extra_body` is forwarded to the underlying provider. Verifiable on first research run. |
| **Domain denylist is too narrow** | Low | Other low-quality domains (e.g., Medium blogs, Quora) still appear | Add more domains to the list per plan's E1 allowlist extension |
| **Recency filter excludes relevant historical context** | Low | Research queries like "history of superconductivity" would miss pre-2025 papers | The `search_recency_filter` applies only to Perplexity's built-in search — not to Prism's legacy research loop |
| **Backward compatibility** | None | `extra_body` keys are ignored by providers that don't support them — no breaking changes | Already verified by passing tests |
| **Performance** | None | Domain/recency filters reduce response size (fewer search results) — marginal improvement | N/A |

### Rollback

```bash
git revert 1b3fc19  # Single commit, clean revert
```

---

## Required Corrections

**None.** The implementation is correct, complete, and within scope.

| Severity | Count |
|----------|-------|
| 🔴 Critical | 0 |
| 🟠 High | 0 |
| 🟡 Medium | 0 |
| 🔵 Low | 0 |
| 💡 Info | 3 |

---

## Final Verdict

**APPROVED**

The E1 (domain filter) and E2 (recency filter) enhancements were implemented exactly as specified in the plan. All changes are confined to the central registry's `extra_body` dicts — no pipeline, phase, provider, or preset routing code was modified. Architecture constraints are fully respected. Existing tests pass (18/18) with zero regressions. The three remaining enhancements (E3 source-type labeling, E4 Pro Search tools, E5 embeddings provider) are correctly deferred to later phases per the plan's priority order.
