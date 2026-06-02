"""Error reporting and admin error log endpoints.

POST /api/error-report  — client error reporting (no auth required)
GET  /api/admin/errors   — admin-only error log viewer
"""

from __future__ import annotations

import secrets
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel

from reasoner.api.dependencies import check_rate_limit, get_current_user
from reasoner.core.settings import settings
from reasoner.domain.saas import User
from reasoner.infrastructure.persistence.error_store import ErrorStore, ErrorEntry

router = APIRouter()

_error_store = ErrorStore()


class ClientErrorReport(BaseModel):
    message: str
    source: str = "client"
    stack: str | None = None
    url: str | None = None
    user_agent: str | None = None


@router.post("/api/error-report")
async def report_client_error(req: ClientErrorReport, request: Request):
    """Accept error reports from the frontend. No auth required."""
    from reasoner.logging_utils import get_correlation_id

    entry = ErrorEntry(
        level="error",
        source=req.source,
        message=req.message,
        correlation_id=get_correlation_id(),
        path=req.url,
        traceback=req.stack,
        extra={"user_agent": req.user_agent},
    )
    row_id = await _error_store.insert(entry)
    return {"status": "logged", "id": row_id}


@router.get("/api/admin/errors", dependencies=[Depends(check_rate_limit)])
async def error_logs(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    level: str | None = Query(None),
    source: str | None = Query(None),
    hours: int | None = Query(None),
    admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    user: User = Depends(get_current_user),
):
    """Admin-only endpoint returning recent error logs."""
    if not settings.ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="Admin endpoint not configured")
    from reasoner.auth import Scope
    user_scopes = getattr(user, "scopes", set())
    if Scope.ADMIN.value not in user_scopes:
        raise HTTPException(status_code=403, detail="Admin scope required")
    if not admin_key or not secrets.compare_digest(admin_key, settings.ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Unauthorized")

    errors = await _error_store.query(
        limit=limit, offset=offset, level=level, source=source, hours=hours,
    )
    stats = await _error_store.get_stats(days=7)

    import logging
    logger = logging.getLogger(__name__)
    logger.info("Admin error-logs accessed by user %s", user.id)
    return {
        "errors": errors,
        "stats": {
            "total_7d": stats.total,
            "by_level": stats.by_level,
            "by_source": stats.by_source,
            "recent_1h": stats.recent_count_1h,
            "recent_24h": stats.recent_count_24h,
            "unique_paths": stats.unique_paths,
        },
    }
