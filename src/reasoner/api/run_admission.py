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

Paid calls that run no pipeline (search, image generation, image preview) go
through :func:`admit_flat_charge` instead (audit-remediation-5 BIL-26).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import anyio
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from reasoner.application.ports.pipeline_ownership_port import OwnershipConflictError
from reasoner.application.services.anonymous_trial_policy import (
    AnonymousTrialCharge,
    enforce_anonymous_trial_cap,
    refund_anonymous_trial,
)
from reasoner.application.services.idempotency import release_run
from reasoner.application.services.run_metering import RunContext, release_unstarted
from reasoner.core.constants_limits import GATE_FREE_CALLS_PER_DAY, SETTLE_TIMEOUT_SECONDS
from reasoner.core.degrade import degraded
from reasoner.core.settings import settings
from reasoner.core.state_machine import Machine
from reasoner.domain.credits import run_reference
from reasoner.domain.saas import User
from reasoner.infrastructure.persistence.pipeline_ownership_repo import (
    get_pipeline_ownership_repo,
)

logger = logging.getLogger(__name__)


class AdmissionPhase(StrEnum):
    """Where one ``admit_run`` call stands. ``HELD`` is the hand-off to ``metered()``."""

    ADMITTING = "admitting"
    HELD = "held"
    REFUSED = "refused"


ADMISSION = Machine(
    "run_admission",
    {
        AdmissionPhase.ADMITTING: {AdmissionPhase.HELD, AdmissionPhase.REFUSED},
        AdmissionPhase.HELD: set(),
        AdmissionPhase.REFUSED: set(),
    },
    initial=AdmissionPhase.ADMITTING,
)


class AdmissionResource(StrEnum):
    """What admission can hold before the run starts; each is given back on a refusal."""

    ANON_CHARGE = "anon_charge"
    EXCLUSIVE_CLAIM = "exclusive_claim"
    RUN_CLAIM = "run_claim"
    QUOTA_SLOT = "quota_slot"


class _Held:
    """Resources taken so far, released newest first by one call.

    A refusal used to release each resource by hand, in an except block: one
    failing (or cancelled) release skipped every later one, leaving a claim held
    until its TTL. Here every release runs, shielded, whatever the others do.
    """

    def __init__(self) -> None:
        self._stack: list[tuple[AdmissionResource, Callable[[], Awaitable[None]]]] = []

    def hold(self, kind: AdmissionResource, release: Callable[[], Awaitable[None]]) -> None:
        self._stack.append((kind, release))

    async def release_all(self) -> None:
        with anyio.CancelScope(shield=True):
            while self._stack:
                kind, release = self._stack.pop()
                try:
                    await release()
                except Exception:
                    logger.warning("Admission release of %s failed", kind, exc_info=True)


