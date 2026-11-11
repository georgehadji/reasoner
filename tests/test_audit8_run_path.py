"""Audit 8 run-path and metering findings, one test each."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reasoner.application.services import run_metering
from reasoner.application.services.anonymous_trial_policy import AnonymousTrialCharge
from reasoner.application.services.run_metering import RunContext, metered, track_run_spend

pytestmark = pytest.mark.unit


class Sink:
    def __init__(self) -> None:
        self.true_ups: list[dict] = []
        self.slot_releases = 0

    async def true_up(self, **kw) -> None:
        self.true_ups.append(kw)

    async def settle(self, **kw) -> None:
        self.true_ups.append(kw)

    async def record_unsettled(self, **kw) -> None: ...

    async def release_quota_slot(self, *, user_id: str) -> None:
        self.slot_releases += 1


def _frame(**event) -> str:
    return "data: " + json.dumps(event)


async def _drain(gen) -> None:
    async for _ in gen:
        pass


@pytest.fixture
def released(monkeypatch):
    calls: list[str | None] = []

    async def fake(claim):
        calls.append(claim)

    monkeypatch.setattr("reasoner.application.services.idempotency.release_run", fake)
    return calls


def _store(monkeypatch, state):
    store = SimpleNamespace(get_aggregate_state=AsyncMock(return_value=state))
    monkeypatch.setattr(
        "reasoner.infrastructure.persistence.event_store.get_event_store", lambda: store
    )


# 1. resume numbers its events after the aggregate's existing ones
async def test_stream_continues_event_version(monkeypatch):
    from reasoner.api.execution.sse_observer import RunStream

    _store(monkeypatch, {"version": 7})
    stream = RunStream("p1", AsyncMock(), lambda _p: None)
    await stream.continue_history()
    assert stream.event_version == 8


async def test_stream_keeps_version_one_for_new_aggregate(monkeypatch):
    from reasoner.api.execution.sse_observer import RunStream

    _store(monkeypatch, None)
    stream = RunStream("p1", AsyncMock(), lambda _p: None)
    await stream.continue_history()
    assert stream.event_version == 1


# 2. a second concurrent resume of one pipeline is refused
async def test_second_exclusive_claim_is_refused(monkeypatch):
    from fastapi import HTTPException

    from reasoner.api import idempotency_http, run_admission
    from reasoner.application.services.idempotency import RunAlreadyInProgressError

    async def taken(client_run_id, *, owner_key):
        raise RunAlreadyInProgressError(client_run_id)

    monkeypatch.setattr(idempotency_http, "register_run", taken)
    monkeypatch.setattr(
        "reasoner.api.dependencies.check_preset_access_if_authenticated", AsyncMock()
    )
    request = MagicMock()
    request.state = SimpleNamespace()
    user = SimpleNamespace(id="u1", scopes=None)
    with pytest.raises(HTTPException) as exc:
        await run_admission.admit_run(
            request, user=user, problem="x", preset="auto-budget", exclusive="resume:p1",
        )
    assert exc.value.status_code == 409


# 3. a failed run gives its idempotency claim back
async def test_failed_done_frame_releases_claim(released):
    async def stream():
        yield _frame(type="done", errors=["boom"])

    ctx = RunContext(preset="p", reference_id="r", run_claim="claim")
    await _drain(metered(stream(), ctx, Sink()))
    assert released == ["claim"]


async def test_successful_done_frame_keeps_claim(released):
    async def stream():
        yield _frame(type="done", errors=[], total_cost_usd=0.01)

    ctx = RunContext(preset="p", reference_id="r", run_claim="claim")
    await _drain(metered(stream(), ctx, Sink()))
    assert released == []


# 4b. a free run gives back the anonymous trial credits
async def test_free_run_refunds_anonymous_charge(monkeypatch):
    refunded = []

    async def fake_refund(charge):
        refunded.append(charge)

    monkeypatch.setattr(run_metering, "refund_anonymous_trial", fake_refund)
    charge = AnonymousTrialCharge(key="k", credits=3)

    async def stream():
        yield _frame(type="done", errors=[], cached=True)

    ctx = RunContext(preset="p", reference_id="r", anon_charge=charge)
    await _drain(metered(stream(), ctx, Sink()))
    assert refunded == [charge]


# 5. a run cut off mid-phase is billed what its state spent
async def test_recorded_spend_is_billed_without_cost_frame():
    sink = Sink()

    class _State:
        total_cost_usd = 0.0

    state = _State()

    async def stream():
        # Like streaming.py: the run task is spawned inside the stream, so it
        # sees the wrapper's context, and it is cancelled but never awaited.
        async def run():
            track_run_spend(lambda: state.total_cost_usd)
            state.total_cost_usd = 0.05
            await asyncio.Event().wait()

        task = asyncio.create_task(run())
        await asyncio.sleep(0)
        yield _frame(type="phase_start", phase=1)
        task.cancel()
        raise asyncio.CancelledError

    ctx = RunContext(preset="p", reference_id="r", user_id="u", reserved_credits=10)
    with pytest.raises(asyncio.CancelledError):
        await _drain(metered(stream(), ctx, sink))
    assert sink.true_ups and sink.true_ups[0]["cost_usd"] == pytest.approx(0.05)


# 7. a settle timeout releases the quota slot once
async def test_settle_timeout_releases_slot_once(monkeypatch):
    sink = Sink()

    async def slow(**_k):
        await asyncio.sleep(10)

    sink.true_up = slow  # type: ignore[assignment]
    monkeypatch.setattr(run_metering, "SETTLE_TIMEOUT_SECONDS", 0.05)

    async def stream():
        yield _frame(type="done", errors=[])

    ctx = RunContext(
        preset="p", reference_id="r", user_id="u", reserved_credits=10, quota_slot=True
    )
    await _drain(metered(stream(), ctx, sink))
    assert sink.slot_releases == 1


# 4a. an anonymous caller is refused a locked preset before the cap is charged
async def test_anonymous_premium_preset_refused_before_cap(monkeypatch):
    from fastapi import HTTPException

    from reasoner.api import run_admission
    from reasoner.application.services.spend_limit_service import required_tier_for
    from reasoner.domain.saas import SubscriptionTier
    from reasoner.presets import PRESETS

    cap = AsyncMock()
    monkeypatch.setattr(run_admission, "enforce_anonymous_trial_cap", cap)
    request = MagicMock()
    request.state = SimpleNamespace()
    monkeypatch.setattr(run_admission.settings, "ENABLE_LEGACY_API_KEY", True)
    monkeypatch.setattr(
        "reasoner.application.services.estimate_service.estimate_cost",
        AsyncMock(return_value={"estimated_cost_usd": 0.2}),
    )
    premium = next(n for n in PRESETS if required_tier_for(n) != SubscriptionTier.FREE)
    with pytest.raises(HTTPException) as exc:
        await run_admission.admit_run(request, user=None, problem="x", preset=premium)
    assert exc.value.status_code == 403
    cap.assert_not_called()


# 6. a run-fatal error on a non-critical phase stops the run
async def test_run_fatal_noncritical_phase_stops_run():
    from reasoner.application.flows import runner as runner_mod
    from reasoner.application.flows.base import PhaseStep
    from reasoner.core.exceptions import AuthenticationError
    from reasoner.domain.pipeline_state import PipelineState

    ran: list[int] = []

    def make(num, raises):
        async def fn(state, services, **_k):
            ran.append(num)
            if raises:
                raise AuthenticationError("bad key")

        return PhaseStep(num, f"p{num}", fn, lambda *_a: {}, critical=False)

    steps = [make(1, True), make(2, False)]
    services = MagicMock()
    r = runner_mod.WorkflowRunner(services, monitor=MagicMock())
    services.run_phase = lambda step, state: r.run_phase(step, state)
    with patch.object(runner_mod, "resolve_phases", return_value=steps):
        await r.run(MagicMock(), PipelineState(problem="p"))
    assert ran == [1]


# 8. search done frame carries a cost; direct fallback sums wasted attempts
async def test_search_done_frame_has_cost(monkeypatch):
    from reasoner.application.services.search_service import SearchService
    from reasoner.core.constants_limits import SEARCH_ESTIMATED_COST_USD

    svc = SearchService()
    monkeypatch.setattr(svc, "search", AsyncMock(return_value=[{"title": "t", "url": "u"}]))
    frames = [f async for f in svc.stream_web_search_results("q", "r")]
    done = json.loads(frames[-1][len("data: "):])
    assert done["type"] == "done" and done["total_cost_usd"] == SEARCH_ESTIMATED_COST_USD


async def test_direct_fallback_sums_empty_attempt_cost(monkeypatch):
    from reasoner.api.execution import direct

    calls = iter([
        ("", {"cost_usd": 0.01, "input_tokens": 1}),
        ("answer", {"cost_usd": 0.02, "input_tokens": 1}),
    ])

    class R:
        def __init__(self, **_k): ...

        async def call(self, **_k):
            return next(calls)

    monkeypatch.setattr(direct, "ProviderRouter", R)
    monkeypatch.setattr("reasoner.infrastructure.llm.registry.build_provider", lambda m: None)
    _, meta = await direct._call_with_model_fallback(MagicMock(), ("a", "b"), "s", "u", 10, 0.0)
    assert meta["cost_usd"] == pytest.approx(0.03)
