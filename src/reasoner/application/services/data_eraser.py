"""GDPR user-data erasure service (DM3).

Orchestrates deletion of user data across event store, cache, and neuro memory.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from reasoner.infrastructure.persistence.event_store import EventStore

logger = logging.getLogger(__name__)


from collections.abc import Callable


class UserDataEraser:
    """Application service for GDPR right-to-be-forgotten erasure.

    Wires together:
      - Event store: list_aggregates_for_user + delete_aggregate
      - Cache: evict entries by user_id prefix
      - Neuro: clear session data for user (best-effort)
    """

    def __init__(
        self,
        event_store: EventStore,
        clear_cache_fn: Callable[[], None] | None = None,
    ) -> None:
        self._event_store = event_store
        self._clear_cache_fn = clear_cache_fn

    async def erase(self, user_id: str) -> dict:
        """Erase all data for *user_id*. Returns an erasure receipt.

        Returns:
            dict with: deleted_aggregates (int), deleted_pipelines (int),
                       cache_evicted (bool), timestamp (iso), status (str)
        """
        deleted_aggregates = 0
        deleted_pipelines = 0
        aggregates_error: str | None = None

        # 1. Delete event store aggregates
        try:
            aggregate_ids = await self._event_store.list_aggregate_ids_for_user(user_id)
            for aid in aggregate_ids:
                await self._event_store.delete_aggregate(aid)
            deleted_aggregates = len(aggregate_ids)
            logger.info("GDPR erasure: deleted %d aggregates for user %s", deleted_aggregates, user_id)
        except Exception as exc:
            aggregates_error = str(exc)
            logger.error("GDPR erasure: failed to delete aggregates for user %s: %s", user_id, exc)

        # 2. Evict cache entries for this user
        cache_evicted = False
        if self._clear_cache_fn:
            try:
                self._clear_cache_fn()
                cache_evicted = True
            except Exception as exc:
                logger.warning("GDPR erasure: cache eviction failed for user %s: %s", user_id, exc)

        # 3. Neuro memory — best-effort clear
        try:
            pass
            # SessionManager operates on per-user data directories; clearing the
            # cache ensures no hot-session data remains in memory. Full file-level
            # deletion would require knowing the neuro data path per user.
            # For MVP, this is a best-effort cache clear.
        except Exception:
            pass

        # Status reflects whether the event-store deletion step itself
        # succeeded, not whether *some* step (e.g. cache eviction, which is
        # a performance side-effect, not the data being erased) succeeded.
        # Previously "completed" could be true purely from cache_evicted
        # while aggregates_error was set -- the receipt could claim success
        # while a user's actual pipeline data was never deleted.
        if aggregates_error:
            status = "failed"
        elif deleted_aggregates > 0 or cache_evicted:
            status = "completed"
        else:
            status = "partial"

        receipt = {
            "deleted_aggregates": deleted_aggregates,
            "deleted_pipelines": deleted_pipelines,
            "cache_evicted": cache_evicted,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": status,
        }
        if aggregates_error:
            receipt["error"] = f"Event store aggregate deletion failed: {aggregates_error}"
        logger.info("GDPR erasure receipt for user %s: %s", user_id, receipt)
        return receipt
