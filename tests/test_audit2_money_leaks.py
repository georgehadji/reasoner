"""PR 1 of docs/plans/audit-remediation-2-2026-10-20.md: BIL-10, BIL-11, BIL-12.

* BIL-12: a client disconnect cancelled ``metered()``'s settlement, so neither
  the reservation release nor the true-up ran.
* BIL-11: the resume stream ran a full pipeline with no reservation or metering.
* BIL-10: ``/api/run-with-context`` ran paid phases with no billing at all.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import anyio
import anyio.lowlevel
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.requests import ClientDisconnect

from reasoner.api.run_admission import Admission, MeteredSSEResponse
from reasoner.application.services.run_metering import RunContext, metered
from reasoner.domain.saas import SubscriptionTier, User

pytestmark = pytest.mark.asyncio

PHASE_FRAME = 'data: {"type": "phase_complete", "total_cost_usd": 0.01}\n\n'


class _Sink:
    """Records ledger calls. Each call awaits first, as the real ledger does,
    so a pending cancellation interrupts it unless settlement is shielded."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def reserve(self, **kwargs) -> int:
        return 0

    async def release(self, *, user_id, credits, reference_id) -> None:
        await asyncio.sleep(0)
        self.calls.append(("release", credits, reference_id))

    async def settle(self, *, user_id, cost_usd, reference_id, preset) -> None:
        await asyncio.sleep(0)
        self.calls.append(("settle", round(cost_usd, 6), reference_id))


async def _one_frame_then_hang():
    yield PHASE_FRAME
    await anyio.sleep_forever()


# ── BIL-12: settlement survives cancellation ───────────────────────────


async def test_cancelled_stream_still_releases_and_settles():
    sink = _Sink()
    ctx = RunContext(preset="p", reference_id="r", user_id="u", reserved_credits=50)
    first = anyio.Event()

    async def consume():
        async for _ in metered(_one_frame_then_hang(), ctx, sink):
            first.set()

    async with anyio.create_task_group() as tg:
        tg.start_soon(consume)
        await first.wait()
        tg.cancel_scope.cancel()

    assert sink.calls == [("release", 50, "r:release"), ("settle", 0.01, "r")]


def _admission() -> Admission:
    return Admission(user_id="u", preset="p", reference_id="r", reserved_credits=50)


async def test_asgi_disconnect_after_first_frame_settles_once():
    """A real ASGI ``http.disconnect`` (ASGI 2.3 path), not ``aclose()``."""
    sink = _Sink()
    adm = _admission()
    response = MeteredSSEResponse(metered(_one_frame_then_hang(), adm.run_context(), sink), adm)
    body_sent = anyio.Event()

    async def send(message):
        await anyio.lowlevel.checkpoint()
        if message["type"] == "http.response.body" and message.get("body"):
            body_sent.set()

    async def receive():
        await body_sent.wait()
        return {"type": "http.disconnect"}

    with patch("reasoner.api.run_observability.CreditSink", lambda: sink):
        await response({"type": "http", "asgi": {"spec_version": "2.3"}}, receive, send)

    # Settled by metered(); the unstarted-stream release must not fire again.
    assert sink.calls == [("release", 50, "r:release"), ("settle", 0.01, "r")]


async def test_disconnect_before_first_frame_releases_the_hold():
    sink = _Sink()
    adm = _admission()
    response = MeteredSSEResponse(metered(_one_frame_then_hang(), adm.run_context(), sink), adm)

    async def send(message):
        await anyio.lowlevel.checkpoint()

    async def receive():
        return {"type": "http.disconnect"}

    with patch("reasoner.api.run_observability.CreditSink", lambda: sink):
        await response({"type": "http", "asgi": {"spec_version": "2.3"}}, receive, send)

    assert not adm.started.is_set()
    assert sink.calls == [("release", 50, "r:release")]


async def test_asgi_24_disconnect_before_first_frame_releases_the_hold():
    """Under ASGI 2.4 Starlette raises ClientDisconnect and skips background tasks."""
    sink = _Sink()
    adm = _admission()
    response = MeteredSSEResponse(metered(_one_frame_then_hang(), adm.run_context(), sink), adm)

    async def send(message):
        raise OSError("client gone")

    async def receive():
        return {"type": "http.disconnect"}

    with patch("reasoner.api.run_observability.CreditSink", lambda: sink):
        with pytest.raises(ClientDisconnect):
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)

    assert sink.calls == [("release", 50, "r:release")]


# ── Route wiring: resume (BIL-11) and run-with-context (BIL-10) ────────


def _as_tier(tier):
    return patch("reasoner.api.dependencies._resolve_user_tier", AsyncMock(return_value=tier))


