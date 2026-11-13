# Meta-Orchestration Assessment — Reasoner (Reasoner Pipeline v2.2)

> **Protocol:** Meta-Orchestration Prompt v3.0
> **Analyzed:** 2026-04-27
> **Source:** ARCHITECTURE_MINDMAP.md (~180 files, 2,481 lines) + live codebase scan

---

## PHASE 0: CONTEXT & STATE ASSESSMENT

### 0.1 Context Intake

| Context Item | Status | Value |
|---|---|---|
| System description | **[VF]** | Production-grade AI reasoning orchestrator (Reasoner v2.2). Hexagonal DDD + CQRS + Event Sourcing + Mixin Composition. FastAPI backend, Next.js frontend. |
| Deployment status | **[UN]** | Claimed production-grade; actual deployment status unknown. |
| P0/P1 incidents (30d) | **[UN]** | No incident data available in provided context. |
| Team size | **[UN]** | Unknown. |
| Hard constraints | **[VF]** | Python 3.12+, SQLite default/PostgreSQL optional, SearXNG self-hosted, OpenRouter primary. |

### 0.2 Decomposition & Scoring

**Subsystem Mapping:**
- **Core Logic:** ReasonerPipeline (902 lines), 11 mixins, 17 reasoning methods, 42 presets, 90+ model registry
- **Data Layer:** SQLite event store (single-threaded), JSONL tagged memory, PostgreSQL (optional/lazy)
- **External Deps:** OpenRouter (primary), SearXNG, Perplexity, Cohere, Supabase, Stripe, Redis, Ollama
- **Interfaces:** FastAPI SSE streaming, WebSocket, Next.js App Router
- **Assumptions:** Self-hosted SearXNG reachable; OpenRouter key available; single-node deployment

**Scores (0-10, justified):**

| Metric | Score | Justification |
|---|---|---|
| **C (Complexity)** | **8** [VF] | 902-line God Object (ReasonerPipeline) + 11 mixins. 5 architectural layers with known violations. 17 reasoning methods x 3 tiers = 51 flow variants. Event sourcing + CQRS present but bypassed in hot path. 647-line SearchMixin. Deferred imports to avoid cycles. |
| **S (Stability)** | **6** [ES] | Circuit breaker, rate limiter, fallback chains, 60+ tests, self-healing CI present. BUT: deferred imports, layer violations, God Object, SPOFs (OpenRouter, SQLite, SearXNG), Windows monkeypatch fragility. |
| **F (Fragility)** | **7** [VF] | OpenRouter = SPOF for LLM. SearXNG = SPOF for search. SQLite = SPOF for event store (single-threaded ThreadPoolExecutor). 90+ models = 90+ failure modes. Perplexity silent fallback assumes 400 error semantics. |
| **G (Growth)** | **5** [ES] | Rich feature set (SaaS billing, Neuro memory, 17 methods, image gen). Unknown actual usage. Active model registry expansion (NVIDIA NIM, Ling-2.6). |
| **P (Pressure)** | **3** [ES] | No competitive threats or deadline pressure identified in context. |

**Derived Composite:**
```
Regret Potential = (C + F) x (10 - S) / 10
                 = (8 + 7) x (10 - 6) / 10
                 = 15 x 0.4
                 = 6.0
```

### 0.3 State Classification

| State | Threshold | Met? |
|---|---|---|
| **OVER-COMPLEX** | C > 7 | **ACTIVE** (C=8) |
| **FRAGILE** | F > 6 | **ACTIVE** (F=7) |
| **STAGNANT** | G < 3 AND S > 7 | Inactive (G=5, S=6) |
| **HEALTHY** | S > 7 AND G > 4 AND Regret Potential < 8 | Inactive (S=6) |

**Active States:** [OVER-COMPLEX, FRAGILE]
**Dominant State:** OVER-COMPLEX
**Confidence:** HIGH

---

## PHASE 1: MODE SELECTION

### 1.1 Eligibility Check

