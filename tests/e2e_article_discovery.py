
import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel
from reasoner.models import PipelineState, TaskType, PerspectiveType, SolutionCandidate
from reasoner.application.mixins.article_pipeline import ArticlePipelineMixin
from reasoner.application.mixins._protocol import PipelineMixinProtocol

# Setup minimal logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- MOCKS ---

class MockState(PipelineState):
    def __init__(self, problem: str = "Test Topic"):
        super().__init__(problem=problem)
        self.writing_state = {
            "document_type": "article",
            "retrieved_sources": [],
            "claims": [],
            "verifications": [],
            "metrics": {}
        }
        self.phase_models = {}
        self.errors = []
        self.pending_events = []
        self.candidates = []
        self.phase_durations = {}

    def log(self, phase: str, message: str):
        logger.info(f"[{phase}] {message}")

class MockSearchClient:
    async def search(self, query, **kwargs):
        return [
            {
                "url": f"http://example.com/{i}",
                "title": f"Source {i}",
                "published": "2024-01-01",
                "score": 0.9,
                "content": f"Content for {query} - claim {i} is verified."
            } for i in range(1, 4)
        ]

class MockPipeline(ArticlePipelineMixin):
    def __init__(self):
        self.verbose = True
        self.initial_state = None
        self.preset_name = "writing"
        self.domain = None
        self.call_count = 0
        self.mock_llm_responses = {}

    def _log(self, phase: str, message: str, state: Any):
        state.log(phase, message)

    async def _call_llm_cached(self, role: str, system_prompt: str, user_prompt: str, state: Any, **kwargs):
        self.call_count += 1
        if role in self.mock_llm_responses:
            return self.mock_llm_responses[role], {"model": "mock-model"}

        if role == "article_decompose":
            return json.dumps({
                "topic": "Climate crisis",
                "subquestions": [{"id": "Q1", "question": "What is the impact?", "priority": "high"}]
            }), {"model": "mock-model"}

        if role == "article_claim_extract":
            return json.dumps({"claims": [{"id": "C1", "text": "Warming is real", "source_url": "http://example.com/1"}]}), {"model": "mock-model"}

        if role == "article_cove_verify":
            return json.dumps({"verification_questions": ["Is it real?"]}), {"model": "mock-model"}

        if role == "article_cove_answer":
            return json.dumps({"answers": [{"question": "Is it real?", "answer": "Yes", "status": "verified"}]}), {"model": "mock-model"}

        if role == "article_cove_revise":
            return json.dumps({
                "claims": [{"id": "C1", "text": "Warming is real", "source_url": "http://example.com/1", "status": "verified"}],
                "changes_made": ["verified"],
                "remaining_uncertainties": []
            }), {"model": "mock-model"}

        if role == "article_verifier":
            # If no override, return verified
            return json.dumps({
                "claims": [{"claim_id": "C1", "status": "VERIFIED", "supporting_sources": ["http://example.com/1"]}]
            }), {"model": "mock-model"}

        if role == "article_sot_skeleton":
            return json.dumps({"sections": [{"heading": "Introduction", "claim_ids": ["C1"]}]}), {"model": "mock-model"}

        if role == "article_sot_solve":
            return json.dumps({"content": "This is a detailed section about warming. " * 10, "word_count": 100}), {"model": "mock-model"}

        if role == "article_synthesize":
            return json.dumps({
                "title": "Climate Report",
                "abstract": "Summary of warming.",
                "article": "Full text body here.",
                "sections": [{"heading": "Intro", "content": "Intro body."}],
                "gaps_noted": []
            }), {"model": "mock-model"}

        if role == "article_humanize":
            return json.dumps({
                "humanized_article": "This is the humanized article content. " * 20,
                "ai_tells": []
            }), {"model": "mock-model"}

        if role == "article_critic":
            score = self.mock_llm_responses.get("critic_score_override", 9.0)
            return json.dumps({"corrections": [], "overall_score": score, "must_revise": score < 5.0}), {"model": "mock-model"}

        if role == "article_pre_mortem":
            return json.dumps({"failure_narrative": "None", "root_causes": [], "weak_sections": []}), {"model": "mock-model"}

        return "{}", {"model": "mock-model"}

# --- TESTS ---

