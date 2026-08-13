"""Tests for decompose query JSON guard."""

from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock

from reasoner.core.search import _decompose_query


@pytest.mark.asyncio
async def test_decompose_malformed_json_graceful():
    """
    If the LLM returns non-JSON, _decompose_query should fall back
    to an empty list instead of crashing.
    """
    # Patch the lazy provider getter so no real LLM is called.
    mock_provider = AsyncMock()
    mock_provider.complete_with_retry = AsyncMock(return_value="not json")
    # _decompose_query lives in the discovery module and resolves the builder from
    # its own namespace; patching the core.search facade left the real provider in
    # place and the test attempted a live API call.
    with patch(
        "reasoner.infrastructure.search.discovery._get_build_provider",
        return_value=lambda _mid: mock_provider,
    ):
        result = await _decompose_query("test query")
        assert result == []
