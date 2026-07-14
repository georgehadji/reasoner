"""Unit tests for PrismClassifier."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from reasoner.application.services.prism_classifier import classify_query, PrismClassification
from reasoner.domain.pipeline_state import PipelineState


@pytest.mark.asyncio
async def test_classify_query_parsing():
    """Classifier parses JSON response into PrismClassification."""
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
    assert result.show_weather_widget is False
    assert result.show_stock_widget is False
    assert result.show_calculation_widget is False
    assert result.standalone_follow_up == "AI attention mechanisms 2024"


@pytest.mark.asyncio
async def test_classify_query_defaults_on_empty_json():
    """Classifier falls back to defaults when JSON fields are missing."""
    mock_services = AsyncMock()
    mock_services.call_llm.return_value = ('{"classification": {}}', {})
    state = PipelineState(problem="hello")
    result = await classify_query(state.problem, mock_services, state)

    assert result.skip_search is False
    assert result.academic_search is False
    assert result.standalone_follow_up == "hello"


@pytest.mark.asyncio
async def test_classify_query_uses_problem_as_fallback():
    """standalone_follow_up defaults to raw problem when absent."""
    mock_services = AsyncMock()
    mock_services.call_llm.return_value = (
        '{"classification": {"skipSearch": true}}',
        {},
    )
    state = PipelineState(problem="weather in Paris")
    result = await classify_query(state.problem, mock_services, state)

    assert result.skip_search is True
    assert result.standalone_follow_up == "weather in Paris"
