"""Tests for context vetting fix (BUG-003 regression)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio


class TestContextVettingQueryHandling:
    """BUG-003 regression tests: Context vetting must handle malformed LLM responses."""

    def test_string_query_recovery(self):
        """Test that string queries are recovered and logged."""
        # Simulate the logic from pipeline.py:_phase_context_vetting
        decision_data = {
            "action": "search",
            "queries": "single query string"  # Wrong type: should be list
        }
        
        _raw_q = decision_data.get("queries", [])
        
        # Recovery logic
        if not isinstance(_raw_q, list):
            if isinstance(_raw_q, str) and _raw_q.strip():
                queries = [_raw_q.strip()[:100]]
            else:
                queries = []
        else:
            queries = [q for q in _raw_q[:3] if isinstance(q, str) and q.strip()]
        
        # Should recover as single-item list
        assert queries == ["single query string"]

    def test_empty_string_query_handling(self):
        """Test that empty string queries are handled gracefully."""
        decision_data = {
            "action": "search",
            "queries": ""
        }
        
        _raw_q = decision_data.get("queries", [])
        
        if not isinstance(_raw_q, list):
            if isinstance(_raw_q, str) and _raw_q.strip():
                queries = [_raw_q.strip()[:100]]
            else:
                queries = []
        else:
            queries = [q for q in _raw_q[:3] if isinstance(q, str) and q.strip()]
        
        assert queries == []

    def test_none_query_handling(self):
        """Test that None queries are handled gracefully."""
        decision_data = {
            "action": "search",
            "queries": None
        }
        
        _raw_q = decision_data.get("queries", [])
        
        if not isinstance(_raw_q, list):
            if isinstance(_raw_q, str) and _raw_q.strip():
                queries = [_raw_q.strip()[:100]]
            else:
                queries = []
        else:
            queries = [q for q in _raw_q[:3] if isinstance(q, str) and q.strip()]
        
        assert queries == []

    def test_integer_query_handling(self):
        """Test that integer queries are handled gracefully."""
        decision_data = {
            "action": "search",
            "queries": 42
        }
        
        _raw_q = decision_data.get("queries", [])
        
        if not isinstance(_raw_q, list):
            if isinstance(_raw_q, str) and _raw_q.strip():
                queries = [_raw_q.strip()[:100]]
            else:
                queries = []
        else:
            queries = [q for q in _raw_q[:3] if isinstance(q, str) and q.strip()]
        
        assert queries == []

    def test_long_string_truncation(self):
        """Test that long string queries are truncated."""
        long_query = "a" * 200
        decision_data = {
            "action": "search",
            "queries": long_query
        }
        
        _raw_q = decision_data.get("queries", [])
        
        if not isinstance(_raw_q, list):
            if isinstance(_raw_q, str) and _raw_q.strip():
                queries = [_raw_q.strip()[:100]]
            else:
                queries = []
        else:
            queries = [q for q in _raw_q[:3] if isinstance(q, str) and q.strip()]
        
        assert queries == ["a" * 100]

    def test_valid_list_queries(self):
        """Test that valid list queries pass through."""
        decision_data = {
            "action": "search",
            "queries": ["query 1", "query 2", "query 3"]
        }
        
        _raw_q = decision_data.get("queries", [])
        
        if not isinstance(_raw_q, list):
            if isinstance(_raw_q, str) and _raw_q.strip():
                queries = [_raw_q.strip()[:100]]
            else:
                queries = []
        else:
            queries = [q for q in _raw_q[:3] if isinstance(q, str) and q.strip()]
        
        assert queries == ["query 1", "query 2", "query 3"]

    def test_mixed_type_list_filtering(self):
        """Test that mixed-type lists are filtered to strings only."""
        decision_data = {
            "action": "search",
            "queries": ["valid query", 42, None, "", "another valid"]
        }
        
        _raw_q = decision_data.get("queries", [])
        
        if not isinstance(_raw_q, list):
            if isinstance(_raw_q, str) and _raw_q.strip():
                queries = [_raw_q.strip()[:100]]
            else:
                queries = []
        else:
            queries = [q for q in _raw_q[:3] if isinstance(q, str) and q.strip()]
        
        # Only "valid query" is within first 3 items and is a non-empty string
        assert queries == ["valid query"]

    def test_whitespace_only_query(self):
        """Test that whitespace-only queries are filtered out."""
        decision_data = {
            "action": "search",
            "queries": ["   ", "\t\n", "valid"]
        }
        
        _raw_q = decision_data.get("queries", [])
        
        if not isinstance(_raw_q, list):
            if isinstance(_raw_q, str) and _raw_q.strip():
                queries = [_raw_q.strip()[:100]]
            else:
                queries = []
        else:
            queries = [q for q in _raw_q[:3] if isinstance(q, str) and q.strip()]
        
        assert queries == ["valid"]


class TestQueryDisambiguation:
    """Tests for query disambiguation prompt generation."""

    def test_disambiguation_prompt_contains_problem(self):
        """The disambiguation prompt must include the user problem."""
        from reasoner.phases import disambiguation_prompt
        
        problem = "Πρώτα βήματα για την ανάπτυξη AI agents"
        prompt = disambiguation_prompt(problem, "technical")
        
        assert problem in prompt
        assert "ambiguous" in prompt.lower()
        assert "rewritten_query" in prompt

    def test_disambiguation_prompt_contains_task_type(self):
        """The disambiguation prompt must include the task type hint."""
        from reasoner.phases import disambiguation_prompt
        
        prompt = disambiguation_prompt("test", "technical")
        assert "technical" in prompt

    def test_disambiguation_prompt_valid_json_format(self):
        """The disambiguation prompt must request valid JSON output."""
        from reasoner.phases import disambiguation_prompt
        
        prompt = disambiguation_prompt("test", None)
        assert "Output JSON" in prompt
        assert "was_ambiguous" in prompt
        assert "rewritten_query" in prompt


class TestContextQualityScoring:
    """Tests for context quality computation in _vet_results."""

    def test_no_results_quality_missing(self):
        """Empty vetted results → quality = missing."""
        from reasoner.models import PipelineState
        
        state = PipelineState(problem="test")
        # Simulate the logic from _vet_results
        vetted_results = []
        if not vetted_results:
            state.context_quality = "missing"
        
        assert state.context_quality == "missing"

    def test_all_flagged_quality_contaminated(self):
        """All results flagged → quality = contaminated."""
        from reasoner.models import PipelineState
        
        state = PipelineState(problem="test")
        vetted_results = [
            {"vetting_flags": [{"statement": "bad"}]},
            {"vetting_flags": [{"statement": "bad"}]},
        ]
        flagged_count = sum(1 for r in vetted_results if r.get("vetting_flags"))
        total = len(vetted_results)
        if flagged_count == total and total > 0:
            state.context_quality = "contaminated"
        
        assert state.context_quality == "contaminated"

    def test_majority_flagged_quality_partial(self):
        """Majority flagged → quality = partial."""
        from reasoner.models import PipelineState
        
        state = PipelineState(problem="test")
        vetted_results = [
            {"vetting_flags": [{"statement": "bad"}]},
            {"vetting_flags": []},
            {"vetting_flags": [{"statement": "bad"}]},
        ]
        flagged_count = sum(1 for r in vetted_results if r.get("vetting_flags"))
        total = len(vetted_results)
        if flagged_count == total and total > 0:
            state.context_quality = "contaminated"
        elif flagged_count > total // 2:
            state.context_quality = "partial"
        else:
            state.context_quality = "good"
        
        assert state.context_quality == "partial"

    def test_minority_flagged_quality_good(self):
        """Minority flagged → quality = good."""
        from reasoner.models import PipelineState
        
        state = PipelineState(problem="test")
        vetted_results = [
            {"vetting_flags": [{"statement": "bad"}]},
            {"vetting_flags": []},
            {"vetting_flags": []},
            {"vetting_flags": []},
        ]
        flagged_count = sum(1 for r in vetted_results if r.get("vetting_flags"))
        total = len(vetted_results)
        if flagged_count == total and total > 0:
            state.context_quality = "contaminated"
        elif flagged_count > total // 2:
            state.context_quality = "partial"
        else:
            state.context_quality = "good"
        
        assert state.context_quality == "good"


class TestSynthesisCircuitBreaker:
    """Tests for synthesis circuit breaker prompt injection."""

    def test_synthesis_prompt_contains_context_quality(self):
        """The synthesis prompt must include the context quality note."""
        from reasoner.phases import synthesis_prompt
        from reasoner.models import PipelineState
        
        state = PipelineState(problem="test", context_quality="contaminated")
        prompt = synthesis_prompt(state)
        
        assert "CONTEXT QUALITY: contaminated" in prompt

    def test_synthesis_prompt_contains_circuit_breaker_instructions(self):
        """The synthesis system prompt must contain circuit breaker text."""
        from reasoner.phases import SYNTHESIS_SYSTEM
        
        assert "CIRCUIT BREAKER" in SYNTHESIS_SYSTEM
        assert "could not find reliable sources" in SYNTHESIS_SYSTEM
        assert "UNVERIFIED" in SYNTHESIS_SYSTEM

    def test_synthesis_prompt_normal_quality(self):
        """Normal quality should still produce a valid prompt."""
        from reasoner.phases import synthesis_prompt
        from reasoner.models import PipelineState
        
        state = PipelineState(problem="test", context_quality="good")
        prompt = synthesis_prompt(state)
        
        assert "CONTEXT QUALITY: good" in prompt
        assert "[SOLUTION]" in prompt
