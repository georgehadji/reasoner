"""Quick smoke test for Prism modules outside pytest."""
from __future__ import annotations

import asyncio
import json
import sys
from unittest.mock import AsyncMock

sys.path.insert(0, "src")

from reasoner.application.services.prism_classifier import classify_query, PrismClassification
from reasoner.application.flows.prism_research import run_prism_research_phase
from reasoner.domain.pipeline_state import PipelineState
from reasoner.core.ports.search_port import SearchServicePort


class MockSearchClient(SearchServicePort):
    def __init__(self, results: list[dict] | None = None):
        self._results = results or []
        self.searched_queries: list[str] = []

    async def search(self, query, num_results=10, categories=None, source_type=None, domain=None):
        self.searched_queries.append(query)
        return [{"url": f"https://example.com/{query.replace(' ', '-')}", "title": query, "snippet": f"Result for {query}"}]

    async def close(self):
        pass


async def test_classify_query_parsing():
    mock_services = AsyncMock()
    mock_services.call_llm.return_value = (
        '{"classification": {"skipSearch": false, "personalSearch": true, '
        '"academicSearch": true, "discussionSearch": false, '
        '"showWeatherWidget": false, "showStockWidget": false, '
        '"showCalculationWidget": false}, "standaloneFollowUp": "AI attention mechanisms 2024"}',
        {},
    )
    state = PipelineState(problem="latest research on transformer attention mechanisms")
    result = await classify_query(state.problem, mock_services, state)
    assert isinstance(result, PrismClassification)
    assert result.skip_search is False
    assert result.personal_search is True
    assert result.academic_search is True
    assert result.discussion_search is False
    assert result.standalone_follow_up == "AI attention mechanisms 2024"
    print("test_classify_query_parsing PASSED")


async def test_classify_query_defaults_on_empty_json():
    mock_services = AsyncMock()
    mock_services.call_llm.return_value = ('{"classification": {}}', {})
    state = PipelineState(problem="hello")
    result = await classify_query(state.problem, mock_services, state)
    assert result.skip_search is False
    assert result.academic_search is False
    assert result.standalone_follow_up == "hello"
    print("test_classify_query_defaults_on_empty_json PASSED")


async def test_classify_query_uses_problem_as_fallback():
    mock_services = AsyncMock()
    mock_services.call_llm.return_value = (
        '{"classification": {"skipSearch": true}}',
        {},
    )
    state = PipelineState(problem="weather in Paris")
    result = await classify_query(state.problem, mock_services, state)
    assert result.skip_search is True
    assert result.standalone_follow_up == "weather in Paris"
    print("test_classify_query_uses_problem_as_fallback PASSED")


async def test_prism_research_loop_basic():
    mock_services = AsyncMock()
    mock_services.log = lambda phase, message, state: None
    mock_services.call_llm.side_effect = [
        (
            json.dumps({"action": "webSearch", "queries": ["foo"], "reasoning": "Need info"}),
            {},
        ),
        (
            json.dumps({"action": "done", "reasoning": "Enough sources"}),
            {},
        ),
    ]

    client = MockSearchClient()
    state = PipelineState(problem="test problem")
    await run_prism_research_phase(state, mock_services, client, mode="speed")

    prism = state.method_state.get("prism")
    assert "citations" in prism
    assert len(prism["citations"]) >= 1
    assert prism["citations"][0]["source_type"] == "web"
    assert "iteration_log" in prism
    print("test_prism_research_loop_basic PASSED")


async def test_prism_research_respects_max_iterations():
    mock_services = AsyncMock()
    mock_services.log = lambda phase, message, state: None
    mock_services.call_llm.return_value = (
        json.dumps({"action": "webSearch", "queries": ["q"], "reasoning": "more"}),
        {},
    )

    client = MockSearchClient()
    state = PipelineState(problem="test")
    await run_prism_research_phase(state, mock_services, client, mode="speed")

    assert mock_services.call_llm.call_count == 2
    print("test_prism_research_respects_max_iterations PASSED")


async def test_prism_research_dedupes_by_url():
    mock_services = AsyncMock()
    mock_services.log = lambda phase, message, state: None
    mock_services.call_llm.side_effect = [
        (
            json.dumps({"action": "webSearch", "queries": ["q1"], "reasoning": "r1"}),
            {},
        ),
        (
            json.dumps({"action": "webSearch", "queries": ["q1"], "reasoning": "r2"}),
            {},
        ),
        (
            json.dumps({"action": "done"}),
            {},
        ),
    ]

    client = MockSearchClient()
    state = PipelineState(problem="test")
    await run_prism_research_phase(state, mock_services, client, mode="balanced")

    prism = state.method_state.get("prism")
    assert len(prism["citations"]) == 1
    print("test_prism_research_dedupes_by_url PASSED")


async def test_prism_research_emits_events():
    mock_services = AsyncMock()
    mock_services.log = lambda phase, message, state: None
    mock_services.call_llm.return_value = (
        json.dumps({"action": "done", "reasoning": "Done"}),
        {},
    )

    client = MockSearchClient()
    state = PipelineState(problem="test")
    await run_prism_research_phase(state, mock_services, client, mode="speed")

    events = state.pending_events
    assert any(e.get("type") == "research_step_emitted" for e in events)
    assert any(e.get("type") == "research_citations_ready" for e in events)
    print("test_prism_research_emits_events PASSED")


async def main():
    await test_classify_query_parsing()
    await test_classify_query_defaults_on_empty_json()
    await test_classify_query_uses_problem_as_fallback()
    await test_prism_research_loop_basic()
    await test_prism_research_respects_max_iterations()
    await test_prism_research_dedupes_by_url()
    await test_prism_research_emits_events()
    print("\nAll 7 Prism tests PASSED")


if __name__ == "__main__":
    asyncio.run(main())
