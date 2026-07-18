# Article Pipeline — Post-Hunt Fix Plan

**Date:** 2026-07-18  
**Trigger:** Two production pipeline runs (article method + multi-perspective method) surfaced 6 defects: 3 HIGH, 2 MEDIUM, 1 LOW.  
**Scope:** Fixes touch 5 files across 3 layers (core → application → infrastructure). No schema migration, no API break.  
**Architecture constraint:** Respect the hexagonal dependency rule — `core` may not import `infrastructure`; `application` wraps `domain`; `api` is the topmost layer.

---

## 1. Defect inventory

| # | Defect | Severity | File(s) | Root cause |
|---|--------|----------|---------|------------|
| **P1** | Style + Copy Edit phase times out at 90s for long articles | HIGH | `core/constants_limits.py` | No dedicated entry in `PHASE_TIMEOUTS`; the phase runs 2 sequential LLM calls |
| **P2** | DeepSeek v3.2 model deprecated → constructive perspective fails with HTTP 400 | HIGH | `infrastructure/llm/registry.py:140` | API no longer accepts `deepseek/deepseek-v3.2` |
| **P3** | Missing API keys cause silent model downgrade with zero logging | HIGH | `application/services/preset_service.py:29-38` | `filter_routing()` substitutes primary_id without diagnostics |
| **P4** | Model display string concatenation without separator | LOW | `infrastructure/llm/router.py:627` | `p.model` already contains the registry shorthand |
| **P5** | Retry-Timeout cascade: audit-failure retry re-runs phases that already timed out | MEDIUM | `application/flows/article.py:73-93` | No timeout-awareness in the retry logic |
| **P6** | `ADAPTER_PHASES` (11 phases) never wired into `ArticleFlow.execute()` (9 phases) | MEDIUM | `flows/article.py` vs `flows/article_adapters.py` | Two diverged phase lists; Gap Retrieval and Surface Signals unreachable |

---

## 2. Fix: P1 — Style + Copy Edit timeout

### Mechanism
`PHASE_TIMEOUTS` (constants_limits.py:368-404) has no entry for `"Style + Copy Edit"`, so the phase falls to `"default": 90.0`. The phase calls two sequential LLM providers — `article_humanize` then `writing_assemble` — both of which process the full article text. For the 11,850-output-token article observed in production, two passes within 90s is marginal.

### Fix

**A. Add a dedicated timeout entry (one-line change, lowest risk):**

```
--- a/src/reasoner/core/constants_limits.py
+++ b/src/reasoner/core/constants_limits.py
@@ -397,6 +397,9 @@
     "Humanize": 90.0,
+    "Style + Copy Edit": 180.0,        # two sequential LLM calls
+    "Style + Copy Edit (retry)": 180.0,
     # Brainstorming ...
     "default": 90.0,
```

**B. Lower-risk variant — split the phase into two separately-timed sub-calls:**

In `run_article_style_copy_edit_phase`, wrap each call in `asyncio.wait_for(..., timeout=120.0)`. This bounds each sub-call, avoiding a single monolithic timeout, and keeps the `ArticleFlow.get_phases()` list unchanged.

**Recommendation:** Apply (A) — it's a single-line change with no side effects. Optionally add (B) as internal hardening.

### Risk

| Vector | Verdict |
|--------|---------|
| Boundary | No edge cases — longer timeout is safe |
| Regression | Existing shorter articles (under 5K tokens) are unaffected |
| Concurrency | None — timeout change is a passive parameter |
| New defect intro | LOW — one config value |

---

## 3. Fix: P2 — DeepSeek v3.2 deprecated

### Mechanism

The registry entry `"deepseek-v3"` maps to `"deepseek/deepseek-v3.2"` (registry.py:138-143). The DeepSeek API now rejects this model path with HTTP 400, accepting only `deepseek-v4-pro` or `deepseek-v4-flash`.

The `multi_perspective-budget` preset (preset_registry.py:30) routes `"constructive"` → `"deepseek-v3"`, which resolves to the dead model. This causes the constructive perspective to silently fail.

