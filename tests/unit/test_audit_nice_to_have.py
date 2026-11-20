"""Audit nice-to-have findings 14-16: each test fails on the code before its fix."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.llm import spend_tracker

pytestmark = pytest.mark.unit


# ── 14: an upload keeps its charge once a vision call has run ───────────────


def test_only_images_without_force_ocr_get_a_billed_description():
    from reasoner.api.routes.uploads import _is_described

    assert _is_described("photo.PNG", force_ocr=False)
    assert not _is_described("photo.png", force_ocr=True)
    assert not _is_described("notes.txt", force_ocr=False)
    assert not _is_described(None, force_ocr=False)


# ── 15: anonymous runs leave no monthly ledger entry ────────────────────────


@pytest.mark.asyncio
async def test_an_anonymous_run_records_no_monthly_spend(monkeypatch):
    from reasoner.core.settings import settings
    from reasoner.infrastructure.llm.executor import LLMExecutor

    monkeypatch.setattr(settings, "SPEND_CAP_PER_RUN_USD", 0.0, raising=False)
    recorded: list[str] = []

    async def record_shared(subject, cost):
        recorded.append(subject)
        return cost

    monkeypatch.setattr(spend_tracker, "record_shared", record_shared)
    executor = LLMExecutor(router=None, phase_configs={}, token_cache=None, caching_enabled=False)

    anon = PipelineState(problem="x", conversation_id="conv-anon")
    anon.spend_cap_monthly_usd = 1.0
    await executor._enforce_spend_caps(anon, 0.01)

    billed = PipelineState(problem="x", conversation_id="conv-1")
    billed.spend_cap_monthly_usd = 1.0
    billed.billing_subject = "u1"
    await executor._enforce_spend_caps(billed, 0.01)

    assert recorded == ["u1"]


# ── 16: the direct lane is skipped when the call needs web search ───────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra_body, assigned_body",
    [
        ({"plugins": [{"id": "web"}]}, None),
        (None, {"web_search_options": {"search_context_size": "high"}}),
    ],
)
async def test_web_grounded_calls_do_not_fall_back_to_ungrounded_vendors(
    monkeypatch, extra_body, assigned_body
):
    from reasoner.core.exceptions import ProviderUnavailableError
    from reasoner.infrastructure.llm import router

    async def walked(*a, **kw):
        raise AssertionError("the direct lane ran")

    monkeypatch.setattr(router, "_walk_direct_fallback_chain", walked)
    result = await router._try_direct_fallback(
        "research",
        "s",
        "u",
        original_error=ProviderUnavailableError("down"),
        max_tokens=10,
        temperature=0.0,
        extra_body=extra_body,
        assigned=SimpleNamespace(model="sonar", extra_body=assigned_body),
    )
    assert result is None


@pytest.mark.asyncio
async def test_a_plain_call_still_takes_the_direct_lane(monkeypatch):
    from reasoner.core.exceptions import ProviderUnavailableError
    from reasoner.infrastructure.llm import router

    async def walked(*a, **kw):
        return "answer", {}

    monkeypatch.setattr(router, "_walk_direct_fallback_chain", walked)
    result = await router._try_direct_fallback(
        "synthesis",
        "s",
        "u",
        original_error=ProviderUnavailableError("down"),
        max_tokens=10,
        temperature=0.0,
        extra_body={"reasoning": {"effort": "low"}},
    )
    assert result == ("answer", {})
