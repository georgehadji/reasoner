# Phase 2 Implementation Plan: Living Ledger

## Scope
Close G1 (stale ledger), G3 (taxonomy inconsistency), G2 (span-lock).
This is the highest-ROI phase — it resolves both CRITICAL bugs from the plan.

## What changes

### Step 1: Canonical `Verdict` Enum + `map_verdict()`

The plan identifies **four** different verdict/value systems currently in play.
Collapse to **one**:

```python
class Verdict(str, Enum):
    VERIFIED = "verified"         # verbatim / direct source match
    SUPPORTED = "supported"       # entailed by source, reworded
    PARTIAL = "partial"           # some support, incomplete
    SPECULATIVE = "speculative"   # opinion / hypothesis / unverifiable
    UNSUPPORTED = "unsupported"   # no source found
```

Pure mapping function:

```python
def map_verdict(raw_verdict: str, is_opinion: bool = False) -> Verdict:
    if is_opinion: return Verdict.SPECULATIVE
    raw = raw_verdict.lower().strip()
    # Normalize from any prompt's taxonomy
    if raw in ("verified", "verifiable", "confirmed"):
        return Verdict.VERIFIED
    if raw in ("supported", "entailed"):
        return Verdict.SUPPORTED
    if raw in ("partial", "partially_supported", "partially supported"):
        return Verdict.PARTIAL
    if raw in ("speculative", "opinion", "hypothesis", "unverifiable"):
        return Verdict.SPECULATIVE
    if raw in ("unsupported", "unsubstantiated", "unconfirmed", "false", "refuted"):
        return Verdict.UNSUPPORTED
    return Verdict.UNSUPPORTED  # safe default
```

### Step 2: Honest `claim_support_ratio()`

```python
def claim_support_ratio(claims: tuple[Claim, ...]) -> float:
    factual = [c for c in claims if c.verdict in (Verdict.VERIFIED, Verdict.SUPPORTED, Verdict.PARTIAL, Verdict.UNSUPPORTED)]
    if not factual: return 0.0
    score = sum({
        Verdict.VERIFIED: 1.0, Verdict.SUPPORTED: 1.0,
        Verdict.PARTIAL: 0.5, Verdict.UNSUPPORTED: 0.0,
    }.get(c.verdict, 0.0) for c in factual)
    return score / len(factual)
```

### Step 3: `reconcile_ledger()`

```python
def reconcile(
    prev_claims: tuple[Claim, ...],
    new_doc: WritingDocument,
) -> tuple[tuple[Claim, ...], list[str]]:
    """
    Returns (carried_claims, claim_bodies_to_reverify).
    - claims whose normalized text still present -> carried forward
    - claims whose text vanished -> dropped
    - new text not in ledger -> added to reverify list
    """
    prev_texts = {c.text.strip().lower() for c in prev_claims if c.text}
    new_text = new_doc.markdown
    
    # Extract sentences/claims from new doc (simple line-based split for v1)
    # In practice: extract factual statements from the markdown
    
    carried = []
    for c in prev_claims:
        if c.text and c.text.strip().lower() in new_text.lower():
            carried.append(c)  # still present, carry forward
        # else: silently dropped (removed by edit)
    
    # Find new text segments not yet claimed
    segments = _extract_claim_candidates(new_doc.markdown)
    to_verify = [s for s in segments if s.strip().lower() not in prev_texts]
    
    return tuple(carried), to_verify
```

For v1, `_extract_claim_candidates` can be a simple sentence-split on `". "` 
— good enough for the structural fix. Phase 3 can improve extraction.

### Step 4: Update `Claim` dataclass

Replace `status: str` with `verdict: Verdict`:

```python
@dataclass(frozen=True)
class Claim:
    id: str = ""
    text: str = ""
    verdict: Verdict = Verdict.SPECULATIVE
    source_url: str = ""
    note: str = ""
    verified_against_version: int = 0
```

### Step 5: Span-lock

After fact-check, set `locked_spans` on the `WritingDocument`:

```python
def compute_locked_spans(markdown: str, claims: tuple[Claim, ...]) -> tuple[tuple[int, int], ...]:
    """Compute char spans of VERIFIED and SUPPORTED claims in the markdown."""
    spans = []
    for c in claims:
        if c.verdict in (Verdict.VERIFIED, Verdict.SUPPORTED) and c.text:
            idx = markdown.find(c.text)
            if idx >= 0:
                spans.append((idx, idx + len(c.text)))
    return tuple(sorted(spans))
```

Then in the style/copy edit adapters, enforce that locked-spans text hasn't changed:

```python
def verify_locked_spans(original: str, edited: str, spans: tuple[tuple[int, int], ...]) -> bool:
    for start, end in spans:
        if original[start:end] not in edited:
            return False  # locked text was removed or altered
    return True
```

If enforcement fails, fall back to the original document.

### Step 6: Wire into adapters

- `fact_check` adapter: call `map_verdict()` for each claim from the LLM response.
- After `fact_check` in the pipeline: call `compute_locked_spans()`.
- `developmental_edit`, `style_copy_edit` adapters: call `verify_locked_spans()`.
- Before `final_audit`: call `reconcile_ledger()` to re-anchor claims against current doc version.
- `final_audit` reads `claim_support_ratio()` from the reconciled ledger, not from the LLM's impression.

### Backward Compatibility

- Old `Claim.status: str` → new `Claim.verdict: Verdict` — breaks serialization.
- `to_pipeline_state()` and `sync_to()` must map `verdict.name.lower()` to the `status` string the prompt builders expect.
- `sync_to()` also writes `claim_support_ratio` into `ws["metrics"]`.
