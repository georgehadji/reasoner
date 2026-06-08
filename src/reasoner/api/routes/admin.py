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
