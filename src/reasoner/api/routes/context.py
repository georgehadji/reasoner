"""External context integration endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import (
    check_quota_if_authenticated,
    check_rate_limit,
    require_auth_if_legacy_disabled,
)
from reasoner.api.schemas import ContextAnalysisRequest
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
from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.saas import User


def _svc(pipeline):
    """The WorkflowServices a phase function takes, bound to this pipeline."""
    return PipelineWorkflowServices(pipeline)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/run-with-context")
async def run_with_context(
    req: ContextAnalysisRequest,
    user: User | None = Depends(require_auth_if_legacy_disabled),
    rate_limit_checked=Depends(check_rate_limit),
    csrf_checked=Depends(require_csrf),
    quota=Depends(check_quota_if_authenticated),
):
    """
    Run the Reasoner pipeline with external context.

    This endpoint accepts collected research context
    (facts, URLs, summaries) and runs deep, validated analysis.
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

    try:
        from reasoner.application.orchestrator import PipelineOrchestrator
        from reasoner.application.services.pipeline_service import PipelineService
        from reasoner.application.services.preset_service import PresetService

        _preset_service = PresetService()
        _orchestrator = PipelineOrchestrator(
            preset_service=_preset_service,
            pipeline_service=PipelineService(),
        )

        # Resolve preset and build router via orchestrator
        effective_preset, _router = _preset_service.build_router(req.preset)

        from reasoner.application.orchestrator import PreflightDecision
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
            verbose=False,
            domain=req.domain if hasattr(req, "domain") else None,
        )

        # Create state with the external context
        state = PipelineState(problem=req.problem, preset_name=req.preset)

        # Validate URLs inside context items before injection
        from reasoner.security.url_validator import is_safe_url
        for item in req.context:
            for _key, value in item.items():
                if isinstance(value, str) and value.startswith(("http://", "https://")):
                    if not is_safe_url(value):
                        raise HTTPException(
                            status_code=403,
                            detail=f"Unsafe URL in context: {value}",
                        )

        # Inject external context directly into the state
        # This bypasses the normal search/vetting phases
        state.web_discovery_results = req.context
        state.vetted_context = req.context

        # Run the appropriate method pipeline.
        #
        # This is a hand-rolled phase sequence, not WorkflowRunner: the endpoint
        # supplies its own vetted context and wants four phases, not a whole
        # method. It therefore gets no retries, no quality gate, no PHASE_*
        # events and no spend ceiling -- a pre-existing gap, listed here rather
        # than silently carried, since routing it through the runner changes
        # what a billed call costs.
        services = _svc(pipeline)
        if req.method == "jury":
            await run_jury_generate_phase(state, services)
            await run_jury_critique_phase(
                state, services, batch_critique=pipeline.batch_critique_jury
            )
            await run_jury_verify_and_meta_eval_phase(state, services)
        else:
            await run_perspectives_phase(state, services, perspectives=pipeline.perspectives)
            await run_critique_phase(state, services)
            await run_stress_test_phase(state, services)

        await run_synthesis_phase(state, services)

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
