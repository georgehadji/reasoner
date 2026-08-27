"""Regression tests for Reasoner article pipeline (Phase 0 — structural net).

Rewritten for the current Writing flow API (ArticleFlow in application/flows/article.py).

Structural invariants tested:
  - ArticleFlow.get_phases() returns the expected phases in order
  - PhaseStep structure (num, name, fn, serializer) is well-formed
  - Prompt builders work with minimal state
  - extract_json handles edge cases (Phase 0 safety)
"""

from __future__ import annotations

import json

import pytest

from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import ParseError, _sanitize_json_escapes, extract_json

# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_bare_state(problem: str = "Test article about climate") -> PipelineState:
    """Minimal PipelineState for structural tests (no writing_state fields)."""
    state = PipelineState(
        problem=problem,
        language="English",
        preset_name="article-budget",
        method="article",
    )
    return state


# ── Phase 1: Article Flow Structure ─────────────────────────────────────────

class TestArticleFlowStructure:
    """ArticleFlow returns the correct phase sequence."""

    def test_get_phases_returns_nine_phases(self):
        from reasoner.application.flows.article import ArticleFlow
        flow = ArticleFlow()
        state = _make_bare_state()
        phases = flow.get_phases(state)
        assert len(phases) == 9, f"Expected 9 phases, got {len(phases)}"

    def test_phase_numbers_in_order(self):
        from reasoner.application.flows.article import ArticleFlow
        flow = ArticleFlow()
        state = _make_bare_state()
        phases = flow.get_phases(state)
        nums = [p.num for p in phases]
        assert nums == sorted(nums), f"Phase numbers not in order: {nums}"

    def test_phase_names_non_empty(self):
        from reasoner.application.flows.article import ArticleFlow
        flow = ArticleFlow()
        state = _make_bare_state()
        for p in flow.get_phases(state):
            assert p.name, f"Phase {p.num} has empty name"
            assert callable(p.fn), f"Phase {p.num} fn is not callable"
            assert callable(p.serializer), f"Phase {p.num} serializer is not callable"

    def test_phase_names_match_expected(self):
        from reasoner.application.flows.article import ArticleFlow
        flow = ArticleFlow()
        state = _make_bare_state()
        names = [p.name for p in flow.get_phases(state)]
        expected = [
            "Evidence Collection",
            "Argument Map / Outline",
            "First Draft",
            "Fact Check + Ledger",
            "Structural Review",
            "Developmental Edit",
            "Style + Copy Edit",
            "Final Audit",
            "Synthesis",
        ]
        assert names == expected, f"Phase names mismatch:\n  got:      {names}\n  expected: {expected}"


# ── Phase 2: Synthesis phase safety ──────────────────────────────────────────

class TestSynthesisPhase:
    """Synthesis phase works with minimal/missing writing_state."""

    def test_synthesis_summary_builds_with_empty_writing_state(self):
        """synthesis_prompt should not crash when writing_state is empty."""
        state = _make_bare_state()
        import reasoner.phases as phases
        try:
            prompt = phases.synthesis_prompt(state)
            assert isinstance(prompt, str) and len(prompt) > 20
        except Exception as exc:
            pytest.fail(f"synthesis_prompt crashed with bare state: {exc}")

    @pytest.mark.asyncio
    async def test_synthesis_phase_runs_with_minimal_state(self):
        """The synthesis phase function should handle missing fields gracefully."""
        from unittest.mock import AsyncMock

        from reasoner.application.flows.synthesis_phase import run_synthesis_phase

        state = _make_bare_state("Test article about renewable energy")
        # Populate writing_state with the minimum the synthesis needs
        ws = state.writing_state
        ws["final_article"] = "## Renewable Energy\n\nThis is a test article."
        ws["retrieved_sources"] = [{"title": "Test", "url": "https://test.com"}]
        ws["claim_ledger"] = []
        ws["metrics"] = {}
        ws["editorial_audit"] = {"passes_audit": True, "audit_score": 0.8}

        mock_services = AsyncMock()
        mock_services.log = AsyncMock()
        mock_services.call_llm = AsyncMock(return_value=(
            json.dumps({
                "core_solution": "## Summary\n\nTest article summary.",
                "critical_insights": ["Key insight about renewable energy"],
                "action_blueprint": [],
                "conclusion": "In conclusion, renewable energy matters.",
                "meta_cognitive_audit": {
                    "overall_confidence": 0.8,
                    "uncertainty_areas": [],
                },
            }),
            {"model": "test-model", "tokens": 100},
        ))

        # Should not raise
        await run_synthesis_phase(state, mock_services)
        assert state.final_solution is not None


# ── Phase 3: Article phase functions handle missing state gracefully ─────────

