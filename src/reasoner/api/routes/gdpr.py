"""GDPR data erasure endpoint (DM3)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import require_key_scope
from reasoner.domain.saas import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gdpr"])


@router.delete(
    "/api/user/data",
    summary="Erase all user data (GDPR)",
    description="Permanently delete all data associated with the authenticated user.",
    dependencies=[Depends(require_csrf)],
)
async def erase_user_data(user: User = Depends(require_key_scope("history:delete"))) -> dict:
    """Permanently erase everything the user produced: runs, uploads, vectors,
    history, long-term memory, cache keys, usage and billing rows.

    The same registry as account deletion, minus the account itself (the users
    row and the sign-in identity), which needs the account-delete scope.
    This operation is **irreversible**.
    """
    from reasoner.api.user_data import data_stores
    from reasoner.application.services.data_eraser import UserDataEraser

    receipt = await UserDataEraser(data_stores()).erase(str(user.id))

    if receipt["status"] != "completed":
        logger.warning("GDPR erasure for user %s was partial: %s", user.id, receipt)
        failed = ", ".join(f["store"] for f in receipt["failed"])
        raise HTTPException(
            status_code=500, detail=f"Erasure partially completed; not erased: {failed}"
        )

    logger.info("GDPR erasure completed for user %s: %s", user.id, receipt["erased"])
    return receipt
