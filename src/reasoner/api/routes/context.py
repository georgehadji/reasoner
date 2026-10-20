"""External context integration endpoint."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable

from fastapi import APIRouter, Depends, HTTPException, Request

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import (
    check_quota_if_authenticated,
    check_rate_limit,
    require_auth_if_legacy_disabled,
    require_credits_if_authenticated,
    resolve_request_tier,
)
from reasoner.api.run_admission import admit_run
from reasoner.api.run_observability import CreditSink, PrometheusObserver
from reasoner.api.schemas import ContextAnalysisRequest
from reasoner.api.sse_utils import _event
from reasoner.application.flows.jury_phases import (
    run_jury_critique_phase,
    run_jury_generate_phase,
    run_jury_verify_and_meta_eval_phase,
)
from reasoner.application.flows.perspective_phases import (
    run_critique_phase,
    run_perspectives_phase,
    run_stress_test_phase,
)
from reasoner.application.flows.services import PipelineWorkflowServices
from reasoner.application.flows.synthesis_phase import run_synthesis_phase
from reasoner.application.services.run_metering import metered
from reasoner.application.services.spend_limit_service import (
    apply_spend_limits,
    check_run_allowed,
)
from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.saas import SubscriptionTier, User


def _svc(pipeline):
    """The WorkflowServices a phase function takes, bound to this pipeline."""
    return PipelineWorkflowServices(pipeline)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _cost_frames(
    state: PipelineState, steps: list[Callable[[], Awaitable[object]]]
) -> AsyncIterator[str]:
    """Run *steps* in order, reporting the running cost after each one.

    These phases emit no SSE frames of their own, so without these
    ``metered()`` saw no cost at all, and a run that failed half way through
    would release its whole reservation instead of paying for what it spent.
    """
    for step in steps:
        await step()
        yield _event({"type": "phase_complete", "total_cost_usd": state.total_cost_usd})
    yield _event({"type": "done", "total_cost_usd": state.total_cost_usd})


@router.post("/api/run-with-context")
async def run_with_context(
    request: Request,
    req: ContextAnalysisRequest,
    user: User | None = Depends(require_auth_if_legacy_disabled),
    rate_limit_checked=Depends(check_rate_limit),
    csrf_checked=Depends(require_csrf),
    quota=Depends(check_quota_if_authenticated),
    credits_checked=Depends(require_credits_if_authenticated),
):
    """
    Run the Reasoner pipeline with external context.

    This endpoint accepts collected research context
    (facts, URLs, summaries) and runs deep, validated analysis.

    It is billed like ``/api/run``: the plan-tier and spend gates, then
    ``admit_run`` (claim and reservation), then ``metered()`` settles the actual
    cost (docs/plans/audit-remediation-2-2026-10-20.md BIL-10).
    """
    if quota is not None and not quota.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Quota exceeded",
                "message": quota.reason,
                "remaining": quota.remaining,
                "retry_after": quota.retry_after,
                "upgrade_url": "/pricing",
            },
            headers={
                "Retry-After": str(quota.retry_after or 3600),
                "X-RateLimit-Remaining": "0",
            },
        )

    # Validate URLs inside context items before anything is reserved.
    from reasoner.security.url_validator import is_safe_url
    for item in req.context:
        for _key, value in item.items():
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                if not is_safe_url(value):
                    raise HTTPException(
                        status_code=403,
                        detail=f"Unsafe URL in context: {value}",
                    )

    from reasoner.application.services.preset_service import PresetService

    _preset_service = PresetService()
    # Resolve preset and build router via orchestrator
    effective_preset, _router = _preset_service.build_router(req.preset)

    # This route skips execution/pipeline.py, where /api/run applies these
    # gates, so it applies them itself.
    user_id = str(user.id) if user else None
    tier = await resolve_request_tier(request, user) if user else SubscriptionTier.FREE
    rejection = check_run_allowed(effective_preset, tier, user_id)
    if rejection is not None:
        raise HTTPException(
            status_code=403 if rejection.cap_type == "preset_tier" else 402,
            detail={"error": rejection.reason, "cap_type": rejection.cap_type},
        )

    try:
        from reasoner.application.orchestrator import PipelineOrchestrator, PreflightDecision
        from reasoner.application.services.pipeline_service import PipelineService

        _orchestrator = PipelineOrchestrator(
            preset_service=_preset_service,
            pipeline_service=PipelineService(),
        )
        _decision = PreflightDecision(
            action="pipeline",
            router=_router,
            effective_preset_name=effective_preset,
            problem=req.problem,
        )

        # Create pipeline via orchestrator (removes direct ReasonerPipeline import)
        pipeline = _orchestrator.create_pipeline(
            _decision,
            top_k=req.top_k,
            parallel_perspectives=True,
            domain=req.domain if hasattr(req, "domain") else None,
            user_id=user_id,
        )

        # Create state with the external context
        state = PipelineState(problem=req.problem, preset_name=req.preset)
        # The executor halts the run if its cost crosses a ceiling.
        apply_spend_limits(state, tier, user_id)

        # Inject external context directly into the state
        # This bypasses the normal search/vetting phases
        state.web_discovery_results = req.context
        state.vetted_context = req.context

        # Run the appropriate method pipeline.
        #
        # This is a hand-rolled phase sequence, not WorkflowRunner: the endpoint
        # supplies its own vetted context and wants four phases, not a whole
        # method. It therefore gets no retries, no quality gate and no PHASE_*
        # events.
        services = _svc(pipeline)
        steps: list[Callable[[], Awaitable[object]]]
        if req.method == "jury":
            steps = [
                lambda: run_jury_generate_phase(state, services),
                lambda: run_jury_critique_phase(
                    state, services, batch_critique=pipeline.batch_critique_jury
                ),
                lambda: run_jury_verify_and_meta_eval_phase(state, services),
            ]
        else:
            steps = [
                lambda: run_perspectives_phase(state, services, perspectives=pipeline.perspectives),
                lambda: run_critique_phase(state, services),
                lambda: run_stress_test_phase(state, services),
            ]
        steps.append(lambda: run_synthesis_phase(state, services))

        # Last, so nothing above can fail while credits are held outside metered().
        adm = await admit_run(request, user=user, problem=req.problem, preset=effective_preset)
        tier_label = tier.value if user else "anonymous"
        async for _ in metered(
            _cost_frames(state, steps),
            adm.run_context(tier=tier_label, interface="context"),
            CreditSink(),
            PrometheusObserver(tier=tier_label, preset=effective_preset, interface="context"),
        ):
            pass

        # Return the final solution
        if state.final_solution:
            return {
                "success": True,
                "solution": state.final_solution,
            }
        else:
            return {"success": False, "error": "Failed to generate solution"}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Context analysis failed: %s", exc, exc_info=False)
        return {"success": False, "error": "Internal server error"}
