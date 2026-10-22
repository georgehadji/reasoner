"""Per-user upload storage usage, reserved atomically before a write.

docs/plans/audit-remediation-2-2026-10-20.md PER-8: the quota used to be
summed from the upload hash index, a JSON file in the package directory. A
redeploy reset it, and two parallel uploads both passed the check before
either wrote, so the cap held for neither.

``reserve`` is one conditional upsert, so N parallel reservations can never
exceed the cap in total. ``adjust`` corrects a reservation to the bytes
actually written (ciphertext and sidecars) and releases on failure or delete;
it never takes usage below zero. ``forget`` drops the row on account deletion.

Postgres when ``DATABASE_URL`` is a Postgres DSN (table from Alembic revision
20261021_000100). Otherwise SQLite beside the uploads, in ``UPLOAD_DIR``, so
usage lives on the same volume as the files it counts.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path

import asyncpg

_RESERVE_SQL = """
    INSERT INTO upload_usage (user_id, bytes) VALUES ({p1}, {p2})
    ON CONFLICT (user_id) DO UPDATE SET bytes = upload_usage.bytes + EXCLUDED.bytes
    WHERE upload_usage.bytes + EXCLUDED.bytes <= {p3}
"""


class SqliteUploadUsageRepository:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS upload_usage "
                "(user_id TEXT PRIMARY KEY, bytes INTEGER NOT NULL DEFAULT 0)"
            )

    def _connect(self) -> sqlite3.Connection:
        # One connection per call: they run on worker threads, and SQLite
        # serializes the writers itself.
        return sqlite3.connect(str(self._db_path), timeout=30)

    async def reserve(self, user_id: str, n: int, cap: int) -> bool:
        if n > cap:
            return False

        def _reserve() -> bool:
            with self._connect() as conn:
                sql = _RESERVE_SQL.format(p1="?", p2="?", p3="?")
                return bool(conn.execute(sql, (user_id, n, cap)).rowcount == 1)

        return await asyncio.to_thread(_reserve)

    async def adjust(self, user_id: str, delta: int) -> None:
        def _adjust() -> None:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO upload_usage (user_id, bytes) VALUES (?, MAX(?, 0)) "
                    "ON CONFLICT (user_id) DO UPDATE SET bytes = MAX(upload_usage.bytes + ?, 0)",
                    (user_id, delta, delta),
                )

        await asyncio.to_thread(_adjust)

    async def get(self, user_id: str) -> int:
        def _get() -> int:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT bytes FROM upload_usage WHERE user_id = ?", (user_id,)
                ).fetchone()
            return int(row[0]) if row else 0

        return await asyncio.to_thread(_get)

    async def forget(self, user_id: str) -> None:
        def _forget() -> None:
            with self._connect() as conn:
                conn.execute("DELETE FROM upload_usage WHERE user_id = ?", (user_id,))

        await asyncio.to_thread(_forget)


class PostgresUploadUsageRepository:
    _pool: asyncpg.Pool | None = None
    _pool_lock: asyncio.Lock | None = None

    def __init__(self, dsn: str, pool_size: int | None = None) -> None:
        self._dsn = dsn
        self._pool_size = (
            pool_size if pool_size is not None else int(os.environ.get("DB_POOL_SIZE", "10"))
        )

    async def _get_pool(self) -> asyncpg.Pool:
        cls = PostgresUploadUsageRepository
        if cls._pool_lock is None:
            cls._pool_lock = asyncio.Lock()
        if cls._pool is None:
            async with cls._pool_lock:
                if cls._pool is None:
                    cls._pool = await asyncpg.create_pool(
                        self._dsn, min_size=1, max_size=self._pool_size
                    )
        return cls._pool

    async def reserve(self, user_id: str, n: int, cap: int) -> bool:
        if n > cap:
            return False
        pool = await self._get_pool()
        status = await pool.execute(
            _RESERVE_SQL.format(p1="$1", p2="$2", p3="$3"), user_id, n, cap
        )
        return bool(status.endswith(" 1"))

    async def adjust(self, user_id: str, delta: int) -> None:
        pool = await self._get_pool()
        await pool.execute(
            "INSERT INTO upload_usage (user_id, bytes) VALUES ($1, GREATEST($2, 0)) "
            "ON CONFLICT (user_id) DO UPDATE SET bytes = GREATEST(upload_usage.bytes + $2, 0)",
            user_id,
            delta,
        )

    async def get(self, user_id: str) -> int:
        pool = await self._get_pool()
        value = await pool.fetchval("SELECT bytes FROM upload_usage WHERE user_id = $1", user_id)
        return int(value or 0)

    async def forget(self, user_id: str) -> None:
        pool = await self._get_pool()
        await pool.execute("DELETE FROM upload_usage WHERE user_id = $1", user_id)


UploadUsageRepository = SqliteUploadUsageRepository | PostgresUploadUsageRepository
_repo: UploadUsageRepository | None = None


def get_upload_usage_repo() -> UploadUsageRepository:
    global _repo
    if _repo is None:
        from reasoner.core.settings import settings
        from reasoner.infrastructure.uploader import UPLOAD_DIR

        if settings.DATABASE_URL and "postgres" in settings.DATABASE_URL:
            _repo = PostgresUploadUsageRepository(
                settings.DATABASE_URL.replace("+asyncpg", ""), pool_size=settings.DB_POOL_SIZE
            )
        else:
            _repo = SqliteUploadUsageRepository(UPLOAD_DIR / ".upload_usage.db")
    return _repo
