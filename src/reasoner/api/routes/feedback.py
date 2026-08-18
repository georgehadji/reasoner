"""Feedback and admin feedback stats endpoints.

POST /api/feedback           — submit feedback from a pipeline run
GET  /api/admin/feedback-stats — admin-only feedback statistics
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from reasoner.api.admin_auth import verify_admin_key
from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import check_rate_limit, get_current_user
from reasoner.core.settings import settings
from reasoner.domain.saas import User
from reasoner.infrastructure.persistence.feedback_store import FeedbackStore, FeedbackEntry

router = APIRouter()
_feedback_store = FeedbackStore()


class FeedbackRequest(BaseModel):
    conversation_id: str = Field(..., max_length=200)
    message_id: str = Field(..., max_length=200)
    rating: str = Field(..., max_length=10)  # "up" | "down"
    reason: str | None = Field(None, max_length=500)
    comment: str | None = Field(None, max_length=4_000)
    context: dict | None = None


@router.post("/api/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    request: Request,
    csrf_checked=Depends(require_csrf),
):
    """Submit feedback for a pipeline run."""
    entry = FeedbackEntry(
        conversation_id=req.conversation_id,
        message_id=req.message_id,
        rating=req.rating,
        reason=req.reason,
        comment=req.comment,
        context=req.context,
    )
    row_id = await _feedback_store.insert(entry)
    return {"status": "received", "id": row_id}


@router.get("/api/admin/feedback-stats", dependencies=[Depends(check_rate_limit)])
async def feedback_stats(
    request: Request,
    days: int = 30,
    admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    user: User = Depends(get_current_user),
):
    """Admin-only endpoint returning feedback statistics."""
    if not settings.ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="Admin endpoint not configured")
    from reasoner.auth import Scope
    user_scopes = getattr(user, "scopes", set())
    if Scope.ADMIN.value not in user_scopes:
        raise HTTPException(status_code=403, detail="Admin scope required")
    if not verify_admin_key(admin_key):
        raise HTTPException(status_code=401, detail="Unauthorized")

    stats = await _feedback_store.get_stats(days=days)

    return {
        "total_entries": stats.total_entries,
        "upvotes": stats.upvotes,
        "downvotes": stats.downvotes,
        "downvote_reasons": stats.downvote_reasons,
        "avg_comment_length": round(stats.avg_comment_length, 2),
        "entries_with_context": stats.entries_with_context,
        "period_days": stats.period_days,
    }
