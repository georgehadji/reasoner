"""Widget and image-generation failures that used to answer as results.

P5, docs/plans/root-cause-remediation-2026-09-07.md.

- A missing quote library surfaced as an ImportError from inside the quote
  lookup instead of the message that names it.
- ``search_web`` returned ``[]`` for a dead backend, which is also exactly what
  a query with no results returns.
- ``_generate_image_guarded`` returned ``str(exc)`` and nothing else. At the
  outermost image-generation boundary that is frequently an empty string or a
  provider's opaque code, with the traceback discarded.
"""

from __future__ import annotations

import logging
import sys

import pytest

from reasoner.infrastructure.llm import image_generation
from reasoner.infrastructure.widgets.discover import DiscoverWidget
from reasoner.infrastructure.widgets.stocks import StockWidget


def test_a_missing_finance_library_is_reported_as_missing(monkeypatch):
    """Neither quote library importable: the error names them, not an ImportError."""
    monkeypatch.setitem(sys.modules, "yahooquery", None)
    monkeypatch.setitem(sys.modules, "yfinance", None)

    result = StockWidget()._fetch_stock_data_sync("AAPL")

    assert "yahooquery" in result["error"]


@pytest.mark.asyncio
async def test_a_dead_search_backend_is_not_an_empty_topic(monkeypatch, caplog):
    from reasoner.infrastructure.search import discovery

    async def _boom():
        raise ConnectionError("no search backend reachable")

    monkeypatch.setattr(discovery, "get_search_client", _boom)

    with caplog.at_level(logging.WARNING):
        results = await DiscoverWidget()._search_web("anything")

    assert results == [], "the widget must still render"
    assert any("widgets.search_web" in r.message for r in caplog.records), (
        f"a dead backend rendered as a topic with no news: "
        f"{[r.message for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_a_failed_image_generation_keeps_its_traceback(monkeypatch, caplog):
    async def _boom(*args, **kwargs):
        raise RuntimeError("")  # the empty-message case this exists for

    monkeypatch.setattr(image_generation, "generate_image_with_model", _boom)

    with caplog.at_level(logging.ERROR):
        result = await image_generation._generate_image_guarded("a cat", "some-model", None)

    assert result["success"] is False
    assert any(r.exc_info for r in caplog.records), (
        "the traceback was discarded and the caller got an empty error string"
    )
