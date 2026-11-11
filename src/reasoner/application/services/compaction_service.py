"""Application-layer compaction service.

Decides when to compact (age threshold, batch size, enabled flag) and
delegates actual deletion to the infrastructure event store. Lives in the
application layer to keep policy decisions out of infrastructure.

Runs only from ``POST /api/admin/compaction/run``, scheduled by the same
external cron as neuro-maintenance. It used to run as a lifespan loop in every
worker, so each one issued the same batches (audit-5 PER-19).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from reasoner.core.constants_limits import COMPACTION_BATCH_SIZE
from reasoner.core.settings import settings

logger = logging.getLogger(__name__)


class CompactionService:
    """Prunes old events from the event store in daily batches."""

    def __init__(self, event_store: Any) -> None:
        self._store = event_store

    def _cutoff(self) -> datetime:
        return datetime.now(tz=UTC) - timedelta(days=settings.EVENT_RETENTION_DAYS)

    async def run_once(self, dry_run: bool = False) -> dict[str, int]:
        """Run one full compaction pass, looping in batches until no more eligible rows remain.

        Args:
            dry_run: If True, count eligible rows without deleting.

        Returns:
            {"deleted_audit_events": A, "deleted_events": N, "batches": M}
        """
        if not settings.COMPACTION_ENABLED:
            logger.info("Compaction disabled (COMPACTION_ENABLED=false)")
            return {"deleted_audit_events": 0, "deleted_events": 0, "batches": 0}

        cutoff = self._cutoff()
        logger.info(
            "Compaction starting (cutoff=%s, dry_run=%s, retention_days=%d)",
            cutoff.isoformat(),
            dry_run,
            settings.EVENT_RETENTION_DAYS,
        )

        if dry_run:
            return await self._count_eligible(cutoff)

        # Two loops, one per row class: a call that pruned both classes could
        # return up to twice the batch and break the "partial batch = done" test.
        audit_deleted, audit_batches = await self._drain(
            self._store.prune_audit_events_before, cutoff
        )
        deleted, batches = await self._drain(self._store.prune_events_before, cutoff)
        logger.info(
            "Compaction complete: %d audit rows and %d events deleted in %d batches",
            audit_deleted,
            deleted,
            audit_batches + batches,
        )
        return {
            "deleted_audit_events": audit_deleted,
            "deleted_events": deleted,
            "batches": audit_batches + batches,
        }

    async def _drain(
        self, prune: Callable[..., Awaitable[int]], cutoff: datetime
    ) -> tuple[int, int]:
        """Call *prune* in batches until a partial batch. Stops on error, never raises."""
        total_deleted = 0
        batches = 0
        while True:
            try:
                deleted = await prune(cutoff=cutoff, batch_size=COMPACTION_BATCH_SIZE)
            except Exception as exc:
                logger.error("Compaction batch %d failed: %s", batches + 1, exc)
                break

            batches += 1
            total_deleted += deleted
            logger.info("Compaction batch %d: deleted %d rows", batches, deleted)

            if deleted < COMPACTION_BATCH_SIZE:
                break  # last batch was partial — nothing left to prune

            await asyncio.sleep(0)  # yield to event loop between batches
        return total_deleted, batches

    async def _count_eligible(self, cutoff: datetime) -> dict[str, Any]:
        if hasattr(self._store, "count_eligible_events"):
            return {
                "eligible_audit_events": await self._store.count_eligible_audit_events(cutoff),
                "eligible_events": await self._store.count_eligible_events(cutoff),
                "dry_run": True,
            }
        return {"eligible_events": -1, "dry_run": True, "note": "count not supported by this store"}