async def test_article_full_success():
    print("\n>>> RUNNING: test_article_full_success")
    pipeline = MockPipeline()
    state = MockState("Global Warming Trends")
    from unittest.mock import patch
    with patch("reasoner.core.search.get_search_client", return_value=(MockSearchClient(), None)), \
         patch("reasoner.core.search.get_discovery_client", return_value=(MockSearchClient(), None)):
        await pipeline._phase_article_decompose(state)
        await pipeline._phase_article_retrieve(state)
        await pipeline._phase_article_extract_claims(state)
        await pipeline._phase_article_verify(state)
        await pipeline._phase_article_synthesize(state)
        await pipeline._phase_article_pre_mortem(state)
        await pipeline._phase_article_critic(state)
        await pipeline._phase_article_assemble(state)
        await pipeline._phase_article_humanize(state)
    assert "humanized_article" in state.writing_state
    print("SUCCESS: Full Article Pipeline Passed")

async def test_article_low_score_gate():
    print("\n>>> RUNNING: test_article_low_score_gate")
    pipeline = MockPipeline()
    state = MockState("Critical Topic")
    pipeline.mock_llm_responses["critic_score_override"] = 1.0
    from unittest.mock import patch
    with patch("reasoner.core.search.get_search_client", return_value=(MockSearchClient(), None)), \
         patch("reasoner.core.search.get_discovery_client", return_value=(MockSearchClient(), None)):
        await pipeline._phase_article_decompose(state)
        await pipeline._phase_article_retrieve(state)
        await pipeline._phase_article_extract_claims(state)
        await pipeline._phase_article_verify(state)
        await pipeline._phase_article_synthesize(state)
        count_before = pipeline.call_count
        await pipeline._phase_article_critic(state)
        count_after = pipeline.call_count
    assert count_after - count_before >= 2
    print("SUCCESS: Quality Gate verified.")

async def test_article_bare_list_fallback():
    print("\n>>> RUNNING: test_article_bare_list_fallback")
    pipeline = MockPipeline()
    state = MockState("Bare List Topic")
    pipeline.mock_llm_responses["article_claim_extract"] = json.dumps([
        {"id": "C1", "text": "Bare list claim", "source_url": "http://test"}
    ])
    from unittest.mock import patch
    with patch("reasoner.core.search.get_search_client", return_value=(MockSearchClient(), None)), \
         patch("reasoner.core.search.get_discovery_client", return_value=(MockSearchClient(), None)):
        await pipeline._phase_article_decompose(state)
        await pipeline._phase_article_retrieve(state)
        await pipeline._phase_article_extract_claims(state)
    assert len(state.writing_state.get("claims", [])) > 0
    # The revision phase mock might change the text, so we just check it exists
    print(f"DEBUG: Found {len(state.writing_state['claims'])} claims after list fallback.")
    print("SUCCESS: Bare list fallback verified.")

async def test_article_re_retrieval():
    print("\n>>> RUNNING: test_article_re_retrieval")
    pipeline = MockPipeline()
    state = MockState("Re-retrieval Topic")
    pipeline.mock_llm_responses["article_verifier"] = json.dumps({
        "claims": [{"claim_id": "C1", "status": "UNKNOWN", "supporting_sources": []}]
    })
    from unittest.mock import patch
    with patch("reasoner.core.search.get_search_client", return_value=(MockSearchClient(), None)), \
         patch("reasoner.core.search.get_discovery_client", return_value=(MockSearchClient(), None)):
        await pipeline._phase_article_decompose(state)
        await pipeline._phase_article_retrieve(state)
        await pipeline._phase_article_extract_claims(state)
        await pipeline._phase_article_verify(state)
    assert state.writing_state.get("re_retrieval_done") is True
    print("SUCCESS: Re-retrieval verified.")

async def test_article_evidence_gate():
    print("\n>>> RUNNING: test_article_evidence_gate")
    pipeline = MockPipeline()
    state = MockState("Empty Topic")
    class EmptySearchClient:
        async def search(self, *args, **kwargs): return []
    from unittest.mock import patch
    with patch("reasoner.core.search.get_search_client", return_value=(EmptySearchClient(), None)), \
         patch("reasoner.core.search.get_discovery_client", return_value=(EmptySearchClient(), None)):
        await pipeline._phase_article_decompose(state)
        await pipeline._phase_article_retrieve(state)
        await pipeline._phase_article_extract_claims(state)
        await pipeline._phase_article_verify(state)
        await pipeline._phase_article_synthesize(state)
    assert state.writing_state.get("insufficient_evidence") is True
    print("SUCCESS: Evidence Gate verified.")

if __name__ == "__main__":
    asyncio.run(test_article_full_success())
    asyncio.run(test_article_low_score_gate())
    asyncio.run(test_article_bare_list_fallback())
    asyncio.run(test_article_re_retrieval())
    asyncio.run(test_article_evidence_gate())
