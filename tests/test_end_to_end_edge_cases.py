import pytest
import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock

# Force local src into path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from reasoner.pipeline import ReasonerPipeline
from reasoner.models import PipelineState
from reasoner.domain.preset_core import PipelinePreset
from reasoner.llm import ProviderRouter

class MockRouter:
    """Mocked router to simulate LLM responses with correct metadata."""
    def __init__(self):
        self.call_count = 0

    async def call(self, role, system_prompt, user_prompt, **kwargs):
        self.call_count += 1
        metadata = {"input_tokens": 100, "output_tokens": 100, "cost_usd": 0.001, "model": "mock-model"}
        
        lower_sys = system_prompt.lower()
        
        # --- UNIVERSAL ---
        if role == "classification" or "classify" in lower_sys:
            return '{"task_type": "research", "language": "English", "rationale": "mocked"}', metadata
        if role in ("decomposition", "article_decompose") or "decompose" in lower_sys:
            return '{"sub_problems": [{"id": "Q1", "question": "mock q1"}], "assumptions": [], "failure_modes": [], "subquestions": []}', metadata
        if role == "context_vetting":
            return '{"next_action": "STOP", "queries": [], "stop": true}', metadata
        if role == "synthesis":
            return '{"core_solution": "Mocked final answer", "critical_insights": [], "action_blueprint": [], "open_questions": [], "meta_audit": {}}', metadata

        # --- ARTICLE / WRITING WORKFLOW ---
        if role == "article_retrieve": # If used directly
            return '{"queries": []}', metadata
        if role == "article_claim_extract":
            return '{"claims": [{"id": "C1", "text": "Test claim"}]}', metadata
        if role == "article_cove_verify":
            return '{"verification_questions": [{"question": "Is it true?", "claim_id": "C1"}]}', metadata
        if role == "article_cove_answer":
            return '{"answers": [{"answer": "Yes", "claim_id": "C1"}]}', metadata
        if role == "article_cove_revise":
            return '{"claims": [{"id": "C1", "text": "Test claim", "status": "verified"}], "changes_made": [], "remaining_uncertainties": []}', metadata
        if role == "article_verifier":
            return '{"claims": [{"claim_id": "C1", "status": "VERIFIED", "supporting_sources": ["http://test.com"]}]}', metadata
        if role == "article_synthesize":
            return '{"title": "Mock Title", "abstract": "Mock Abstract", "sections": [{"heading": "H1", "content": "C1"}], "gaps_noted": []}', metadata
        if role == "article_pre_mortem":
            return '{"root_causes": [], "weak_sections": []}', metadata
        if role == "article_critic":
            return '{"overall_score": 0.9, "must_revise": false, "corrections": []}', metadata
        if role == "article_assemble":
            return '{"article": "Final Mocked Article"}', metadata
        
        return '{}', metadata

@pytest.mark.asyncio
class TestEndToEndEdgeCases:
    
    async def get_pipeline(self, preset_name="basic-budget"):
        router_logic = MockRouter()
        real_router = MagicMock(spec=ProviderRouter)
        real_router.call = AsyncMock(side_effect=router_logic.call)
        
        mock_provider = MagicMock()
        mock_provider.model = "mock-model"
        real_router.get.return_value = mock_provider
        
        pipeline = ReasonerPipeline(router=real_router, preset_name=preset_name)
        # Mock search to avoid real network calls
        pipeline.search_web = AsyncMock(return_value=[{"url": "http://test.com", "title": "Test"}])
        return pipeline, router_logic

    async def test_empty_problem_input(self):
        """Edge Case: The user provides an empty string as a problem."""
        from reasoner.pipeline import ReasonerPipeline
        real_router = MagicMock(spec=ProviderRouter)
        pipeline = ReasonerPipeline(router=real_router, preset_name="basic-budget")
        with pytest.raises(ValueError, match="Problem cannot be empty"):
            await pipeline.run("")

    async def test_research_method_no_search_results(self):
        """Edge Case: Research method finds zero search results."""
        pipeline, router = await self.get_pipeline(preset_name="research-budget")
        pipeline.search_web = AsyncMock(return_value=[])
        
        state = await pipeline.run("Test query")
        
        assert state.preset_name == "research-budget"
        assert state.final_solution.core_solution == "Mocked final answer"

    async def test_article_method_json_truncation_recovery(self):
        """Edge Case: Verifier returns truncated JSON; salvage should work."""
        pipeline, router = await self.get_pipeline(preset_name="writing-budget")
        
        async def truncated_call(role, *args, **kwargs):
            metadata = {"input_tokens": 100, "output_tokens": 100, "cost_usd": 0.0, "model": "m"}
            if role == "article_verifier":
                # Truncated inside the supporting_sources array
                return '{"claims": [{"claim_id": "C1", "status": "VERIFIED", "supporting_sources": ["http://truncated...', metadata
            return await router.call(role, *args, **kwargs)

        pipeline.router.call.side_effect = truncated_call
        
        state = await pipeline.run("Test article")
        
        # If it fails, "Article synthesize: no usable claims" appears in state.errors.
        # We check state.errors and also that final_solution is populated.
        assert not any("Article synthesize: no usable claims" in err for err in state.errors)
        assert state.final_solution.core_solution != ""

    async def test_unknown_task_type_coerces_instead_of_crashing(self):
        """Edge Case: an unrecognised task_type must not break the run.

        TaskType no longer has a "refusal" member and classification is folded into
        the "fusion" phase; content safety is handled by sanitisation and the
        persuasion defence rather than a refusal task type. What still matters here
        is that an unexpected classifier value coerces to a valid TaskType.
        """
        from reasoner.domain.models import TaskType

        pipeline, router = await self.get_pipeline(preset_name="debate-budget")

        async def refusal_call(role, *args, **kwargs):
            metadata = {"input_tokens": 10, "output_tokens": 10, "cost_usd": 0.0, "model": "m"}
            if role == "fusion":
                return '{"task_type": "refusal", "language": "English"}', metadata
            return await router.call(role, *args, **kwargs)

        pipeline.router.call.side_effect = refusal_call
        state = await pipeline.run("Bad prompt")
        assert isinstance(state.task_type, TaskType)

    async def test_language_drift_prevention(self):
        """Edge Case: Guard against forced translation to English."""
        pipeline, _ = await self.get_pipeline()
        # Original is Greek
        is_valid = pipeline._validate_enhancement("Γράψε κάτι", "Write something")
        assert is_valid is False
