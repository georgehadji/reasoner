import pytest
import json
import os
from pathlib import Path
from reasoner.models import PipelineState, PerspectiveType, SolutionCandidate, TaskType
from reasoner.models import load

def test_resume_with_invalid_enum_value(tmp_path):
    """
    BUG-002 Regression: Verify that loading a state file with an invalid 
    PerspectiveType string does not crash the application.
    """
    state_file = tmp_path / "corrupted_state.json"
    
    # Create a state dictionary with an invalid perspective value
    data = {
        "problem": "Test problem",
        "task_type": "analytical",
        "candidates": [
            {
                "perspective": "invalid_perspective_name", # This is the bad value
                "content": "Candidate content",
                "key_insights": ["Insight 1"],
                "model_used": "gpt-4"
            },
            {
                "perspective": "constructive", # This is valid
                "content": "Valid candidate",
                "key_insights": ["Insight 2"],
                "model_used": "gpt-4"
            }
        ],
        "scores": [],
        "top_candidates": []
    }
    
    with open(state_file, "w") as f:
        json.dump(data, f)
    
    # This should NOT raise ValueError
    state = load(state_file)
    
    # Verify that the invalid candidate was skipped but the valid one remains
    assert len(state.candidates) == 1
    assert state.candidates[0].perspective == PerspectiveType.CONSTRUCTIVE
    assert state.candidates[0].content == "Valid candidate"

if __name__ == "__main__":
    # Manual run if needed
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
    pytest.main([__file__])
