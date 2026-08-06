"""External context integration endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import (
    check_quota_if_authenticated,
    check_rate_limit,
    get_optional_user,
)
from reasoner.api.schemas import ContextAnalysisRequest
from reasoner.domain.saas import User
from reasoner.domain.pipeline_state import PipelineState

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/run-with-context")
async def run_with_context(
    req: ContextAnalysisRequest,
    user: User | None = Depends(get_optional_user),
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
        from reasoner.application.services.preset_service import PresetService
        from reasoner.application.services.pipeline_service import PipelineService
        from reasoner.application.orchestrator import PipelineOrchestrator

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

        # Run the appropriate method pipeline
        if req.method == "jury":
            await pipeline._phase_jury_generate(state)
            await pipeline._phase_jury_critique(state)
            await pipeline._phase_jury_verify_and_meta_eval(state)
        else:
            # Multi-perspective
            await pipeline._phase_2_perspectives(state)
            await pipeline._phase_3_critique(state)
            await pipeline._phase_4_stress_test(state)

        # Run synthesis
        await pipeline._phase_synthesis(state)

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
