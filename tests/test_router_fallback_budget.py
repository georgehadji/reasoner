"""PRV-3: a fallback must not cost an order of magnitude more than the model it replaces.

A role with no explicit fallback retried on the preset primary with no price
check. `tot-premium`'s `tot_evaluate` runs on qwen3.5-9b and fell back to
claude-sonnet: 48 times the price, on a call chosen to be cheap.
"""

from __future__ import annotations

import pytest

from reasoner.domain.pricing import (
    FALLBACK_MAX_PRICE_RATIO,
    ModelPricing,
    blended_usd_per_mtok,
    fallback_within_budget,
)
from reasoner.infrastructure.llm.router import ProviderRouter

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("assigned", "candidate", "ok"),
    [
        (1.0, 1.0, True),
        (1.0, 10.0, True),  # exactly at the ratio
        (1.0, 10.01, False),
        (10.0, 0.5, True),  # a cheaper fallback is always fine
        (0.0, 3.0, True),  # a free model: the floor, not infinity, is the base
        (0.0, 50.0, False),
    ],
)
def test_fallback_within_budget_table(assigned: float, candidate: float, ok: bool) -> None:
    assert fallback_within_budget(assigned, candidate, ratio=FALLBACK_MAX_PRICE_RATIO) is ok


def test_blended_price_is_per_million_tokens() -> None:
    assert blended_usd_per_mtok(ModelPricing(1.0e-6, 3.0e-6)) == pytest.approx(4.0)


class _Provider:
    def __init__(self, model: str) -> None:
        self.model = model
        self.extra_body: dict = {}


def _router(
    assigned: str, primary: str, explicit: str | None = None
) -> tuple[ProviderRouter, _Provider]:
    cheap = _Provider(assigned)
    router = ProviderRouter(
        primary=_Provider(primary),
        routing_table={"tot_evaluate": cheap},
        fallback_table={"tot_evaluate": _Provider(explicit)} if explicit else None,
    )
    return router, cheap


def test_cheap_role_is_not_retried_on_a_48x_primary() -> None:
    router, cheap = _router("qwen3.5-9b", "claude-sonnet")

    assert router._resolve_fallback("tot_evaluate", cheap) is None


def test_comparable_primary_is_still_the_fallback() -> None:
    router, cheap = _router("claude-haiku", "claude-sonnet")

    fallback = router._resolve_fallback("tot_evaluate", cheap)

    assert fallback is not None and fallback.model == "claude-sonnet"


def test_an_explicit_fallback_is_checked_too() -> None:
    router, cheap = _router("qwen3.5-9b", "claude-haiku", explicit="claude-sonnet")

    # The explicit candidate is over budget, so the router moves on to the
    # primary; claude-haiku is still over 10x of qwen3.5-9b, so nothing is left.
    assert router._resolve_fallback("tot_evaluate", cheap) is None


async def test_direct_fallback_chain_is_bounded(monkeypatch) -> None:
    """Eight sequential vendors must share one budget, not eight."""
    import asyncio

    from reasoner.infrastructure.llm import router as router_mod

    class _Settings:
        MULTI_PROVIDER_FALLBACK_ENABLED = True

    class _Hung:
        model = "hung"

        async def complete(self, **kwargs):
            await asyncio.sleep(5.0)

    monkeypatch.setattr("reasoner.core.settings.settings", _Settings())
    monkeypatch.setattr(
        "reasoner.infrastructure.llm.providers.direct.build_fallback_provider", lambda name: _Hung()
    )
    monkeypatch.setattr(router_mod, "DIRECT_FALLBACK_BUDGET_S", 0.1)

    result = await router_mod._try_direct_fallback(
        "role", "s", "u", original_error=RuntimeError("x"), max_tokens=10, temperature=0.0
    )

    assert result is None
