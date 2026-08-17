"""Health check endpoint — /api/health.

Comprehensive health check for system status and subsystem pass/fail.
Public response omits internal details (memory bytes, pool sizes, Python version).
Full diagnostics available with valid X-Admin-Key header.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from reasoner.api.admin_auth import verify_admin_key
from reasoner.api.cache import CACHE_DIR
from reasoner.api.dependencies import get_optional_user
from reasoner.application.services.health_service import check_health
from reasoner.core.settings import settings
from reasoner.domain.saas import User

router = APIRouter()


@router.get("/api/health")
async def health_check(
    request: Request,
    user: User | None = Depends(get_optional_user),
):
    """Comprehensive health check endpoint."""
    is_admin = verify_admin_key(request.headers.get("X-Admin-Key"))
    if settings.ENVIRONMENT == "production":
        is_admin = is_admin and user is not None and "admin" in user.scopes
    cache_file_count = len(list(CACHE_DIR.glob("*.json"))) if is_admin else None
    return await check_health(is_admin=is_admin, cache_file_count=cache_file_count)