### Fix

**A. Update the registry entry to point to the live v4-flash model:**

```
--- a/src/reasoner/infrastructure/llm/registry.py
+++ b/src/reasoner/infrastructure/llm/registry.py
@@ -138,7 +138,10 @@
-    # V3.2: DeepSeek's VFM-tier model, strong reasoning at lower cost than V4
+    # Re-pointed to v4-flash: v3.2 deprecated, API no longer accepts it.
     "deepseek-v3": {
         "cls": "compat",
-        "model": "deepseek/deepseek-v3.2",            # $0.12/$0.50, 1M ctx — budget VFM
+        "model": "deepseek/deepseek-v4-flash",        # re-pointed from deprecated v3.2
         "base": "https://api.deepseek.com/v1",
         "env": "DEEPSEEK_API_KEY",
     },
```

**B. Or, update the preset to use `deepseek-v4-flash` directly (breaks fewer callers):**

In `preset_registry.py:30`, change `"constructive": "deepseek-v3"` → `"constructive": "deepseek-v4-flash"`.

**Recommendation:** Apply (A) — it fixes every preset that references `deepseek-v3` at once (the registry shorthand approach was designed for this). Apply (B) as well since the preset should reference the intended model explicitly and not an alias.

### Risk

| Vector | Verdict |
|--------|---------|
| Boundary | v4-flash has lower max tokens than v3.2 (128K vs 1M); for perspective generation, 128K is far more than needed (perspectives are ~2K tokens) |
| Regression | Any code calling `deepseek-v3` gets the new model transparently |
| Concurrency | None |
| New defect intro | LOW — model swap under the same registry key |

---

## 4. Fix: P3 — Silent model downgrade on missing API keys

### Mechanism

`PresetService.filter_routing()` (preset_service.py:29-38) checks every role→model mapping in a preset: if the model requires an environment variable (`entry.get("env")` → e.g., `"DEEPSEEK_API_KEY"`) and that variable is not set, **silently replaces** the role's model with `primary_id`. No log entry, no warning event, no SSE notification.

In the production article run, the user had `OPENROUTER_API_KEY` set (which covers OpenRouter-proxied models like claude-sonnet, gpt-4o-mini, qwen-*), but likely did not have `DEEPSEEK_API_KEY` or `ANTHROPIC_API_KEY` set. Because the registry entries for `claude-sonnet` and `deepseek-v4-*` specify `"cls": "compat"` and may require their own env keys, those models were silently replaced. The result: qwen3.5-flash (available via OpenRouter, no special key needed) was used for drafting, outlining, reviewing, editing, and auditing — instead of the multi-provider ensemble the preset author intended.

### Fix

**A. Add a `logger.warning()` call in `filter_routing()` (minimal, non-breaking):**

```
--- a/src/reasoner/application/services/preset_service.py
+++ b/src/reasoner/application/services/preset_service.py
@@ -29,10 +29,15 @@
     def filter_routing(self, routing: dict[str, str], primary_id: str) -> dict[str, str]:
         filtered: dict[str, str] = {}
+        downgraded: list[str] = []
         for role, model_id in routing.items():
             entry = _REGISTRY.get(model_id, {})
             env = entry.get("env")
             if env and not os.environ.get(env):
                 filtered[role] = primary_id
+                downgraded.append(f"{role}: {model_id} → {primary_id} (missing {env})")
             else:
                 filtered[role] = model_id
+        if downgraded:
+            logger.warning("Model downgrades due to missing API keys: %s", "; ".join(downgraded))
         return filtered
```

**B. Emit a warning event through the SSE channel (medium, needs deps wiring):**

If `telemetry` or an event-bus port is available, publish a `ModelDowngrade` event that the frontend can surface. Deferred to a follow-up since this requires threading a publisher through `PresetService`.

**C. Make OpenRouter models not require their own env keys:**

