"""
Persistent API key storage using SQLite (aiosqlite).

Provides durable storage for API keys so that generated keys survive
process restarts and are visible across multiple workers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from reasoner.core.ports.crypto_port import EncryptionPort
from reasoner.security.encryption import get_encryption_service

logger = logging.getLogger(__name__)

# Schema version for future migrations
_SCHEMA_VERSION = 1

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS api_keys (
    key_hash TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    scopes TEXT NOT NULL,          -- JSON list of scope strings
    is_active INTEGER NOT NULL DEFAULT 1,
    rate_limit_tier TEXT NOT NULL DEFAULT 'default',
    created_at TEXT NOT NULL,      -- ISO-8601
    expires_at TEXT,               -- ISO-8601 or NULL
    created_by TEXT,
    last_used_at TEXT,             -- ISO-8601 or NULL
    usage_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS auth_schema (
    version INTEGER PRIMARY KEY
);
"""


class AuthStore:
    """SQLite-backed persistent store for API keys."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._lock = asyncio.Lock()
        self._initialized = False
        self._encryption: EncryptionPort = get_encryption_service()

    async def _ensure_schema(self, conn: aiosqlite.Connection) -> None:
        """Create tables if they don't exist."""
        await conn.executescript(_CREATE_SQL)
        await conn.execute(
            "INSERT OR IGNORE INTO auth_schema (version) VALUES (?)",
            (_SCHEMA_VERSION,),
        )
        await conn.commit()

    async def _get_conn(self) -> aiosqlite.Connection:
        """Return a connection with schema guaranteed."""
        conn = await aiosqlite.connect(self._db_path)
        # Without this, rows come back as plain tuples and _row_to_dict's
        # dict(row) raises ValueError on every read.
        conn.row_factory = aiosqlite.Row
        if not self._initialized:
            async with self._lock:
                if not self._initialized:
                    await self._ensure_schema(conn)
                    self._initialized = True
        return conn

    # ── CRUD operations ──

    async def insert(
        self,
        key_hash: str,
        name: str,
        scopes: set[str],
        is_active: bool,
        rate_limit_tier: str,
        created_at: datetime,
        expires_at: datetime | None,
        created_by: str | None,
    ) -> None:
        """Insert a new API key. Metadata is encrypted (Phase 3: E2EE)."""
        conn = await self._get_conn()
        try:
            # Encrypt sensitive metadata (Phase 3: E2EE)
            encrypted_name = self._encryption.encrypt(name)
            encrypted_scopes = self._encryption.encrypt(json.dumps(sorted(scopes)))

            await conn.execute(
                """
                INSERT INTO api_keys (
                    key_hash, name, scopes, is_active, rate_limit_tier,
                    created_at, expires_at, created_by, last_used_at, usage_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key_hash,
                    encrypted_name,
                    encrypted_scopes,
                    1 if is_active else 0,
                    rate_limit_tier,
                    created_at.astimezone(UTC).isoformat(),
                    expires_at.astimezone(UTC).isoformat() if expires_at else None,
                    created_by,
                    None,
                    0,
                ),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def get_by_hash(self, key_hash: str) -> dict | None:
        """Retrieve a key by its hash. Returns None if not found."""
        conn = await self._get_conn()
        try:
            async with conn.execute(
                "SELECT * FROM api_keys WHERE key_hash = ?", (key_hash,)
            ) as cursor:
                row = await cursor.fetchone()
                if row is None:
                    return None
                return self._row_to_dict(row)
        finally:
            await conn.close()

    async def update_usage(self, key_hash: str) -> None:
        """Increment usage_count and set last_used_at to now."""
        conn = await self._get_conn()
        try:
            await conn.execute(
                """
                UPDATE api_keys
                SET usage_count = usage_count + 1,
                    last_used_at = ?
                WHERE key_hash = ?
                """,
                (datetime.now(UTC).isoformat(), key_hash),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def revoke(self, key_hash: str) -> bool:
        """Deactivate a key. Returns True if the key existed."""
        conn = await self._get_conn()
        try:
            cursor = await conn.execute(
                "UPDATE api_keys SET is_active = 0 WHERE key_hash = ?",
                (key_hash,),
            )
            await conn.commit()
            return cursor.rowcount > 0
        finally:
            await conn.close()

    async def list_all(self) -> list[dict]:
        """Return all keys (for admin listing)."""
        conn = await self._get_conn()
        try:
            async with conn.execute(
                "SELECT * FROM api_keys ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_dict(row) for row in rows]
        finally:
            await conn.close()

    # ── helpers ──

    def _row_to_dict(self, row: aiosqlite.Row) -> dict:
        """Convert a database row to a dict. Decrypts metadata (Phase 3: E2EE)."""
        d = dict(row)

        # Decrypt sensitive metadata (Phase 3: E2EE). Each field is handled
        # independently: decrypt_optional passes legacy plaintext through but
        # raises on a real key mismatch, so a rotated-away key surfaces as an
        # error instead of silently yielding a key with zero scopes.
        d["name"] = self._encryption.decrypt_optional(d.get("name"))
        scopes_raw = self._encryption.decrypt_optional(d.pop("scopes", None)) or "[]"

        # JSON-decode scopes
        d["scopes"] = set(json.loads(scopes_raw))
        # Boolean conversion
        d["is_active"] = bool(d.pop("is_active", 1))
        # Datetime parsing
        for key in ("created_at", "expires_at", "last_used_at"):
            val = d.get(key)
            if val:
                d[key] = datetime.fromisoformat(val)
            else:
                d[key] = None
        return d
