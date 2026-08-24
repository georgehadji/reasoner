"""Unit tests for PrismResearcher loop."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from reasoner.application.flows.prism_research import run_prism_research_phase
from reasoner.core.ports.search_port import SearchServicePort
from reasoner.domain.pipeline_state import PipelineState


class MockSearchClient(SearchServicePort):
    def __init__(self, results: list[dict] | None = None):
        self._results = results or []
        self.searched_queries: list[str] = []

    async def search(self, query, num_results=10, categories=None, source_type=None, domain=None):
        self.searched_queries.append(query)
        return [{"url": f"https://example.com/{query.replace(' ', '-')}", "title": query, "snippet": f"Result for {query}"}]

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_prism_research_loop_basic():
    """Researcher runs iterations and stores citations in method_state."""
    mock_services = AsyncMock()
    mock_services.log = lambda phase, message, state: None
    # First iteration: search, second: done
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
    assert state.remainder.web_discovery_results == []  # research_phases.py handles backfill


@pytest.mark.asyncio
async def test_prism_research_respects_max_iterations():
    """Loop stops at max_iterations even if LLM never returns done."""
    mock_services = AsyncMock()
    mock_services.log = lambda phase, message, state: None
    mock_services.call_llm.return_value = (
        json.dumps({"action": "webSearch", "queries": ["q"], "reasoning": "more"}),
        {},
    )

    client = MockSearchClient()
    state = PipelineState(problem="test")
    await run_prism_research_phase(state, mock_services, client, mode="speed")

    # speed mode = 2 iterations
    assert mock_services.call_llm.call_count == 2


@pytest.mark.asyncio
async def test_prism_research_dedupes_by_url():
    """Duplicate URLs across iterations are deduplicated."""
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
    # Same query produces same URL, so should be deduped
    assert len(prism["citations"]) == 1


@pytest.mark.asyncio
async def test_prism_research_emits_events():
    """Researcher appends events to state.pending_events."""
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


@pytest.mark.asyncio
async def test_prism_merges_duplicate_url_content():
    """Verify duplicate URLs merge their snippets instead of dropping the second."""
    mock_services = AsyncMock()
    mock_services.log = lambda phase, message, state: None
    mock_services.call_llm.side_effect = [
        (
            json.dumps({"action": "webSearch", "queries": ["query1"], "reasoning": "r1"}),
            {},
        ),
        (
            json.dumps({"action": "webSearch", "queries": ["query1"], "reasoning": "r2"}),
            {},
        ),
        (
            json.dumps({"action": "done"}),
            {},
        ),
    ]

    # Custom search client to return different snippets for the same URL in subsequent queries
    class CustomSearchClient(SearchServicePort):
        def __init__(self):
            self.calls = 0
        async def search(self, query, num_results=10, categories=None, source_type=None, domain=None):
            self.calls += 1
            return [{
                "url": "https://example.com/same-url",
                "title": f"Title {self.calls}",
                "snippet": f"Content fragment {self.calls}"
            }]
        async def close(self):
            pass

    client = CustomSearchClient()
    state = PipelineState(problem="test problem")
    await run_prism_research_phase(state, mock_services, client, mode="balanced")

    prism = state.method_state.get("prism")
    assert len(prism["citations"]) == 1
    snippet = prism["citations"][0]["snippet"]
    assert "Content fragment 1" in snippet
    assert "Content fragment 2" in snippet


@pytest.mark.asyncio
async def test_prism_dedupes_identical_snippet():
    """Verify duplicate URL with identical snippet does not append duplicate fragment."""
    mock_services = AsyncMock()
    mock_services.log = lambda phase, message, state: None
    mock_services.call_llm.side_effect = [
        (
            json.dumps({"action": "webSearch", "queries": ["q"], "reasoning": "r"}),
            {},
        ),
        (
            json.dumps({"action": "webSearch", "queries": ["q"], "reasoning": "r"}),
            {},
        ),
        (
            json.dumps({"action": "done"}),
            {},
        ),
    ]

    class CustomSearchClient(SearchServicePort):
        async def search(self, query, num_results=10, categories=None, source_type=None, domain=None):
            return [{
                "url": "https://example.com/same-url",
                "title": "Title",
                "snippet": "Same static content snippet"
            }]
        async def close(self):
            pass

    client = CustomSearchClient()
    state = PipelineState(problem="test problem")
    await run_prism_research_phase(state, mock_services, client, mode="balanced")

    prism = state.method_state.get("prism")
    assert len(prism["citations"]) == 1
    snippet = prism["citations"][0]["snippet"]
    assert snippet == "Same static content snippet"


@pytest.mark.asyncio
async def test_prism_citations_bm25_sorted():
    """Citations are sorted by BM25 relevance relative to the problem."""
    mock_services = AsyncMock()
    mock_services.log = lambda phase, message, state: None
    mock_services.call_llm.side_effect = [
        (
            json.dumps({"action": "webSearch", "queries": ["q"], "reasoning": "r"}),
            {},
        ),
        (
            json.dumps({"action": "done"}),
            {},
        ),
    ]

    class SearchClient(SearchServicePort):
        async def search(self, query, num_results=10, categories=None, source_type=None, domain=None):
            return [
                {
                    "url": "https://example.com/irrelevant",
                    "title": "unrelated",
                    "snippet": "totally different topic word"
                },
                {
                    "url": "https://example.com/relevant",
                    "title": "quantum computing",
                    "snippet": "something about quantum physics computing and mechanics"
                },
            ]
        async def close(self):
            pass

    client = SearchClient()
    state = PipelineState(problem="quantum computing physics")
    await run_prism_research_phase(state, mock_services, client, mode="balanced")

    prism = state.method_state.get("prism")
    assert len(prism["citations"]) == 2
    # The more relevant one (quantum computing title/snippet) should come first due to BM25 pre-sort
    assert prism["citations"][0]["url"] == "https://example.com/relevant"
    assert prism["citations"][1]["url"] == "https://example.com/irrelevant"


@pytest.mark.asyncio
async def test_prism_rerank_disabled_by_default(monkeypatch):
    """With settings.PRISM_RERANK_ENABLED=False, rerank_documents is not called."""
    mock_services = AsyncMock()
    mock_services.log = lambda phase, message, state: None
    mock_services.call_llm.side_effect = [
        (
            json.dumps({"action": "webSearch", "queries": ["q"], "reasoning": "r"}),
            {},
        ),
        (
            json.dumps({"action": "done"}),
            {},
        ),
    ]

    from reasoner.core.settings import settings
    monkeypatch.setattr(settings, "PRISM_RERANK_ENABLED", False)

    rerank_called = False
    async def mock_rerank(query, documents, top_n):
        nonlocal rerank_called
        rerank_called = True
        return documents

    monkeypatch.setattr("reasoner.core.rerank.rerank_documents", mock_rerank)

    client = MockSearchClient()
    state = PipelineState(problem="test")
    await run_prism_research_phase(state, mock_services, client, mode="balanced")

    assert not rerank_called


@pytest.mark.asyncio
async def test_prism_rerank_graceful_fallback(monkeypatch):
    """When PRISM_RERANK_ENABLED=True but reranker fails, falls back to BM25 sorting."""
    mock_services = AsyncMock()
    mock_services.log = lambda phase, message, state: None
    mock_services.call_llm.side_effect = [
        (
            json.dumps({"action": "webSearch", "queries": ["q"], "reasoning": "r"}),
            {},
        ),
        (
            json.dumps({"action": "done"}),
            {},
        ),
    ]

    from reasoner.core.settings import settings
    monkeypatch.setattr(settings, "PRISM_RERANK_ENABLED", True)

    async def mock_rerank_fail(query, documents, top_n):
        raise RuntimeError("Reranker down")

    monkeypatch.setattr("reasoner.core.rerank.rerank_documents", mock_rerank_fail)

    class SearchClient(SearchServicePort):
        async def search(self, query, num_results=10, categories=None, source_type=None, domain=None):
            return [
                {
                    "url": "https://example.com/irrelevant",
                    "title": "unrelated",
                    "snippet": "totally different topic word"
                },
                {
                    "url": "https://example.com/relevant",
                    "title": "quantum computing",
                    "snippet": "something about quantum physics computing and mechanics"
                },
            ]
        async def close(self):
            pass

    client = SearchClient()
    state = PipelineState(problem="quantum computing physics")
    # This should not raise an exception, and should successfully fall back to the BM25 order
    await run_prism_research_phase(state, mock_services, client, mode="balanced")

    prism = state.method_state.get("prism")
    assert len(prism["citations"]) == 2
    assert prism["citations"][0]["url"] == "https://example.com/relevant"


@pytest.mark.asyncio
async def test_prism_rerank_enabled_success(monkeypatch):
    """When PRISM_RERANK_ENABLED=True and reranker succeeds, uses reranked order."""
    mock_services = AsyncMock()
    mock_services.log = lambda phase, message, state: None
    mock_services.call_llm.side_effect = [
        (
            json.dumps({"action": "webSearch", "queries": ["q"], "reasoning": "r"}),
            {},
        ),
        (
            json.dumps({"action": "done"}),
            {},
        ),
    ]

    from reasoner.core.settings import settings
    monkeypatch.setattr(settings, "PRISM_RERANK_ENABLED", True)

    async def mock_rerank_success(query, documents, top_n):
        # Reverse the incoming list of documents to prove rerank reordering was used
        return list(reversed(documents))

    monkeypatch.setattr("reasoner.core.rerank.rerank_documents", mock_rerank_success)

    class SearchClient(SearchServicePort):
        async def search(self, query, num_results=10, categories=None, source_type=None, domain=None):
            return [
                {
                    "url": "https://example.com/doc1",
                    "title": "computing doc1",
                    "snippet": "some computing stuff"
                },
                {
                    "url": "https://example.com/doc2",
                    "title": "computing doc2",
                    "snippet": "other computing stuff"
                },
            ]
        async def close(self):
            pass

    client = SearchClient()
    state = PipelineState(problem="computing")
    await run_prism_research_phase(state, mock_services, client, mode="balanced")

    prism = state.method_state.get("prism")
    assert len(prism["citations"]) == 2
    # The list is reversed, so doc2 should now be first
    assert prism["citations"][0]["url"] == "https://example.com/doc2"
    assert prism["citations"][1]["url"] == "https://example.com/doc1"


def test_prism_system_prompts_vary_by_mode():
    """Verify that different modes return distinct, customized system prompts."""
    from reasoner.phases._prism import prism_research_system

    speed_prompt = prism_research_system("speed")
    balanced_prompt = prism_research_system("balanced")
    quality_prompt = prism_research_system("quality")

    assert speed_prompt != balanced_prompt
    assert quality_prompt != balanced_prompt

    assert "extremely fast" in speed_prompt
    assert "Tesla" in balanced_prompt
    assert "exhaustive, ultra-thorough" in quality_prompt


def test_research_synthesis_prompt_discipline():
    """Verify that when the preset is 'research', the synthesis prompt enforces report discipline."""
    from reasoner.phases._universal import synthesis_prompt

    state_research = PipelineState(problem="test", preset_name="research-budget")
    prompt_research = synthesis_prompt(state_research)
    assert "RESEARCH METHOD CITATION AND REPORT DISCIPLINE" in prompt_research

    state_standard = PipelineState(problem="test", preset_name="standard-budget")
    prompt_standard = synthesis_prompt(state_standard)
    assert "RESEARCH METHOD CITATION AND REPORT DISCIPLINE" not in prompt_standard
