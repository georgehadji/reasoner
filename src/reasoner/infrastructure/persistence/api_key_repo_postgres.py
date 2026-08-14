"""Postgres implementation of ApiKeyRepository."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import asyncpg

from reasoner.core.ports.api_key_repository import ApiKeyRepository
from reasoner.domain.api_keys import ApiKey

logger = logging.getLogger(__name__)

_COLUMNS = (
    "id, user_id, name, key_hash, key_prefix, scopes, "
    "last_used_at, expires_at, revoked_at, created_at"
)


def _to_key(row: asyncpg.Record) -> ApiKey:
    return ApiKey(
        id=row["id"],
        user_id=row["user_id"],
        name=row["name"],
        key_hash=row["key_hash"],
        key_prefix=row["key_prefix"],
        scopes=frozenset(row["scopes"] or ()),
        last_used_at=row["last_used_at"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
        created_at=row["created_at"],
    )


class PostgresApiKeyRepository(ApiKeyRepository):
    """API key storage in PostgreSQL."""

    _pool: asyncpg.Pool | None = None
    _pool_lock: asyncio.Lock | None = None

    def __init__(self, dsn: str, pool_size: int | None = None):
        self._dsn = dsn
        self._pool_size = (
            pool_size
            if pool_size is not None
            else int(os.environ.get("DB_POOL_SIZE", "10"))
        )

    async def _get_pool(self) -> asyncpg.Pool:
        if PostgresApiKeyRepository._pool_lock is None:
            PostgresApiKeyRepository._pool_lock = asyncio.Lock()

        if PostgresApiKeyRepository._pool is not None:
            return PostgresApiKeyRepository._pool

        async with PostgresApiKeyRepository._pool_lock:
            if PostgresApiKeyRepository._pool is None:
                PostgresApiKeyRepository._pool = await asyncpg.create_pool(
                    self._dsn,
                    min_size=1,
                    max_size=self._pool_size,
                )
            return PostgresApiKeyRepository._pool

    async def create(
        self,
        user_id: str,
        name: str,
        key_hash: str,
        key_prefix: str,
        scopes: frozenset[str],
        expires_at: Optional[datetime] = None,
    ) -> ApiKey:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            "INSERT INTO api_keys (user_id, name, key_hash, key_prefix, scopes, expires_at) "
            f"VALUES ($1, $2, $3, $4, $5, $6) RETURNING {_COLUMNS}",
            UUID(str(user_id)),
            name,
            key_hash,
            key_prefix,
            sorted(scopes),
            expires_at,
        )
        return _to_key(row)

    async def get_by_hash(self, key_hash: str) -> Optional[ApiKey]:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            f"SELECT {_COLUMNS} FROM api_keys WHERE key_hash = $1",
            key_hash,
        )
        return _to_key(row) if row else None

    async def list_for_user(self, user_id: str, include_revoked: bool = False) -> list[ApiKey]:
        pool = await self._get_pool()
        query = f"SELECT {_COLUMNS} FROM api_keys WHERE user_id = $1"
        if not include_revoked:
            query += " AND revoked_at IS NULL"
        query += " ORDER BY created_at DESC"
        rows = await pool.fetch(query, UUID(str(user_id)))
        return [_to_key(r) for r in rows]

    async def count_live_for_user(self, user_id: str) -> int:
        pool = await self._get_pool()
        count = await pool.fetchval(
            "SELECT COUNT(*) FROM api_keys WHERE user_id = $1 AND revoked_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > NOW())",
            UUID(str(user_id)),
        )
        return int(count or 0)

    async def revoke(self, user_id: str, key_id: UUID) -> bool:
        pool = await self._get_pool()
        # user_id in the predicate prevents cross-account revocation by id guessing.
        result = await pool.execute(
            "UPDATE api_keys SET revoked_at = NOW() "
            "WHERE id = $1 AND user_id = $2 AND revoked_at IS NULL",
            key_id,
            UUID(str(user_id)),
        )
        return result.rsplit(" ", 1)[-1] != "0"

    async def touch_last_used(self, key_id: UUID) -> None:
        pool = await self._get_pool()
        await pool.execute(
            "UPDATE api_keys SET last_used_at = NOW() WHERE id = $1",
            key_id,
        )

    async def get_owner(self, key_id: UUID) -> Optional[UUID]:
        pool = await self._get_pool()
        return await pool.fetchval(
            "SELECT user_id FROM api_keys WHERE id = $1",
            key_id,
        )
