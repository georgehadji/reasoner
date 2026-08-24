"""
Defect-hunt regression tests (V7 Protocol — Phase 7 artifacts).

Tests the verified defects D1 and D3 found during the proactive audit
of the article pipeline.

D1 (HIGH): writing_state_to_context never read ws['claim_ledger'],
            so Context.ledger was always empty.
D3 (MEDIUM): locked_spans with OOB indices became silent no-ops.

Each test asserts: fails without the fix, passes with it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from reasoner.application.flows.article_adapters import (
    AdapterDeps,
    context_to_writing_state,
    writing_state_to_context,
)
from reasoner.domain.article_domain import (
    Context,
    Document,
    Verdict,
)


def _make_deps() -> AdapterDeps:
    return AdapterDeps(services=AsyncMock())


def _make_ctx(**kw) -> Context:
    base = {"problem": "test", "content_class": "blog", "language": "English"}
    base.update(kw)
    return Context(**base)


# ═════════════════════════════════════════════════════════════════════
# D1 — Claim ledger data-flow gap
# ═════════════════════════════════════════════════════════════════════

class TestD1ClaimLedgerDataFlow:
    """D1: writing_state_to_context must read claim_ledger from ws dict."""

    # ── Proof-of-defect ──────────────────────────────────────────────

    def test_proof_ledger_materialized_from_claim_ledger(self):
        """Without the D1 fix, Context.ledger stays empty after round-trip
        even when writing_state has a populated claim_ledger."""
        doc = Document(version=1, markdown="Test.", title="T", produced_by="draft")
        ctx = _make_ctx(doc=doc, ledger=())

        ws = context_to_writing_state(ctx)
        ws["claim_ledger"] = [
            {"claim": "Verified claim", "source": "https://ex.com", "status": "verified"},
            {"claim": "Unsupported claim", "source": None, "status": "unsupported"},
        ]

        ctx2 = writing_state_to_context(ctx, ws, _make_deps())

        # Post-fix: the ledger must be populated
        assert len(ctx2.ledger) > 0, (
            "D1 DEFECT: claim_ledger was written to ws but never read back "
            "into Context.ledger — reconciliation, span-lock, and signals "
            "all received empty data"
        )

    def test_proof_verdicts_correctly_mapped(self):
        """Each entry's status must be resolved to the canonical Verdict."""
        doc = Document(version=1, markdown="Test.", title="T", produced_by="draft")
        ctx = _make_ctx(doc=doc, ledger=())
        ws = context_to_writing_state(ctx)
        ws["claim_ledger"] = [
            {"claim": "C1", "source": "https://a.com", "status": "verified"},
            {"claim": "C2", "source": None, "status": "partial"},
            {"claim": "C3", "source": None, "status": "speculative"},
        ]
        ctx2 = writing_state_to_context(ctx, ws, _make_deps())
        assert len(ctx2.ledger) == 3
        verdicts = [c.verdict for c in ctx2.ledger]
        assert Verdict.VERIFIED in verdicts
        assert Verdict.PARTIAL in verdicts
        assert Verdict.SPECULATIVE in verdicts

    def test_proof_sources_preserved(self):
        """Source URLs must flow through to Claim.sources."""
        doc = Document(version=1, markdown="Test.", title="T", produced_by="draft")
        ctx = _make_ctx(doc=doc, ledger=())
        ws = context_to_writing_state(ctx)
        ws["claim_ledger"] = [
            {"claim": "C1", "source": "https://ex.com/article", "status": "verified"},
            {"claim": "C2", "source": None, "status": "unsupported"},
        ]
        ctx2 = writing_state_to_context(ctx, ws, _make_deps())
        assert ctx2.ledger[0].sources == ("https://ex.com/article",)
        assert ctx2.ledger[1].sources == ()

    # ── Boundary tests ──────────────────────────────────────────────

    def test_boundary_empty_claim_ledger(self):
        """Empty claim_ledger should not crash — ledger stays empty."""
        doc = Document(version=1, markdown="Test.", title="T", produced_by="draft")
        ctx = _make_ctx(doc=doc, ledger=())
        ws = context_to_writing_state(ctx)
        ws["claim_ledger"] = []
        ctx2 = writing_state_to_context(ctx, ws, _make_deps())
        assert len(ctx2.ledger) == 0

    def test_boundary_missing_claim_ledger(self):
        """Missing claim_ledger key should not crash."""
        doc = Document(version=1, markdown="Test.", title="T", produced_by="draft")
        ctx = _make_ctx(doc=doc, ledger=())
        ws = context_to_writing_state(ctx)
        # Don't set claim_ledger at all
        ctx2 = writing_state_to_context(ctx, ws, _make_deps())
        assert len(ctx2.ledger) == 0  # stays as ctx.ledger

    def test_boundary_malformed_entry_skipped(self):
        """An entry with missing 'claim' text should be skipped."""
        doc = Document(version=1, markdown="Test.", title="T", produced_by="draft")
        ctx = _make_ctx(doc=doc, ledger=())
        ws = context_to_writing_state(ctx)
        ws["claim_ledger"] = [
            {"claim": "", "source": "https://ex.com", "status": "verified"},
            {"claim": "Real claim", "source": None, "status": "supported"},
        ]
        ctx2 = writing_state_to_context(ctx, ws, _make_deps())
        assert len(ctx2.ledger) == 1
        assert ctx2.ledger[0].text == "Real claim"

    def test_boundary_non_dict_in_list_skipped(self):
        """Non-dict entries in claim_ledger should be skipped."""
        doc = Document(version=1, markdown="Test.", title="T", produced_by="draft")
        ctx = _make_ctx(doc=doc, ledger=())
        ws = context_to_writing_state(ctx)
        ws["claim_ledger"] = [
            "not a dict",
            42,
            {"claim": "Valid", "status": "verified"},
        ]
        ctx2 = writing_state_to_context(ctx, ws, _make_deps())
        assert len(ctx2.ledger) == 1
        assert ctx2.ledger[0].text == "Valid"

    def test_boundary_claim_ledger_not_a_list(self):
        """Non-list claim_ledger (e.g., string) should be ignored."""
        doc = Document(version=1, markdown="Test.", title="T", produced_by="draft")
        ctx = _make_ctx(doc=doc, ledger=())
        ws = context_to_writing_state(ctx)
        ws["claim_ledger"] = "not a list"
        ctx2 = writing_state_to_context(ctx, ws, _make_deps())
        # Should not crash; ledger stays as ctx.ledger
        assert ctx2.ledger == ()

    # ── No-regression tests ─────────────────────────────────────────

    def test_no_regression_empty_ws_preserves_context(self):
        """Empty ws should not mutate Context fields."""
        doc = Document(version=1, markdown="Original.", title="T", produced_by="test")
        ctx = _make_ctx(doc=doc, ledger=(), sources=({"url": "https://ex.com"},))
        ctx2 = writing_state_to_context(ctx, {}, _make_deps())
        assert ctx2.problem == ctx.problem
        assert ctx2.content_class == ctx.content_class
        assert ctx2.doc.markdown == ctx.doc.markdown

    def test_no_regression_document_versioning_still_works(self):
        """Document version increments on content change."""
        doc = Document(version=3, markdown="Same.", title="T", produced_by="draft")
        ctx = _make_ctx(doc=doc)
        ws = context_to_writing_state(ctx)
        ws["final_article"] = "Modified."
        ws["_current_phase"] = "edit"
        ctx2 = writing_state_to_context(ctx, ws, _make_deps())
        assert ctx2.doc.version == 4