The core issue is that models mapped via OpenRouter shouldn't need provider-specific API keys. Check whether `claude-sonnet` in the registry has `"env"` set — if it does and the value is `"ANTHROPIC_API_KEY"`, consider adding `"base": None` or `"cls": "openrouter"` so it routes through OpenRouter (which only needs `OPENROUTER_API_KEY`). This is the architectural root cause.

**Recommendation:** Apply (A) immediately — a 4-line change with zero side effects. Apply (C) as the structural fix: audit every registry entry to ensure OpenRouter-proxied models don't require provider-specific env keys.

### Risk

| Vector | Verdict |
|--------|---------|
| Boundary | Only adds logging — no behavior change |
| Regression | None — the routing behavior is identical |
| Concurrency | None |
| New defect intro | LOW — diagnostics-only |

---

## 5. Fix: P4 — Model display string concatenation

### Mechanism

`ProviderRouter.describe()` (router.py:627) builds `f"{p.model}{suffix}"` where `p.model` is set when the provider was constructed. In some paths, `p.model` already contains the registry shorthand concatenated with the resolved OpenRouter path, producing `qwen3.5-flash-02-23qwen/qwen3.5-flash-02-23` instead of `qwen/qwen3.5-flash-02-23`.

The root cause is likely in `build_provider()`, where two different string sources are joined. Fix at the build-site, not at the display site.

### Fix

**Investigate `build_provider()` caller to find where `p.model` gets its corrupted value.** The likely suspect is a code path that calls `build_provider(shorthand)` and then appends the resolved path without clearing the shorthand first. Once located:

```
--- a/src/reasoner/infrastructure/llm/registry.py (or executor.py)
+++ b/ (call site)
@@ -N,N +N,N @@
- provider.model = shorthand + resolved  (corrupted)
+ provider.model = resolved              (fixed)
```

### Risk

| Vector | Verdict |
|--------|---------|
| Boundary | LOW — cosmetic display change |
| Regression | None — only changes what the user sees |
| Concurrency | None |
| New defect intro | LOW — search for all consumers of `p.model` to ensure none depend on the corrupted value |

---

## 6. Fix: P5 — Retry-Timeout Cascade

### Mechanism

`ArticleFlow.execute()` (article.py:73-93) retries three phases when the final audit fails, regardless of whether any of them already timed out. The retried "Style + Copy Edit" is likely to time out again (same article text, same 90s budget), producing two sequential 90s timeouts = 180s of user wait with no benefit.

### Fix

**A. Break the timeout-vs-audit feedback loop (add a per-phase timeout check):**

Before entering the retry block, check whether the phases being retried already timed out. If `"Style + Copy Edit"` timed out in the primary pass, skip the retry and surface a degraded result instead:

```
--- a/src/reasoner/application/flows/article.py
+++ b/src/reasoner/application/flows/article.py
@@ -73,10 +73,20 @@
             if not audit_retried and step.fn is run_article_final_audit_phase:
                 audit = state.writing_state.get("editorial_audit", {})
                 if not audit.get("passes_audit", False):
+                    # Check for prior timeouts to avoid cascade
+                    timed_out = any(
+                        "Style + Copy Edit" in e.get("message", "")
+                        for e in state.pending_events
+                        if isinstance(e, dict)
+                    )
+                    if timed_out:
+                        services.log("WRITING", "Skipping retry — style/copy already timed out", state)
+                        break
                     services.log("WRITING", "Audit failed — retrying...")
```

**B. Raise the timeout before retrying (complementary to P1 fix):**

When the audit fails and a retry is triggered, double the timeout for the retried phases:

```
                     services.log("WRITING", "Audit failed — retrying with extended timeout...")
                     await services.run_phase(
                         PhaseStep(5.1, "Developmental Edit (retry)", ...),
                         state,
+                        timeout=180.0,  # extended for retry
                     )
```

