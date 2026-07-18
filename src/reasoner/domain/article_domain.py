"""
Immutable domain model for the Article pipeline (Phase 1 — boundary layer).

This module defines the value objects and typed effects that form the
"functional core" of the article pipeline.  Phases consume and produce
`Context` — an immutable value — rather than mutating PipelineState.

Per the plan (§2.3 pragmatism clause): Python is not Haskell.  Local
mutation inside a phase is fine; immutability is enforced only at phase
*boundaries* via frozen dataclasses and the Result type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar, Union


# ═════════════════════════════════════════════════════════════════════
# Typed effects: Result[T, E]
# ═════════════════════════════════════════════════════════════════════

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True)
class Ok(Generic[T]):
    """Successful result carrying a value."""
    value: T


@dataclass(frozen=True)
class Err(Generic[E]):
    """Failed result carrying an error and optional degraded fallback."""
    error: E
    fallback: object | None = None  # degraded Context, if any


Result = Union[Ok, Err]


# ═════════════════════════════════════════════════════════════════════
# Phase error taxonomy
# ═════════════════════════════════════════════════════════════════════

class PhaseError(Enum):
    """Reasons a phase may return Err instead of Ok."""
    PARSE = "parse"          # JSON parsing failure
    TIMEOUT = "timeout"      # LLM call timed out
    LLM = "llm"              # LLM returned empty or unusable response
    BUDGET = "budget"       # Cost budget exhausted
    INTERNAL = "internal"    # Unexpected exception in phase logic


# ═════════════════════════════════════════════════════════════════════
# Canonical claim taxonomy (§6.1 — fixes G3)
# ═════════════════════════════════════════════════════════════════════

class Verdict(Enum):
    """One canonical verdict for every claim in the ledger.

    Replaces the ad-hoc 3-value (supported/unsupported/partially_supported)
    and 4-value (verified/supported/speculative/unsupported) taxonomies
    that previously existed without a crosswalk.
    """
    VERIFIED = "verified"         # verbatim / direct source match
    SUPPORTED = "supported"       # entailed by source, reworded
    PARTIAL = "partial"           # some support, incomplete
    SPECULATIVE = "speculative"   # opinion / hypothesis / unverifiable
    UNSUPPORTED = "unsupported"   # no source found


class VerifyMethod(Enum):
    """How a claim's verdict was determined."""
    QUOTE_MATCH = "quote_match"
    ENTAILMENT = "entailment"
    LIVE_SEARCH = "live_search"
    NONE = "none"


class HumanDecision(Enum):
    """Human override status for a claim."""
    NONE = "none"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EDITED = "edited"


@dataclass(frozen=True)
class Claim:
    """A single factual claim extracted from the article.

    This is the canonical value object for the living claim ledger.
    Every claim is immutable and versioned against the document revision
    it was verified against.
    """
    id: str
    text: str                                   # normalized claim text
    span: tuple[int, int] | None = None         # char offsets into verified_against_version
    sources: tuple[str, ...] = ()
    verdict: Verdict = Verdict.UNSUPPORTED
    confidence: float = 0.0                     # 0..1
    method: VerifyMethod = VerifyMethod.NONE
    verified_against_version: int = 0           # WHICH doc revision this verdict describes
    human: HumanDecision = HumanDecision.NONE
    needs_review: bool = False


# ═════════════════════════════════════════════════════════════════════
# Verdict mapping (§6.1) — pure function
# ═════════════════════════════════════════════════════════════════════

def map_verdict(
    raw_verdict: str,
    method: VerifyMethod = VerifyMethod.ENTAILMENT,
    is_opinion: bool = False,
) -> Verdict:
    """Map a legacy 3-value or 4-value verdict string to the canonical Verdict.

    This is a pure function — no I/O, no state.  It's the single source
    of truth for verdict resolution, replacing the ad-hoc mappings that
    previously existed in different parts of the codebase.
    """
    if is_opinion:
        return Verdict.SPECULATIVE

    raw = raw_verdict.strip().lower()

    # QUOTE_MATCH always overrides raw-string matching: verbatim quote = VERIFIED
    if method == VerifyMethod.QUOTE_MATCH:
        return Verdict.VERIFIED

    if raw == "unsupported":
        return Verdict.UNSUPPORTED
    if raw in ("partial", "partially_supported"):
        return Verdict.PARTIAL
    if raw == "verified":
        return Verdict.VERIFIED
    if raw in ("supported", "entailed"):
        return Verdict.SUPPORTED
    if raw == "speculative":
        return Verdict.SPECULATIVE

    # Default: if method says entailment, treat broad "supported" as SUPPORTED
    return Verdict.SUPPORTED