# ═════════════════════════════════════════════════════════════════════
# D3 — Out-of-bounds locked_spans
# ═════════════════════════════════════════════════════════════════════

class TestD3LockedSpanBounds:
    """D3: OOB locked_spans must be removed during context conversion."""

    # ── Proof-of-defect ──────────────────────────────────────────────

    def test_proof_oob_span_removed(self):
        """Without the D3 fix, a span past doc length silently becomes
        a no-op in span-lock enforcement — 'protected' content is actually
        unprotected."""
        doc = Document(
            version=1, markdown="Short.", title="T", produced_by="test",
            locked_spans=((100, 200),),  # completely past end of 6-char doc
        )
        ctx = _make_ctx(doc=doc)
        ctx2 = writing_state_to_context(ctx, {}, _make_deps())
        assert (100, 200) not in ctx2.doc.locked_spans, (
            "D3 DEFECT: OOB span (100, 200) survived validation — "
            "the locked span is past the end of 'Short' and would "
            "silently protect nothing"
        )

    def test_proof_valid_span_preserved(self):
        """In-bounds spans must be preserved."""
        doc = Document(
            version=1, markdown="Hello world.", title="T", produced_by="test",
            locked_spans=((0, 5),),  # "Hello" — 12-char doc
        )
        ctx = _make_ctx(doc=doc)
        ctx2 = writing_state_to_context(ctx, {}, _make_deps())
        assert (0, 5) in ctx2.doc.locked_spans

    # ── Boundary tests ──────────────────────────────────────────────

    def test_boundary_negative_start_removed(self):
        """Negative span start must be removed."""
        doc = Document(
            version=1, markdown="Hello world.", title="T", produced_by="test",
            locked_spans=((-5, 10),),
        )
        ctx = _make_ctx(doc=doc)
        ctx2 = writing_state_to_context(ctx, {}, _make_deps())
        assert (-5, 10) not in ctx2.doc.locked_spans

    def test_boundary_exact_end_boundary_preserved(self):
        """Span ending exactly at doc length must be preserved."""
        doc = Document(
            version=1, markdown="Hello world.", title="T", produced_by="test",
            locked_spans=((0, 12),),  # 12 is len("Hello world.") — exact boundary
        )
        ctx = _make_ctx(doc=doc)
        ctx2 = writing_state_to_context(ctx, {}, _make_deps())
        assert (0, 12) in ctx2.doc.locked_spans

    def test_boundary_start_equals_end_removed(self):
        """Zero-length span (start == end) must be removed."""
        doc = Document(
            version=1, markdown="Hello world.", title="T", produced_by="test",
            locked_spans=((5, 5),),  # zero-length
        )
        ctx = _make_ctx(doc=doc)
        ctx2 = writing_state_to_context(ctx, {}, _make_deps())
        assert (5, 5) not in ctx2.doc.locked_spans

    def test_boundary_mixed_valid_and_invalid(self):
        """Valid and invalid spans mixed — only valid survive."""
        doc = Document(
            version=1, markdown="Hello world.", title="T", produced_by="test",
            locked_spans=(
                (0, 5),     # valid
                (100, 200), # OOB
                (6, 11),    # valid
                (-1, 3),    # negative start
            ),
        )
        ctx = _make_ctx(doc=doc)
        ctx2 = writing_state_to_context(ctx, {}, _make_deps())
        assert (0, 5) in ctx2.doc.locked_spans
        assert (6, 11) in ctx2.doc.locked_spans
        assert (100, 200) not in ctx2.doc.locked_spans
        assert (-1, 3) not in ctx2.doc.locked_spans
        assert len(ctx2.doc.locked_spans) == 2

    # ── No-regression test ──────────────────────────────────────────

    def test_no_regression_empty_locked_spans_unchanged(self):
        """An empty locked_spans tuple should pass through unchanged."""
        doc = Document(
            version=1, markdown="Hello world.", title="T", produced_by="test",
            locked_spans=(),
        )
        ctx = _make_ctx(doc=doc)
        ctx2 = writing_state_to_context(ctx, {}, _make_deps())
        assert ctx2.doc.locked_spans == ()
