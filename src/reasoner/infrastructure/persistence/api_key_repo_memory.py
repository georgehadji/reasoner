"""
In-memory ApiKeyRepository — for tests and single-process local development.

Keys live in the process and vanish on restart, so the service factory only
selects this outside production environments.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from reasoner.core.ports.api_key_repository import ApiKeyRepository
from reasoner.domain.api_keys import ApiKey


class InMemoryApiKeyRepository(ApiKeyRepository):
    """Dict-backed API key storage keyed by key id."""

    def __init__(self) -> None:
        self._keys: dict[UUID, ApiKey] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        user_id: str,
        name: str,
        key_hash: str,
        key_prefix: str,
        scopes: frozenset[str],
        expires_at: datetime | None = None,
    ) -> ApiKey:
        record = ApiKey(
            id=uuid4(),
            user_id=UUID(str(user_id)),
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=frozenset(scopes),
            expires_at=expires_at,
        )
        async with self._lock:
            self._keys[record.id] = record
        return record

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        async with self._lock:
            for record in self._keys.values():
                if record.key_hash == key_hash:
                    return record
        return None

    async def list_for_user(self, user_id: str, include_revoked: bool = False) -> list[ApiKey]:
        uid = UUID(str(user_id))
        async with self._lock:
            records = [
                k
                for k in self._keys.values()
                if k.user_id == uid and (include_revoked or not k.is_revoked)
            ]
        return sorted(records, key=lambda k: k.created_at, reverse=True)

    async def count_live_for_user(self, user_id: str) -> int:
        uid = UUID(str(user_id))
        async with self._lock:
            return sum(1 for k in self._keys.values() if k.user_id == uid and k.is_usable())

    async def revoke(self, user_id: str, key_id: UUID) -> bool:
        uid = UUID(str(user_id))
        async with self._lock:
            record = self._keys.get(key_id)
            if record is None or record.user_id != uid or record.is_revoked:
                return False
            self._keys[key_id] = ApiKey(
                id=record.id,
                user_id=record.user_id,
                name=record.name,
                key_hash=record.key_hash,
                key_prefix=record.key_prefix,
                scopes=record.scopes,
                last_used_at=record.last_used_at,
                expires_at=record.expires_at,
                revoked_at=datetime.now(UTC),
                created_at=record.created_at,
            )
            return True

    async def touch_last_used(self, key_id: UUID) -> None:
        async with self._lock:
            record = self._keys.get(key_id)
            if record is None:
                return
            self._keys[key_id] = ApiKey(
                id=record.id,
                user_id=record.user_id,
                name=record.name,
                key_hash=record.key_hash,
                key_prefix=record.key_prefix,
                scopes=record.scopes,
                last_used_at=datetime.now(UTC),
                expires_at=record.expires_at,
                revoked_at=record.revoked_at,
                created_at=record.created_at,
            )

    async def get_owner(self, key_id: UUID) -> UUID | None:
        async with self._lock:
            record = self._keys.get(key_id)
        return record.user_id if record else None
