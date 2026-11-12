"""Run routes hand metered() the whole admission, not a hand-built copy.

/api/run, /api/run-followup and both agent routes built their RunContext by
hand and left out ``run_claim`` and ``quota_slot``. metered() could then not
give either back: a run that failed mid-stream kept its client_run_id (the
documented retry got 409 for an hour) and a run that cost nothing kept its
quota slot. Also: /agent/run/sync has no MeteredSSEResponse, so a failure
before metered() started released nothing at all.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from reasoner.api.run_admission import Admission
from reasoner.api.schemas import FollowupRequest, RunRequest
from reasoner.domain.saas import SubscriptionTier, User

pytestmark = pytest.mark.unit

USER = User(id=UUID("11111111-1111-1111-1111-111111111111"), email="u@example.com")


def _admission(user_id: str | None = None) -> Admission:
    return Admission(
        user_id=user_id, preset="debate-budget", reference_id="r", reserved_credits=7,
        run_claim="claim-1", quota_slot=True,
    )


async def _done(*args, **kwargs):
    yield 'data: {"type":"done"}\n\n'


def _capturing_metered(captured: dict):
    async def fake_metered(stream, ctx, sink, observer):
        captured["ctx"] = ctx
        async for chunk in stream:
            yield chunk

    return fake_metered


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["run", "followup"])
async def test_web_routes_pass_the_claim_and_slot_to_metered(route):
    import reasoner.api as api

    captured: dict = {}
    with (
        patch("reasoner.application.services.run_metering.metered", _capturing_metered(captured)),
        patch("reasoner.api.run_stream_cached", _done),
        patch("reasoner.api.run_followup_stream", _done),
    ):
        if route == "run":
            gen = api._run_stream_with_metrics(
                RunRequest(problem="x", preset="debate-budget"), None, None, None, None,
                adm=_admission(),
            )
        else:
            gen = api._run_followup_stream_with_metrics(
                FollowupRequest(
                    question="x", preset="debate-budget",
                    conversation_id="c1", history=[], previous_synthesis="s",
                ),
                None, None, adm=_admission(),
            )
        async for _ in gen:
            pass

    ctx = captured["ctx"]
    assert (ctx.run_claim, ctx.quota_slot, ctx.reserved_credits) == ("claim-1", True, 7)


@pytest.mark.asyncio
async def test_agent_stream_passes_the_claim_and_slot_to_metered():
    from reasoner.api.routes import agent

    captured: dict = {}
    with (
        patch.object(agent, "metered", _capturing_metered(captured)),
        patch.object(agent, "resolve_request_tier", AsyncMock(return_value=SubscriptionTier.PRO)),
        patch("reasoner.api.streaming.run_stream_cached", _done),
    ):
        async for _ in agent._metered_agent_stream(
            RunRequest(problem="x"), SimpleNamespace(), USER, None, None,
            interface="agent_http", adm=_admission(str(USER.id)),
        ):
            pass

    ctx = captured["ctx"]
    assert (ctx.run_claim, ctx.quota_slot) == ("claim-1", True)


@pytest.mark.asyncio
async def test_sync_route_releases_a_run_that_failed_before_metering():
    from reasoner.api.routes import agent

    adm = _admission(str(USER.id))
    release = AsyncMock()
    with (
        patch.object(agent, "admit_run", AsyncMock(return_value=adm)),
        patch.object(agent, "resolve_request_tier", AsyncMock(side_effect=RuntimeError("tier"))),
        patch.object(agent, "release_unstarted", release),
        pytest.raises(RuntimeError),
    ):
        await agent.agent_run_sync(
            SimpleNamespace(), RunRequest(problem="x"), USER,
            preset_service=None, pipeline_service=None,
        )

    release.assert_awaited_once()
    ctx = release.await_args.args[1]
    assert (ctx.reference_id, ctx.run_claim, ctx.quota_slot) == ("r", "claim-1", True)
    assert not adm.started.is_set()  # so release_unstarted really releases


@pytest.mark.asyncio
async def test_prism_scrape_is_capped():
    from reasoner.application.flows import prism_research

    scrape = AsyncMock(return_value=[])
    with patch("reasoner.scraper.scrape_urls", scrape):
        await prism_research._action_scrape([f"https://e.com/{i}" for i in range(300)])

    assert len(scrape.await_args.args[0]) == prism_research._MAX_SCRAPE_URLS
