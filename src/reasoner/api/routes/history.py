"""Search history endpoints.

Every route reads through the HistoryRepository port, scoped to the caller:
there is no way to name another owner's entries (PER-12). An anonymous run's
entries belong to the anonymous owner, so no authenticated caller reaches them.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import get_current_user, require_key_scope
from reasoner.api.history import history_repo
from reasoner.domain.saas import User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/history")
async def get_history(
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Get search history for the authenticated user."""
    entries, total = await history_repo().list(str(user.id), limit, offset)
    return {
        "total": total,
        "entries": entries,
    }


@router.get("/api/history/tagged")
async def get_tagged_history(
    tag: str,
    user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=1000),
):
    """Get history entries by tag for the authenticated user."""
    entries, _ = await history_repo().list(str(user.id), limit, 0, tag=tag)
    return {
        "tag": tag,
        "total": len(entries),
        "entries": entries,
    }


@router.get("/api/history/{entry_id}")
async def get_history_entry(
    entry_id: str,
    user: User = Depends(get_current_user),
):
    """Get a specific history entry (must belong to the authenticated user)."""
    entry = await history_repo().get(str(user.id), entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


@router.delete("/api/history/{entry_id}")
async def delete_history_entry(
    entry_id: str,
    user: User = Depends(require_key_scope("history:delete")),
    csrf_checked=Depends(require_csrf),
):
    """Delete a history entry (must belong to the authenticated user)."""
    try:
        deleted = await history_repo().delete(str(user.id), entry_id)
    except OSError as e:
        logger.error(f"Failed to delete history entry {entry_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete entry") from e
    if not deleted:
        raise HTTPException(status_code=404, detail="Entry not found")
    return {"status": "deleted"}


@router.delete("/api/history")
async def clear_history(
    user: User = Depends(require_key_scope("history:delete")),
    csrf_checked=Depends(require_csrf),
):
    """Clear all history for the authenticated user."""
    cleared, failed = await history_repo().erase(str(user.id))
    return {"cleared": cleared, "failed": failed}