@dataclass(frozen=True)
class Admission:
    """What a route may run, and the reservation already held for it."""

    user_id: str | None
    preset: str
    reference_id: str
    reserved_credits: int
    #: Set by ``metered()`` when the stream starts; see :class:`MeteredSSEResponse`.
    started: asyncio.Event = field(default_factory=asyncio.Event, compare=False)
    #: The ``client_run_id`` claim, released if the run does not complete.
    run_claim: str | None = None
    #: A quota slot was taken at admission; ``metered()`` gives it back if the run costs nothing.
    quota_slot: bool = False
    #: Credits counted against an anonymous caller's daily cap; refunded if the
    #: stream never starts (see :class:`MeteredSSEResponse`).
    anon_charge: AnonymousTrialCharge | None = field(default=None, compare=False)
    #: A claim that keeps a second concurrent run of the same thing out (resume of one
    #: pipeline). Unlike ``run_claim`` it is released whether the run completed or not.
    exclusive_claim: str | None = None

    def run_context(self, *, tier: str = "anonymous", interface: str = "web") -> RunContext:
        return RunContext(
            preset=self.preset,
            reference_id=self.reference_id,
            user_id=self.user_id,
            tier=tier,
            interface=interface,
            reserved_credits=self.reserved_credits,
            started=self.started,
            run_claim=self.run_claim,
            quota_slot=self.quota_slot,
            anon_charge=self.anon_charge,
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


def require_credentials_resolved(request: Request, user: User | None) -> None:
    """Refuse a run whose credentials were sent but did not resolve.

    ``get_optional_user`` returns None for a revoked key, an expired token and a
    database error alike, so with legacy access enabled all three ran anonymously,
    unreserved and unbilled. Callers who sent nothing are unchanged.
    """
    if user is not None:
        return
    failure = getattr(request.state, "auth_failure", None)
    if failure == "rejected":
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if failure == "unavailable":
        raise HTTPException(
            status_code=503,
            detail="Authentication is temporarily unavailable. Retry shortly.",
            headers={"Retry-After": "5"},
        )


def require_run_scope(request: Request, user: User | None) -> None:
    """Refuse an API key that lacks the ``run`` scope, and note keys that run.

    Inside admission, not a route ``Depends``, so a new run route cannot forget
    it (docs/plans/audit-remediation-5-2026-10-29.md SEC-19). Session and JWT
    callers pass, as with ``require_key_scope``: scopes only narrow keys.
    """
    if user is None or getattr(request.state, "auth_method", None) != "api_key":
        return
    from reasoner.domain.api_keys import RUN_SCOPE, key_allows

    if not key_allows(user.scopes, RUN_SCOPE):
        raise HTTPException(status_code=403, detail=f"API key lacks the '{RUN_SCOPE}' scope")
    record_key_run(user)


def record_key_run(user: User) -> None:
    """Stamp ``last_run_at`` for the caller's key, off the request path."""
    if getattr(user, "api_key_id", None) is None:
        return
    from reasoner.api import dependencies as deps

    try:
        asyncio.get_running_loop().create_task(
            deps._get_api_key_service().record_run(user.api_key_id)
        )
    except RuntimeError:  # no running loop (sync test context)
        pass


async def admit_run(
    request: Request,
    *,
    user: User | None,
    problem: str,
    preset: str,
    client_run_id: str | None = None,
    kind: str = "run",
    exclusive: str | None = None,
) -> Admission:
    """Run every admission step, in order, or raise the HTTP error for the first that fails.

    Every refusal comes before the ``client_run_id`` claim, so a 403 or 429 does
    not lock the id, and before the reservation, so a refused run holds no credits.
    The quota slot is claimed atomically just before the reservation (the claim is
    the quota 429; ``check_quota_if_authenticated`` is only a cheap early read).
    """
    # Module lookups at call time, not import time, so tests can patch them.
    from reasoner.api import dependencies as deps
    from reasoner.api import idempotency_http

    require_credentials_resolved(request, user)
    require_auth_if_legacy_disabled(user)
    require_run_scope(request, user)
    await deps.check_preset_access_if_authenticated(preset, user, request)

    held = _Held()
    anon_charge: AnonymousTrialCharge | None = None
    if user is None:
        # No account to reserve credits against, so anonymous spend is capped
        # separately (Phase 2 metering).
        from reasoner.api.client_ip import get_client_ip
        from reasoner.application.services.estimate_service import estimate_cost
        from reasoner.application.services.spend_limit_service import (
            anonymous_tier,
            check_run_allowed,
        )

        # The runtime tier gate refuses a locked preset only after the run has
        # started, so the cap below was charged and never refunded.
        rejection = check_run_allowed(preset, anonymous_tier())
        if rejection is not None:
            raise HTTPException(status_code=403, detail=rejection.reason)

        estimate = await estimate_cost(problem, preset)
        anon_charge = await enforce_anonymous_trial_cap(
            get_client_ip(request), estimate["estimated_cost_usd"]
        )
        held.hold(
            AdmissionResource.ANON_CHARGE, lambda: refund_anonymous_trial(anon_charge)
        )

    user_id = str(user.id) if user else None
    owner_key = user_id or _anonymous_owner_key(request)
    claim: str | None = None
    exclusive_claim: str | None = None
    try:
        if exclusive is not None:
            exclusive_claim = await idempotency_http.register_run_or_error(
                exclusive, owner_key=owner_key,
            )
            held.hold(
                AdmissionResource.EXCLUSIVE_CLAIM, lambda: release_run(exclusive_claim)
            )
        claim = await idempotency_http.register_run_or_error(client_run_id, owner_key=owner_key)
        held.hold(AdmissionResource.RUN_CLAIM, lambda: release_run(claim))
    except BaseException:
        ADMISSION.move(AdmissionPhase.ADMITTING, AdmissionPhase.REFUSED)
        await held.release_all()  # refused: nothing ran
        raise
    quota_slot = False
    try:
        if client_run_id:
            # The id is the pipeline id: refuse it before any credit is held
            # if another caller already owns that pipeline (SEC-7).
            try:
                await get_pipeline_ownership_repo().set_owner(
                    client_run_id, user_id, client_run_id,
                )
            except OwnershipConflictError as exc:
                raise HTTPException(
                    status_code=409,
                    detail=f"Run id {client_run_id} is already in use. Choose another id.",
                ) from exc
        # Atomic claim, before the reservation so a denial holds no credits.
        quota_slot = await deps.claim_quota_slot(user, preset, request)
        if quota_slot:
            held.hold(AdmissionResource.QUOTA_SLOT, lambda: deps.release_quota_slot(user))
        reference_id = run_reference(client_run_id, kind)
        reserved_credits = await deps.reserve_or_402(
            user_id=user_id, preset=preset, problem=problem, reference_id=reference_id,
        )
    except BaseException:
        # Refused after the claim (402, 409, a ledger error): give the id back,
        # so the documented retry with the same id works (SEC-7). The quota
        # slot goes back too: a refused run is not a run.
        ADMISSION.move(AdmissionPhase.ADMITTING, AdmissionPhase.REFUSED)
        await held.release_all()
        raise
    ADMISSION.move(AdmissionPhase.ADMITTING, AdmissionPhase.HELD)
    return Admission(
        user_id=user_id,
        preset=preset,
        reference_id=reference_id,
        reserved_credits=reserved_credits,
        run_claim=claim,
        quota_slot=quota_slot,
        anon_charge=anon_charge,
        exclusive_claim=exclusive_claim,
    )


@dataclass(frozen=True)
class FlatCharge:
    """A paid call that runs no pipeline. The hold is the charge: there is no
    true-up, so its reference never ends in ``:reserve`` and the orphan sweeper
    leaves it alone."""

    user_id: str | None
    reference_id: str  # "<kind>:<uuid4>"
    credits: int
    cost_usd: float
    #: The ledger was down at admission, so nothing is held. A served call is
    #: then recorded for the unsettled-run replay, or it would be free for good.
    unreserved: bool = False
    anon_charge: AnonymousTrialCharge | None = field(default=None, compare=False)


async def admit_flat_charge(
    request: Request, *, user: User | None, cost_usd: float, kind: str
) -> FlatCharge:
    """Admission for a flat-priced paid call, or raise the HTTP error for the first refusal.

    Anonymous callers count against the per-IP trial cap; signed-in callers
    hold ``cost_usd`` (402 when the balance cannot cover it).
    """
    require_credentials_resolved(request, user)
    require_auth_if_legacy_disabled(user)
    require_run_scope(request, user)
    reference_id = f"{kind}:{uuid.uuid4()}"
    if user is None:
        from reasoner.api.client_ip import get_client_ip

        anon = await enforce_anonymous_trial_cap(get_client_ip(request), cost_usd)
        return FlatCharge(None, reference_id, 0, cost_usd, anon_charge=anon)
    credits = await _reserve_flat(str(user.id), cost_usd, reference_id, kind)
    return FlatCharge(
        str(user.id), reference_id, credits or 0, cost_usd, unreserved=credits is None
    )


async def _reserve_flat(user_id: str, cost_usd: float, reference_id: str, kind: str) -> int | None:
    """Hold ``cost_usd``. Returns None on a ledger outage (fail-open, counted)."""
    if cost_usd <= 0:
        return 0
    from reasoner.api import dependencies as deps
    from reasoner.api.run_observability import CreditSink, count_credit_failopen
    from reasoner.domain.credits import InsufficientCreditsError

    if not deps._persistence_is_configured() and settings.ENVIRONMENT != "production":
        return 0
    deps._require_persistence("Credits")
    try:
        return await CreditSink().reserve(
            user_id=user_id, estimated_cost_usd=cost_usd, reference_id=reference_id, preset=kind,
        )
    except InsufficientCreditsError as exc:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Insufficient credits",
                "message": "Your credit balance can't cover this request's cost.",
                "required": exc.required,
                "available": exc.available,
                "upgrade_url": "/pricing",
            },
        ) from exc
    except HTTPException:
        raise
    except Exception as exc:
        deps._refuse_missing_account(exc)
        logger.warning("Flat-charge reservation failed; allowing unreserved", exc_info=True)
        count_credit_failopen("reserve")
        return None


