# Plan: Post-Critique Epistemic Label Filter

## Problem

Perspective models self-assign epistemic labels (`[VERIFIED]`, `[HYPOTHESIS]`, `[UNKNOWN]`) as inline text in `SolutionCandidate.content` with no external validation. A model can fabricate statistics and mark them `[VERIFIED]` — the pipeline accepts these at face value and passes them to synthesis.

The critique phase **already detects this**: in the observed failure, the critique scored the destructive perspective `0.0` with `bias_flags: ["hallucinated statistics"]` and `evidence_support: 0.0`. But these signals are never used to correct the labels — they only affect candidate ranking.

## Design

### Intervention Point

After critique scores are computed and before candidates are ranked/passed to synthesis.

```
Perspectives → Critique → ★ EPISTEMIC FILTER ★ → Rank → Synthesis
                                   ↑
                            Uses CritiqueScore signals
```

**File:** `src/reasoner/application/flows/perspective_phases.py` — inside `run_critique_phase()`, after `state.scores` is populated (line ~134) and before `state.candidates.sort(...)` (line ~138).

### Downgrade Signals

Two independent triggers — either causes downgrade:

| Signal | Source | Threshold | Rationale |
|--------|--------|-----------|-----------|
| `evidence_support` | `CritiqueScore.evidence_support` | `< 3.0` (out of 10) | Evidence score below 30% means the critique found claims unsubstantiated |
| `bias_flags` match | `CritiqueScore.bias_flags` | Contains any of: `"hallucinated"`, `"fabricated"`, `"unsupported"`, `"unverified"`, `"no evidence"` | The critique explicitly flagged fabrication |

**Why `evidence_support < 3.0`?** The critique rubric scores evidence quality 0–10. A score below 3.0 means "weak or absent evidence" — at that level, any `[VERIFIED]` label is overconfident. We do NOT use `logical_consistency` because a logically consistent argument can still use fabricated data.

**Why not `total < threshold`?** Because `total` averages four dimensions. A perspective could score 8.0 on `logical_consistency` and `feasibility` but 1.0 on `evidence_support` — total 5.75, which passes most thresholds. But its "verified" claims are still unsubstantiated.

### Downgrade Logic

```python
def _downgrade_unverified_labels(
    candidate: SolutionCandidate,
    score: CritiqueScore,
    evidence_threshold: float = 3.0,
) -> SolutionCandidate:
    """Downgrade [VERIFIED] → [HYPOTHESIS] on candidates with weak evidence support.

    Called after critique scores are computed. If the critique found that a
    perspective's claims are poorly evidenced or explicitly flagged as
    hallucinated, all [VERIFIED] labels in that candidate's content are
    demoted to [HYPOTHESIS] — the safe direction.

    Does NOT modify [HYPOTHESIS] or [UNKNOWN] labels (already appropriately cautious).
    Does NOT modify content semantics — only the label markers change.
    """
    # Check evidence_support threshold
    needs_downgrade = score.evidence_support < evidence_threshold

    # Check bias_flags for hallucination markers
    if not needs_downgrade and score.bias_flags:
        hallucination_markers = {"hallucinated", "fabricated", "unsupported", "unverified", "no evidence"}
        flags_lower = {f.lower() for f in score.bias_flags}
        needs_downgrade = bool(flags_lower & hallucination_markers)

    if not needs_downgrade:
        return candidate

    # Downgrade [VERIFIED] → [HYPOTHESIS] in content
    import re
    new_content = re.sub(
        r'\[VERIFIED\]',
        '[HYPOTHESIS]',
        candidate.content,
    )

    # Also downgrade in key_insights
    new_insights = [
        re.sub(r'\[VERIFIED\]', '[HYPOTHESIS]', insight)
        for insight in candidate.key_insights
    ]

    # Log the downgrade count for observability
    downgrade_count = candidate.content.count('[VERIFIED]') - new_content.count('[VERIFIED]')

    return SolutionCandidate(
        perspective=candidate.perspective,
        content=new_content,
        key_insights=new_insights,
        model_used=candidate.model_used,
    ), downgrade_count
```

### Integration

In `run_critique_phase()` (`perspective_phases.py`), after scores are parsed and before ranking:

```python
# ── Post-Critique Epistemic Filter ──
# Downgrade [VERIFIED] → [HYPOTHESIS] on candidates with weak evidence
score_map_full = {s.perspective: s for s in state.scores}
for i, candidate in enumerate(state.candidates):
    score = score_map_full.get(candidate.perspective)
    if score is None:
        continue
    updated, count = _downgrade_unverified_labels(candidate, score)
    if count > 0:
        state.candidates[i] = updated
        services.log(
            "PHASE-3",
            f"Epistemic downgrade: {count} [VERIFIED] → [HYPOTHESIS] "
            f"in '{candidate.perspective}' (evidence_support={score.evidence_support:.1f}, "
            f"bias_flags={score.bias_flags})",
            state,
        )
```

### What Does NOT Change

| Component | Change? | Reason |
|-----------|---------|--------|
| Perspective prompts | No | Models still generate labels — the filter corrects them post-hoc |
| Critique prompts | No | Critique already produces the signals we need |
| `CritiqueScore` dataclass | No | No new fields needed |
| `SolutionCandidate` dataclass | No | Labels remain inline text |
| Synthesis phase | No | Receives corrected candidates transparently |
| `FinalSolution.claim_labels` | No | Populated by synthesis from its own analysis |
| Frontend rendering | No | Inline markers render unchanged |

