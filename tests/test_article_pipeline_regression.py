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
from reasoner.parsing import extract_json, ParseError, _sanitize_json_escapes


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


# ── Phase 3: Prompt builders — structural tests ─────────────────────────────

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
        assert isinstance(normal, str)
        assert isinstance(sonar, str)

    def test_final_audit_prompt_has_audit_instructions(self):
        from reasoner.phases.article import article_final_audit_prompt
        state = self._make_test_state()
        prompt = article_final_audit_prompt(state)
        assert "audit_score" in prompt or "passes_audit" in prompt


# ── Phase 4: extract_json type safety ──────────────────────────────────────

class TestExtractJsonSafety:
    """extract_json must handle edge cases safely."""

    def test_extract_json_handles_arrays(self):
        """extract_json wraps JSON arrays in a {'results': [...]} dict."""
        result = extract_json('["just", "an", "array"]')
        assert isinstance(result, dict)
        assert "results" in result
        assert result["results"] == ["just", "an", "array"]

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

    def test_sanitize_json_escapes_hex_and_null(self):
        assert _sanitize_json_escapes(r'"value": "\x41\x42"') == r'"value": "\u0041\u0042"'
        assert _sanitize_json_escapes(r'"value": "hello\0world"') == r'"value": "helloworld"'
        # Non-escaped content passes through unchanged
        assert _sanitize_json_escapes(r"it's a test") == r"it's a test"

    def test_extract_json_fences_variants(self):
        """extract_json handles various fence styles."""
        # Direct JSON (no fences)
        result = extract_json('{"key": "value"}')
        assert result == {"key": "value"}, f"Direct JSON: {result}"

        # JSON wrapped in triple-backtick fences (actual newlines)
        result = extract_json('```json\n{"key": "value"}\n```')
        assert result == {"key": "value"}, f"Fence json: {result}"

        # Plain triple-backtick fences
        result = extract_json('```\n{"key": "value"}\n```')
        assert result == {"key": "value"}, f"Fence plain: {result}"
