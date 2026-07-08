"""Admin endpoints — manual operations requiring ADMIN_API_KEY authentication."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from reasoner.core.settings import settings

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
