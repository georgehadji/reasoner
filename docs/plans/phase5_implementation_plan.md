# Phase 5 Implementation Plan: Additive Event Log

## Scope
Add a lightweight, append-only event log as a provenance channel through the
Article pipeline.  This is the "additive event log" from the plan (§2.2,
§4.1) — an observability/provenance layer layered on top of the existing
pipeline, not a replacement for the control flow.

## What changes

### Step 1: `ArticleEvent` frozen dataclass

Simple, lightweight event type stored in `ArticleContext.events`.

```python
@dataclass(frozen=True)
class ArticleEvent:
    phase: str                     # which adapter/phase produced it
    event: str                     # event name: sources_retrieved | outline_built | draft_completed | ...
    summary: str                   # human-readable one-liner (≤200 chars)
    details: dict = ()            # structured key-value data (tokens, counts, metrics)
    timestamp: float = 0.0         # time.monotonic() when emitted
```

### Step 2: `ArticleContext.events` field

```python
events: tuple[ArticleEvent, ...] = ()
```

Adapters append via: `ctx.replace(events=ctx.events + (article_event,))`

### Step 3: Event emission in adapters

Each adapter emits an event after its work:

| Adapter | Event name | Summary | Details |
|---------|-----------|---------|---------|
| `retrieve_sources` | `sources_retrieved` | "Retrieved N sources for problem" | count |
| `build_outline` | `outline_built` | "Built outline with N sections" | sections, title |
| `first_draft` | `draft_completed` | "Completed first draft (N chars)" | char_count, title |
| `fact_check` | `claim_verification` | "Verified N claims, ratio=R" | total, supported, unsupported, speculative, partial, ratio |
| `fact_check` (after) | `locked_spans` | "Locked N spans for verified claims" | count |
| `structural_review` | `structural_review` | "Structural review score: R" | rigor_score, logical_gaps |
| `developmental_edit` | `dev_edit_completed` | "Developmental edit completed" | char_count |
| `style_copy_edit` | `style_edit_completed` | "Style + copy edit completed" | passes_span_check |
| `final_audit` | `audit_completed` | "Audit: passes=R, score=R, gates=S" | gate_score, passes, failures |
| `reconcile_ledger` (Phase 2) | `ledger_reconciled` | "Reconciled ledger: N carried, N new to verify" | carried, to_verify |

### Step 4: Event log serializer for SSE

A lightweight serializer function that reads `ctx.events` and produces
an SSE-friendly payload:

```python
def serialize_article_events(ctx: ArticleContext) -> dict:
    """Serialize the additive event log for SSE emission."""
    return {
        "events": [
            {"phase": e.phase, "event": e.event, "summary": e.summary, "details": e.details}
            for e in ctx.events
        ]
    }
```

### Step 5: Wire into pipeline

- Event emission added inside each adapter after its main work
- `surface_signals` called at end of execute() as before
- Event data available to serializers via `ctx.events` or `state.writing_state["article_events"]`
