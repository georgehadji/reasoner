"""
Feedback Persistence Layer

Stores user feedback in SQLite for durability and queryability.
Migrates existing JSONL data on first initialization.
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
class FeedbackEntry:
    """Single feedback submission."""
    conversation_id: str
    message_id: str
    rating: str  # "up" | "down"
    reason: str | None = None
    comment: str | None = None
    context: dict | None = None
    timestamp: str | None = None


@dataclass
class FeedbackStats:
    """Aggregated feedback statistics."""
    total_entries: int
    upvotes: int
    downvotes: int
    downvote_reasons: dict[str, int]
    avg_comment_length: float
    entries_with_context: int
    period_days: int


class FeedbackStore:
    """
    SQLite-based feedback store.

    Features:
    - Atomic insertions with row-level locking
    - JSONL backfill migration on first init
    - Aggregated stats for admin dashboard
    """

    def __init__(
        self,
        db_path: str | Path | None = None,
        jsonl_path: str | Path | None = None,
    ):
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "feedback.db"
        if jsonl_path is None:
            jsonl_path = Path(__file__).parent.parent.parent.parent / "feedback" / "feedback.jsonl"

        self.db_path = Path(db_path)
        self.jsonl_path = Path(jsonl_path)
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._executor: ThreadPoolExecutor | None = None

        self._init_db()
        self._maybe_migrate_jsonl()

    def _get_executor(self) -> ThreadPoolExecutor:
        """Get or create thread pool executor."""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="feedback_store")
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
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS feedback_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                conversation_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                rating TEXT NOT NULL CHECK(rating IN ('up', 'down')),
                reason TEXT,
                comment TEXT,
                context_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_feedback_rating
                ON feedback_entries(rating);
            CREATE INDEX IF NOT EXISTS idx_feedback_reason
                ON feedback_entries(reason);
            CREATE INDEX IF NOT EXISTS idx_feedback_timestamp
                ON feedback_entries(timestamp);
            CREATE INDEX IF NOT EXISTS idx_feedback_conversation
                ON feedback_entries(conversation_id);

            -- Remove duplicates before creating unique index (migration)
            DELETE FROM feedback_entries WHERE rowid NOT IN (
                SELECT MIN(rowid) FROM feedback_entries GROUP BY conversation_id, message_id
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_feedback_unique
                ON feedback_entries(conversation_id, message_id);
        """)
        conn.commit()

    def _maybe_migrate_jsonl(self) -> None:
        """Backfill existing JSONL data if table is empty and JSONL exists."""
        if not self.jsonl_path.exists():
            return

        conn = self._get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM feedback_entries")
        count = cursor.fetchone()[0]
        if count > 0:
            return

        migrated = 0
        skipped = 0
        entries: list[tuple] = []

        try:
            with open(self.jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        skipped += 1
                        continue

                    entries.append((
                        data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                        data.get("conversation_id", ""),
                        data.get("message_id", ""),
                        data.get("rating", ""),
                        data.get("reason"),
                        data.get("comment"),
                        json.dumps(data.get("context")) if data.get("context") else None,
                    ))

            if entries:
                conn.executemany(
                    """
                    INSERT INTO feedback_entries
                        (timestamp, conversation_id, message_id, rating, reason, comment, context_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    entries,
                )
                conn.commit()
                migrated = len(entries)

        except OSError as exc:
            logger.warning("Failed to read JSONL for migration: %s", exc)
            return

        if migrated or skipped:
            logger.info(
                "Migrated %d feedback entries from JSONL (%d skipped)",
                migrated,
                skipped,
            )
            # Rename file to indicate migration; never delete
            migrated_path = self.jsonl_path.with_suffix(".jsonl.migrated")
            try:
                self.jsonl_path.rename(migrated_path)
                logger.info("Renamed %s -> %s", self.jsonl_path, migrated_path)
            except OSError as exc:
                logger.warning("Failed to rename JSONL after migration: %s", exc)

    def _insert_sync(self, entry: FeedbackEntry) -> int:
        """Synchronous insert. Must be called inside lock."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            INSERT OR REPLACE INTO feedback_entries
                (timestamp, conversation_id, message_id, rating, reason, comment, context_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.timestamp or datetime.now(timezone.utc).isoformat(),
                entry.conversation_id,
                entry.message_id,
                entry.rating,
                entry.reason,
                entry.comment,
                json.dumps(entry.context) if entry.context else None,
            ),
        )
        conn.commit()
        return cursor.lastrowid

    def _get_stats_sync(self, days: int) -> FeedbackStats:
        """Synchronous stats aggregation. Must be called inside lock."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN rating = 'up' THEN 1 ELSE 0 END) as upvotes,
                SUM(CASE WHEN rating = 'down' THEN 1 ELSE 0 END) as downvotes,
                SUM(CASE WHEN context_json IS NOT NULL THEN 1 ELSE 0 END) as with_context,
                AVG(LENGTH(COALESCE(comment, ''))) as avg_comment_length
            FROM feedback_entries
            WHERE timestamp >= datetime('now', ?)
            """,
            (f"-{days} days",),
        )
        row = cursor.fetchone()

        # Reason breakdown for downvotes
        reason_cursor = conn.execute(
            """
            SELECT reason, COUNT(*) as cnt
            FROM feedback_entries
            WHERE rating = 'down'
              AND timestamp >= datetime('now', ?)
              AND reason IS NOT NULL
            GROUP BY reason
            """,
            (f"-{days} days",),
        )
        downvote_reasons = {r["reason"]: r["cnt"] for r in reason_cursor.fetchall()}

        return FeedbackStats(
            total_entries=row["total"] or 0,
            upvotes=row["upvotes"] or 0,
            downvotes=row["downvotes"] or 0,
            downvote_reasons=downvote_reasons,
            avg_comment_length=row["avg_comment_length"] or 0.0,
            entries_with_context=row["with_context"] or 0,
            period_days=days,
        )

    def _get_entries_sync(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FeedbackEntry]:
        """Synchronous paginated retrieval. Must be called inside lock."""
        conn = self._get_connection()
        cursor = conn.execute(
            """
            SELECT timestamp, conversation_id, message_id, rating, reason, comment, context_json
            FROM feedback_entries
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = cursor.fetchall()
        return [
            FeedbackEntry(
                timestamp=r["timestamp"],
                conversation_id=r["conversation_id"],
                message_id=r["message_id"],
                rating=r["rating"],
                reason=r["reason"],
                comment=r["comment"],
                context=json.loads(r["context_json"]) if r["context_json"] else None,
            )
            for r in rows
        ]

    # ── Public async API ──

    async def insert(self, entry: FeedbackEntry) -> int:
        """Insert a feedback entry. Returns the new row id."""
        return await self._run_in_executor(self._insert_sync, entry)

    async def get_stats(self, days: int = 30) -> FeedbackStats:
        """Aggregated stats for the last N days."""
        return await self._run_in_executor(self._get_stats_sync, days)

    async def get_entries(self, limit: int = 100, offset: int = 0) -> list[FeedbackEntry]:
        """Paginated retrieval of feedback entries."""
        return await self._run_in_executor(self._get_entries_sync, limit, offset)
