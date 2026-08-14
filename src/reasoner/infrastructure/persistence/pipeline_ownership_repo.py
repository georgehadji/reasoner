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

# Default location of the retired JSON ownership store (formerly
# domain/pipeline_owner.py, deleted in Phase 3 of
# docs/plans/pipeline-ownership-authz-hardening.md). Kept only as a path
# constant so backfill_from_json() can still find pre-migration data on a
# deployment that has not yet had a process start since the cutover.
_LEGACY_PIPELINE_OWNERS_PATH = (
    Path(__file__).parent.parent.parent / "domain" / "history" / "pipeline_owners.json"
)


class PipelineOwnershipRepository:
    """SQLite-backed pipeline ownership store, sharing the event store DB."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            # Defaulted to `<package>/events.db` — inside the image in a
            # container, so every redeploy wiped it. This store decides who owns
            # which pipeline, so losing it drops authorization records, not just
            # cache. EVENT_STORE_PATH lets deployments point it at a mounted
            # volume; the historical location stays the fallback for local runs.
            import os

            env_path = os.environ.get("EVENT_STORE_PATH")
            db_path = (
                Path(env_path)
                if env_path
                else Path(__file__).parent.parent.parent / "events.db"
            )
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
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
            json_path = _LEGACY_PIPELINE_OWNERS_PATH

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


# ─────────────────────────────────────────────────────────────────────
# GLOBAL SINGLETON — mirrors event_store.py's get_event_store() pattern.
# ─────────────────────────────────────────────────────────────────────

_pipeline_ownership_repo: PipelineOwnershipRepository | None = None
_backfill_done = False


def get_pipeline_ownership_repo(
    db_path: str | Path | None = None,
) -> PipelineOwnershipRepository:
    """Get or create the global pipeline ownership repository.

    When db_path is not given, shares the SQLite EventStore's file (so
    ownership records live alongside the aggregates they describe) if the
    event store backend is SQLite. Falls back to this repo's own default
    file when the event store backend is Postgres
    (EVENT_STORE_BACKEND=postgres) — pipeline ownership does not yet have a
    Postgres adapter (tracked in
    docs/plans/pipeline-ownership-authz-hardening.md). In that
    configuration, ownership lives in a separate SQLite file from the
    Postgres-backed events — a known limitation, not the final state, but
    still strictly better than the JSON file it replaces (durable, fails
    closed on lookup errors instead of silently allowing).
    """
    global _pipeline_ownership_repo
    if _pipeline_ownership_repo is None:
        if db_path is None:
            from reasoner.infrastructure.persistence.event_store import get_event_store
            event_store = get_event_store()
            db_path = getattr(event_store, "db_path", None)
        _pipeline_ownership_repo = PipelineOwnershipRepository(db_path=db_path)
    return _pipeline_ownership_repo


async def ensure_pipeline_ownership_backfilled() -> None:
    """Run the legacy-JSON backfill once per process.

    Idempotent and safe to call on every request: no-ops immediately once
    the first successful backfill has run. If that attempt fails (e.g. a
    transient disk error), the next call retries rather than giving up for
    the rest of the process lifetime.
    """
    global _backfill_done
    if _backfill_done:
        return
    try:
        await get_pipeline_ownership_repo().backfill_from_json()
        _backfill_done = True
    except Exception:
        logger.warning(
            "Pipeline ownership backfill failed; will retry on next access",
            exc_info=True,
        )


def reset_pipeline_ownership_repo() -> None:
    """Reset the global singleton and backfill flag (for testing)."""
    global _pipeline_ownership_repo, _backfill_done
    _pipeline_ownership_repo = None
    _backfill_done = False
