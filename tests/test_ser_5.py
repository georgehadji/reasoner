"""
Tests for synthesis serialization (api.py _ser_5 function).

Tests the fix for: AttributeError: 'dict' object has no attribute 'action_blueprint'
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock


class MockPipelineState:
    """Mock PipelineState for testing."""
    
    def __init__(self, final_solution=None, phase_tokens=None, method_state=None):
        self.final_solution = final_solution
        self.phase_tokens = phase_tokens or {}
        self.method_state = method_state or {}


class TestSer5DictFormat:
    """Test _ser_5 with dict format (most common case from pipeline.py)."""
    
    def _get_ser_5(self):
        """Import and return the synthesis serializer.

        The synthesis-dict contract (core_solution / action_blueprint / etc.)
        moved out of api._ser_5 into services.serializers._ser_synthesis during
        the serializer refactor; _ser_5 now dispatches method-specific Phase-5
        state. This suite targets synthesis serialization, so it follows.
        """
        from reasoner.application.services.serializers import _ser_synthesis
        return _ser_synthesis
    
    def test_dict_format_complete(self):
        """Test dict with all fields populated."""
        state = MockPipelineState(
            final_solution={
                "core_solution": "Test solution",
                "critical_insights": ["Insight 1", "Insight 2"],
                "action_blueprint": [
                    {"step": 1, "action": "Do X", "time_horizon": "short", "go_criteria": "Done", "fallback": "None"}
                ],
                "open_questions": ["Question 1?"],
                "claim_labels": {"claim1": "VERIFIED"},
                "meta_audit": {"most_dangerous_assumption": "Test", "dominant_bias": "None"},
            },
            phase_tokens={"Phase 8: Synthesis": {"input": 100, "output": 200}}
        )
        
        _ser_5 = self._get_ser_5()
        result = _ser_5(state)
        
        assert result["core_solution"] == "Test solution"
        assert result["critical_insights"] == ["Insight 1", "Insight 2"]
        assert len(result["action_blueprint"]) == 1
        assert result["action_blueprint"][0]["step"] == 1
        assert result["open_questions"] == ["Question 1?"]
        assert result["claim_labels"] == {"claim1": "VERIFIED"}
        assert result["meta_audit"]["most_dangerous_assumption"] == "Test"
        assert result["tokens"] == {"input": 100, "output": 200}
    
    def test_dict_format_empty(self):
        """Test dict with empty fields."""
        state = MockPipelineState(
            final_solution={},
            phase_tokens={}
        )
        
        _ser_5 = self._get_ser_5()
        result = _ser_5(state)
        
        assert result["core_solution"] == ""
        assert result["critical_insights"] == []
        assert result["action_blueprint"] == []
        assert result["open_questions"] == []
        assert result["claim_labels"] == {}
        assert result["meta_audit"] == {}
        assert result["tokens"] == {"input": 0, "output": 0}
    
    def test_dict_format_none_values(self):
        """Test dict with None values (not missing, but explicitly None)."""
        state = MockPipelineState(
            final_solution={
                "core_solution": None,
                "critical_insights": None,
                "action_blueprint": None,
                "open_questions": None,
                "claim_labels": None,
                "meta_audit": None,
            },
            phase_tokens={}
        )
        
        _ser_5 = self._get_ser_5()
        result = _ser_5(state)
        
        # None values should be converted to safe defaults
        assert result["core_solution"] == ""
        assert result["critical_insights"] == []
        assert result["action_blueprint"] == []
        assert result["open_questions"] == []
        assert result["claim_labels"] == {}
        assert result["meta_audit"] == {}
    
    def test_dict_format_missing_keys(self):
        """Test dict with some keys missing."""
        state = MockPipelineState(
            final_solution={"core_solution": "Only solution"},
            phase_tokens={}
        )
        
        _ser_5 = self._get_ser_5()
        result = _ser_5(state)
        
        assert result["core_solution"] == "Only solution"
        assert result["critical_insights"] == []
        assert result["action_blueprint"] == []
        assert result["open_questions"] == []
    
    def test_dict_format_malformed_blueprint(self):
        """Test dict with malformed action_blueprint (not a list)."""
        state = MockPipelineState(
            final_solution={
                "core_solution": "Test",
                "action_blueprint": "not a list",  # Should be list
            },
            phase_tokens={}
        )
        
        _ser_5 = self._get_ser_5()
        result = _ser_5(state)
        
        # Should handle gracefully - returns empty list for non-list
        assert result["core_solution"] == "Test"
        assert result["action_blueprint"] == []


class TestSer5EdgeCases:
    """Edge case tests for _ser_5."""
    
    def _get_ser_5(self):
        from reasoner.application.services.serializers import _ser_synthesis
        return _ser_synthesis
    
    def test_final_solution_none(self):
        """Test when final_solution is None."""
        state = MockPipelineState(final_solution=None)
        
        _ser_5 = self._get_ser_5()
        result = _ser_5(state)
        
        assert result == {}
    
    def test_final_solution_string(self):
        """Test when final_solution is a string (unexpected type)."""
        state = MockPipelineState(final_solution="unexpected string")
        
        _ser_5 = self._get_ser_5()
        result = _ser_5(state)
        
        # Should return safe defaults
        assert result["core_solution"] == ""
        assert result["action_blueprint"] == []
    
    def test_final_solution_list(self):
        """Test when final_solution is a list (unexpected type)."""
        state = MockPipelineState(final_solution=[1, 2, 3])
        
        _ser_5 = self._get_ser_5()
        result = _ser_5(state)
        
        # Should return safe defaults
        assert result["core_solution"] == ""
        assert result["action_blueprint"] == []
    
    def test_final_solution_int(self):
        """Test when final_solution is an int (unexpected type)."""
        state = MockPipelineState(final_solution=42)
        
        _ser_5 = self._get_ser_5()
        result = _ser_5(state)
        
        # Should return safe defaults
        assert result["core_solution"] == ""
        assert result["action_blueprint"] == []
    
    def test_phase_tokens_none(self):
        """Test when phase_tokens is None."""
        state = MockPipelineState(
            final_solution={"core_solution": "Test"},
            phase_tokens=None
        )
        
        _ser_5 = self._get_ser_5()
        result = _ser_5(state)
        
        # Should handle gracefully
        assert result["core_solution"] == "Test"
        assert result["tokens"] == {"input": 0, "output": 0}
    
    def test_unicode_in_solution(self):
        """Test with unicode characters in solution."""
        state = MockPipelineState(
            final_solution={
                "core_solution": "Ελληνική λύση - 中文解决方案 🎉",
                "critical_insights": ["Инсайт 1", "💡"],
            },
            phase_tokens={}
        )
        
        _ser_5 = self._get_ser_5()
        result = _ser_5(state)
        
        assert "Ελληνική" in result["core_solution"]
        assert "中文" in result["core_solution"]
    
    def test_very_long_strings(self):
        """Test with very long strings (boundary test)."""
        long_string = "x" * 100000
        state = MockPipelineState(
            final_solution={
                "core_solution": long_string,
                "critical_insights": [long_string],
            },
            phase_tokens={}
        )
        
        _ser_5 = self._get_ser_5()
        result = _ser_5(state)
        
        assert len(result["core_solution"]) == 100000
        assert len(result["critical_insights"][0]) == 100000


class TestSer5LegacyObjectFormat:
    """Test _ser_5 with legacy FinalSolution object format."""
    
    def _get_ser_5(self):
        from reasoner.application.services.serializers import _ser_synthesis
        return _ser_synthesis
    
    def test_legacy_final_solution_object(self):
        """Test with legacy FinalSolution object (if still used)."""
        # Create a mock FinalSolution-like object
        class MockFinalSolution:
            def __init__(self):
                self.core_solution = "Legacy solution"
                self.critical_insights = ["Legacy insight"]
                self.action_blueprint = [{"step": 1, "action": "Legacy action"}]
                self.open_questions = ["Legacy question?"]
                self.claim_labels = {"c": "VERIFIED"}
                self.meta_audit = type('MetaAudit', (), {
                    "most_dangerous_assumption": "Legacy assumption",
                    "dominant_bias": "Legacy bias",
                    "remaining_uncertainty": "Legacy uncertainty",
                    "assumption_failure_impact": "Legacy impact",
                    "non_obvious_insight": "Legacy insight"
                })()
        
        state = MockPipelineState(final_solution=MockFinalSolution())
        
        _ser_5 = self._get_ser_5()
        result = _ser_5(state)
        
        assert result["core_solution"] == "Legacy solution"
        assert result["action_blueprint"][0]["step"] == 1


class TestIntegrationSmokeTest:
    """Integration smoke tests - verify module integrates correctly."""
    
    def _get_ser_5(self):
        from reasoner.application.services.serializers import _ser_synthesis
        return _ser_synthesis
    
    def test_returns_valid_json_serializable_dict(self):
        """Verify return value is JSON serializable."""
        state = MockPipelineState(
            final_solution={
                "core_solution": "Test",
                "critical_insights": ["a", "b"],
                "action_blueprint": [{"step": 1}],
                "open_questions": ["?"],
                "claim_labels": {"k": "v"},
                "meta_audit": {"k": "v"},
            },
            phase_tokens={"Synthesis": {"input": 1, "output": 2}}
        )
        
        _ser_5 = self._get_ser_5()
        result = _ser_5(state)
        
        # Should not raise when serialized
        import json
        json_str = json.dumps(result)
        assert json_str is not None
    
    def test_all_methods_still_work(self):
        """Verify all methods can call serializer without crashing."""
        methods = ["multi-perspective", "iterative", "debate", "jury", "research", "scientific", "socratic"]
        
        _ser_5 = self._get_ser_5()
        
        for method in methods:
            # Each method has different phase numbers
            phase_tokens_key = f"Phase 5: Synthesis" if method != "iterative" else "Phase 8: Synthesis"
            
            state = MockPipelineState(
                final_solution={"core_solution": f"Test for {method}"},
                phase_tokens={phase_tokens_key: {"input": 100, "output": 200}}
            )
            
            result = _ser_5(state)
            assert result["core_solution"] == f"Test for {method}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])