async def _post(path, json, overrides, patches):
    import reasoner.api as api

    api.app.dependency_overrides.update(overrides)
    try:
        with _as_tier(SubscriptionTier.PRO):
            for p in patches:
                p.start()
            try:
                async with AsyncClient(
                    transport=ASGITransport(app=api.app), base_url="http://test"
                ) as client:
                    return await client.post(path, json=json)
            finally:
                for p in patches:
                    p.stop()
    finally:
        for dep in overrides:
            api.app.dependency_overrides.pop(dep, None)


def _paid_overrides(user_dep):
    from reasoner.api.dependencies import (
        check_quota_if_authenticated,
        require_credits_if_authenticated,
    )

    user = User(id=uuid4(), email="leak@test.local")
    return {
        user_dep: lambda: user,
        check_quota_if_authenticated: lambda: None,
        require_credits_if_authenticated: lambda: None,
    }


def _refuse_reservation():
    return patch(
        "reasoner.api.dependencies.reserve_or_402",
        AsyncMock(side_effect=HTTPException(status_code=402, detail="Insufficient credits")),
    )


def _resume_patches():
    registry = SimpleNamespace(
        handle_command=AsyncMock(return_value={"problem": "p", "preset": "debate-budget"})
    )
    return [
        patch("reasoner.api.routes.pipelines._check_pipeline_ownership", AsyncMock(return_value=True)),
        patch("reasoner.api.get_architecture_components", return_value=(None, registry)),
    ]


async def test_resume_with_no_credits_is_402():
    from reasoner.api.dependencies import get_current_user

    response = await _post(
        "/api/pipelines/pid-1/resume-stream", None,
        _paid_overrides(get_current_user), [*_resume_patches(), _refuse_reservation()],
    )
    assert response.status_code == 402, response.text


async def test_funded_resume_releases_and_charges_under_a_resume_reference():
    from reasoner.api.dependencies import get_current_user

    sink = _Sink()
    reserve = AsyncMock(return_value=7)

    async def fake_run_stream(*args, **kwargs):
        yield 'data: {"type": "done", "total_cost_usd": 0.02}\n\n'

    response = await _post(
        "/api/pipelines/pid-1/resume-stream", None,
        _paid_overrides(get_current_user),
        [
            *_resume_patches(),
            patch("reasoner.api.dependencies.reserve_or_402", reserve),
            patch("reasoner.api.streaming.run_stream", fake_run_stream),
            patch("reasoner.api.routes.pipelines.CreditSink", lambda: sink),
        ],
    )
    assert response.status_code == 200, response.text
    reference = reserve.await_args.kwargs["reference_id"]
    assert reference.startswith("resume:pid-1:")
    assert sink.calls == [("release", 7, f"{reference}:release"), ("settle", 0.02, reference)]


async def test_run_with_context_with_no_credits_is_402():
    from reasoner.api.dependencies import require_auth_if_legacy_disabled

    response = await _post(
        "/api/run-with-context",
        {"problem": "x", "preset": "multi-perspective-budget", "method": "multi-perspective", "context": []},
        _paid_overrides(require_auth_if_legacy_disabled), [_refuse_reservation()],
    )
    assert response.status_code == 402, response.text


def _context_phases(*, fail_at: str | None = None):
    def phase(name):
        async def run(state, *args, **kwargs):
            if name == fail_at:
                raise RuntimeError("provider down")
            state.total_cost_usd += 0.01
            if name == "run_synthesis_phase":
                state.final_solution = {"core_solution": "answer"}
        return patch(f"reasoner.api.routes.context.{name}", run)

    return [
        phase(n) for n in (
            "run_perspectives_phase", "run_critique_phase",
            "run_stress_test_phase", "run_synthesis_phase",
        )
    ]


@pytest.mark.parametrize("fail_at,charged,success", [
    (None, 0.04, True),
    # A run that dies half way pays for the phases it already ran.
    ("run_critique_phase", 0.01, False),
])
async def test_funded_run_with_context_is_metered(fail_at, charged, success):
    from reasoner.api.dependencies import require_auth_if_legacy_disabled

    sink = _Sink()
    reserve = AsyncMock(return_value=9)
    response = await _post(
        "/api/run-with-context",
        {"problem": "x", "preset": "multi-perspective-budget", "method": "multi-perspective", "context": []},
        _paid_overrides(require_auth_if_legacy_disabled),
        [
            patch("reasoner.api.dependencies.reserve_or_402", reserve),
            patch("reasoner.api.routes.context.CreditSink", lambda: sink),
            *_context_phases(fail_at=fail_at),
        ],
    )
    assert response.status_code == 200, response.text
    assert response.json()["success"] is success
    reference = reserve.await_args.kwargs["reference_id"]
    assert sink.calls == [("release", 9, f"{reference}:release"), ("settle", charged, reference)]