| Mode | Condition | Met? |
|---|---|---|
| **SIMPLIFY** | C > 6 OR [OVER-COMPLEX] active | **YES** (C=8) |
| **HARDEN** | Regret Potential > 10 OR F > 6 OR [FRAGILE] active | YES (F=7) |
| **EXPAND** | S > 7 AND G > 3 AND [STAGNANT] active | NO |
| **NONE** | [HEALTHY] only | NO |

### 1.2 Selection Report

**Selected Mode:** SIMPLIFY
**Mode Confidence:** HIGH
**Influential Metric:** C = 8 (highest complexity subsystem: ReasonerPipeline at 902 lines + 11 mixins)

**Rejection Rationale:**
- **HARDEN rejected** despite F=7 and [FRAGILE] active because protocol priority is SIMPLIFY > HARDEN > EXPAND, and the dominant state is OVER-COMPLEX. Hardening a God Object preserves the complexity that generates fragility.
- **EXPAND rejected** — [STAGNANT] is inactive and S=6 fails the S > 7 gate.

---

## PHASE 2: EXECUTION MODE — SIMPLIFY

### 2.S.1 Target Selection

**Target:** pipeline.py — ReasonerPipeline class (902 lines + 11 mixins)

**Justification [VF]:** The Architecture Mindmap explicitly flags this as a **High-severity God Object** — the #1 architectural risk in the system. It combines orchestration, LLM execution, caching, cost tracking, phase sequencing, and state mutation in a single class. Extracting a responsibility is the highest-leverage simplification possible.

### 2.S.2 Primary Simplification Path

**Path:** Extract _call_llm_cached() and related LLM orchestration concerns from ReasonerPipeline into a standalone LLMExecutor class in infrastructure/llm/executor.py.

**What moves:**
- _call_llm_cached() method (~80-100 lines)
- Token cache interaction logic
- Cost tracking invocation
- ProviderRouter delegation logic

**What stays:**
- Phase sequencing (run(), _phase_*)
- State initialization
- Mixin composition (for now)

**C delta:** -0.7 [ES]
**Effort:** Small-Medium (2-3 hours, localized change)

**Rationale:** This is a clear responsibility boundary violation. LLM execution (caching, routing, retry, cost tracking) is infrastructure/orchestration, not pipeline phase logic. Extracting it reduces ReasonerPipeline to its core concern: phase sequencing and state management.

### 2.S.3 Fallback Inventory

| Fallback | Scope | C Delta | Risk Level |
|---|---|---|---|
| **Partial:** Extract only CostTrackingState mutation into CostTracker helper class. | Move cost tracking out of _call_llm_cached into a focused utility. | -0.3 | **Low** — cost tracking is already partially isolated in PipelineState. |
| **Interface-only:** Define LLMExecutorProtocol in core/protocol.py without moving implementation. | Create a formal port for LLM execution. ReasonerPipeline depends on the protocol, not concrete method. | -0.1 | **Minimal** — pure additive change, no behavioral change. |

### 2.S.4 Rollback & Verification

**Snapshot:** Git commit on main with clean test run before any edits.

**Rollback Trigger:**
- pytest pass rate drops below 95% of baseline
- ReasonerPipeline line count does not decrease by > 80 lines
- New circular import introduced
- _call_llm_cached no longer accessible to mixins (breaks mixin contract)

**Verification Tests:**
1. Run full pytest suite — assert >= 95% baseline pass rate
2. Run python main.py --problem "test" --preset default — end-to-end smoke test
3. Verify ReasonerPipeline no longer contains token_cache or build_provider inline logic
4. Verify all 11 mixins still function (they call self._call_llm_cached() via LLMExecutor delegation)

---

## PHASE 3: RESILIENCE & CONVERGENCE CHECK

### 3.1 Stress Test

| Scenario | Assessment |
|---|---|
| **Adversarial misuse** | LLMExecutor exposes only execute(state, role, prompt, config) — state is read/write but isolated from phase sequencing. No new attack surface. |
| **10x load** | LLMExecutor delegates to existing ProviderRouter and TokenCache which already handle concurrency. No regression. |
| **Primary dep collapse (OpenRouter)** | Fallback chain remains inside ProviderRouter, unchanged. LLMExecutor is a thin wrapper. |
| **Maintenance attrition** | New file is ~100 lines with single responsibility. Easier to onboard than understanding 902-line ReasonerPipeline. |
| **Partial rollback failure** | Change touches one new file + one modified file (pipeline.py). Git revert is trivial. No schema or API changes. |

