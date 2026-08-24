"""Application-layer compaction service.

Decides when to compact (age threshold, batch size, enabled flag) and
delegates actual deletion to the infrastructure event store. Lives in the
application layer to keep policy decisions out of infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
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
            {"deleted_events": N, "batches": M}
        """
        if not settings.COMPACTION_ENABLED:
            logger.info("Compaction disabled (COMPACTION_ENABLED=false)")
            return {"deleted_events": 0, "batches": 0}

        cutoff = self._cutoff()
        logger.info(
            "Compaction starting (cutoff=%s, dry_run=%s, retention_days=%d)",
            cutoff.isoformat(),
            dry_run,
            settings.EVENT_RETENTION_DAYS,
        )

        if dry_run:
            return await self._count_eligible(cutoff)

        total_deleted = 0
        batches = 0
        while True:
            try:
                deleted = await self._store.prune_events_before(
                    cutoff=cutoff,
                    batch_size=COMPACTION_BATCH_SIZE,
                )
            except Exception as exc:
                logger.error("Compaction batch %d failed: %s", batches + 1, exc)
                break

            batches += 1
            total_deleted += deleted
            logger.info("Compaction batch %d: deleted %d rows", batches, deleted)

            if deleted < COMPACTION_BATCH_SIZE:
                break  # last batch was partial — nothing left to prune

            await asyncio.sleep(0)  # yield to event loop between batches

        logger.info(
            "Compaction complete: %d events deleted in %d batches",
            total_deleted,
            batches,
        )
        return {"deleted_events": total_deleted, "batches": batches}

    async def _count_eligible(self, cutoff: datetime) -> dict[str, int]:
        if hasattr(self._store, "count_eligible_events"):
            n = await self._store.count_eligible_events(cutoff)
            return {"eligible_events": n, "dry_run": True}
        return {"eligible_events": -1, "dry_run": True, "note": "count not supported by this store"}


async def run_nightly_compaction_loop(event_store: Any) -> None:
    """Background loop that runs compaction once per day at COMPACTION_RUN_HOUR_UTC.

    Designed to run as a long-lived asyncio task from the FastAPI lifespan.
    Handles asyncio.CancelledError cleanly for graceful shutdown.
    """
    service = CompactionService(event_store)

    while True:
        now = datetime.now(tz=UTC)
        target_hour = settings.COMPACTION_RUN_HOUR_UTC

        next_run = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)

        sleep_seconds = (next_run - now).total_seconds()
        logger.info(
            "Compaction loop sleeping %.0fs until %s UTC",
            sleep_seconds,
            next_run.isoformat(),
        )

        try:
            await asyncio.sleep(sleep_seconds)
        except asyncio.CancelledError:
            logger.info("Compaction loop cancelled during sleep")
            return

        try:
            await service.run_once()
        except asyncio.CancelledError:
            logger.info("Compaction loop cancelled during run")
            return
        except Exception as exc:
            logger.error("Nightly compaction failed: %s", exc, exc_info=True)
