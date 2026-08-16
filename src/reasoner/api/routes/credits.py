"""Credit balance, ledger, and administrative grant endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import (
    _get_credit_service,
    _resolve_user_tier,
    check_rate_limit,
    get_current_user,
)
from reasoner.auth import Scope
from reasoner.domain.credits import (
    CREDITS_PER_USD,
    CreditReason,
    TIER_MONTHLY_CREDITS,
    credits_to_usd,
    monthly_allowance,
)
from reasoner.domain.saas import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/credits", tags=["credits"])


class GrantRequest(BaseModel):
    """Administrative credit grant."""

    user_id: str = Field(..., description="Target user UUID")
    credits: int = Field(..., gt=0, le=10_000_000, description="Credits to add")
    description: str | None = Field(None, max_length=200)
    reference_id: str | None = Field(
        None,
        max_length=120,
        description="Idempotency key — replaying it will not double-grant.",
    )


@router.get("")
async def get_credits(user: User = Depends(get_current_user)):
    """Return the caller's credit balance and this period's allowance.

    Also tops up the monthly tier allowance if it has not been granted yet,
    so a balance read is enough to keep an account current.
    """
    service = _get_credit_service()
    tier = await _resolve_user_tier(str(user.id))

    try:
        await service.ensure_monthly_allowance(str(user.id), tier)
    except Exception:
        logger.warning("Monthly allowance top-up failed", exc_info=True)

    balance = await service.get_balance(str(user.id))
    return {
        **balance.to_dict(),
        "tier": tier.value,
        "monthly_allowance": monthly_allowance(tier),
        "credits_per_usd": CREDITS_PER_USD,
    }


@router.get("/ledger")
async def get_ledger(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
):
    """Return the caller's credit ledger, newest entries first."""
    service = _get_credit_service()
    entries = await service.list_ledger(str(user.id), limit=limit, offset=offset)
    return {
        "entries": [e.to_dict() for e in entries],
        "limit": limit,
        "offset": offset,
    }


@router.get("/pricing")
async def get_credit_pricing():
    """Public reference for how credits map to money and tier allowances."""
    return {
        "credits_per_usd": CREDITS_PER_USD,
        "usd_per_credit": credits_to_usd(1),
        "tier_monthly_allowance": {
            tier.value: credits for tier, credits in TIER_MONTHLY_CREDITS.items()
        },
        "reasons": [r.value for r in CreditReason],
    }


@router.post("/grant", dependencies=[Depends(check_rate_limit), Depends(require_csrf)])
async def grant_credits(
    body: GrantRequest,
    user: User = Depends(get_current_user),
):
    """Grant credits to a user. Admin scope required."""
    if Scope.ADMIN.value not in getattr(user, "scopes", set()):
        raise HTTPException(status_code=403, detail="Admin scope required")

    service = _get_credit_service()
    try:
        entry = await service.grant(
            body.user_id,
            credits=body.credits,
            reason=CreditReason.ADMIN_ADJUSTMENT,
            reference_id=body.reference_id,
            description=body.description or f"Granted by {user.email}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("Admin %s granted %s credits to %s", user.id, body.credits, body.user_id)
    return {"status": "granted", "entry": entry.to_dict()}