async def close_flat_charge(charge: FlatCharge, *, served: bool) -> None:
    """Keep the charge of a served call; give back the hold of one that was not.

    Call it from ``finally``. Shielded, so a client disconnect cannot leave the
    hold debited, and bounded, so a stuck ledger cannot hang the request.
    """
    from reasoner.api.run_observability import CreditSink

    with anyio.CancelScope(shield=True), anyio.move_on_after(SETTLE_TIMEOUT_SECONDS):
        if served:
            if charge.unreserved and charge.user_id:
                await CreditSink().record_unsettled(
                    user_id=charge.user_id,
                    reference_id=charge.reference_id,
                    cost_usd=charge.cost_usd,
                    reserved_credits=0,
                    preset=charge.reference_id.split(":", 1)[0],
                    error="flat-charge reservation failed",
                )
            return
        await refund_anonymous_trial(charge.anon_charge)
        if charge.user_id and charge.credits > 0:
            try:
                await CreditSink().release(
                    user_id=charge.user_id,
                    credits=charge.credits,
                    reference_id=f"{charge.reference_id}:release",
                )
            except Exception as exc:
                logger.warning("Flat-charge release failed for %s: %s", charge.reference_id, exc)


async def within_gate_allowance(user_id: str) -> bool:
    """Count one HyperGate preview against the caller's free daily allowance.

    The gate stays free (audit-5 decision Q9) but capped: without a cap one
    account could spend about $24 a day by varying the problem text. A Valkey
    error fails open to the hourly rate limit.
    """
    from reasoner.infrastructure.valkey.client import get_valkey_pool

    key = f"gate:{user_id}:{datetime.now(UTC):%Y-%m-%d}"
    try:
        pool = get_valkey_pool()
        count = await pool.incr(key)
        await pool.expire(key, 90_000)
    except Exception as exc:
        return degraded("gate.allowance", True, exc=exc)
    return int(count) <= GATE_FREE_CALLS_PER_DAY


def seconds_until_utc_midnight() -> int:
    now = datetime.now(UTC)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - now).total_seconds()))


def _anonymous_owner_key(request: Request) -> str:
    from reasoner.api.client_ip import get_client_ip

    return f"anon:{get_client_ip(request)}"


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

            ctx = self._admission.run_context()
            await release_unstarted(CreditSink(), ctx)
            if not self._admission.started.is_set():
                await refund_anonymous_trial(self._admission.anon_charge)
            with anyio.CancelScope(shield=True):
                await release_run(self._admission.exclusive_claim)


__all__ = [
    "Admission",
    "FlatCharge",
    "MeteredSSEResponse",
    "admit_flat_charge",
    "admit_run",
    "close_flat_charge",
    "record_key_run",
    "require_auth_if_legacy_disabled",
    "require_run_scope",
    "seconds_until_utc_midnight",
    "within_gate_allowance",
]
