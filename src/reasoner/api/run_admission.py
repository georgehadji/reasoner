"""One admission sequence for every HTTP route that starts a billed run.

Each paid route used to hand-assemble the same steps: the legacy-auth gate, the
preset-tier gate, the anonymous trial cap, the ``client_run_id`` claim and the
credit reservation. ``/api/run-with-context`` and the resume stream forgot
them, and ran premium pipelines for free (docs/plans/
audit-remediation-2-2026-10-20.md BIL-10, BIL-11). One function cannot forget
a step its siblings have.

The per-request guards that FastAPI resolves from the request itself stay as
route ``Depends``: ``check_rate_limit``, ``check_quota_if_authenticated``,
``require_credits_if_authenticated`` and ``require_csrf``.

The MCP tools keep their own sequence (``api/mcp/tools.py::_run_and_bill``):
they have no ``Request`` and must raise tool errors, not ``HTTPException``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from reasoner.application.services.run_metering import RunContext, release_unstarted
from reasoner.core.settings import settings
from reasoner.domain.credits import run_reference
from reasoner.domain.saas import User


@dataclass(frozen=True)
class Admission:
    """What a route may run, and the reservation already held for it."""

    user_id: str | None
    preset: str
    reference_id: str
    reserved_credits: int
    #: Set by ``metered()`` when the stream starts; see :class:`MeteredSSEResponse`.
    started: asyncio.Event = field(default_factory=asyncio.Event, compare=False)

    def run_context(self, *, tier: str = "anonymous", interface: str = "web") -> RunContext:
        return RunContext(
            preset=self.preset,
            reference_id=self.reference_id,
            user_id=self.user_id,
            tier=tier,
            interface=interface,
            reserved_credits=self.reserved_credits,
            started=self.started,
        )


def require_auth_if_legacy_disabled(user: User | None) -> None:
    """Backward-compat gate: require auth when legacy API key mode is disabled."""
    if user is None and not settings.ENABLE_LEGACY_API_KEY:
        raise HTTPException(
            status_code=401,
            detail=(
                "Authentication required. "
                "Set ENABLE_LEGACY_API_KEY=true for v1 backward compatibility."
            ),
        )


async def admit_run(
    request: Request,
    *,
    user: User | None,
    problem: str,
    preset: str,
    client_run_id: str | None = None,
    kind: str = "run",
) -> Admission:
    """Run every admission step, in order, or raise the HTTP error for the first that fails.

    Every refusal comes before the ``client_run_id`` claim, so a 403 or 429 does
    not lock the id, and before the reservation, so a refused run holds no credits.
    """
    # Module lookups at call time, not import time, so tests can patch them.
    from reasoner.api import dependencies as deps
    from reasoner.api import idempotency_http

    require_auth_if_legacy_disabled(user)
    await deps.check_preset_access_if_authenticated(preset, user, request)

    if user is None:
        # No account to reserve credits against, so anonymous spend is capped
        # separately (Phase 2 metering).
        from reasoner.api.client_ip import get_client_ip
        from reasoner.application.services.anonymous_trial_policy import (
            enforce_anonymous_trial_cap,
        )
        from reasoner.application.services.estimate_service import estimate_cost

        estimate = await estimate_cost(problem, preset)
        await enforce_anonymous_trial_cap(get_client_ip(request), estimate["estimated_cost_usd"])

    await idempotency_http.register_run_or_error(client_run_id)
    reference_id = run_reference(client_run_id, kind)
    user_id = str(user.id) if user else None
    reserved_credits = await deps.reserve_or_402(
        user_id=user_id, preset=preset, problem=problem, reference_id=reference_id,
    )
    return Admission(
        user_id=user_id,
        preset=preset,
        reference_id=reference_id,
        reserved_credits=reserved_credits,
    )


class MeteredSSEResponse(StreamingResponse):
    """An SSE response that releases its reservation if the stream never started.

    A client that drops before the first frame never enters ``metered()``, so
    its ``finally`` never runs. Starlette also skips ``background`` tasks on a
    disconnect under ASGI 2.4, so the release lives here, around the whole call.
    """

    def __init__(
        self,
        content: AsyncIterator[str],
        admission: Admission,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            content,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", **(headers or {})},
        )
        self._admission = admission

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            from reasoner.api.run_observability import CreditSink

            await release_unstarted(CreditSink(), self._admission.run_context())


__all__ = ["Admission", "MeteredSSEResponse", "admit_run", "require_auth_if_legacy_disabled"]
