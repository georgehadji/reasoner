"""
SearXNG integration tests — Layer 2 (Health/Schema) and Layer 3 (DiscoveryClient).

These tests require a live SearXNG instance and are marked with `searxng`.
They skip gracefully if engines return zero results (common when engines are rate-limited).
"""

from __future__ import annotations

import pytest
import httpx

_discovery = pytest.importorskip(
    "reasoner.infrastructure.search.discovery",
    reason="reasoner.infrastructure.search.discovery not available in this build",
)
DiscoveryClient = _discovery.DiscoveryClient
get_searxng_base_url = _discovery.get_searxng_base_url


pytestmark = [pytest.mark.integration, pytest.mark.searxng]


def _skip_if_empty(results: list) -> None:
    """Skip test instead of failing when SearXNG engines are flaky."""
    if not results:
        pytest.skip("SearXNG returned zero results — engines may be rate-limited")


def _get_or_skip(url: str, **kwargs) -> httpx.Response:
    """Make a synchronous GET; skip the test on any transport-level failure."""
    try:
        return httpx.get(url, **kwargs)
    except httpx.TransportError as exc:
        pytest.skip(f"SearXNG transport error ({type(exc).__name__}) — skipping health test")


class TestSearXNGHealth:
    """Canary tests that verify the SearXNG container is alive."""

    def test_searxng_health_endpoint(self, searxng_container: str):
        """SearXNG /healthz should return 200."""
        response = _get_or_skip(f"{searxng_container}/healthz", timeout=30)
        assert response.status_code == 200

    def test_searxng_json_search_schema(self, searxng_container: str):
        """A JSON search should return valid schema."""
        response = _get_or_skip(
            f"{searxng_container}/search",
            params={"q": "Python programming", "format": "json"},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert isinstance(data["results"], list)

        for r in data["results"][:3]:
            assert "title" in r
            assert "url" in r
            assert "engine" in r

    def test_searxng_returns_at_least_one_result(self, searxng_container: str):
        """Soft test: if zero results, skip rather than fail."""
        response = _get_or_skip(
            f"{searxng_container}/search",
            params={"q": "artificial intelligence", "format": "json"},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        results = data.get("results", [])
        _skip_if_empty(results)
        assert len(results) >= 1


class TestDiscoveryClientFunctional:
    """DiscoveryClient tests against the live SearXNG instance."""

    @pytest.mark.asyncio
    async def test_discovery_client_search_general(self, searxng_client: DiscoveryClient):
        """General search should return results."""
        results = await searxng_client.search("machine learning", num_results=5)
        _skip_if_empty(results)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_discovery_client_source_type_academic(self, searxng_client: DiscoveryClient):
        """Academic source type should query academic engines."""
        results = await searxng_client.search(
            "neural networks",
            num_results=5,
            source_type="academic",
        )
        _skip_if_empty(results)
        # Best-effort: at least one result should come from an academic engine
        academic_engines = {"arxiv", "google scholar", "crossref", "semantic scholar", "pubmed"}
        engines = {r.get("source", "").lower() for r in results}
        assert any(e in academic_engines for e in engines), f"Expected academic engine, got {engines}"

    @pytest.mark.asyncio
    async def test_discovery_client_source_type_code(self, searxng_client: DiscoveryClient):
        """Code source type should query code engines."""
        results = await searxng_client.search(
            "python asyncio",
            num_results=5,
            source_type="code",
        )
        _skip_if_empty(results)
        code_engines = {"github", "gitlab", "stackoverflow", "npm"}
        engines = {r.get("source", "").lower() for r in results}
        assert any(e in code_engines for e in engines), f"Expected code engine, got {engines}"

    @pytest.mark.asyncio
    async def test_discovery_client_domain_filter(self, searxng_client: DiscoveryClient):
        """Domain filter should restrict results to the given domain."""
        results = await searxng_client.search(
            "Python",
            num_results=5,
            domain="wikipedia.org",
        )
        _skip_if_empty(results)
        for r in results:
            url = r.get("url", "")
            assert "wikipedia.org" in url, f"Expected wikipedia.org in {url}"

    @pytest.mark.asyncio
    async def test_discovery_client_num_results_respected(self, searxng_client: DiscoveryClient):
        """num_results should cap the returned list."""
        results = await searxng_client.search("technology", num_results=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_discovery_client_refined_result_shape(self, searxng_client: DiscoveryClient):
        """Each result must contain the expected keys."""
        results = await searxng_client.search("space exploration", num_results=3)
        _skip_if_empty(results)
        required_keys = {"title", "url", "content", "snippet", "source", "full_content"}
        for r in results:
            assert set(r.keys()) >= required_keys, f"Missing keys in {r.keys()}"

    @pytest.mark.asyncio
    async def test_discovery_client_handles_timeout_gracefully(self):
        """Unreachable host should return [] without raising."""
        client = DiscoveryClient(base_url="http://localhost:59999")
        results = await client.search("anything", num_results=3)
        assert results == []
        await client.close()

    @pytest.mark.asyncio
    async def test_discovery_client_respects_env_url(self, searxng_container: str):
        """When no base_url is passed, get_discovery_client should use SEARXNG_URL."""
        import os
        from reasoner.core.search import get_discovery_client, reset_discovery_client
        reset_discovery_client()
        # Ensure env matches the fixture
        old = os.environ.get("SEARXNG_URL")
        os.environ["SEARXNG_URL"] = searxng_container
        try:
            client, _ = await get_discovery_client()
            assert client.base_url == searxng_container.rstrip("/")
        finally:
            if old is None:
                os.environ.pop("SEARXNG_URL", None)
            else:
                os.environ["SEARXNG_URL"] = old
            reset_discovery_client()