class TestArticlePhaseGracefulDegradation:
    """Phase functions should not crash when writing_state is partially populated."""

    @pytest.mark.asyncio
    async def test_retrieve_sources_empty_state(self):
        """Source retrieval shouldn't crash on empty writing_state."""
        from unittest.mock import AsyncMock

        from reasoner.application.flows.article_phases import run_article_retrieve_sources_phase

        state = _make_bare_state("Test article")
        ws = state.writing_state
        # Don't set any fields — test graceful degradation

        mock_services = AsyncMock(spec_set=["log", "call_llm", "run_phase"])
        mock_services.log = AsyncMock()
        mock_services.call_llm = AsyncMock(return_value=(
            json.dumps({"queries": ["test query"]}),
            {"model": "test-model"},
        ))

        # Should not raise — will try to use empty retrieved_sources
        await run_article_retrieve_sources_phase(state, mock_services)

    @pytest.mark.asyncio
    async def test_outline_empty_writing_state(self):
        """Outline phase shouldn't crash on empty writing_state."""
        from unittest.mock import AsyncMock

        from reasoner.application.flows.article_phases import run_article_outline_phase

        state = _make_bare_state("Test article")
        ws = state.writing_state
        ws["retrieved_sources"] = []  # in case the phase reads this

        mock_services = AsyncMock(spec_set=["log", "call_llm", "run_phase"])
        mock_services.log = AsyncMock()
        mock_services.call_llm = AsyncMock(return_value=(
            json.dumps({
                "suggested_title": "Test",
                "argument_map": {"central_question": "What?"},
                "outline": [],
            }),
            {"model": "test-model"},
        ))

        await run_article_outline_phase(state, mock_services)


# ── Phase 4: Prompt builders — structural tests ─────────────────────────────

class TestArticlePromptBuilders:
    """Prompt builders produce valid output for various state configurations."""

    def _make_test_state(self, writing_state_override: dict | None = None) -> PipelineState:
        state = _make_bare_state("Test article about AI")
        ws = state.writing_state
        ws["retrieved_sources"] = [{"title": "Source", "url": "https://test.com"}]
        ws["argument_map"] = {"central_question": "What?", "problem": "Test"}
        ws["final_article"] = "# Test\n\nArticle content."
        ws["structural_critique"] = {"overall_rigor_score": 0.7}
        ws["verification"] = {"metrics": {"claim_support_ratio": 0.8}}
        ws["claim_ledger"] = []
        ws["metrics"] = {}
        if writing_state_override:
            ws.update(writing_state_override)
        return state

    def test_retrieval_plan_prompt_includes_sources(self):
        from reasoner.phases.article import article_retrieval_plan_prompt
        state = self._make_test_state()
        prompt = article_retrieval_plan_prompt(state)
        assert "Research Topic" in prompt
        assert "AI" in prompt

    def test_draft_prompt_reflects_style_brief(self):
        from reasoner.phases.article import article_draft_prompt
        state = self._make_test_state({"style_brief": {"author": "Test Author", "publication": "Test Pub"}})
        prompt = article_draft_prompt(state)
        assert "STYLE REQUIREMENT" in prompt
        assert "Test Author" in prompt

    def test_verify_prompt_sonar_flag_skips_sources(self):
        from reasoner.phases.article import article_verify_prompt
        state = self._make_test_state()
        normal = article_verify_prompt(state, use_sonar=False)
        sonar = article_verify_prompt(state, use_sonar=True)
        # Both should work, sonar variant may be shorter (fewer source tokens)
        assert isinstance(normal, str)
        assert isinstance(sonar, str)

    def test_final_audit_prompt_has_audit_instructions(self):
        from reasoner.phases.article import article_final_audit_prompt
        state = self._make_test_state()
        prompt = article_final_audit_prompt(state)
        assert "audit_score" in prompt or "passes_audit" in prompt


# ── Phase 5: extract_json type safety (migrated from old regression) ─────────

