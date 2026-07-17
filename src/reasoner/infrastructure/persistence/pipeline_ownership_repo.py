"""
Pipeline Ownership Repository — SQLite-backed adapter for PipelineOwnershipPort.

Persists which user_id owns a pipeline run in the ``pipeline_owners`` table,
sharing the event store's SQLite database (see event_store_connection.py) so
ownership records live in the same durable, WAL-mode store as the aggregates
they describe — rather than a JSON file in the source tree that vanishes on
any ephemeral container restart.

See application/ports/pipeline_ownership_port.py for why get_owner
distinguishes "no record" (None) from "explicitly unowned"
(OwnershipRecord(user_id=None)), and why lookup failures raise instead of
collapsing to None.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from reasoner.application.ports.pipeline_ownership_port import OwnershipRecord
from reasoner.infrastructure.persistence.event_store_connection import EventStoreConnection

logger = logging.getLogger(__name__)


class PipelineOwnershipRepository:
    """SQLite-backed pipeline ownership store, sharing the event store DB."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "events.db"
        self._conn = EventStoreConnection(Path(db_path))
        self._conn.init_db()

    async def get_owner(self, pipeline_id: str) -> OwnershipRecord | None:
        def _query() -> OwnershipRecord | None:
            row = self._conn._get_connection().execute(
                "SELECT user_id, run_id FROM pipeline_owners WHERE pipeline_id = ?",
                (pipeline_id,),
            ).fetchone()
            if row is None:
                return None
            return OwnershipRecord(user_id=row["user_id"], run_id=row["run_id"])

        return await self._conn.run_in_executor(_query)

    async def set_owner(self, pipeline_id: str, user_id: str | None, run_id: str) -> None:
        def _upsert() -> None:
            conn = self._conn._get_connection()
            conn.execute(
                """
                INSERT INTO pipeline_owners (pipeline_id, user_id, run_id)
                VALUES (?, ?, ?)
                ON CONFLICT(pipeline_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    run_id = excluded.run_id
                """,
                (pipeline_id, user_id, run_id),
            )
            conn.commit()

        await self._conn.run_in_executor(_upsert)

    async def list_pipeline_ids_for_user(self, user_id: str) -> list[str]:
        def _query() -> list[str]:
            rows = self._conn._get_connection().execute(
                "SELECT pipeline_id FROM pipeline_owners WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            return [r["pipeline_id"] for r in rows]

        return await self._conn.run_in_executor(_query)

    async def backfill_from_json(self, json_path: Path | None = None) -> int:
        """One-shot import of the legacy JSON ownership file into this table.

        Only fills gaps (INSERT OR IGNORE on the pipeline_id primary key) —
        never overwrites a row already present, so it is safe to call on
        every startup during the migration window and after cutover once the
        JSON file is gone (it then imports nothing).

        The JSON format is ``{pipeline_id: user_id | null}`` with no run_id
        recorded separately; the pipeline_id and run_id are the same value
        in practice (see api/execution/pipeline.py's
        ``_save_pipeline_owner(run_id, user_id)`` call), so run_id is
        backfilled as pipeline_id.

        Returns the number of rows inserted (0 if the JSON file is absent
        or empty).
        """
        if json_path is None:
            from reasoner.domain.pipeline_owner import _PIPELINE_OWNERS_PATH
            json_path = _PIPELINE_OWNERS_PATH

        if not json_path.exists():
            return 0

        try:
            mapping: dict[str, str | None] = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Pipeline ownership backfill: failed to read %s: %s", json_path, exc)
            return 0

        if not mapping:
            return 0

        def _backfill() -> int:
            conn = self._conn._get_connection()
            inserted = 0
            for pipeline_id, user_id in mapping.items():
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO pipeline_owners (pipeline_id, user_id, run_id)
                    VALUES (?, ?, ?)
                    """,
                    (pipeline_id, user_id, pipeline_id),
                )
                inserted += cur.rowcount
            conn.commit()
            return inserted

        count = await self._conn.run_in_executor(_backfill)
        if count:
            logger.info("Pipeline ownership backfill: imported %d record(s) from %s", count, json_path)
        return count

    def close(self) -> None:
        self._conn.close()
