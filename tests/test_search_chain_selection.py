"""Backend selection in ``get_search_client_for_method``.

Two defects this locks down:

1. ``openrouter_web`` returned ``(None, source_type)``. All 14 call sites unpack
   ``client, _ = await ...`` and then call ``client.search(...)``, so any chain
   reaching that entry raised AttributeError. Both "direct" chains *start* with
   it.
2. The ``perplexity`` branch tried Tavily and Brave before Perplexity, inverting
   every chain that declares ``perplexity`` first (multi_perspective, research).
"""

from __future__ import annotations

import pytest

from reasoner.core.constants_limits import SEARCH_METHOD_CHAINS
from reasoner.infrastructure.search import discovery


class _Stub:
    def __init__(self, name: str) -> None:
        self.name = name

    async def search(self, *args, **kwargs):
        return []


@pytest.fixture
def backends(monkeypatch):
    """Stub every backend and make all three providers look configured."""

    async def fake_get_search_client(source_type=None):
        return _Stub("perplexity"), source_type

    monkeypatch.setattr(discovery, "get_search_client", fake_get_search_client)
    monkeypatch.setattr(
        "reasoner.infrastructure.search.tavily_adapter.TavilyAdapter",
        lambda *a, **k: _Stub("tavily"),
    )
    monkeypatch.setattr(
        "reasoner.infrastructure.search.brave_adapter.BraveSearchAdapter",
        lambda *a, **k: _Stub("brave"),
    )

    from reasoner.core.settings import settings

    for attr, value in (
        ("OPENROUTER_API_KEY", "test-key"),
        ("TAVILY_API_KEY", "test-key"),
        ("TAVILY_SEARCH_ENABLED", True),
        ("BRAVE_SEARCH_API_KEY", "test-key"),
        ("BRAVE_SEARCH_ENABLED", True),
    ):
        monkeypatch.setattr(settings, attr, value, raising=False)
    return settings


async def _pick(method: str, tier: str) -> str:
    client, _ = await discovery.get_search_client_for_method(method, tier)
    assert client is not None, f"{method}/{tier} returned None as the search client"
    return client.name


@pytest.mark.asyncio
class TestDeclaredOrderIsHonoured:
    async def test_perplexity_first_chain_picks_perplexity(self, backends):
        # multi_perspective/budget declares ["perplexity", "tavily", "brave"].
        # Previously returned "tavily" because the perplexity branch tried the
        # fallbacks first.
        assert await _pick("multi_perspective", "budget") == "perplexity"

    async def test_research_chains_pick_perplexity(self, backends):
        assert await _pick("research", "budget") == "perplexity"
        assert await _pick("research", "premium") == "perplexity"

    async def test_tavily_first_chain_still_picks_tavily(self, backends):
        # prism/budget declares ["tavily", "brave", "perplexity"].
        assert await _pick("prism", "budget") == "tavily"

    async def test_brave_first_chain_still_picks_brave(self, backends):
        # article/budget declares ["brave", "tavily", "perplexity"].
        assert await _pick("article", "budget") == "brave"

    async def test_brave_llm_maps_to_brave(self, backends):
        # article/premium declares ["brave_llm", "perplexity_deep", "tavily"].
        assert await _pick("article", "premium") == "brave"


@pytest.mark.asyncio
class TestOpenrouterWebIsSkipped:
    async def test_direct_chain_falls_through_instead_of_returning_none(self, backends):
        # direct/budget declares ["openrouter_web", "tavily", "perplexity"].
        assert await _pick("direct", "budget") == "tavily"

    async def test_direct_premium_falls_through_to_brave(self, backends):
        # direct/premium declares ["openrouter_web", "brave_llm", "perplexity"].
        assert await _pick("direct", "premium") == "brave"

    async def test_falls_all_the_way_to_perplexity(self, backends, monkeypatch):
        monkeypatch.setattr(backends, "TAVILY_SEARCH_ENABLED", False, raising=False)
        monkeypatch.setattr(backends, "BRAVE_SEARCH_ENABLED", False, raising=False)
        assert await _pick("direct", "budget") == "perplexity"

    @pytest.mark.parametrize(
        "method,tier",
        [(m, t) for m, tiers in SEARCH_METHOD_CHAINS.items() for t in tiers],
    )
    async def test_no_declared_chain_ever_yields_none(self, backends, method, tier):
        await _pick(method, tier)

    async def test_unknown_method_still_returns_a_client(self, backends):
        assert await _pick("no_such_method", "budget") == "perplexity"