This requires `run_phase` to accept a `timeout` kwarg, which it currently doesn't. The `WorkflowRunner.run_phase()` signature would need to be extended — a medium-sized change touching `base.py` (PhaseStep), `runner.py` (WorkflowRunner), and the `WorkflowServices` protocol.

**Recommendation:** Apply (A) immediately (guard condition). Defer (B) to the Phase 5 runner refactoring.

### Risk

| Vector | Verdict |
|--------|---------|
| Boundary | If "Style + Copy Edit" timed out but the audit passes anyway, skip the edit-retry — no harm |
| Regression | An audit failure after a timeout now surfaces immediately instead of retrying |
| Concurrency | None |
| New defect intro | LOW — the `break` path only fires when a prior timeout was already recorded |

---

## 7. Fix: P6 — ADAPTER_PHASES never wired into ArticleFlow

### Mechanism

`ADAPTER_PHASES` (article_adapters.py:643-655) is an 11-phase list that includes Gap Retrieval and Surface Signals with budget guards. It's defined but never referenced outside `article_adapters.py`. The actual execution path (`ArticleFlow.get_phases()` in `article.py:46-56`) returns a completely separate 9-phase list using the raw `run_article_*_phase` functions directly — not the adapters.

This means:
- Gap Retrieval never runs (evidence gaps are logged but never addressed)
- Surface Signals never emit `quality_warning` events to the frontend
- `with_budget_guard` never wraps any phase in the production path

### Fix

**A. Wire `ArticleFlow.get_phases()` to use the adapters (recommended):**

Replace the hardcoded `PhaseStep` list with calls to adapter functions. Since each adapter has signature `(Context, AdapterDeps) → Result[Context, PhaseError]`, and `PhaseStep.fn` expects `(state: PipelineState, services: WorkflowServices) → None`, we need a thin bridge:

```python
# In article.py
from reasoner.application.flows.article_adapters import (
    adapter_retrieve_sources, adapter_build_outline, adapter_draft,
    adapter_fact_check, adapter_gap_retrieval, adapter_structural_review,
    adapter_developmental_edit, adapter_style_copy_edit,
    adapter_final_audit, adapter_surface_signals, adapter_synthesis,
    AdapterDeps,
)

def _to_phase_fn(adapter_fn):
    """Bridge adapter (Context, Deps) -> PhaseStep.fn (PipelineState, Services)."""
    async def wrapped(state, services, **kwargs):
        from reasoner.domain.article_domain import Context
        # ... build Context from state, call adapter, write back ...
        pass  # full implementation below
    return wrapped

def get_phases(self, state):
    return [
        PhaseStep(1, "Evidence Collection",   _to_phase_fn(adapter_retrieve_sources), ...),
        PhaseStep(2, "Argument Map/Outline",    _to_phase_fn(adapter_build_outline),  ...),
        PhaseStep(3, "First Draft",            _to_phase_fn(adapter_draft),           ...),
        PhaseStep(4, "Fact Check + Ledger",    _to_phase_fn(adapter_fact_check),      ...),
        PhaseStep(4.5, "Gap Retrieval",        _to_phase_fn(adapter_gap_retrieval),   ...),
        PhaseStep(4.6, "Structural Review",     _to_phase_fn(adapter_structural_review), ...),
        PhaseStep(5, "Developmental Edit",      _to_phase_fn(adapter_developmental_edit), ...),
        PhaseStep(6, "Style + Copy Edit",      _to_phase_fn(adapter_style_copy_edit),  ...),
        PhaseStep(7, "Final Audit",            _to_phase_fn(adapter_final_audit),      ...),
        PhaseStep(7.5, "Surface Signals",      _to_phase_fn(adapter_surface_signals),  ...),
        PhaseStep(8, "Synthesis",              _to_phase_fn(adapter_synthesis),        ...),
    ]
```

**B. Feature-flag the migration:**

```python
WIRING_USE_ADAPTERS = os.environ.get("ARTICLE_USE_ADAPTERS", "0") == "1"

def get_phases(self, state):
    if WIRING_USE_ADAPTERS:
        return _phases_with_adapters(state)
    return _phases_legacy(state)  # current hardcoded list
```

