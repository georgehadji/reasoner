"""Event store and pipeline management endpoints."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import get_current_user
from reasoner.domain.saas import User

from reasoner.application.queries import GetPipelineStatusQuery
from reasoner.api.history import _get_pipeline_owner
from reasoner.auth import Scope

logger = logging.getLogger(__name__)
router = APIRouter()


def _check_pipeline_ownership(pipeline_id: str, user: User) -> bool:
    """Return True if *user* is allowed to access *pipeline_id*."""
    # Admins can access any pipeline
    if hasattr(user, "scopes") and Scope.ADMIN.value in user.scopes:
        return True
    # Legacy pipelines without an owner are world-accessible (for backward compat)
    owner = _get_pipeline_owner(pipeline_id)
    if owner is None:
        return True
    return str(user.id) == owner


@router.get("/api/events/stats")
async def get_event_stats(user: User = Depends(get_current_user)):
    """Get event store statistics."""
    try:
        from reasoner.api import get_architecture_components

        event_store, _ = get_architecture_components()
        stats = await event_store.get_stats()
        return stats
    except Exception as e:
        logger.error(f"Event stats error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/pipelines")
async def list_pipelines(
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = None,
):
    """List pipelines from event store."""
    try:
        from reasoner.api import get_architecture_components

        event_store, _ = get_architecture_components()
        pipelines = await event_store.list_pipelines(
            limit=limit,
            offset=offset,
            status=status,
        )
        # Filter to only pipelines owned by the requesting user (unless admin)
        if not (hasattr(user, "scopes") and Scope.ADMIN.value in user.scopes):
            user_id_str = str(user.id)
            pipelines = [
                p for p in pipelines
                if _get_pipeline_owner(p.get("aggregate_id", p.get("id", ""))) in (None, user_id_str)
            ]
        return {"pipelines": pipelines, "total": len(pipelines)}
    except Exception as e:
        logger.error(f"List pipelines error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/pipelines/{pipeline_id}")
async def get_pipeline_status(
    pipeline_id: str,
    user: User = Depends(get_current_user),
):
    """Get pipeline status from event store."""
    if not _check_pipeline_ownership(pipeline_id, user):
        raise HTTPException(status_code=403, detail="Not authorized to access this pipeline")
    try:
        from reasoner.api import get_architecture_components

        event_store, handler_registry = get_architecture_components()

        query = GetPipelineStatusQuery(
            query_id=f"status-{pipeline_id}",
            timestamp=time.time(),
            pipeline_id=pipeline_id,
        )

        result = await handler_registry.handle_query(query)
        return result
    except Exception as e:
        logger.error(f"Get pipeline error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/pipelines/{pipeline_id}/resume")
async def resume_pipeline(
    pipeline_id: str,
    user: User = Depends(get_current_user),
    csrf_checked=Depends(require_csrf),
):
    """Resume a paused/failed pipeline from event history."""
    if not _check_pipeline_ownership(pipeline_id, user):
        raise HTTPException(status_code=403, detail="Not authorized to access this pipeline")
    try:
        from reasoner.api import get_architecture_components
        from reasoner.application.commands import ResumePipelineCommand

        _, handler_registry = get_architecture_components()
        command = ResumePipelineCommand(
            command_id=f"resume-{pipeline_id}",
            timestamp=time.time(),
            pipeline_id=pipeline_id,
        )
        result = await handler_registry.handle_command(command)
        return result
    except ValueError as e:
        return {"error": str(e), "can_resume": False}
    except Exception as e:
        logger.error(f"Resume pipeline error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/pipelines/{pipeline_id}/resume-stream")
async def resume_pipeline_stream(
    pipeline_id: str,
    user: User = Depends(get_current_user),
    csrf_checked=Depends(require_csrf),
):
    if not _check_pipeline_ownership(pipeline_id, user):
        raise HTTPException(status_code=403, detail="Not authorized to access this pipeline")
    """Resume a pipeline by reconstructing its context and starting a fresh stream.

    This is a "resume-as-restart" approach: the pipeline's problem, preset, and
    prior synthesis are recovered from the event store, then a new run is started.
    The original pipeline metadata is returned in the first SSE event.
    """
    from fastapi.responses import StreamingResponse

    from reasoner.api import get_architecture_components
    from reasoner.application.commands import ResumePipelineCommand
    from reasoner.api.streaming import run_stream
    from reasoner.api.schemas import RunRequest
    from reasoner.api.serializers import _event

    _, handler_registry = get_architecture_components()
    command = ResumePipelineCommand(
        command_id=f"resume-stream-{pipeline_id}",
        timestamp=time.time(),
        pipeline_id=pipeline_id,
    )

    try:
        result = await handler_registry.handle_command(command)
    except ValueError as e:
        return {"error": str(e), "can_resume": False}
    except Exception as e:
        logger.error(f"Resume stream error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

    problem = result.get("problem", "")
    preset = result.get("preset", "auto-budget")

    if not problem:
        return {"error": "Recovered problem is empty", "can_resume": False}

    req = RunRequest(
        problem=problem,
        preset=preset,
        top_k=2,
        sequential=False,
        no_cache=True,
        client_run_id=pipeline_id,
    )

    async def stream_with_resume_meta():
        yield _event({
            "type": "resume_meta",
            "original_pipeline_id": pipeline_id,
            "phases_completed": result.get("phases_completed", []),
            "previous_synthesis": result.get("previous_synthesis", ""),
        })
        async for chunk in run_stream(req, user_id=str(user.id)):
            yield chunk

    return StreamingResponse(
        stream_with_resume_meta(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/api/pipelines/{pipeline_id}")
async def delete_pipeline(
    pipeline_id: str,
    user: User = Depends(get_current_user),
    csrf_checked=Depends(require_csrf),
):
    """Delete pipeline and all events (GDPR compliance)."""
    if not _check_pipeline_ownership(pipeline_id, user):
        raise HTTPException(status_code=403, detail="Not authorized to access this pipeline")
    try:
        from reasoner.api import get_architecture_components

        event_store, _ = get_architecture_components()
        await event_store.delete_aggregate(pipeline_id)
        return {"status": "deleted", "pipeline_id": pipeline_id}
    except Exception as e:
        logger.error(f"Delete pipeline error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
