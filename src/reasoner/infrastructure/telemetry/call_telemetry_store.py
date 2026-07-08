"""SQLite-backed per-call telemetry store for adaptive routing (ACR Phase 1)."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

import aiosqlite

from reasoner.domain.telemetry import LLMCallTelemetry, ModelRoleStats


class SQLiteCallTelemetryStore:
    """Persists per-call LLM telemetry to SQLite for adaptive routing analytics.

    Uses a separate database file from the event store to keep concerns
    separated and avoid migration coupling.

    Schema is auto-created on first use.
    """

    TABLE = "llm_call_telemetry"

    def __init__(self, db_path: str | None = None) -> None:
        """Initialise the store.

        Args:
            db_path: Path to the SQLite database file.
                     Defaults to ``~/.reasoner/acr/telemetry.db``.
        """
        if db_path is None:
            db_path = str(
                Path.home() / ".reasoner" / "acr" / "telemetry.db"
            )
        self._db_path = db_path
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Create parent directories if they don't exist."""
        parent = os.path.dirname(self._db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    async def _connect(self) -> aiosqlite.Connection:
        """Get a database connection with the table created."""
        conn = await aiosqlite.connect(self._db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await self._ensure_table(conn)
        return conn

    async def _ensure_table(self, conn: aiosqlite.Connection) -> None:
        """Create the telemetry table if it doesn't exist."""
        await conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.TABLE} (
                call_id         TEXT PRIMARY KEY,
                run_id          TEXT NOT NULL,
                timestamp       TEXT NOT NULL,
                model_id        TEXT NOT NULL,
                role            TEXT NOT NULL,
                preset_id       TEXT NOT NULL,
                method          TEXT NOT NULL,
                phase           INTEGER NOT NULL,
                latency_ms      REAL NOT NULL,
                input_tokens    INTEGER NOT NULL,
                output_tokens   INTEGER NOT NULL,
                cost_usd        REAL NOT NULL,
                success         INTEGER NOT NULL,
                json_valid      INTEGER,
                is_fallback     INTEGER NOT NULL DEFAULT 0,
                fallback_reason TEXT,
                circuit_state   TEXT NOT NULL,
                critique_score  REAL,
                stress_test_pass INTEGER,
                vendor          TEXT NOT NULL,
                bloc            TEXT NOT NULL
            )
        """)
        # Create indexes for common query patterns
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_telemetry_model_role
            ON {self.TABLE}(model_id, role)
        """)
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp
            ON {self.TABLE}(timestamp)
        """)
        await conn.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_telemetry_role
            ON {self.TABLE}(role)
        """)
        await conn.commit()

    async def record_call(self, event: LLMCallTelemetry) -> None:
        """Persist a single LLM call telemetry event."""
        conn = await self._connect()
        try:
            await conn.execute(
                f"""
                INSERT OR REPLACE INTO {self.TABLE} (
                    call_id, run_id, timestamp, model_id, role,
                    preset_id, method, phase, latency_ms,
                    input_tokens, output_tokens, cost_usd, success,
                    json_valid, is_fallback, fallback_reason, circuit_state,
                    critique_score, stress_test_pass, vendor, bloc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.call_id,
                    event.run_id,
                    event.timestamp,
                    event.model_id,
                    event.role,
                    event.preset_id,
                    event.method,
                    event.phase,
                    event.latency_ms,
                    event.input_tokens,
                    event.output_tokens,
                    event.cost_usd,
                    1 if event.success else 0,
                    1 if event.json_valid else 0 if event.json_valid is not None else None,
                    1 if event.is_fallback else 0,
                    event.fallback_reason,
                    event.circuit_state,
                    event.critique_score,
                    1 if event.stress_test_pass else 0 if event.stress_test_pass is not None else None,
                    event.vendor,
                    event.bloc,
                ),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def query_model_role_stats(
        self,
        model_id: str,
        role: str,
        window_hours: int = 168,
    ) -> ModelRoleStats:
        """Aggregate stats for a (model, role) pair over a time window."""
        conn = await self._connect()
        try:
            cursor = await conn.execute(
                f"""
                SELECT
                    COUNT(*)                                          AS total_calls,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END)      AS successful_calls,
                    SUM(CASE WHEN is_fallback = 1 THEN 1 ELSE 0 END)  AS fallback_calls,
                    AVG(latency_ms)                                   AS avg_latency_ms,
                    AVG(input_tokens)                                 AS avg_input_tokens,
                    AVG(output_tokens)                                AS avg_output_tokens,
                    AVG(cost_usd)                                     AS avg_cost_usd,
                    SUM(cost_usd)                                     AS total_cost_usd,
                    AVG(CASE WHEN json_valid IS NOT NULL
                             THEN CAST(json_valid AS FLOAT) ELSE NULL END) AS json_valid_rate,
                    AVG(critique_score)                               AS avg_critique_score,
                    AVG(CASE WHEN stress_test_pass IS NOT NULL
                             THEN CAST(stress_test_pass AS FLOAT) ELSE NULL END) AS stress_test_pass_rate,
                    MAX(vendor)                                       AS vendor,
                    MAX(bloc)                                         AS bloc
                FROM {self.TABLE}
                WHERE model_id = ?
                  AND role = ?
                  AND timestamp >= datetime('now', ?)
                """,
                (model_id, role, f"-{window_hours} hours"),
            )
            row = await cursor.fetchone()
            if row is None or row["total_calls"] == 0:
                return ModelRoleStats(model_id=model_id, role=role)

            total = row["total_calls"]
            success_rate = row["successful_calls"] / total if total > 0 else 0.0

            return ModelRoleStats(
                model_id=model_id,
                role=role,
                total_calls=total,
                successful_calls=row["successful_calls"] or 0,
                fallback_calls=row["fallback_calls"] or 0,
                avg_latency_ms=row["avg_latency_ms"] or 0.0,
                avg_input_tokens=int(row["avg_input_tokens"] or 0),
                avg_output_tokens=int(row["avg_output_tokens"] or 0),
                avg_cost_usd=row["avg_cost_usd"] or 0.0,
                total_cost_usd=row["total_cost_usd"] or 0.0,
                success_rate=success_rate,
                json_valid_rate=row["json_valid_rate"],
                avg_critique_score=row["avg_critique_score"],
                stress_test_pass_rate=row["stress_test_pass_rate"],
                vendor=row["vendor"] or "",
                bloc=row["bloc"] or "",
                sample_count=total,
            )
        finally:
            await conn.close()

    async def query_role_leaderboard(
        self,
        role: str,
        window_hours: int = 168,
        limit: int = 10,
    ) -> list[ModelRoleStats]:
        """Top models for a role, ranked by composite quality score.

        The composite score blends success rate, critique score (if available),
        and penalty for high cost/latency — matching the utility function shape
        that the Adaptive Router uses.
        """
        conn = await self._connect()
        try:
            cursor = await conn.execute(
                f"""
                SELECT
                    model_id,
                    COUNT(*)                                          AS total_calls,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END)      AS successful_calls,
                    SUM(CASE WHEN is_fallback = 1 THEN 1 ELSE 0 END)  AS fallback_calls,
                    AVG(latency_ms)                                   AS avg_latency_ms,
                    AVG(cost_usd)                                     AS avg_cost_usd,
                    SUM(cost_usd)                                     AS total_cost_usd,
                    AVG(critique_score)                               AS avg_critique_score,
                    MAX(vendor)                                       AS vendor,
                    MAX(bloc)                                         AS bloc,
                    AVG(CASE WHEN stress_test_pass IS NOT NULL
                             THEN CAST(stress_test_pass AS FLOAT) ELSE NULL END) AS stress_test_pass_rate
                FROM {self.TABLE}
                WHERE role = ?
                  AND timestamp >= datetime('now', ?)
                GROUP BY model_id
                HAVING total_calls >= 5
                ORDER BY successful_calls DESC
                LIMIT ?
                """,
                (role, f"-{window_hours} hours", limit),
            )
            rows = await cursor.fetchall()
            results: list[ModelRoleStats] = []
            for row in rows:
                total = row["total_calls"]
                success_rate = row["successful_calls"] / total if total > 0 else 0.0
                results.append(
                    ModelRoleStats(
                        model_id=row["model_id"],
                        role=role,
                        total_calls=total,
                        successful_calls=row["successful_calls"] or 0,
                        fallback_calls=row["fallback_calls"] or 0,
                        avg_latency_ms=row["avg_latency_ms"] or 0.0,
                        avg_cost_usd=row["avg_cost_usd"] or 0.0,
                        total_cost_usd=row["total_cost_usd"] or 0.0,
                        success_rate=success_rate,
                        avg_critique_score=row["avg_critique_score"],
                        stress_test_pass_rate=row["stress_test_pass_rate"],
                        vendor=row["vendor"] or "",
                        bloc=row["bloc"] or "",
                        sample_count=total,
                    )
                )
            return results
        finally:
            await conn.close()

    async def get_recent_calls(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch recent telemetry events (for admin dashboard)."""
        conn = await self._connect()
        try:
            cursor = await conn.execute(
                f"""
                SELECT * FROM {self.TABLE}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
        finally:
            await conn.close()


__all__ = ["SQLiteCallTelemetryStore"]