### Risk

| Vector | Verdict |
|--------|---------|
| Boundary | The adapter bridge must convert PipelineState ↔ Context correctly — this is the highest-risk change |
| Regression | Feature flag allows rollback per-run via env var |
| Concurrency | None |
| New defect intro | MEDIUM — the bridge conversion must be thoroughly tested before removing the flag |

**Migration strategy:** Ship the feature flag first. Enable in staging for one week. Remove the flag and the old path after confirming no regressions.

---

## 8. Migration roadmap

| Step | Change | Files touched | Rollback | Effort |
|------|--------|---------------|----------|--------|
| **1** | P1: Add `"Style + Copy Edit"` timeout | `constants_limits.py` (+2 lines) | Revert commit | 5 min |
| **2** | P2: Re-point `deepseek-v3` → v4-flash | `registry.py` (+1 line), `preset_registry.py` (+1 line) | Revert commit | 5 min |
| **3** | P3: Add `logger.warning()` to `filter_routing` | `preset_service.py` (+4 lines) | Revert commit | 5 min |
| **4** | P5: Add timeout guard in retry block | `article.py` (+6 lines) | Revert commit | 10 min |
| **5** | P4: Trace and fix model display | `registry.py` or `executor.py` (~3 lines) | Revert commit | 15 min |
| **6** | P6: Wire adapters into ArticleFlow behind feature flag | `article.py` (+40 lines), `article_adapters.py` (+15 lines bridge) | Set `ARTICLE_USE_ADAPTERS=0` | 2h |
| **7** | P6 follow-up: Remove feature flag after staging validation | `article.py` (~-50 old lines) | Flag reverse | 30 min |

Steps 1–5 are independent and can ship together as a single hotfix (total ~20 lines). Steps 6–7 are the adapter wiring, deferred to a separate PR.

---

## 9. Testing strategy

### Per-fix tests

| Fix | Test type | Assertion |
|-----|-----------|-----------|
| P1 | Integration | Run article mode with 8000+ word input; assert no timeout |
| P2 | Unit | `build_provider("deepseek-v3")` returns a provider with model `deepseek/deepseek-v4-flash` |
| P3 | Unit | Call `filter_routing` with missing env; assert logger.warning called with downgrade message |
| P4 | Unit | `router.describe()["writing_draft"]` returns a single well-formed model string |
| P5 | Integration | Run article flow with audit failure + prior timeout; assert retry is skipped |
| P6 | Integration | `ARTICLE_USE_ADAPTERS=1`, run article golden set entry; assert 11 phases complete |

### Regression suite

Run the existing article test suite (466 tests) after each step. The golden set baseline comparison (`ARTICLE_CHECK_BASELINE=1`) should be re-captured after P6 to update the prompt-length baselines for the new 11-phase sequence.

---

## 10. Architectural notes

### Layer placement summary

| Fix | Layer | Module |
|-----|-------|--------|
| P1 timeout | **core** (constants) | `core/constants_limits.py` |
| P2 model deprecation | **infrastructure** (registry) | `infrastructure/llm/registry.py` |
| P3 model downgrade logging | **application** (service) | `application/services/preset_service.py` |
| P4 model display | **infrastructure** (registry/executor) | `infrastructure/llm/executor.py` or `registry.py` |
| P5 retry guard | **application** (flow) | `application/flows/article.py` |
| P6 adapter wiring | **application** (flow + adapters) | `application/flows/article.py` + `article_adapters.py` |

### Respecting the hexagonal dependency rule

All six fixes stay within the existing dependency graph:
- **core/constants_limits.py** imports nothing from application or infrastructure — safe
- **infrastructure/llm/registry.py** imports only core constants — safe
- **application/services/preset_service.py** imports from domain + infrastructure — safe (application may import infrastructure)
- **application/flows/article.py** already imports from article_phases — adding adapter imports stays within the same layer (flow → flow)