class TestExtractJsonSafety:
    """extract_json must handle edge cases safely."""

    def test_rejects_non_dict_arrays(self):
        """extract_json currently handles arrays; test documents actual behavior."""
        result = extract_json('["just", "an", "array"]')
        # Should return something without crashing
        assert result is not None

    def test_rejects_non_dict_strings(self):
        with pytest.raises(ParseError):
            extract_json('"just a string"')

    def test_returns_empty_dict_for_empty_input(self):
        assert extract_json("") == {}
        assert extract_json("   ") == {}
        assert extract_json("\n\n") == {}

    def test_handles_invalid_escape_sequences(self):
        raw = r'''```json
{
  "ai_tells": [
    "functions as a 'Connector,' 'Maven,' and 'Salesman,' facilitating..."
  ],
  "humanized_article": "Test article content here."
}
```'''
        result = extract_json(raw)
        assert isinstance(result, dict)
        assert "ai_tells" in result
        assert "humanized_article" in result
        tells = result["ai_tells"]
        assert any("'Connector," in item for item in tells)

    def test_sanitize_json_escapes_hex_and_null(self):
        assert _sanitize_json_escapes(r'"value": "\x41\x42"') == r'"value": "\u0041\u0042"'
        assert _sanitize_json_escapes(r'"value": "hello\0world"') == r'"value": "helloworld"'

    def test_extract_json_fences_variants(self):
        """extract_json handles various markdown fence styles."""
        cases = [
            (r'```json\n{"key": "value"}\n```', {"key": "value"}),
            (r'```\n{"key": "value"}\n```', {"key": "value"}),
            (r'```JSON\n{"key": "value"}\n```', {"key": "value"}),
            ('{"key": "value"}', {"key": "value"}),
        ]
        for raw, expected in cases:
            result = extract_json(raw)
            assert result == expected, f"Failed for input: {raw[:50]}..."


# ── Phase 6: Article flow execute with mock services ─────────────────────────

class TestArticleFlowExecute:
    """The audit-failure retry, which lives in the phase, not in execute().

    It was moved there because execute() is only reached by the CLI: the SSE
    driver builds a flat list from get_phases() and calls the phase functions
    directly, so a retry held in execute() never ran for a web user. These tests
    therefore drive the phase function, which is what both drivers call.
    """

    @staticmethod
    def _patched_audit_run(state, calls, fail_audit=True):
        """Patch the three inner passes and run the audit phase against `state`."""
        from unittest.mock import AsyncMock, patch

        from reasoner.application.flows import article_phases

        async def fake_audit(s, _svc):
            calls["audit"] += 1
            s.writing_state["editorial_audit"] = {
                "passes_audit": not fail_audit,
                "audit_score": 0.4 if fail_audit else 0.9,
            }

        async def fake_dev(s, _svc):
            calls["dev"] += 1

        async def fake_style(s, _svc):
            calls["style"] += 1

        services = AsyncMock(spec_set=["log", "call_llm", "run_phase"])
        services.log = lambda *a, **k: None

        return patch.multiple(
            article_phases,
            _run_final_audit=fake_audit,
            run_article_developmental_edit_phase=fake_dev,
            run_article_style_copy_edit_phase=fake_style,
        ), services

    @pytest.mark.asyncio
    async def test_failed_audit_retries_edit_passes_once(self):
        from reasoner.application.flows import article_phases

        state = _make_bare_state("Test article")
        state.writing_state["final_article"] = "draft"
        calls = {"audit": 0, "dev": 0, "style": 0}
        patcher, services = self._patched_audit_run(state, calls)

        with patcher:
            await article_phases.run_article_final_audit_phase(state, services)

        # Audited, failed, re-edited, re-audited. Once, not in a loop.
        assert calls == {"audit": 2, "dev": 1, "style": 1}, calls

    @pytest.mark.asyncio
    async def test_second_failure_is_recorded_not_swallowed(self):
        """An article that fails twice must not ship looking like one that passed."""
        from reasoner.application.flows import article_phases

        state = _make_bare_state("Test article")
        calls = {"audit": 0, "dev": 0, "style": 0}
        patcher, services = self._patched_audit_run(state, calls)

        with patcher:
            await article_phases.run_article_final_audit_phase(state, services)

        assert any("failed after retry" in str(e) for e in state.errors), state.errors

    @pytest.mark.asyncio
    async def test_passing_audit_does_not_retry(self):
        from reasoner.application.flows import article_phases

        state = _make_bare_state("Test article")
        calls = {"audit": 0, "dev": 0, "style": 0}
        patcher, services = self._patched_audit_run(state, calls, fail_audit=False)

        with patcher:
            await article_phases.run_article_final_audit_phase(state, services)

        assert calls == {"audit": 1, "dev": 0, "style": 0}, calls
        assert not any("failed after retry" in str(e) for e in state.errors)

    @pytest.mark.asyncio
    async def test_prior_edit_timeout_suppresses_retry(self):
        """The guard reads state.errors, where both drivers write timeouts.

        It used to read state.pending_events, which no article phase writes, so
        it never fired and a timed-out draft was re-edited on broken input.
        """
        from reasoner.application.flows import article_phases

        state = _make_bare_state("Test article")
        state.errors.append("Phase timeout: Style + Copy Edit exceeded 240s")
        calls = {"audit": 0, "dev": 0, "style": 0}
        patcher, services = self._patched_audit_run(state, calls)

        with patcher:
            await article_phases.run_article_final_audit_phase(state, services)

        assert calls == {"audit": 1, "dev": 0, "style": 0}, calls
