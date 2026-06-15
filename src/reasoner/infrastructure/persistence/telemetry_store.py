"""TelemetryStore — queryable per-phase telemetry for cross-run analytics.

Stores per-phase and per-run data in a separate table from EventStore.
Uses the same SQLite DB file, same threading model (ThreadPoolExecutor + Lock).
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CREATE_PHASE_TELEMETRY = """
CREATE TABLE IF NOT EXISTS phase_telemetry (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT    NOT NULL,
    preset      TEXT    NOT NULL,
    method      TEXT,
    phase       TEXT    NOT NULL,
    cost_usd    REAL    NOT NULL DEFAULT 0.0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    retries     INTEGER NOT NULL DEFAULT 0,
    quality_score REAL,
    quality_passed INTEGER,
    models      TEXT,
    is_fallback INTEGER NOT NULL DEFAULT 0,
    ts          TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pt_preset  ON phase_telemetry(preset);
CREATE INDEX IF NOT EXISTS idx_pt_run     ON phase_telemetry(run_id);
CREATE INDEX IF NOT EXISTS idx_pt_ts      ON phase_telemetry(ts);
"""

_CREATE_RUN_TELEMETRY = """
CREATE TABLE IF NOT EXISTS run_telemetry (
    run_id          TEXT PRIMARY KEY,
    preset          TEXT NOT NULL,
    method          TEXT,
    total_cost_usd  REAL NOT NULL DEFAULT 0.0,
    fallback_count  INTEGER NOT NULL DEFAULT 0,
    fallback_events TEXT,
    ts              TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_rt_preset ON run_telemetry(preset);
CREATE INDEX IF NOT EXISTS idx_rt_ts     ON run_telemetry(ts);
"""


class TelemetryStore:
    """Queryable per-phase telemetry for cross-run analytics."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = "events.db"
        self.db_path = Path(db_path)
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._executor: ThreadPoolExecutor | None = None
        self._init_db()

    def _get_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="telemetry_store"
            )
        return self._executor

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path), check_same_thread=False
            )
            self._connection.row_factory = sqlite3.Row
        return self._connection

    async def _run_in_executor(self, func, *args) -> Any:
        loop = asyncio.get_event_loop()
        def locked():
            with self._lock:
                return func(*args)
        return await loop.run_in_executor(self._get_executor(), locked)

    def _init_db(self) -> None:
        conn = self._get_connection()
        conn.executescript(_CREATE_PHASE_TELEMETRY)
        conn.executescript(_CREATE_RUN_TELEMETRY)
        conn.commit()

    async def save_run(
        self,
        run_id: str,
        preset: str,
        method: str | None,
        phase_results: list[dict[str, Any]],
        fallback_events: list[dict[str, Any]],
        total_cost_usd: float,
    ) -> None:
        def _sync():
            conn = self._get_connection()
            try:
                for pr in phase_results:
                    conn.execute("""
                        INSERT INTO phase_telemetry
                        (run_id, preset, method, phase, cost_usd, duration_ms,
                         retries, quality_score, quality_passed, models, is_fallback)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        run_id, preset, method,
                        pr.get("phase_name", ""),
                        round(pr.get("cost_usd", 0.0), 6),
                        int(pr.get("duration_ms", 0)),
                        pr.get("retries_used", 0),
                        pr.get("quality_score"),
                        int(bool(pr.get("quality_passed"))) if pr.get("quality_passed") is not None else None,
                        json.dumps(pr.get("models") or []),
                        0,
                    ))
                for fe in fallback_events:
                    conn.execute("""
                        INSERT INTO phase_telemetry
                        (run_id, preset, method, phase, cost_usd, duration_ms,
                         retries, models, is_fallback)
                        VALUES (?, ?, ?, ?, 0, 0, 0, ?, 1)
                    """, (
                        run_id, preset, method,
                        fe.get("role", ""),
                        json.dumps([fe.get("actual", "")]),
                    ))
                conn.execute("""
                    INSERT OR REPLACE INTO run_telemetry
                    (run_id, preset, method, total_cost_usd,
                     fallback_count, fallback_events)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    run_id, preset, method,
                    round(total_cost_usd, 6),
                    len(fallback_events),
                    json.dumps(fallback_events),
                ))
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                logger.error("TelemetryStore.save_run failed: %s", exc)
                raise

        await self._run_in_executor(_sync)

    async def query_by_preset(
        self, preset: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        def _sync():
            conn = self._get_connection()
            cursor = conn.execute("""
                SELECT * FROM run_telemetry
                WHERE preset = ?
                ORDER BY ts DESC LIMIT ?
            """, (preset, limit))
            return [dict(row) for row in cursor.fetchall()]
        return await self._run_in_executor(_sync)

    async def query_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        def _sync():
            conn = self._get_connection()
            cursor = conn.execute("""
                SELECT * FROM run_telemetry
                ORDER BY ts DESC LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
        return await self._run_in_executor(_sync)

    async def get_preset_stats(self, preset: str) -> dict[str, Any]:
        """Aggregate stats for a preset: avg cost, avg fallback rate, phase retries."""
        def _sync():
            conn = self._get_connection()
            run_cur = conn.execute("""
                SELECT
                    COUNT(*)            AS run_count,
                    AVG(total_cost_usd) AS avg_cost,
                    SUM(fallback_count) AS total_fallbacks
                FROM run_telemetry WHERE preset = ?
            """, (preset,))
            run_row = dict(run_cur.fetchone())

            phase_cur = conn.execute("""
                SELECT
                    phase,
                    AVG(cost_usd)     AS avg_cost,
                    AVG(retries)      AS avg_retries,
                    AVG(quality_score) AS avg_quality,
                    SUM(is_fallback)  AS fallback_count
                FROM phase_telemetry
                WHERE preset = ?
                GROUP BY phase
            """, (preset,))
            phases = [dict(r) for r in phase_cur.fetchall()]
            return {**run_row, "phases": phases}
        return await self._run_in_executor(_sync)

    async def get_scorecard_rows(self, window_days: int = 7) -> list[dict[str, Any]]:
        """Return per-phase aggregated metrics for all presets over a time window.

        Each row is a dict with preset, phase, model, and aggregated cost/
        duration/quality/fallback stats. Used by ScorecardService.
        """
        def _sync():
            conn = self._get_connection()
            rows = conn.execute("""
                SELECT
                    pt.preset,
                    pt.phase,
                    pt.models,
                    COUNT(*)                    AS total_calls,
                    COALESCE(SUM(pt.cost_usd), 0.0)   AS total_cost_usd,
                    COALESCE(SUM(pt.duration_ms), 0)  AS total_duration_ms,
                    COALESCE(AVG(pt.quality_score), 0.0) AS avg_quality_score,
                    COALESCE(SUM(pt.quality_passed), 0)  AS quality_passed,
                    COALESCE(SUM(CASE WHEN pt.quality_passed = 0 AND pt.quality_score IS NOT NULL THEN 1 ELSE 0 END), 0) AS quality_failed,
                    COALESCE(SUM(pt.retries), 0)  AS total_retries,
                    COALESCE(SUM(pt.is_fallback), 0) AS fallback_count
                FROM phase_telemetry pt
                WHERE pt.ts >= datetime('now', '-' || ? || ' days')
                GROUP BY pt.preset, pt.phase, pt.models
                ORDER BY pt.preset, pt.phase
            """, (window_days,))
            return [dict(r) for r in rows.fetchall()]
        return await self._run_in_executor(_sync)

    async def get_scorecard_fallback_events(
        self, window_days: int = 7
    ) -> dict[str, list[dict[str, Any]]]:
        """Return fallback events grouped by preset over the time window."""
        def _sync():
            conn = self._get_connection()
            rows = conn.execute("""
                SELECT run_id, preset, fallback_events
                FROM run_telemetry
                WHERE fallback_count > 0
                  AND ts >= datetime('now', '-' || ? || ' days')
                ORDER BY ts DESC
            """, (window_days,))
            by_preset: dict[str, list[dict[str, Any]]] = {}
            for r in rows.fetchall():
                preset = r["preset"]
                events = json.loads(r["fallback_events"] or "[]")
                if isinstance(events, list):
                    by_preset.setdefault(preset, []).extend(events)
            return by_preset
        return await self._run_in_executor(_sync)

    async def get_run_counts(
        self, window_days: int = 7
    ) -> dict[str, dict[str, int]]:
        """Return per-preset run counts (total, completed, failed) over a window.

        Returns a dict keyed by preset name, each value a dict with keys
        'total_runs', 'completed_runs', 'failed_runs'.
        """
        def _sync():
            conn = self._get_connection()
            rows = conn.execute("""
                SELECT preset,
                       COUNT(*)                                                                  AS total_runs,
                       COUNT(*)                                                                  AS all_runs,
                       COALESCE(SUM(CASE WHEN total_cost_usd > 0 THEN 1 ELSE 0 END), 0)          AS completed_runs
                  FROM run_telemetry
                 WHERE ts >= datetime('now', '-' || ? || ' days')
                 GROUP BY preset
            """, (window_days,))
            result: dict[str, dict[str, int]] = {}
            for r in rows.fetchall():
                total = r["total_runs"]
                completed = r["completed_runs"]
                result[r["preset"]] = {
                    "total_runs": total,
                    "completed_runs": completed,
                    "failed_runs": total - completed,
                }
            return result
        return await self._run_in_executor(_sync)

    async def get_recovery_count(
        self, window_days: int = 7
    ) -> dict[str, int]:
        """Count runs per preset that had fallbacks but still completed."""
        def _sync():
            conn = self._get_connection()
            rows = conn.execute("""
                SELECT preset, COUNT(*) AS recovery_count
                FROM run_telemetry
                WHERE fallback_count > 0
                  AND ts >= datetime('now', '-' || ? || ' days')
                GROUP BY preset
            """, (window_days,))
            return {r["preset"]: r["recovery_count"] for r in rows.fetchall()}
        return await self._run_in_executor(_sync)

    def close(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None


_telemetry_store: TelemetryStore | None = None


def get_telemetry_store(db_path: str | Path | None = None) -> TelemetryStore:
    global _telemetry_store
    if _telemetry_store is None:
        _telemetry_store = TelemetryStore(db_path)
    return _telemetry_store


def reset_telemetry_store() -> None:
    global _telemetry_store
    if _telemetry_store:
        _telemetry_store.close()
    _telemetry_store = None
