"""Tests for decompose query JSON guard."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from reasoner.core.search import _decompose_query


@pytest.mark.asyncio
async def test_decompose_malformed_json_graceful():
    """
    If the LLM returns non-JSON, _decompose_query should fall back
    to an empty list instead of crashing.
    """
    # Patch the lazy provider getter so no real LLM is called.
    #
    # _decompose_query's real implementation lives in
    # reasoner.infrastructure.search.discovery (core.search re-exports it
    # lazily via __getattr__ for import convenience only). discovery.py keeps
    # its own independent _get_build_provider()/_build_provider cache rather
    # than reusing core.search's DI-injected one -- core.search's version is
    # set by api/__init__.py at FastAPI bootstrap but is never read by
    # discovery.py (and CLI entry points main.py/headless.py never call
    # set_build_provider() at all), so patching core.search's copy is a
    # no-op here: the function's __globals__ are discovery.py's, not
    # core.search's, regardless of which module name it was imported under.
    mock_provider = AsyncMock()
    mock_provider.complete_with_retry = AsyncMock(return_value="not json")
    with patch(
        "reasoner.infrastructure.search.discovery._get_build_provider",
        return_value=lambda _mid: mock_provider,
    ):
        result = await _decompose_query("test query")
        assert result == []
