"""Widget and image-generation failures that used to answer as results.

P5, docs/plans/root-cause-remediation-2026-09-07.md.

- ``_has_yahooquery``/``_has_yfinance`` had lost the import they were meant to
  test, leaving ``try: return True``. Every machine therefore reported both
  libraries present, the "Demo Mode" branch of ``get_stock_data`` became
  unreachable, and a missing dependency surfaced as an ImportError from inside
  the quote lookup instead of the message that names it.
- ``search_web`` returned ``[]`` for a dead backend, which is also exactly what
  a query with no results returns.
- ``_generate_image_guarded`` returned ``str(exc)`` and nothing else. At the
  outermost image-generation boundary that is frequently an empty string or a
  provider's opaque code, with the traceback discarded.
"""

from __future__ import annotations

import importlib.util
import logging

import pytest

from reasoner.infrastructure import widgets_legacy
from reasoner.infrastructure.llm import image_generation


def test_a_missing_finance_library_is_reported_as_missing(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: None)

    assert widgets_legacy._has_yahooquery() is False
    assert widgets_legacy._has_yfinance() is False


def test_get_stock_data_can_still_reach_demo_mode(monkeypatch):
    """The branch the broken stubs made unreachable."""
    monkeypatch.setattr(widgets_legacy, "_has_yahooquery", lambda: False)
    monkeypatch.setattr(widgets_legacy, "_has_yfinance", lambda: False)

    result = widgets_legacy.get_stock_data("AAPL")

    assert result["source"] == "Demo Mode"
    assert "yahooquery" in result["note"]


@pytest.mark.asyncio
async def test_a_dead_search_backend_is_not_an_empty_topic(monkeypatch, caplog):
    from reasoner.infrastructure.search import discovery

    async def _boom():
        raise ConnectionError("no search backend reachable")

    monkeypatch.setattr(discovery, "get_search_client", _boom)

    with caplog.at_level(logging.WARNING):
        results = await widgets_legacy.search_web("anything")

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
