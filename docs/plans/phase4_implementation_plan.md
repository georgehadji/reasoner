# Phase 4 Implementation Plan: Combinators + Surface Signals

## Scope
Add the combinator layer from the plan (§4.2) — `with_retry`, `branch` — and
`surface_signals` for structured quality/status emission. Budget circuit-breaker
is deferred (it requires the `Budget` type from the plan's §4.1 which needs
cost tracking integration).

## What changes

### Step 1: `with_retry` combinator

```python
def with_retry(phase_fn, *, max_retries=2, on_retry=None):
    """Wrap a phase with retry logic.
    
    on_retry(ctx, attempt) -> ctx : prepare context for retry
    """
    async def wrapped(ctx, deps):
        for attempt in range(max_retries + 1):
            result = await phase_fn(ctx, deps)
            if isinstance(result, Ok):
                return result
            if attempt < max_retries and isinstance(result, Err) and result.fallback is not None:
                ctx = result.fallback
                if on_retry:
                    ctx = await on_retry(ctx, attempt)
                continue
            return result
    return wrapped
```

### Step 2: `branch` combinator

```python
def branch(predicate, then_phase, otherwise=None):
    """Conditionally run a phase if predicate(ctx) is True."""
    async def wrapped(ctx, deps):
        if predicate(ctx):
            return await then_phase(ctx, deps)
        if otherwise:
            return await otherwise(ctx, deps)
        return Ok(ctx)
    return wrapped
```

### Step 3: `surface_signals` adapter

Read the final `ArticleContext` and emit user-facing structured signals:

```python
def surface_signals(ctx: ArticleContext) -> dict:
    signals = {}
    audit = ctx.editorial_audit or {}
    gate_failures = audit.get("gate_failures", [])
    
    if not audit.get("passes_audit", True):
        signals["quality_warning"] = {
            "severity": "high" if ctx.content_class in ("greek_briefing", "policy_brief") else "medium",
            "message": f"Article did not pass editorial audit (gate score: {audit.get('gate_score', 0):.2f})",
            "failures": gate_failures,
        }
    
    if ctx.gaps_noted:
        signals["evidence_gaps"] = {
            "count": len(ctx.gaps_noted),
            "gaps": ctx.gaps_noted[:5],
        }
    
    if claim_support_ratio(ctx.claims) < 0.5:
        signals["low_support_ratio"] = {
            "ratio": claim_support_ratio(ctx.claims),
        }
    
    return signals
```

### Step 4: Wire into pipeline

- `with_retry` wraps the existing audit/retry pattern instead of the hardcoded `_retry_audit_failure`.
- `branch(has_evidence_gaps, gap_retrieval)` goes between `fact_check` and `final_audit`.
- `surface_signals` runs as the last step before returning, writing results into `ArticleContext.surface_signals`.

### Step 5: ArticleContext additions

- Add `surface_signals: dict` field.
- Update `sync_to()` to write it into `state.writing_state["surface_signals"]`.
