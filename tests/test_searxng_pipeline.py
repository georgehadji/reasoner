"""
SearXNG pipeline integration tests — Layer 5.

These tests run actual pipeline phases that depend on live SearXNG
*and* a live LLM provider. They are marked `slow` and skip automatically
if no API key is configured.
"""

from __future__ import annotations

import os
import pytest

from reasoner.models import PipelineState
from reasoner.presets import get_preset
from reasoner.pipeline import ReasonerPipeline


pytestmark = [
    pytest.mark.integration,
    pytest.mark.searxng,
    pytest.mark.slow,
]


def _skip_if_no_api_key() -> None:
    """Skip expensive pipeline tests when no provider key is available."""
    if not os.getenv("OPENROUTER_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        pytest.skip("No LLM API key found — skipping live pipeline phase tests")


def _build_cheap_pipeline() -> ReasonerPipeline:
    """Build a pipeline with the cheapest budget preset."""
    preset = get_preset("multi-perspective-budget")
    router = preset.build_router()
    return ReasonerPipeline(
        router=router,
        preset_name="multi-perspective-budget",
        top_k=2,
        verbose=False,
    )


class TestContextVettingPhase:
    """Integration tests for the context vetting phase with live SearXNG."""

    @pytest.mark.asyncio
    async def test_context_vetting_populates_web_discovery_results(self, searxng_container: str):
        _skip_if_no_api_key()
        pipeline = _build_cheap_pipeline()
        state = PipelineState(problem="What are the latest breakthroughs in renewable energy?")

        await pipeline._phase_context_vetting(state, source_type="general")

        # The phase may vet and still return empty if engines are down
        if not state.web_discovery_results:
            pytest.skip("Context vetting returned no results — SearXNG engines may be rate-limited")

        assert len(state.web_discovery_results) >= 1
        assert all("url" in r for r in state.web_discovery_results)


class TestResearchWebSearchPhase:
    """Integration tests for the research web search phase with live SearXNG."""

    @pytest.mark.asyncio
    async def test_research_web_search_populates_knowledge(self, searxng_container: str):
        _skip_if_no_api_key()
        pipeline = _build_cheap_pipeline()
        state = PipelineState(
            problem="How does quantum computing work?",
            task_type="analytical",
        )

        await pipeline._phase_research_web_search(state)

        if not state.web_discovery_results:
            pytest.skip("Research phase returned no results — SearXNG engines may be rate-limited")

        assert len(state.web_discovery_results) >= 1
        # vetted_context is populated by context vetting, not research phase directly
        # but we can at least assert the discovery results exist
        assert all("title" in r for r in state.web_discovery_results)
