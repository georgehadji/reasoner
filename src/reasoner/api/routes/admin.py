"""Admin endpoints — manual operations requiring ADMIN_API_KEY authentication."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from reasoner.core.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin")


def _require_admin(request: Request) -> None:
    """Raise 403 unless request carries a valid X-Admin-Key header."""
    admin_key = settings.ADMIN_API_KEY or ""
    if not admin_key:
        raise HTTPException(status_code=403, detail="Admin key not configured")
    import secrets
    provided = request.headers.get("X-Admin-Key", "")
    if not secrets.compare_digest(provided, admin_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")


@router.post("/compaction/run")
async def trigger_compaction(request: Request, dry_run: bool = False):
    """Manually trigger event store compaction.

    Use ?dry_run=true to count eligible rows without deleting.
    Requires X-Admin-Key header.
    """
    _require_admin(request)

    if settings.DATABASE_URL:
        from reasoner.infrastructure.persistence.postgres_store import get_postgres_store
        store = get_postgres_store()
    else:
        from reasoner.infrastructure.persistence.event_store import get_event_store
        store = get_event_store()

    from reasoner.application.services.compaction_service import CompactionService
    service = CompactionService(store)
    result = await service.run_once(dry_run=dry_run)
    return {"status": "ok", **result}


# ── Dead-Letter Queue (Phase 0.3) ─────────────────────────────────────────────


@router.get("/dead-letter")
async def list_dead_letter_events(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    event_type: str | None = None,
):
    """List dead-letter events with pagination.

    Requires X-Admin-Key header.
    """
    _require_admin(request)
    from reasoner.application.services.deadletter_replay_service import EventBusReplayService
    service = EventBusReplayService()
    return await service.list_events(limit=min(limit, 500), offset=offset, event_type_filter=event_type)


@router.post("/dead-letter/replay")
async def replay_dead_letter_events(
    request: Request,
    event_ids: list[str] | None = None,
    max_count: int = 50,
):
    """Replay dead-letter events through the EventBus.

    Optionally specify event_ids to replay specific events.
    Requires X-Admin-Key header.
    """
    _require_admin(request)
    from reasoner.application.services.deadletter_replay_service import EventBusReplayService
    service = EventBusReplayService()
    result = await service.replay_events(event_ids=event_ids, max_count=min(max_count, 200))
    return {"status": "ok", **result}


# ── Neuro Lifecycle Maintenance (Phase 1.7) ───────────────────────────────────


@router.post("/cron/neuro-maintenance")
async def trigger_neuro_maintenance(request: Request):
    """Run neuro lifecycle maintenance: archive hot→warm→cold sessions.

    Sets the cron heartbeat metric on success.
    Requires X-Admin-Key header.
    Called by external scheduler (e.g., cron: curl -X POST .../api/admin/cron/neuro-maintenance).
    """
    _require_admin(request)
    from reasoner.api.cron import run_neuro_maintenance
    result = await run_neuro_maintenance()
    return {"status": "ok", **result}


# ── ACR (Adaptive Capability Router) Admin —───────────────────────────────────


@router.get("/acr/status")
async def acr_status(request: Request):
    """Return ACR current mode, model count, telemetry volume.

    Requires X-Admin-Key header.
    """
    _require_admin(request)
    from reasoner.core.settings import settings as app_settings
    return {
        "acr_enabled": app_settings.ACR_ENABLED,
        "acr_mode": app_settings.ACR_MODE,
        "acr_learning_enabled": app_settings.ACR_LEARNING_ENABLED,
        "acr_benchmarks_enabled": app_settings.ACR_BENCHMARKS_ENABLED,
        "exploration_rate_budget": app_settings.ACR_EXPLORATION_RATE_BUDGET,
        "exploration_rate_premium": app_settings.ACR_EXPLORATION_RATE_PREMIUM,
        "warmup_calls": app_settings.ACR_BENCHMARK_WARMUP_CALLS,
    }


@router.get("/acr/leaderboard/{role}")
async def acr_leaderboard(
    request: Request,
    role: str,
    window_hours: int = 168,
    limit: int = 10,
):
    """Top models for a pipeline role, ranked by telemetry quality.

    Requires X-Admin-Key header.
    """
    _require_admin(request)
    try:
        from reasoner.infrastructure.telemetry.call_telemetry_store import (
            SQLiteCallTelemetryStore,
        )
        store = SQLiteCallTelemetryStore()
        leaderboard = await store.query_role_leaderboard(
            role=role, window_hours=window_hours, limit=limit,
        )
        return {
            "role": role,
            "window_hours": window_hours,
            "leaderboard": [
                {
                    "model_id": s.model_id,
                    "total_calls": s.total_calls,
                    "success_rate": s.success_rate,
                    "avg_latency_ms": s.avg_latency_ms,
                    "avg_critique_score": s.avg_critique_score,
                    "vendor": s.vendor,
                    "bloc": s.bloc,
                }
                for s in leaderboard
            ],
        }
    except Exception as exc:
        logger.exception("ACR leaderboard query failed for role '%s'", role)
        raise HTTPException(status_code=500, detail=f"Leaderboard query failed: {exc}") from exc


@router.get("/acr/profile/{model_id}")
async def acr_profile(request: Request, model_id: str):
    """Return a model's capability profile.

    Requires X-Admin-Key header.
    """
    _require_admin(request)
    try:
        from reasoner.infrastructure.llm.capability_registry import (
            CapabilityRegistry,
        )
        registry = CapabilityRegistry()
        profile = registry.get_profile(model_id)
        if profile is None:
            return {"model_id": model_id, "error": "Unknown model"}
        return {
            "model_id": profile.model_id,
            "constraints": {
                "max_context_tokens": profile.constraints.max_context_tokens,
                "cost_per_1k_input_usd": profile.constraints.cost_per_1k_input_usd,
                "cost_per_1k_output_usd": profile.constraints.cost_per_1k_output_usd,
                "supports_tools": profile.constraints.supports_tools,
                "supports_vision": profile.constraints.supports_vision,
                "supports_json_mode": profile.constraints.supports_json_mode,
                "vendor": profile.constraints.vendor,
                "bloc": profile.constraints.bloc,
            },
            "capabilities": dict(profile.capabilities.scores) if profile.capabilities else {},
            "has_capabilities": profile.has_capabilities,
        }
    except Exception as exc:
        logger.exception("ACR profile query failed for model '%s'", model_id)
        raise HTTPException(status_code=500, detail=f"Profile query failed: {exc}") from exc


@router.post("/acr/mode")
async def acr_set_mode(request: Request, mode: str):
    """Switch ACR operating mode: shadow, advisory, or adaptive.

    Requires X-Admin-Key header.
    """
    _require_admin(request)
    valid_modes = {"shadow", "advisory", "adaptive"}
    if mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Choose from: {', '.join(sorted(valid_modes))}")
    # Mode change applies to the next pipeline run via settings at runtime
    import os as _os
    _os.environ["ACR_MODE"] = mode
    # Also update the live settings singleton
    from reasoner.core.settings import settings as app_settings
    app_settings.ACR_MODE = mode
    return {"status": "ok", "mode": mode}
