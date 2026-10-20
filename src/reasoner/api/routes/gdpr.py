"""GDPR data erasure endpoint (DM3)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import require_key_scope
from reasoner.domain.saas import User
from reasoner.infrastructure.persistence.event_store import get_event_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gdpr"])


@router.delete(
    "/api/user/data",
    summary="Erase all user data (GDPR)",
    description="Permanently delete all data associated with the authenticated user.",
    dependencies=[Depends(require_csrf)],
)
async def erase_user_data(user: User = Depends(require_key_scope("history:delete"))) -> dict:
    """Permanently erase all pipeline data, cache entries, and logs for the requesting user.

    This operation is **irreversible**. A confirmation parameter is required.
    """
    # The store the events go to. A bare EventStore() is the SQLite class, so
    # on the Postgres backend this erased nothing and still reported
    # "completed" (docs/plans/audit-remediation-2026-10-20.md PER-3).
    store = get_event_store()
    from reasoner.api.cache import clear_memory_cache
    from reasoner.application.services.data_eraser import UserDataEraser

    eraser = UserDataEraser(store, clear_cache_fn=clear_memory_cache)
    receipt = await eraser.erase(user.id)

    if receipt["status"] != "completed":
        logger.warning("GDPR erasure for user %s was partial: %s", user.id, receipt)
        raise HTTPException(
            status_code=500,
            detail=f"Erasure partially completed: deleted {receipt['deleted_aggregates']} aggregates",
        )

    logger.info("GDPR erasure completed for user %s: %d aggregates deleted", user.id, receipt["deleted_aggregates"])
    return receipt
