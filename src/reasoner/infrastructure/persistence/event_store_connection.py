"""
SQLite connection management for the EventStore.

Extracted from ``event_store.py`` to keep the main class focused on
event persistence rather than connection lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class EventStoreConnection:
    """Manages a single SQLite connection with WAL mode, thread pool, and locking."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._executor: ThreadPoolExecutor | None = None

    def _get_executor(self) -> ThreadPoolExecutor:
        """Get or create thread pool executor."""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="event_store"
            )
        return self._executor

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path), check_same_thread=False,
            )
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.execute("PRAGMA busy_timeout=5000")
        return self._connection

    async def run_in_executor(self, func: Callable, *args: Any) -> Any:
        """Run a sync function in the thread pool with the store lock held."""
        loop = asyncio.get_running_loop()
        executor = self._get_executor()

        def locked_func() -> Any:
            with self._lock:
                return func(*args)

        return await loop.run_in_executor(executor, locked_func)

    def init_db(self) -> None:
        """Create tables if they don't exist."""
        conn = self._get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                event_type TEXT NOT NULL,
                aggregate_id TEXT NOT NULL,
                aggregate_type TEXT NOT NULL DEFAULT 'pipeline',
                version INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_events_aggregate
                ON events(aggregate_id, version);
            CREATE INDEX IF NOT EXISTS idx_events_type
                ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_created_at
                ON events(created_at);

            CREATE TABLE IF NOT EXISTS snapshots (
                aggregate_id TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS pipeline_owners (
                pipeline_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            -- Aggregates table (current state snapshot). The refactor that split
            -- connection handling into this module dropped it; prune_events_before,
            -- aggregate persistence, stats and listing all query it.
            CREATE TABLE IF NOT EXISTS aggregates (
                aggregate_id TEXT PRIMARY KEY,
                aggregate_type TEXT NOT NULL,
                current_version INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                problem TEXT,
                preset TEXT,
                method TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_aggregates_status
                ON aggregates(status);
            CREATE INDEX IF NOT EXISTS idx_aggregates_created
                ON aggregates(created_at);

            -- Dead-letter queue for un-persistable events (DM8)
            CREATE TABLE IF NOT EXISTS dead_letter_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                event_type TEXT NOT NULL,
                raw_payload TEXT NOT NULL,
                error TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """)
        conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None
