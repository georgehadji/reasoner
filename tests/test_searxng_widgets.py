"""
SearXNG widget integration tests — Layer 4.

These tests run the actual widgets against a live SearXNG instance.
They skip gracefully when engines are temporarily unavailable.
"""

from __future__ import annotations

import pytest

from reasoner.infrastructure.widgets.discover import DiscoverWidget
from reasoner.infrastructure.widgets.image_search import ImageSearchWidget
from reasoner.infrastructure.widgets.video_search import VideoSearchWidget


pytestmark = [pytest.mark.integration, pytest.mark.searxng]


def _skip_if_demo_mode(data: dict) -> None:
    """Widgets fall back to demo mode when SearXNG is empty; skip instead of failing."""
    results = data.get("results", [])
    if not results:
        pytest.skip("Widget returned empty results — SearXNG engines may be rate-limited")
    # Discover widget explicitly labels demo mode
    if any("Demo Mode" in str(r.get("title", "")) for r in results):
        pytest.skip("Widget is in demo mode — SearXNG engines may be rate-limited")


class TestDiscoverWidget:
    """Integration tests for DiscoverWidget with live SearXNG."""

    @pytest.mark.asyncio
    async def test_discover_widget_returns_results(self):
        widget = DiscoverWidget()
        result = await widget.execute({"topic": "tech"})
        assert result.success is True
        _skip_if_demo_mode(result.data)
        assert len(result.data.get("results", [])) >= 1
        assert result.data.get("topic") == "tech"


class TestImageSearchWidget:
    """Integration tests for ImageSearchWidget with live SearXNG."""

    @pytest.mark.asyncio
    async def test_image_search_widget_returns_results(self):
        widget = ImageSearchWidget()
        result = await widget.execute({"query": "mountains", "limit": 3})
        assert result.success is True
        _skip_if_demo_mode(result.data)
        results = result.data.get("results", [])
        assert len(results) <= 3
        if results:
            assert "url" in results[0] or "img_src" in results[0]


class TestVideoSearchWidget:
    """Integration tests for VideoSearchWidget with live SearXNG."""

    @pytest.mark.asyncio
    async def test_video_search_widget_returns_results(self):
        widget = VideoSearchWidget()
        result = await widget.execute({"query": "python tutorial", "limit": 3})
        assert result.success is True
        _skip_if_demo_mode(result.data)
        results = result.data.get("results", [])
        assert len(results) <= 3
        if results:
            assert "url" in results[0]
