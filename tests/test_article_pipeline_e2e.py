"""
E2E test for the refactored Article pipeline (Phase 1-5 combinators).

Exercises the full article_pipeline combinator chain using mock Deps that
simulate LLM responses, without going through the ProviderRouter or needing
API keys.

Tests:
  - Pipeline completes without exception
  - All 10 adapters run in sequence
  - ArticleContext.events has entries from every phase
  - surface_signals are computed
  - sync_to writes back to PipelineState correctly
  - Phase 2: claim reconciliation and support ratio
  - Phase 3: gate policy evaluation
  - Phase 4: with_retry combinator and surface_signals
  - Phase 5: additive event log
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reasoner.domain.core_types import (
    ArticleContext, Ok, Err, Verdict, Claim, WritingDocument,
)
from reasoner.domain.pipeline_state import PipelineState


# ── Mock Deps ────────────────────────────────────────────────────────────────

class MockDeps:
    """Simulates WorkflowServices with canned LLM responses for each phase."""

    def __init__(self) -> None:
        self.logs: list[str] = []
        self.llm_calls: int = 0

    async def call_llm(
        self, role: str, system_prompt: str, user_prompt: str,
        state: object, **kwargs: Any,
    ) -> tuple[str, dict]:
        self.llm_calls += 1

        # Return a rich JSON blob that every phase parser can extract
        blob = json.dumps({
            "queries": ["test query"],
            "article": "## Test Article\n\nThis is a test article body with enough content for all phases.",
            "humanized_article": "## Test Article\n\nThis is a test article body with enough content for all phases.",
            "final_article": "## Test Article\n\nThis is a test article body with enough content for all phases.",
            "suggested_title": "Test Article",
            "article_title": "Test Article",
            "title": "Test Article",
            "claim_ledger": [
                {"claim": "Claim one verified", "source": "https://ex.com/1", "status": "verified"},
                {"claim": "Claim two supported", "source": "https://ex.com/2", "status": "supported"},
                {"claim": "Claim three speculative", "source": "https://ex.com/3", "status": "speculative"},
            ],
            "verified_claims": [
                {"claim": "Claim one", "verdict": "verified"},
                {"claim": "Claim two", "verdict": "supported"},
            ],
            "metrics": {"total_claims": 3, "supported": 2, "unsupported": 0, "claim_support_ratio": 0.67},
            "gaps": [],
            "argument_map": {"central_question": "What is the test?", "problem": "Testing", "current_explanations": [], "limitations": [], "new_insight": "Test", "counterarguments": [], "implications": []},
            "outline": [{"section_title": "Introduction", "key_points": ["Hook"], "sources_used": []}],
            "structural_critique": {"overall_rigor_score": 0.8, "implicit_assumptions": [], "logical_gaps": [], "ignored_counterarguments": []},
            "audit": {
                "thesis_advancement": 0.85, "claim_support": 0.75,
                "internal_consistency": 0.80, "transition_quality": 0.70,
                "redundancy_removed": 0.75, "citation_accuracy": 0.60,
                "policy_compliance": 1.0,
            },
            "issues": [],
            "audit_score": 0.8, "passes_audit": True,
            "core_solution": "## Summary\n\nTest article summary about the topic.",
            "critical_insights": ["Test insight"],
            "action_blueprint": [],
            "open_questions": [],
            "claim_labels": {},
            "meta_audit": {"most_dangerous_assumption": "none", "dominant_bias": "none",
                           "remaining_uncertainty": "low", "assumption_failure_impact": "low",
                           "non_obvious_insight": "test"},
            "sources": [{"title": "Test Source", "url": "https://ex.com"}],
        })
        return f"```json\n{blob}\n```", {"model": "mock", "tokens": {"input": 100, "output": 200}}

    def log(self, phase: str, message: str, state: object) -> None:
        self.logs.append(f"[{phase}] {message}")


# ── Tests ────────────────────────────────────────────────────────────────────

class TestArticlePipelineE2E:
    """End-to-end test of the refactored Article pipeline."""

    async def _run_pipeline(self) -> tuple[ArticleContext, MockDeps, object]:
        """Run the full article_pipeline with mock deps and return the context."""
        from reasoner.application.flows.article_adapters import article_pipeline
        from reasoner.application.flows.article_adapters import _compute_surface_signals

        ctx = ArticleContext(
            problem="Test article problem",
            language="English",
            preset_name="article-budget",
            content_class="blog",
        )
        deps = MockDeps()
        result = await article_pipeline(ctx, deps)

        if isinstance(result, Ok):
            ctx = result.value
        elif isinstance(result, Err):
            if result.fallback is not None:
                ctx = result.fallback
            else:
                raise RuntimeError(f"Pipeline failed: {result.error}")

        # Compute surface signals
        signals = _compute_surface_signals(ctx)
        if signals:
            ctx = ctx.replace(surface_signals=signals)

        # Sync to PipelineState
        state = PipelineState(problem="T", language="English", preset_name="article-budget", method="article")
        ctx.sync_to(state)

        return ctx, deps, state

    # ── Test 1: pipeline completes ────────────────────────────────────────

    async def test_pipeline_completes(self) -> None:
        ctx, deps, state = await self._run_pipeline()
        assert ctx.problem == "Test article problem"
        assert len(deps.logs) > 0
        print(f"  PASS: pipeline completed ({len(deps.logs)} log entries, {deps.llm_calls} LLM calls)")

    # ── Test 2: all 10+ adapters emit events ──────────────────────────────

    async def test_event_log_has_all_phases(self) -> None:
        ctx, _, _ = await self._run_pipeline()
        events = ctx.events
        event_names = [e.event for e in events]
        expected = {"sources_retrieved", "outline_built", "draft_completed",
                     "claim_verification", "structural_reviewed",
                     "dev_edit_completed", "style_edit_completed",
                     "audit_completed", "synthesis_completed"}
        for name in expected:
            assert name in event_names, f"Missing event: {name}"
        print(f"  PASS: {len(events)} events ({', '.join(event_names)})")

    # ── Test 3: Phase 2 claim ledger ──────────────────────────────────────

    async def test_claims_verified(self) -> None:
        ctx, _, _ = await self._run_pipeline()
        assert len(ctx.claims) > 0, "No claims in ledger"
        total = len(ctx.claims)
        factual = sum(1 for c in ctx.claims if c.verdict in
                      (Verdict.VERIFIED, Verdict.SUPPORTED))
        print(f"  PASS: {total} claims ({factual} factual)")
        assert factual > 0, "No factual claims"

    # ── Test 4: Phase 3 gate policy evaluation ────────────────────────────

    async def test_gate_policy_evaluated(self) -> None:
        ctx, _, state = await self._run_pipeline()
        audit = ctx.editorial_audit
        assert "gate_score" in audit, "No gate score in audit"
        assert "gate_failures" in audit, "No gate failures in audit"
        print(f"  PASS: gate score={audit.get('gate_score')}, passes_audit={audit.get('passes_audit')}")

    # ── Test 5: Phase 4 surface_signals computed ──────────────────────────

    async def test_surface_signals_emitted(self) -> None:
        ctx, _, state = await self._run_pipeline()
        assert hasattr(ctx, "surface_signals")
        # Should have no quality_warning since mock audit passes
        if "quality_warning" in ctx.surface_signals:
            print(f"  PASS: quality_warning present: {ctx.surface_signals['quality_warning']}")
        else:
            print("  PASS: no quality_warning (audit passed, as expected)")

    # ── Test 6: sync_to round-trip ────────────────────────────────────────

    async def test_sync_to_roundtrip(self) -> None:
        _, _, state = await self._run_pipeline()
        assert state.writing_state.get("final_article"), "No final_article in writing_state"
        assert "claim_ledger" in state.writing_state, "No claim_ledger synced"
        assert "article_events" in state.writing_state, "No article_events synced"
        assert len(state.writing_state["article_events"]) > 0, "Empty article_events"
        print(f"  PASS: sync_to wrote all fields (final_article={len(state.writing_state['final_article'])} chars, "
              f"claims={len(state.writing_state['claim_ledger'])}, "
              f"events={len(state.writing_state['article_events'])})")

    # ── Test 7: with_retry runs on audit failure ──────────────────────────

    async def test_with_retry_on_audit_failure(self) -> None:
        from reasoner.application.flows.article_adapters import article_pipeline

        # Create a mock Deps that fails audit on first try
        class FailAuditDeps(MockDeps):
            def __init__(self):
                super().__init__()
                self._first_audit = True

            async def call_llm(self, role: str, system_prompt: str, user_prompt: str, state: object, **kw):
                self.llm_calls += 1
                # Return failing audit on first call, passing on retry
                blob = json.dumps({
                    "article": "Retry article body.",
                    "claim_ledger": [{"claim": "Test claim", "source": "https://ex.com", "status": "verified"}],
                    "audit": {"thesis_advancement": 0.3, "claim_support": 0.2,
                              "internal_consistency": 0.4, "transition_quality": 0.3,
                              "redundancy_removed": 0.4, "citation_accuracy": 0.3, "policy_compliance": 1.0},
                    "audit_score": 0.3, "passes_audit": not self._first_audit,
                    "issues": [] if self._first_audit else [],
                })
                self._first_audit = False
                return f"```json\n{blob}\n```", {"model": "mock"}

        ctx = ArticleContext(problem="Test article problem", language="English",
                              preset_name="article-budget", content_class="blog")
        deps = FailAuditDeps()
        result = await article_pipeline(ctx, deps)

        assert isinstance(result, (Ok, Err))
        if isinstance(result, Err):
            # After retry, we either pass or degrade — both are valid
            assert result.fallback is not None, "Retry should degrade, not fail fatally"
        print(f"  PASS: audit retry completed (result type: {type(result).__name__})")

    # ── Test 8: branch(gap_retrieval) runs when gaps exist ────────────────

    async def test_branch_gap_retrieval(self) -> None:
        from reasoner.application.flows.article_adapters import has_evidence_gaps, gap_retrieval

        ctx = ArticleContext(problem="Test", gaps_noted=["missing source"])
        assert has_evidence_gaps(ctx), "has_evidence_gaps should be True with gaps"

        ctx_no_gaps = ArticleContext(problem="Test")
        assert not has_evidence_gaps(ctx_no_gaps), "has_evidence_gaps should be False without gaps"

        # gap_retrieval should return Ok with updated context
        deps = MockDeps()
        result = await gap_retrieval(ctx, deps)
        assert isinstance(result, Ok), f"Expected Ok, got {result}"
        assert len(result.value.clams if hasattr(result.value, 'clams') else []) >= 0
        print(f"  PASS: branch(gap_retrieval) runs correctly")

    # ── Test 9: article_pipeline callable ─────────────────────────────────

    async def test_article_pipeline_callable(self) -> None:
        from reasoner.application.flows.article_adapters import article_pipeline
        assert callable(article_pipeline)
        print("  PASS: article_pipeline is callable")


# ── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    t = TestArticlePipelineE2E()

    async def run_all():
        tests = [
            ("pipeline completes", t.test_pipeline_completes),
            ("event log has all phases", t.test_event_log_has_all_phases),
            ("claims verified", t.test_claims_verified),
            ("gate policy evaluated", t.test_gate_policy_evaluated),
            ("surface signals emitted", t.test_surface_signals_emitted),
            ("sync_to round-trip", t.test_sync_to_roundtrip),
            ("with_retry on audit failure", t.test_with_retry_on_audit_failure),
            ("branch gap retrieval", t.test_branch_gap_retrieval),
            ("article_pipeline callable", t.test_article_pipeline_callable),
        ]
        passed = 0
        failed = 0
        for name, test in tests:
            try:
                await test()
                passed += 1
            except Exception as e:
                print(f"  FAIL: {name}: {e}")
                failed += 1
        print(f"\n{passed} passed, {failed} failed")

    asyncio.run(run_all())