### Configuration

Add to `settings.py`:

```python
# Epistemic filter: downgrade [VERIFIED] labels on perspectives with weak evidence
EPISTEMIC_FILTER_ENABLED: bool = os.getenv("EPISTEMIC_FILTER_ENABLED", "true").lower() == "true"
EPISTEMIC_EVIDENCE_THRESHOLD: float = float(os.getenv("EPISTEMIC_EVIDENCE_THRESHOLD", "3.0"))
```

The filter checks `settings.EPISTEMIC_FILTER_ENABLED` before running. This allows disabling via env var if the filter produces false positives.

### Edge Cases

| Case | Handling |
|------|----------|
| No critique scores (critique phase failed) | Filter skips — no `CritiqueScore` → no downgrade signal |
| Perspective not in score_map (name mismatch) | Filter skips that candidate — logged as warning |
| `[VERIFIED]` appears in `key_insights` | Downgraded along with content |
| `evidence_support` exactly 3.0 | NOT downgraded (threshold is `< 3.0`, not `<=`) |
| Candidate has 0 `[VERIFIED]` labels | No-op — no regex matches, no log |
| `bias_flags` contains partial match (e.g., "potentially hallucinated") | NOT matched — only exact set membership. Partial matches could be added to the marker set. |
| Multiple downgrades on same candidate | Idempotent — regex replaces all `[VERIFIED]` in one pass |
| Debate method (sides A/B, not perspectives) | Filter uses `perspective` field which is coerced to `constructive`/`destructive` for debate — works unchanged |

### Observability

The filter emits a structured log line per downgrade:

```
[PHASE-3] Epistemic downgrade: 7 [VERIFIED] → [HYPOTHESIS] in 'destructive'
          (evidence_support=0.0, bias_flags=['hallucinated statistics'])
```

This appears in:
- Backend logs
- SSE event stream (via `services.log`)
- Frontend phase timeline (if the UI renders PHASE-3 logs)

Future: a `phase_quality` SSE event could include `epistemic_downgrades: int` for the frontend to render a badge.

---

## Files Modified

| File | Change |
|------|--------|
| `src/reasoner/application/flows/perspective_phases.py` | Add `_downgrade_unverified_labels()` function + call it in `run_critique_phase()` after scores |
| `src/reasoner/core/settings.py` | Add `EPISTEMIC_FILTER_ENABLED` and `EPISTEMIC_EVIDENCE_THRESHOLD` settings |

**Total: 2 files, ~40 lines added.**

---

## Verification

```bash
# 1. Unit test: downgrade triggers on low evidence_support
python -c "
from reasoner.domain.core_types import SolutionCandidate, CritiqueScore
from reasoner.application.flows.perspective_phases import _downgrade_unverified_labels

candidate = SolutionCandidate(
    perspective='destructive',
    content='AI will [VERIFIED] replace all jobs [VERIFIED] within 5 years [HYPOTHESIS]',
    key_insights=['[VERIFIED] Claim 1', '[HYPOTHESIS] Claim 2'],
    model_used='test',
)
score = CritiqueScore(
    perspective='destructive',
    logical_consistency=7.0,
    evidence_support=1.0,   # Below 3.0 → triggers downgrade
    failure_resilience=5.0,
    feasibility=6.0,
    bias_flags=['hallucinated statistics'],
    steel_man='N/A',
)
updated, count = _downgrade_unverified_labels(candidate, score)
assert count == 2, f'Expected 2 downgrades, got {count}'
assert '[VERIFIED]' not in updated.content
assert updated.content.count('[HYPOTHESIS]') == 3  # 2 downgraded + 1 original
assert updated.key_insights[0] == '[HYPOTHESIS] Claim 1'
print('All assertions passed')
"

# 2. Unit test: NO downgrade on high evidence_support
python -c "
from reasoner.domain.core_types import SolutionCandidate, CritiqueScore
from reasoner.application.flows.perspective_phases import _downgrade_unverified_labels

candidate = SolutionCandidate(
    perspective='constructive',
    content='[VERIFIED] Well-sourced claim [HYPOTHESIS] Speculative claim',
    key_insights=[],
    model_used='test',
)
score = CritiqueScore(
    perspective='constructive',
    logical_consistency=8.0,
    evidence_support=7.5,   # Above 3.0 → no downgrade
    failure_resilience=6.0,
    feasibility=7.0,
    bias_flags=[],
    steel_man='N/A',
)
updated, count = _downgrade_unverified_labels(candidate, score)
assert count == 0, f'Expected 0 downgrades, got {count}'
assert '[VERIFIED]' in updated.content  # Preserved
print('All assertions passed')
"

# 3. End-to-end: run a pipeline and check for downgrade log lines
# python main.py --problem "..." --preset multi-perspective-budget
# Expected: if any perspective scores evidence_support < 3.0,
# the log shows "Epistemic downgrade: N [VERIFIED] → [HYPOTHESIS]"
```

---

## Execution Order

1. `settings.py` — add 2 settings (no dependencies)
2. `perspective_phases.py` — add function + integration (needs settings from step 1)
3. Verify with unit tests above
</content>
</invoke>