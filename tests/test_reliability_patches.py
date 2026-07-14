import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from reasoner.models import PipelineState, PerspectiveType, ClaimLabel
from reasoner.hypergate.hyperagent import HyperGateAgent
from reasoner.gate_agent import GateDecision

# ─────────────────────────────────────────────────────────────────────
# BUG-002: Enum Reconstruction Resilience
# ─────────────────────────────────────────────────────────────────────

def test_pipeline_state_enum_resilience(tmp_path):
    """Verify that malformed or outdated enums in saved state don't crash the load."""
    state_file = tmp_path / "legacy_state.json"
    
    # State containing a mix of valid and 'hallucinated' enum values
    data = {
        "problem": "Test",
        "candidates": [
            {"perspective": "constructive", "content": "valid", "key_insights": [], "model_used": "m1"},
            {"perspective": "hallucinated_perspective", "content": "invalid", "key_insights": [], "model_used": "m1"}
        ],
        "final_solution": {
            "claim_labels": {
                "claim1": "VERIFIED",
                "claim2": "OUTDATED_LABEL_TYPE"
            }
        }
    }
    
    with open(state_file, "w") as f:
        json.dump(data, f)
        
    state = PipelineState.load(state_file)
    
    # 1. Valid candidate preserved
    assert len(state.candidates) == 1
    assert state.candidates[0].perspective == PerspectiveType.CONSTRUCTIVE
    
    # 2. Outdated label defaulted to UNKNOWN instead of crashing
    assert state.final_solution.claim_labels["claim2"] == ClaimLabel.UNKNOWN


# ─────────────────────────────────────────────────────────────────────
# BUG-003: HyperGate Fast-Path Hallucination Fix
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hypergate_creative_technical_routing():
    """Verify that creative frames for technical topics bypass the direct fast-path."""
    router = MagicMock()
    gate = HyperGateAgent(router)
    
    # This prompt used to trigger the creative fast-path (action="direct")
    # and hallucinate technical details without research.
    problem = "Write a poem about the specific vulnerabilities of the NIST SP 800-90A Dual_EC_DRBG."
    
    # Mock _run_phase1 so we don't actually call sub-agents
    mock_ctx = MagicMock()
    # We mock synthesis to return a pipeline decision to prove we reached this stage
    gate._run_phase1 = AsyncMock(return_value=mock_ctx)
    gate._synthesize = MagicMock(return_value=GateDecision(action="pipeline", method="research", confidence=1.0))
    
    decision = await gate.decide(problem)
    
    # If the fast-path was bypassed, we should have called _run_phase1
    gate._run_phase1.assert_called_once()
    assert decision.action == "pipeline"
    assert "creative-writing request" not in (decision.reasoning or "").lower()


# ─────────────────────────────────────────────────────────────────────
# BUG-001: CLI Resource Cleanup
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cli_cleanup_on_exit():
    """Verify that main() ensures resource cleanup via finally block."""
    from reasoner.main import main
    
    args = MagicMock()
    args.list_presets = False
    args.list_models = False
    args.resume = ""
    args.problem = "test"
    args.force_pipeline = True
    args.output = ""
    args.save_state = ""
    
    # Mock the internal logic to prevent real execution
    with patch("reasoner.main.build_router"), \
         patch("reasoner.main.ReasonerPipeline") as mock_pipeline, \
         patch("reasoner.main.render_pipeline_result"), \
         patch("reasoner.main.export_to_json"), \
         patch("reasoner.scraper.close_scraper_client", new_callable=AsyncMock) as mock_close_scraper, \
         patch("reasoner.infrastructure.llm.providers.openai_compat.OpenAICompatibleProvider.close_shared_pool", new_callable=AsyncMock) as mock_close_llm:
        
        # Mock successful pipeline run
        mock_pipeline.return_value.run = AsyncMock(return_value=MagicMock())
        
        await main(args)
        
        # Verify cleanup was called
        mock_close_scraper.assert_called_once()
        mock_close_llm.assert_called_once()

if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
    pytest.main([__file__, "-v"])
