"""
Error Persistence Layer

Stores application errors in SQLite for durability and queryability.
Captures unhandled exceptions, HTTP errors, and client-reported issues
with full request context for debugging production issues.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import asyncio
import threading
from pathlib import Path
from typing import Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


@dataclass
class ErrorEntry:
    """Single error occurrence with full context."""
    level: str  # error | warning | critical
    source: str  # api | pipeline | llm | client | system
    message: str
    correlation_id: str | None = None
    user_id: str | None = None
    path: str | None = None
    method: str | None = None
    status_code: int | None = None
    traceback: str | None = None
    extra: dict[str, Any] | None = None
    timestamp: str | None = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class ErrorStats:
    """Aggregated error statistics."""
    total: int
    by_level: dict[str, int]
    by_source: dict[str, int]
    recent_count_1h: int
    recent_count_24h: int
    unique_paths: int
    period_days: int


class ErrorStore:
    """
    SQLite-based error store.

    Features:
    - Atomic insertions with row-level locking
    - Queryable by time range, level, source, path
    - Aggregated stats for admin dashboard
    - Automatic retention (configurable, default 30 days)
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        retention_days: int = 30,
    ):
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "errors.db"

        self.db_path = Path(db_path)
        self.retention_days = retention_days
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._executor: ThreadPoolExecutor | None = None

        self._init_db()
        self._prune_old()

    def _get_executor(self) -> ThreadPoolExecutor:
        """Get or create thread pool executor."""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="error_store")
        return self._executor

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection

    async def _run_in_executor(self, func: Callable, *args) -> Any:
        """Run sync function in thread pool with locking."""
        loop = asyncio.get_running_loop()
        executor = self._get_executor()

        def locked_func():
            with self._lock:
                return func(*args)

        return await loop.run_in_executor(executor, locked_func)

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                source TEXT NOT NULL,
                message TEXT NOT NULL,
                correlation_id TEXT,
                user_id TEXT,
                path TEXT,
                method TEXT,
                status_code INTEGER,
                traceback TEXT,
                extra_json TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_errors_timestamp ON errors(timestamp)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_errors_level ON errors(level)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_errors_source ON errors(source)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_errors_path ON errors(path)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_errors_user ON errors(user_id)
        """)
        conn.commit()

    def _prune_old(self) -> None:
        """Remove errors older than retention period."""
        try:
            conn = self._get_connection()
            cutoff = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            # SQLite datetime math
            conn.execute(
                "DELETE FROM errors WHERE datetime(timestamp) < datetime('now', '-{} days')".format(
                    self.retention_days
                )
            )
            conn.commit()
        except Exception as exc:
            logger.warning("Error pruning old entries: %s", exc)

    def _insert_sync(self, entry: ErrorEntry) -> int:
        """Synchronous insert."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            INSERT INTO errors (
                timestamp, level, source, message, correlation_id,
                user_id, path, method, status_code, traceback, extra_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.timestamp,
                entry.level,
                entry.source,
                entry.message,
                entry.correlation_id,
                entry.user_id,
                entry.path,
                entry.method,
                entry.status_code,
                entry.traceback,
                json.dumps(entry.extra) if entry.extra else None,
            ),
        )
        conn.commit()
        return cursor.lastrowid

    async def insert(self, entry: ErrorEntry) -> int:
        """Insert an error entry asynchronously."""
        return await self._run_in_executor(self._insert_sync, entry)

    def _query_sync(
        self,
        limit: int = 100,
        offset: int = 0,
        level: str | None = None,
        source: str | None = None,
        path: str | None = None,
        user_id: str | None = None,
        hours: int | None = None,
    ) -> list[dict[str, Any]]:
        """Synchronous query."""
        conn = self._get_connection()
        conditions = []
        params = []

        if level:
            conditions.append("level = ?")
            params.append(level)
        if source:
            conditions.append("source = ?")
            params.append(source)
        if path:
            conditions.append("path = ?")
            params.append(path)
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if hours:
            conditions.append("datetime(timestamp) > datetime('now', '-{} hours')".format(hours))

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        cursor = conn.execute(
            f"""
            SELECT * FROM errors
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        return [dict(row) for row in cursor.fetchall()]

    async def query(
        self,
        limit: int = 100,
        offset: int = 0,
        level: str | None = None,
        source: str | None = None,
        path: str | None = None,
        user_id: str | None = None,
        hours: int | None = None,
    ) -> list[dict[str, Any]]:
        """Query errors with optional filters."""
        return await self._run_in_executor(
            self._query_sync, limit, offset, level, source, path, user_id, hours
        )

    def _stats_sync(self, days: int = 7) -> ErrorStats:
        """Synchronous stats aggregation."""
        conn = self._get_connection()

        total = conn.execute(
            "SELECT COUNT(*) FROM errors WHERE datetime(timestamp) > datetime('now', '-{} days')".format(days)
        ).fetchone()[0]

        by_level = {}
        for row in conn.execute(
            "SELECT level, COUNT(*) FROM errors WHERE datetime(timestamp) > datetime('now', '-{} days') GROUP BY level".format(days)
        ):
            by_level[row[0]] = row[1]

        by_source = {}
        for row in conn.execute(
            "SELECT source, COUNT(*) FROM errors WHERE datetime(timestamp) > datetime('now', '-{} days') GROUP BY source".format(days)
        ):
            by_source[row[0]] = row[1]

        recent_1h = conn.execute(
            "SELECT COUNT(*) FROM errors WHERE datetime(timestamp) > datetime('now', '-1 hours')"
        ).fetchone()[0]

        recent_24h = conn.execute(
            "SELECT COUNT(*) FROM errors WHERE datetime(timestamp) > datetime('now', '-24 hours')"
        ).fetchone()[0]

        unique_paths = conn.execute(
            "SELECT COUNT(DISTINCT path) FROM errors WHERE datetime(timestamp) > datetime('now', '-{} days')".format(days)
        ).fetchone()[0]

        return ErrorStats(
            total=total,
            by_level=by_level,
            by_source=by_source,
            recent_count_1h=recent_1h,
            recent_count_24h=recent_24h,
            unique_paths=unique_paths,
            period_days=days,
        )

    async def get_stats(self, days: int = 7) -> ErrorStats:
        """Get aggregated error statistics."""
        return await self._run_in_executor(self._stats_sync, days)
