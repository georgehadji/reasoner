"""Port: persistence contract for user-owned API keys."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable
from uuid import UUID

from reasoner.domain.api_keys import ApiKey


@runtime_checkable
class ApiKeyRepository(Protocol):
    """Storage for API key records. Never stores plaintext secrets."""

    async def create(
        self,
        user_id: str,
        name: str,
        key_hash: str,
        key_prefix: str,
        scopes: frozenset[str],
        expires_at: datetime | None = None,
    ) -> ApiKey:
        """Persist a new key record and return it."""
        ...

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        """Look up a key by its stored hash. Returns None when unknown."""
        ...

    async def list_for_user(self, user_id: str, include_revoked: bool = False) -> list[ApiKey]:
        """Return the user's keys, newest first."""
        ...

    async def count_live_for_user(self, user_id: str) -> int:
        """Number of keys that are neither revoked nor expired."""
        ...

    async def revoke(self, user_id: str, key_id: UUID) -> bool:
        """Revoke a key the user owns. Returns False when not found.

        Must scope the update by ``user_id`` so one user can never revoke
        another user's key by guessing its id.
        """
        ...

    async def touch_last_used(self, key_id: UUID) -> None:
        """Record that the key was just used. Best-effort, never blocking."""
        ...

    async def get_owner(self, key_id: UUID) -> UUID | None:
        """Return the user id that owns ``key_id``, or None."""
        ...
