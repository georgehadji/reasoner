"""
API Key Service — mint, list, revoke, and authenticate user API keys.

Business rules enforced here:
- A key's scopes can never exceed what a user may assign to themselves.
- Keys are capped per user to bound credential sprawl.
- Authentication rejects revoked and expired keys, and refreshes ``last_used_at``
  without blocking the request.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from reasoner.core.ports.api_key_repository import ApiKeyRepository
from reasoner.domain.api_keys import (
    ApiKey,
    MAX_KEYS_PER_USER,
    generate_key,
    hash_key,
    normalize_scopes,
)

logger = logging.getLogger(__name__)

#: Longest lifetime a user may set on a key.
MAX_EXPIRY_DAYS = 365

#: Name length bound — long enough to be descriptive, short enough to render.
MAX_NAME_LENGTH = 64


class ApiKeyLimitError(Exception):
    """Raised when a user already holds the maximum number of live keys."""


@dataclass(frozen=True, slots=True)
class MintedKey:
    """Result of creating a key. ``plaintext`` is returned exactly once."""

    key: ApiKey
    plaintext: str

    def to_dict(self) -> dict:
        return {**self.key.to_dict(), "key": self.plaintext}


class ApiKeyService:
    """Orchestrates the API key lifecycle."""

    def __init__(self, repository: ApiKeyRepository):
        self._repository = repository

    # ── Lifecycle ──────────────────────────────────────────────────────

    async def create(
        self,
        user_id: str,
        name: str,
        scopes: Optional[set[str]] = None,
        expires_in_days: Optional[int] = None,
    ) -> MintedKey:
        """Mint a key for ``user_id``.

        Raises:
            ValueError: on an empty name or an out-of-range expiry.
            InvalidScopeError: on a scope the user may not assign.
            ApiKeyLimitError: when the per-user key cap is reached.
        """
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("Key name is required.")
        if len(clean_name) > MAX_NAME_LENGTH:
            raise ValueError(f"Key name must be at most {MAX_NAME_LENGTH} characters.")

        if expires_in_days is not None and not 1 <= expires_in_days <= MAX_EXPIRY_DAYS:
            raise ValueError(f"Expiry must be between 1 and {MAX_EXPIRY_DAYS} days.")

        live = await self._repository.count_live_for_user(user_id)
        if live >= MAX_KEYS_PER_USER:
            raise ApiKeyLimitError(
                f"Key limit reached ({MAX_KEYS_PER_USER}). Revoke an existing key first."
            )

        granted = normalize_scopes(scopes)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=expires_in_days)
            if expires_in_days
            else None
        )

        minted = generate_key()
        record = await self._repository.create(
            user_id=user_id,
            name=clean_name,
            key_hash=minted.key_hash,
            key_prefix=minted.key_prefix,
            scopes=granted,
            expires_at=expires_at,
        )
        logger.info("API key %s created for user %s", record.key_prefix, user_id)
        return MintedKey(key=record, plaintext=minted.plaintext)

    async def list_keys(self, user_id: str, include_revoked: bool = False) -> list[ApiKey]:
        return await self._repository.list_for_user(user_id, include_revoked=include_revoked)

    async def revoke(self, user_id: str, key_id: UUID) -> bool:
        """Revoke a key the caller owns. Returns False when not found."""
        revoked = await self._repository.revoke(user_id, key_id)
        if revoked:
            logger.info("API key %s revoked by user %s", key_id, user_id)
        return revoked

    # ── Authentication ─────────────────────────────────────────────────

    async def authenticate(self, plaintext: str) -> Optional[ApiKey]:
        """Resolve a plaintext key to its record, or None if it cannot be used.

        Returns None for unknown, revoked, and expired keys alike so callers
        cannot distinguish between them.
        """
        record = await self._repository.get_by_hash(hash_key(plaintext))
        if record is None or not record.is_usable():
            return None

        # Usage tracking must never delay or fail the request it describes.
        try:
            asyncio.create_task(self._touch(record.id))
        except RuntimeError:  # no running loop (sync test context)
            pass
        return record

    async def _touch(self, key_id: UUID) -> None:
        try:
            await self._repository.touch_last_used(key_id)
        except Exception as exc:
            logger.debug("Failed to update last_used_at for key %s: %s", key_id, exc)


__all__ = ["ApiKeyService", "ApiKeyLimitError", "MintedKey", "MAX_EXPIRY_DAYS"]
