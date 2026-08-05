"""Tests for reasoner.headless — the in-process integration entry point."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reasoner import headless
from reasoner.application.orchestrator import PreflightDecision
from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.llm.ports import DegradedLLMResponse


def _mock_router() -> MagicMock:
    router = MagicMock()
    router.call = AsyncMock(return_value=("mocked direct answer", {}))
    return router


@pytest.mark.asyncio
async def test_ask_direct_action_returns_answer():
    decision = PreflightDecision(
        action="direct",
        router=_mock_router(),
        effective_preset_name="research-budget",
    )
    with patch.object(
        headless.PipelineOrchestrator, "preflight", new=AsyncMock(return_value=decision)
    ):
        result = await headless.ask("Is X better than Y?", preset="research-budget")

    assert result.action == "direct"
    assert result.answer == "mocked direct answer"
    assert result.state is None
    assert result.search_results is None


@pytest.mark.asyncio
async def test_ask_direct_action_raises_on_degraded_response():
    router = MagicMock()
    router.call = AsyncMock(return_value=(DegradedLLMResponse(error="all providers down"), {}))
    decision = PreflightDecision(action="direct", router=router, effective_preset_name="research-budget")

    with patch.object(
        headless.PipelineOrchestrator, "preflight", new=AsyncMock(return_value=decision)
    ):
        with pytest.raises(Exception, match="all providers down"):
            await headless.ask("Is X better than Y?")


@pytest.mark.asyncio
async def test_ask_web_search_action_returns_results():
    decision = PreflightDecision(
        action="web_search",
        router=_mock_router(),
        effective_preset_name="research-budget",
    )
    fake_results = [{"title": "A", "url": "http://a", "snippet": "..."}]
    fake_client = MagicMock()
    fake_client.search = AsyncMock(return_value=fake_results)

    with patch.object(
        headless.PipelineOrchestrator, "preflight", new=AsyncMock(return_value=decision)
    ), patch(
        "reasoner.infrastructure.search.discovery.get_search_client",
        new=AsyncMock(return_value=(fake_client, None)),
    ):
        result = await headless.ask("latest news on X")

    assert result.action == "web_search"
    assert result.search_results == fake_results
    assert result.state is None


@pytest.mark.asyncio
async def test_ask_pipeline_action_returns_state():
    decision = PreflightDecision(
        action="pipeline",
        router=_mock_router(),
        effective_preset_name="research-budget",
        auto_selected_method="research",
    )
    expected_state = PipelineState(problem="Is X better than Y?")
    fake_pipeline = MagicMock()
    fake_pipeline.run = AsyncMock(return_value=expected_state)

    with patch.object(
        headless.PipelineOrchestrator, "preflight", new=AsyncMock(return_value=decision)
    ), patch("reasoner.pipeline.ReasonerPipeline", return_value=fake_pipeline):
        result = await headless.ask("Is X better than Y?", preset="research-budget")

    assert result.action == "pipeline"
    assert result.state is expected_state
    assert result.auto_selected_method == "research"
    fake_pipeline.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_ask_does_not_close_shared_pools_per_call():
    """Per-call cleanup would tear down the shared httpx pool out from under a
    concurrent call in a long-lived host process — ask() must leave that to
    headless.shutdown() instead (see module docstring)."""
    decision = PreflightDecision(
        action="direct",
        router=_mock_router(),
        effective_preset_name="research-budget",
    )
    with patch.object(
        headless.PipelineOrchestrator, "preflight", new=AsyncMock(return_value=decision)
    ), patch(
        "reasoner.infrastructure.llm.providers.openai_compat.OpenAICompatibleProvider.close_shared_pool",
        new=AsyncMock(),
    ) as mock_close_pool, patch(
        "reasoner.scraper.close_scraper_client", new=AsyncMock()
    ) as mock_close_scraper:
        await headless.ask("Is X better than Y?")

    mock_close_pool.assert_not_awaited()
    mock_close_scraper.assert_not_awaited()


@pytest.mark.asyncio
async def test_ask_propagates_pipeline_exceptions():
    """No swallowing — the host app decides how to surface errors."""
    with patch.object(
        headless.PipelineOrchestrator, "preflight", new=AsyncMock(side_effect=RuntimeError("boom"))
    ):
        with pytest.raises(RuntimeError, match="boom"):
            await headless.ask("Is X better than Y?")


@pytest.mark.asyncio
async def test_shutdown_isolates_pool_close_failure_from_scraper_close():
    """One cleanup step failing must not skip the other."""
    with patch(
        "reasoner.infrastructure.llm.providers.openai_compat.OpenAICompatibleProvider.close_shared_pool",
        new=AsyncMock(side_effect=RuntimeError("pool close failed")),
    ), patch(
        "reasoner.scraper.close_scraper_client", new=AsyncMock()
    ) as mock_close_scraper:
        await headless.shutdown()

    mock_close_scraper.assert_awaited_once()


def test_build_argv_rejects_preset_and_routing_together():
    with pytest.raises(ValueError):
        headless._build_argv("problem", "research-budget", '{"primary": "x"}')


def test_build_argv_translates_flags_and_values():
    argv = headless._build_argv(
        "problem", "research-budget", None, top_k=3, sequential=True, quiet=False
    )
    assert argv == ["--problem", "problem", "--preset", "research-budget", "--top-k", "3", "--sequential"]
