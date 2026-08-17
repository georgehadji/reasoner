"""Shared admin-key verification primitive.

security-remediation-plan.md Phase 5 item 1: five call sites (admin.py,
api/__init__.py's cache-clear route, routes/errors.py, routes/feedback.py,
routes/health.py) each hand-rolled the same constant-time
``X-Admin-Key`` comparison against ``settings.ADMIN_API_KEY``. This is the
one shared primitive; each route keeps its own policy layer on top (some
also require a scoped JWT, some only in production, health.py wants a pure
boolean rather than a raised exception) since those policies genuinely
differ and collapsing them into one dependency would either overreach or
underreach for at least one call site.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request

from reasoner.core.settings import settings


def verify_admin_key(provided: str | None) -> bool:
    """Constant-time compare against the configured admin key.

    False whenever no key is configured -- an unset ADMIN_API_KEY must
    never compare as a match against an empty/missing header.
    """
    admin_key = settings.ADMIN_API_KEY or ""
    if not admin_key:
        return False
    return secrets.compare_digest(provided or "", admin_key)


def require_admin_key(request: Request) -> None:
    """FastAPI dependency: raise 403 unless the request carries a valid
    X-Admin-Key header. Use for routes with no additional scope policy."""
    if not verify_admin_key(request.headers.get("X-Admin-Key")):
        raise HTTPException(status_code=403, detail="Admin access required")


__all__ = ["verify_admin_key", "require_admin_key"]
