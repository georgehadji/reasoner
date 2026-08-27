"""Agent-facing endpoints.

Authenticate with ``Authorization: Bearer <key>`` -- a Reasoner account key
(``rsn_live_...``), a JWT, or (when ``ENABLE_LEGACY_API_KEY=true``) a
self-hosted legacy key; ``get_current_user`` already resolves all three to the
same ``User``. No CSRF token: a page cannot attach a caller's bearer key to a
forged cross-origin request, so the attack CSRF defends against does not exist
on this path (``require_csrf`` grants the identical exemption to ``/api/run``).

Every run here is idempotency-guarded and metered exactly like a web run --
same credit ledger, same Prometheus counter, same ownership record -- via the
shared ``run_metering.metered()`` wrapper. That parity is the point: these
used to authenticate against a different, unmetered key store.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from reasoner.api.dependencies import (
    check_quota_if_authenticated,
    check_rate_limit,
    get_current_user,
    get_pipeline_service,
    get_preset_service,
    require_credits_if_authenticated,
)
from reasoner.api.idempotency_http import register_run_or_error
from reasoner.api.run_observability import CreditSink, PrometheusObserver
from reasoner.api.schemas import RunRequest, RunResult
from reasoner.application.services.agent_results import summarise
from reasoner.application.services.pipeline_service import PipelineService
from reasoner.application.services.preset_service import PresetService
from reasoner.application.services.run_metering import RunContext, metered
from reasoner.domain.saas import QuotaResult, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["Agent"])


# ── Tool discovery ──────────────────────────────────────────────────


def _agent_tool_payload(fmt: str) -> list[dict]:
    """Tool definitions in *fmt*, projected from RunRequest's own JSON Schema."""
    from reasoner.application.services.tool_schema import FORMATS, build_tool_definitions

    serialise = FORMATS.get(fmt)
    if serialise is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown format '{fmt}'. Supported: {', '.join(sorted(FORMATS))}.",
        )
    return serialise(build_tool_definitions(RunRequest.model_json_schema()))


@router.get("/tools")
async def agent_tools(format: str = "anthropic"):
    """Function-calling definitions for the agent-facing endpoints.

    GET, because discovery is idempotent and worth caching: an agent fetches
    this once at startup and registers the result verbatim. ``format=openai``
    returns the same tools in OpenAI's function-calling dialect.
    """
    payload = _agent_tool_payload(format)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return JSONResponse(
        content=payload,
        headers={
            "Cache-Control": "public, max-age=3600",
            "ETag": f'"{hashlib.sha256(body.encode()).hexdigest()[:32]}"',
        },
    )


@router.post("/tools", include_in_schema=False, deprecated=True)
async def agent_tools_legacy(format: str = "anthropic"):
    """Deprecated alias for ``GET /api/agent/tools``; identical body."""
    return _agent_tool_payload(format)


# ── Running a pipeline ──────────────────────────────────────────────


async def _metered_agent_stream(
    req: RunRequest,
    request: Request,
    user: User,
    preset_service: PresetService,
    pipeline_service: PipelineService,
    *,
    preset: str,
    interface: str,
    reference_id: str,
    reserved_credits: int = 0,
) -> AsyncIterator[str]:
    """The one place an agent route turns a request into a billed run.

    Shared by the streaming and the sync endpoint so a blocking caller is
    metered through the identical path a streaming caller is -- not a second,
    hand-copied settlement.

    ``reference_id``/``reserved_credits`` come from the caller, which already
    reserved this run's estimated cost via ``reserve_or_402`` before invoking
    this generator -- ``agent_run``'s streaming response can't turn a
    mid-generator exception into a clean 402, so the reservation (and its
    possible failure) has to happen before the generator starts.
    """
    from reasoner.api.streaming import run_stream_cached

    ctx = RunContext(
        preset=preset,
        reference_id=reference_id,
        user_id=str(user.id),
        tier="free",
        interface=interface,
        reserved_credits=reserved_credits,
    )
    stream = run_stream_cached(
        req,
        request=request,
        user_id=str(user.id),
        preset_service=preset_service,
        pipeline_service=pipeline_service,
    )
    async for chunk in metered(
        stream,
        ctx,
        CreditSink(),
        PrometheusObserver(tier="free", preset=preset, interface=interface),
    ):
        yield chunk


@router.post("/run")
async def agent_run(
    request: Request,
    req: RunRequest,
    user: User = Depends(get_current_user),
    _rate_limited=Depends(check_rate_limit),
    _quota: QuotaResult | None = Depends(check_quota_if_authenticated),
    _credits=Depends(require_credits_if_authenticated),
    preset_service: PresetService = Depends(get_preset_service),
    pipeline_service: PipelineService = Depends(get_pipeline_service),
):
    """Run a pipeline; identical SSE event shape to ``/api/run``."""
    from reasoner.api.dependencies import reserve_or_402

    await register_run_or_error(req.client_run_id)
    preset = req.preset or "auto-budget"
    reference_id = req.client_run_id or f"run:{uuid.uuid4()}"
    reserved_credits = await reserve_or_402(
        user_id=str(user.id), preset=preset, problem=req.problem, reference_id=reference_id,
    )
    return StreamingResponse(
        _metered_agent_stream(
            req, request, user, preset_service, pipeline_service,
            preset=preset, interface="agent_http",
            reference_id=reference_id, reserved_credits=reserved_credits,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/run/sync", response_model=RunResult)
async def agent_run_sync(
    request: Request,
    req: RunRequest,
    user: User = Depends(get_current_user),
    _rate_limited=Depends(check_rate_limit),
    _quota: QuotaResult | None = Depends(check_quota_if_authenticated),
    _credits=Depends(require_credits_if_authenticated),
    preset_service: PresetService = Depends(get_preset_service),
    pipeline_service: PipelineService = Depends(get_pipeline_service),
) -> RunResult:
    """Run a pipeline and block until it finishes, returning one JSON object.

    A run can legitimately take up to the pipeline's own cap
    (``PIPELINE_ABSOLUTE_TIMEOUT_SECONDS``, currently 600s) -- set the client
    timeout above that rather than below it.
    """
    from reasoner.api.dependencies import reserve_or_402

    await register_run_or_error(req.client_run_id)
    preset = req.preset or "auto-budget"
    reference_id = req.client_run_id or f"run:{uuid.uuid4()}"
    reserved_credits = await reserve_or_402(
        user_id=str(user.id), preset=preset, problem=req.problem, reference_id=reference_id,
    )

    events: list[dict] = []
    async for chunk in _metered_agent_stream(
        req, request, user, preset_service, pipeline_service,
        preset=preset, interface="agent_sync",
        reference_id=reference_id, reserved_credits=reserved_credits,
    ):
        if chunk.startswith("data: "):
            try:
                events.append(json.loads(chunk[6:]))
            except json.JSONDecodeError:
                pass

    summary = summarise(events, preset=preset)
    return RunResult(
        preset=summary.preset,
        method=summary.method,
        errors=list(summary.errors),
        total_tokens=dict(summary.total_tokens),
        total_cost_usd=summary.total_cost_usd,
        duration_seconds=summary.duration_seconds,
        synthesis=summary.synthesis,
        critical_insights=list(summary.critical_insights),
        open_questions=list(summary.open_questions),
        claim_labels=dict(summary.claim_labels),
        premises=[dict(p) for p in summary.premises],
        action_blueprint=list(summary.action_blueprint),
        citations=list(summary.citations),
        models_used=list(summary.models_used),
    )