def claim_support_ratio(ledger: tuple[Claim, ...]) -> float:
    """Compute an honest support ratio over the claim ledger.

    Partial support contributes 0.5 (not 0), speculative claims are excluded.
    This resolves the lossy metric issue (G3).
    """
    factual = [c for c in ledger if c.verdict != Verdict.SPECULATIVE]
    if not factual:
        return 0.0

    score_map = {
        Verdict.VERIFIED: 1.0,
        Verdict.SUPPORTED: 1.0,
        Verdict.PARTIAL: 0.5,
        Verdict.UNSUPPORTED: 0.0,
    }

    score = sum(score_map.get(c.verdict, 0.0) for c in factual)
    return score / len(factual)


def _normalize_claim_text(text: str) -> str:
    """Normalize claim text for hash-based matching.

    Strips whitespace, lowercases, removes punctuation for fuzzy matching.
    """
    import re
    normalized = text.strip().lower()
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return normalized


def reconcile(
    prev_ledger: tuple[Claim, ...],
    new_doc: Document,
) -> tuple[tuple[Claim, ...], tuple[dict, ...]]:
    """Reconcile the claim ledger against a new document revision.

    The core of G1: after developmental/style edits modify the article text,
    this function determines which claims survive, which are dropped, and
    which new text segments need fresh verification.

    Pure function — no I/O.  The caller is responsible for invoking LLM
    verification on the returned `deltas_to_verify`.

    Returns:
        (carried_ledger, deltas_to_verify)
        - carried_ledger: claims whose text is still present (re-anchored)
        - deltas_to_verify: new text segments that need verification
    """
    # Build normalized-text index for the new document
    doc_text = new_doc.markdown
    doc_lower = doc_text.lower()

    # Build sentence-level index for delta detection
    import re
    doc_sentences = re.split(r'(?<=[.!?])\s+', doc_text)
    doc_sentence_hashes = {
        _normalize_claim_text(s): s for s in doc_sentences if len(s.strip()) > 10
    }

    carried: list[Claim] = []
    deltas: list[dict] = []

    for claim in prev_ledger:
        norm = _normalize_claim_text(claim.text)

        if not norm:
            continue

        # Check if claim text (or close variant) exists in new doc
        if norm in doc_lower:
            # Exact match — carry forward, re-anchor
            offset = doc_lower.index(norm)
            carried.append(Claim(
                id=claim.id,
                text=claim.text,
                span=(offset, offset + len(norm)),
                sources=claim.sources,
                verdict=claim.verdict,
                confidence=claim.confidence,
                method=claim.method,
                verified_against_version=new_doc.version,
                human=claim.human,
                needs_review=claim.needs_review,
            ))
        else:
            # No exact match — try fuzzy: check if any sentence hash matches
            fuzzy_match = None
            for s_hash, s_text in doc_sentence_hashes.items():
                # Check if claim norm is a substring of the sentence hash
                if len(norm) > 10 and (norm in s_hash or s_hash in norm):
                    fuzzy_match = s_text
                    break
                # Check word overlap for short claims
                claim_words = set(norm.split())
                sentence_words = set(s_hash.split())
                if len(claim_words) > 2:
                    overlap = len(claim_words & sentence_words)
                    if overlap / len(claim_words) >= 0.7:
                        fuzzy_match = s_text
                        break

            if fuzzy_match:
                offset = doc_lower.index(_normalize_claim_text(fuzzy_match))
                carried.append(Claim(
                    id=claim.id,
                    text=claim.text,
                    span=(offset, offset + len(_normalize_claim_text(fuzzy_match))),
                    sources=claim.sources,
                    verdict=claim.verdict,
                    confidence=claim.confidence * 0.9,  # slight discount on fuzzy
                    method=claim.method,
                    verified_against_version=new_doc.version,
                    human=claim.human,
                    needs_review=True,  # fuzzy match flagged for review
                ))
            else:
                # Claim text vanished — dropped from ledger
                pass  # dropped silently (could log via events in caller)

    # Detect new sentences not covered by any carried claim
    carried_texts = {_normalize_claim_text(c.text) for c in carried}
    for s_hash, s_text in doc_sentence_hashes.items():
        if s_hash not in carried_texts:
            # This sentence may be new (not in any carried claim)
            # Only flag if it looks like a factual claim (not a header or transition)
            if len(s_text) > 30 and not s_text.startswith('#'):
                deltas.append({
                    "text": s_text,
                    "span": (doc_text.index(s_text), doc_text.index(s_text) + len(s_text)),
                    "reason": "new_or_unverified",
                })

    return tuple(carried), tuple(deltas)

