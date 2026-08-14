"""User-owned API key management endpoints.

Keys are created, listed, and revoked by their owner. The plaintext key is
returned exactly once, at creation.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from reasoner.api.auth_deps import check_rate_limit, require_csrf
from reasoner.api.dependencies import _get_api_key_service, get_current_user
from reasoner.application.services.api_key_service import ApiKeyLimitError, MAX_EXPIRY_DAYS
from reasoner.domain.api_keys import (
    ASSIGNABLE_SCOPES,
    DEFAULT_SCOPES,
    InvalidScopeError,
    MAX_KEYS_PER_USER,
)
from reasoner.domain.saas import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/account/api-keys", tags=["api-keys"])


class CreateKeyRequest(BaseModel):
    """Request body for minting a key."""

    name: str = Field(..., min_length=1, max_length=64)
    scopes: list[str] | None = Field(
        None,
        description=f"Subset of {sorted(ASSIGNABLE_SCOPES)}. Defaults to read-only.",
    )
    expires_in_days: int | None = Field(None, ge=1, le=MAX_EXPIRY_DAYS)


@router.get("")
async def list_api_keys(
    include_revoked: bool = False,
    user: User = Depends(get_current_user),
):
    """List the caller's API keys. Secrets are never returned."""
    service = _get_api_key_service()
    keys = await service.list_keys(str(user.id), include_revoked=include_revoked)
    return {
        "keys": [k.to_dict() for k in keys],
        "limits": {
            "max_keys": MAX_KEYS_PER_USER,
            "max_expiry_days": MAX_EXPIRY_DAYS,
            "assignable_scopes": sorted(ASSIGNABLE_SCOPES),
            "default_scopes": sorted(DEFAULT_SCOPES),
        },
    }


@router.post("", status_code=201, dependencies=[Depends(check_rate_limit), Depends(require_csrf)])
async def create_api_key(
    body: CreateKeyRequest,
    user: User = Depends(get_current_user),
):
    """Mint a new API key.

    The response contains the only copy of the plaintext key that will ever
    exist — it cannot be recovered afterwards.
    """
    service = _get_api_key_service()
    try:
        minted = await service.create(
            str(user.id),
            name=body.name,
            scopes=set(body.scopes) if body.scopes else None,
            expires_in_days=body.expires_in_days,
        )
    except InvalidScopeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ApiKeyLimitError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "status": "created",
        "warning": "Store this key now. It cannot be shown again.",
        **minted.to_dict(),
    }


@router.delete("/{key_id}", dependencies=[Depends(check_rate_limit), Depends(require_csrf)])
async def revoke_api_key(
    key_id: str,
    user: User = Depends(get_current_user),
):
    """Revoke one of the caller's API keys."""
    try:
        parsed = UUID(key_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid key id") from exc

    service = _get_api_key_service()
    revoked = await service.revoke(str(user.id), parsed)
    if not revoked:
        # Same response whether the key belongs to someone else or does not
        # exist, so ids cannot be probed for existence.
        raise HTTPException(status_code=404, detail="API key not found")

    return {"status": "revoked", "id": key_id}
