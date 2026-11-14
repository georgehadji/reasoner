"""Postgres implementation of ApiKeyRepository."""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

import asyncpg

from reasoner.core.ports.api_key_repository import ApiKeyRepository
from reasoner.domain.api_keys import ApiKey
from reasoner.infrastructure.persistence.pg_pool import get_shared_pool

logger = logging.getLogger(__name__)

_COLUMNS = (
    "id, user_id, name, key_hash, key_prefix, scopes, "
    "last_used_at, expires_at, revoked_at, created_at"
)


_LIVE_COUNT_SQL = (
    "SELECT COUNT(*) FROM api_keys WHERE user_id = $1 AND revoked_at IS NULL "
    "AND (expires_at IS NULL OR expires_at > NOW())"
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

    def __init__(self, dsn: str):
        self._dsn = dsn

    async def _get_pool(self) -> asyncpg.Pool:
        return await get_shared_pool(self._dsn)

    async def create(
        self,
        user_id: str,
        name: str,
        key_hash: str,
        key_prefix: str,
        scopes: frozenset[str],
        expires_at: datetime | None = None,
        max_live: int | None = None,
    ) -> ApiKey | None:
        pool = await self._get_pool()
        uid = UUID(str(user_id))
        async with pool.acquire() as conn, conn.transaction():
            if max_live is not None:
                # Serialise this user's creates until commit, so N parallel
                # requests cannot all read "19 live" and all insert.
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", str(uid))
                if await conn.fetchval(_LIVE_COUNT_SQL, uid) >= max_live:
                    return None
            row = await conn.fetchrow(
                "INSERT INTO api_keys (user_id, name, key_hash, key_prefix, scopes, expires_at) "
                f"VALUES ($1, $2, $3, $4, $5, $6) RETURNING {_COLUMNS}",
                uid,
                name,
                key_hash,
                key_prefix,
                sorted(scopes),
                expires_at,
            )
        return _to_key(row)

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
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
        count = await pool.fetchval(_LIVE_COUNT_SQL, UUID(str(user_id)))
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
            "UPDATE api_keys SET last_used_at = NOW() WHERE id = $1 AND revoked_at IS NULL",
            key_id,
        )

    async def touch_last_run(self, key_id: UUID) -> None:
        pool = await self._get_pool()
        await pool.execute(
            "UPDATE api_keys SET last_run_at = NOW() WHERE id = $1",
            key_id,
        )

    async def get_owner(self, key_id: UUID) -> UUID | None:
        pool = await self._get_pool()
        return await pool.fetchval(
            "SELECT user_id FROM api_keys WHERE id = $1",
            key_id,
        )
