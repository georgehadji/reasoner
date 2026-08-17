"""Tests for Brave image/video search and the widgets that consume it.

Covers the SearXNG replacement path: BraveSearchAdapter.search_images /
search_videos and the image/video widgets that call them.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from reasoner.infrastructure.search.brave_adapter import BraveSearchAdapter


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


_IMAGE_PAYLOAD = {
    "results": [
        {
            "title": "A cat",
            "url": "https://example.com/cat-page",
            "source": "example.com",
            "thumbnail": {"src": "https://imgs.search.brave.com/thumb.jpg"},
            "properties": {"url": "https://example.com/cat-full.jpg"},
        }
    ]
}

_VIDEO_PAYLOAD = {
    "results": [
        {
            "title": "A talk",
            "url": "https://youtube.com/watch?v=abc",
            "age": "2 days ago",
            "thumbnail": {"src": "https://imgs.search.brave.com/vid.jpg"},
            "video": {"duration": "12:22", "publisher": "YouTube", "creator": "gameranx"},
            "meta_url": {"netloc": "youtube.com"},
        }
    ]
}


class TestBraveImageSearch:
    async def test_maps_fields_from_brave_schema(self):
        adapter = BraveSearchAdapter(api_key="test-key")
        adapter._client = AsyncMock()
        adapter._client.get = AsyncMock(return_value=_FakeResponse(_IMAGE_PAYLOAD))

        results = await adapter.search_images("cats", num_results=5)

        assert len(results) == 1
        assert results[0] == {
            "title": "A cat",
            "url": "https://example.com/cat-page",
            "img_src": "https://example.com/cat-full.jpg",
            "thumbnail": "https://imgs.search.brave.com/thumb.jpg",
            "source": "example.com",
        }

    async def test_tolerates_bare_string_thumbnail(self):
        adapter = BraveSearchAdapter(api_key="test-key")
        payload = {"results": [{"title": "T", "url": "https://e.com", "thumbnail": "https://t.jpg"}]}
        adapter._client = AsyncMock()
        adapter._client.get = AsyncMock(return_value=_FakeResponse(payload))

        results = await adapter.search_images("q")

        assert results[0]["thumbnail"] == "https://t.jpg"

    async def test_falls_back_to_page_url_without_properties(self):
        adapter = BraveSearchAdapter(api_key="test-key")
        payload = {"results": [{"title": "T", "url": "https://e.com/page"}]}
        adapter._client = AsyncMock()
        adapter._client.get = AsyncMock(return_value=_FakeResponse(payload))

        results = await adapter.search_images("q")

        assert results[0]["img_src"] == "https://e.com/page"

    async def test_returns_empty_without_api_key(self):
        # BraveSearchAdapter.__init__ does `api_key or settings.BRAVE_SEARCH_API_KEY`,
        # so passing "" alone falls back to a real configured key in this dev
        # environment and makes a live API call — patch the settings key too.
        with patch("reasoner.infrastructure.search.brave_adapter.settings.BRAVE_SEARCH_API_KEY", ""):
            adapter = BraveSearchAdapter(api_key="")
            assert await adapter.search_images("q") == []

    async def test_returns_empty_on_http_failure(self):
        adapter = BraveSearchAdapter(api_key="test-key")
        adapter._client = AsyncMock()
        adapter._client.get = AsyncMock(side_effect=RuntimeError("boom"))

        assert await adapter.search_images("q") == []


class TestBraveVideoSearch:
    async def test_maps_fields_from_brave_schema(self):
        adapter = BraveSearchAdapter(api_key="test-key")
        adapter._client = AsyncMock()
        adapter._client.get = AsyncMock(return_value=_FakeResponse(_VIDEO_PAYLOAD))

        results = await adapter.search_videos("talks", num_results=5)

        assert len(results) == 1
        assert results[0] == {
            "title": "A talk",
            "url": "https://youtube.com/watch?v=abc",
            "thumbnail": "https://imgs.search.brave.com/vid.jpg",
            "source": "YouTube",
            "duration": "12:22",
            "published": "2 days ago",
        }

    async def test_falls_back_to_meta_url_netloc_for_source(self):
        adapter = BraveSearchAdapter(api_key="test-key")
        payload = {
            "results": [
                {"title": "T", "url": "https://v.com", "meta_url": {"netloc": "vimeo.com"}}
            ]
        }
        adapter._client = AsyncMock()
        adapter._client.get = AsyncMock(return_value=_FakeResponse(payload))

        results = await adapter.search_videos("q")

        assert results[0]["source"] == "vimeo.com"

    async def test_returns_empty_without_api_key(self):
        with patch("reasoner.infrastructure.search.brave_adapter.settings.BRAVE_SEARCH_API_KEY", ""):
            adapter = BraveSearchAdapter(api_key="")
            assert await adapter.search_videos("q") == []


class TestMediaWidgetsUseBrave:
    async def test_image_widget_returns_brave_results(self):
        from reasoner.infrastructure.widgets.image_search import ImageSearchWidget

        widget = ImageSearchWidget()
        with patch.object(
            BraveSearchAdapter, "search_images", AsyncMock(return_value=[{"title": "x"}])
        ):
            with patch("reasoner.core.settings.settings.BRAVE_SEARCH_API_KEY", "k"), \
                 patch("reasoner.core.settings.settings.BRAVE_SEARCH_ENABLED", True):
                results = await widget._search_images("cats", 10)

        assert results == [{"title": "x"}]

    async def test_image_widget_empty_without_key(self):
        from reasoner.infrastructure.widgets.image_search import ImageSearchWidget

        widget = ImageSearchWidget()
        with patch("reasoner.core.settings.settings.BRAVE_SEARCH_API_KEY", ""):
            assert await widget._search_images("cats", 10) == []

    async def test_video_widget_returns_brave_results(self):
        from reasoner.infrastructure.widgets.video_search import VideoSearchWidget

        widget = VideoSearchWidget()
        with patch.object(
            BraveSearchAdapter, "search_videos", AsyncMock(return_value=[{"title": "v"}])
        ):
            with patch("reasoner.core.settings.settings.BRAVE_SEARCH_API_KEY", "k"), \
                 patch("reasoner.core.settings.settings.BRAVE_SEARCH_ENABLED", True):
                results = await widget._search_videos("talks", 10)

        assert results == [{"title": "v"}]

    async def test_video_widget_empty_without_key(self):
        from reasoner.infrastructure.widgets.video_search import VideoSearchWidget

        widget = VideoSearchWidget()
        with patch("reasoner.core.settings.settings.BRAVE_SEARCH_API_KEY", ""):
            assert await widget._search_videos("talks", 10) == []


class TestSearXNGIsGone:
    """Regression guard: the SearXNG symbols must not come back."""

    def test_discovery_module_exposes_no_searxng_helpers(self):
        import reasoner.infrastructure.search.discovery as discovery

        for name in ("SearXNGAdapter", "DiscoveryClient", "get_searxng_urls",
                     "get_searxng_base_url", "get_discovery_client"):
            assert not hasattr(discovery, name), f"{name} should have been removed"

    def test_settings_has_no_searxng_url(self):
        from reasoner.core.settings import settings

        assert not hasattr(settings, "SEARXNG_URL")