@dataclass(frozen=True)
class Document:
    """An immutable, versioned article document.

    Every revision is a new instance — phases return new Documents via
    dataclasses.replace(), never mutate in place.

    `locked_spans` marks the character ranges of VERIFIED/SUPPORTED claims
    that downstream phases (style edit, copy edit) must not alter.  This
    is the enforcement mechanism for G2.
    """
    version: int
    markdown: str
    title: str
    produced_by: str                           # phase name that emitted this revision
    locked_spans: tuple[tuple[int, int], ...] = ()


# ═════════════════════════════════════════════════════════════════════
# Budget tracking
# ═════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Budget:
    """Cost and time budget for a pipeline run.

    Immutable — spent values produce a new Budget instance via
    `spend()` rather than mutating in place.
    """
    usd_cap: float
    seconds_cap: float
    usd_spent: float = 0.0
    seconds_spent: float = 0.0

    def remaining_usd(self) -> float:
        return max(0.0, self.usd_cap - self.usd_spent)

    def remaining_seconds(self) -> float:
        return max(0.0, self.seconds_cap - self.seconds_spent)

    def spend(self, usd: float = 0.0, seconds: float = 0.0) -> "Budget":
        """Return a new Budget with added spend (immutable)."""
        return Budget(
            usd_cap=self.usd_cap,
            seconds_cap=self.seconds_cap,
            usd_spent=self.usd_spent + usd,
            seconds_spent=self.seconds_spent + seconds,
        )


# ═════════════════════════════════════════════════════════════════════
# The Context (immutable blackboard — §4.1)
# ═════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Context:
    """Immutable shared context passed between article pipeline phases.

    This is the "context" in the functional-core sense: a value that
    flows through the pipeline, with each phase producing a new Context
    (via dataclasses.replace or explicit construction).

    Fields are optional (None) before the phase that produces them and
    populated afterward.  The runner ensures invariants at the composition
    level.
    """
    # ── Input ──
    problem: str
    content_class: str                     # blog, policy_brief, explainer, etc.

    # ── Search & outline (populated by early phases) ──
    sources: tuple[dict, ...] = ()
    outline: dict | None = None

    # ── Document (populated by draft phase, updated by edit phases) ──
    doc: Document | None = None

    # ── Claim ledger (populated by fact-check phase, reconciled by reconcile_ledger) ──
    ledger: tuple[Claim, ...] = ()

    # ── Audit & metrics (populated by final audit) ──
    audit: dict | None = None
    metrics: dict | None = None

    # ── Critique (populated by structural review) ──
    structural_critique: dict | None = None

    # ── Budget (tracked across the run) ──
    budget: Budget | None = None

    # ── Provenance (append-only event log) ──
    events: tuple[dict, ...] = ()

    # ── Augmentation / pre-research insights ──
    pre_research_summary: str = ""
    pre_research_insights: tuple[dict, ...] = ()

    # ── Style brief ──
    style_brief: dict | None = None

    # ── Verification artifacts ──
    verification: dict | None = None
    editorial_audit: dict | None = None

    # ── Pipeline metadata ──
    preset_name: str = ""
    language: str = "English"
    errors: tuple[str, ...] = ()
