"""Search history endpoints."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from reasoner.api import history as _history_module
from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import get_current_user
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
    entries, total = _history_module._list_history(
        user_id=str(user.id), limit=limit, offset=offset
    )
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
    from reasoner.core.memory import TaggedMemory

    tagged = TaggedMemory(_history_module.HISTORY_DIR)
    entries = tagged.get_by_tag(tag, limit=limit)
    # Filter to current user's entries only
    user_entries = [e for e in entries if e.get("user_id") == str(user.id)]
    return {
        "tag": tag,
        "total": len(user_entries),
        "entries": user_entries,
    }


@router.get("/api/history/{entry_id}")
async def get_history_entry(
    entry_id: str,
    user: User = Depends(get_current_user),
):
    """Get a specific history entry (must belong to the authenticated user)."""
    safe_id = Path(entry_id).name
    path = _history_module.HISTORY_DIR / f"{safe_id}.json"
    if not path.exists() or not str(path.resolve()).startswith(str(_history_module.HISTORY_DIR.resolve())):
        raise HTTPException(status_code=404, detail="Entry not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("user_id") and data.get("user_id") != str(user.id):
        raise HTTPException(status_code=404, detail="Entry not found")
    return data


@router.delete("/api/history/{entry_id}")
async def delete_history_entry(
    entry_id: str,
    user: User = Depends(get_current_user),
    csrf_checked=Depends(require_csrf),
):
    """Delete a history entry (must belong to the authenticated user)."""
    safe_id = Path(entry_id).name
    path = _history_module.HISTORY_DIR / f"{safe_id}.json"
    try:
        if not path.exists() or not str(path.resolve()).startswith(str(_history_module.HISTORY_DIR.resolve())):
            raise HTTPException(status_code=404, detail="Entry not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("user_id") and data.get("user_id") != str(user.id):
            raise HTTPException(status_code=404, detail="Entry not found")
        path.unlink(missing_ok=True)
        return {"status": "deleted"}
    except HTTPException:
        raise
    except OSError as e:
        logger.error(f"Failed to delete history entry {entry_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete entry") from e


@router.delete("/api/history")
async def clear_history(
    user: User = Depends(get_current_user),
    csrf_checked=Depends(require_csrf),
):
    """Clear all history for the authenticated user."""
    cleared = 0
    failed = 0
    for f in _history_module.HISTORY_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if data.get("user_id") == str(user.id):
                f.unlink(missing_ok=True)
                cleared += 1
        except OSError as e:
            logger.warning(f"Failed to delete history file {f}: {e}")
            failed += 1
    return {"cleared": cleared, "failed": failed}
