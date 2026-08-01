# Phase 3 Implementation Plan: Verifier Independence + Quality Gates

## Scope
Close G4 (monoculture verification) and G6 (per-phase config/quality gates).
Two separate subsystems, one shared goal: make the audit *mean* something.

---

## Step 1: `route_verifier()` — Provider-Family Independence

### The invariant

From the survey:
- **article-budget**: verifier = critic = `hy3` (Tencent) — **same family violation**
- **article-premium**: verifier = synthesis = `qwen3.7-max` (Qwen) — **same family violation**
- Both: verifier is Chinese while drafter is US — cross-bloc ✅

The invariant: `provider_family(verifier) ∉ {provider_family(drafter), provider_family(critic), provider_family(factcheck)}`

### Implementation

```python
def route_verifier(
    drafter: str, critic: str, factcheck: str,
    registry: dict,  # PRESETS or a routing table
    verboten_families: set[str] | None = None,
) -> str: ...
```

For Phase 3, this is a **structural validation** (tested in golden set / preset tests),
not yet a runtime model pick. The assert fires at registration time.

---

## Step 2: `GatePolicy` + `Threshold` — Specification Pattern

### The plan's design (§7.2)

```python
@dataclass(frozen=True)
class Threshold:
    dimension: str
    min_value: float
    weight: float

@dataclass(frozen=True)
class GatePolicy:
    thresholds: tuple[Threshold, ...]
    
    def evaluate(self, audit: dict) -> tuple[bool, dict]:
        """Returns (passes, details_dict)."""
        weighted = sum(audit[t.dimension] * t.weight for t in self.thresholds)
        total_w = sum(t.weight for t in self.thresholds)
        hard_ok = all(audit.get(t.dimension, 0) >= t.min_value for t in self.thresholds)
        score = weighted / total_w if total_w > 0 else 0.0
        return (hard_ok and score >= 0.6), {"score": score, "hard_ok": hard_ok}
```

### Per-content-class policies

```python
# Trust dimensions weigh more and floor higher than prose dimensions:
TRUST_FIRST = GatePolicy((
    Threshold("claim_support",       0.75, 3.0),
    Threshold("citation_accuracy",   0.80, 3.0),
    Threshold("internal_consistency",0.65, 2.0),
    Threshold("thesis_advancement",  0.60, 1.0),
    Threshold("transition_quality",  0.55, 1.0),
    Threshold("redundancy_removed",  0.55, 1.0),
    Threshold("policy_compliance",   0.90, 2.0),
))

# Lower stakes — prose and flow matter more:
BALANCED = GatePolicy((
    Threshold("claim_support",       0.65, 2.0),
    Threshold("citation_accuracy",   0.70, 2.0),
    Threshold("thesis_advancement",  0.60, 2.0),
    Threshold("transition_quality",  0.60, 2.0),
    Threshold("redundancy_removed",  0.60, 2.0),
    Threshold("internal_consistency",0.60, 2.0),
    Threshold("policy_compliance",   0.80, 2.0),
))
```

### Policy selection by `content_class`

```python
GATE_POLICIES: dict[str, GatePolicy] = {
    "greek_briefing":     TRUST_FIRST,   # NIKH briefings — high trust bar
    "policy_brief":       TRUST_FIRST,   # policy analysis — high trust bar
    "news_analysis":      TRUST_FIRST,   # current events — high trust bar
    "technical":          TRUST_FIRST,   # technical writing — high trust bar
    "explainer":          BALANCED,      # explainers — moderate trust bar
    "op_ed":              BALANCED,      # opinion pieces — moderate trust bar
    "blog":               BALANCED,      # blog posts — moderate trust bar
}
```

---

## Step 3: `claim_support` Gate from Honest Ratio

The `claim_support` dimension in the audit is currently LLM self-judged.
Replace with the programmatic `claim_support_ratio()` from Phase 2:

In the `final_audit` adapter, after reconciliation:
```python
honest_ratio = claim_support_ratio(reconciled_ledger)

# Inject the honest ratio into the audit data before policy evaluation:
audit_data = {**llm_audit, "claim_support": honest_ratio}

# Evaluate against gate policy:
policy = GATE_POLICIES.get(content_class, BALANCED)
passes, details = policy.evaluate(audit_data)
```

This makes `claim_support` a **programmatic, verifiable measurement** instead of
the LLM's impresionistic self-assessment.

---

## Step 4: Gate Enforcement

In the `final_audit` adapter, after LLM response:
- Evaluate policy against audit data
- If `not passes`: return `Err("audit failed", fallback=ctx)`  
  The `pipeline()` combinator will degrade to the fallback (current article without passing audit).
  Retry will attempt dev edit + re-audit (existing `_retry_audit_failure` path).
- Write `passes_audit` back into `ctx.editorial_audit` for surface_signals (Phase 4)

---

## Step 5: Test Updates

- `tests/test_article_presets.py`: add `test_drafter_verifier_are_different_families` as **enforced** (was soft-skip)
- `tests/test_article_golden_set.py`: add `GatePolicy.evaluate` property tests
- New test file: `tests/test_gate_policies.py` — parametrized gate evaluations
