"""GDPR data erasure endpoint (DM3)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import get_current_user
from reasoner.domain.saas import User
from reasoner.infrastructure.persistence.event_store import EventStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gdpr"])


@router.delete(
    "/api/user/data",
    summary="Erase all user data (GDPR)",
    description="Permanently delete all data associated with the authenticated user.",
    dependencies=[Depends(require_csrf)],
)
async def erase_user_data(user: User = Depends(get_current_user)) -> dict:
    """Permanently erase all pipeline data, cache entries, and logs for the requesting user.

    This operation is **irreversible**. A confirmation parameter is required.
    """
    # Instantiate the event store
    store = EventStore()
    from reasoner.application.services.data_eraser import UserDataEraser
    from reasoner.api.cache import clear_memory_cache

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