### 3.2 Convergence Verification

| Metric | Before | After [ES] | Target | Achieved? |
|---|---|---|---|---|
| C (Complexity) | 8.0 | 7.3 | < 7.5 | **YES** |
| S (Stability) | 6.0 | 6.2 | > 5.5 | **YES** |
| F (Fragility) | 7.0 | 7.0 | No increase | **YES** |
| Regret Potential | 6.0 | 5.5 | < 8.0 | **YES** |

**Verdict:** CONVERGED

**Confidence:** HIGH — the change is localized, testable, and directly addresses the #1 architectural risk without touching external dependencies or data schemas.

---

## PHASE 4: FINAL OUTPUT

### 4.1 Summary

1. **System State:** OVER-COMPLEX + FRAGILE. God Object (ReasonerPipeline, 902 lines) is the dominant complexity driver. Regret Potential = 6.0.
2. **Mode & Confidence:** SIMPLIFY. HIGH confidence. Priority rule selects SIMPLIFY over HARDEN because C > 6 and [OVER-COMPLEX] is dominant.
3. **Scoped Action Plan:** Extract _call_llm_cached() from ReasonerPipeline into infrastructure/llm/executor.py as LLMExecutor class. Reduces ReasonerPipeline by ~100 lines, creates clean infrastructure port, enables independent testing.
4. **Two Fallbacks:** (a) Partial — extract only CostTracker, C-0.3; (b) Interface-only — define LLMExecutorProtocol, C-0.1.
5. **Risk/Regret Delta:** Regret Potential drops from 6.0 -> 5.5 [ES]. Complexity drops from 8.0 -> 7.3 [ES]. No fragility increase.
6. **Rollback Protocol:** Git snapshot + 95% test pass gate + line-count gate. Revert if any gate fails.

### 4.2 Re-evaluation Triggers

- C increases by +2 (e.g., adding new mixins without extraction)
- New P0/P1 incident (forces HARDEN mode next cycle)
- Team size +/-50% (changes simplification velocity)
- New depth>1 dependency added
- Regret Potential > 12 (system divergence)

### 4.3 Machine-Readable Block

```json
{
  "prompt_version": "meta-orchestration-v3.0",
  "cycle": 1,
  "system_state": {
    "active_states": ["OVER-COMPLEX", "FRAGILE"],
    "dominant": "OVER-COMPLEX",
    "confidence": "HIGH"
  },
  "scores": {
    "C": 8,
    "S": 6,
    "F": 7,
    "G": 5,
    "P": 3,
    "regret_potential": 6.0
  },
  "decision": {
    "mode": "SIMPLIFY",
    "mode_confidence": "HIGH",
    "security_override": false,
    "rejected_modes": ["HARDEN", "EXPAND"],
    "primary_metric": "C"
  },
  "execution": {
    "target": "pipeline.py / ReasonerPipeline God Object",
    "path": "Extract _call_llm_cached into infrastructure/llm/executor.py",
    "c_delta": -0.7,
    "effort": "Small-Medium",
    "fallbacks": [
      {"name": "Partial CostTracker extraction", "c_delta": -0.3, "risk": "Low"},
      {"name": "Interface-only protocol definition", "c_delta": -0.1, "risk": "Minimal"}
    ]
  },
  "convergence": {
    "verdict": "CONVERGED",
    "cycles_remaining": 2,
    "regret_after": 5.5,
    "c_after": 7.3
  },
  "next_assessment": "After extraction PR merged and 7-day burn-in, or immediately if re-evaluation trigger fires"
}
```

---

## SELF-OPTIMIZATION NOTE (for next cycle)

1. **Most impactful [UN] input:** **P0/P1 incident history (30 days)**. If a production incident occurred due to the God Object (e.g., _call_llm_cached deadlock or state corruption), the mode selection would flip to HARDEN under the "recent P0/P1 incident" rule.
2. **Complexity Budget block:** No block occurred. The proposed change is self-contained and meets the budget constraint (C delta = -0.7, no increase).
