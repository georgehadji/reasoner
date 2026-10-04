"""GDPR user-data erasure service (DM3).

Orchestrates deletion of user data across event store, cache, and neuro memory.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from reasoner.infrastructure.persistence.event_store import EventStore

logger = logging.getLogger(__name__)


from collections.abc import Awaitable, Callable


class UserDataEraser:
    """Application service for GDPR right-to-be-forgotten erasure.

    Wires together:
      - Event store: list_aggregates_for_user + delete_aggregate
      - Cache: evict entries by user_id prefix
      - Neuro: NeuroService.erase_owner removes every Neuro tenant (L1/L2/L3
        memory, in-memory and on disk) belonging to the user
    """

    def __init__(
        self,
        event_store: EventStore,
        clear_cache_fn: Callable[[], None] | None = None,
        erase_neuro_fn: Callable[[str], Awaitable[dict]] | None = None,
    ) -> None:
        self._event_store = event_store
        self._clear_cache_fn = clear_cache_fn
        # Injectable for tests; production default (lazy import, see erase())
        # calls the process-wide NeuroService so pipeline and erasure share
        # one view of tenant state.
        self._erase_neuro_fn = erase_neuro_fn

    async def erase(self, user_id: str) -> dict:
        """Erase all data for *user_id*. Returns an erasure receipt.

        Returns:
            dict with: deleted_aggregates (int), deleted_pipelines (int),
                       cache_evicted (bool), neuro_memory_erased (bool),
                       timestamp (iso), status (str)
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

        # 3. Neuro long-term memory.
        #
        # Neuro isolates a signed-in user's data by tenant_key(owner, agent_id)
        # = "u-{owner}-{agent_id}" -- one tenant per (owner, conversation) pair,
        # not a single directory per user -- so erasure has to enumerate every
        # tenant this owner has ever used, in memory and on disk. This used to
        # import SessionManager, never call it, and fall through with a
        # "best-effort cache clear" comment: Neuro L1/L2/L3 memory holds the
        # user's prompts and our responses verbatim, so it survived every
        # Article 17 erasure while the receipt said "completed".
        # See neuro.server.NeuroService.erase_owner.
        neuro_erased = False
        neuro_error: str | None = None
        try:
            erase_neuro = self._erase_neuro_fn
            if erase_neuro is None:
                from reasoner.neuro.server import get_neuro_service

                erase_neuro = get_neuro_service().erase_owner

            neuro_result = await erase_neuro(str(user_id))
            neuro_erased = bool(neuro_result.get("erased"))
            if neuro_erased:
                logger.info(
                    "GDPR erasure: removed neuro memory for user %s "
                    "(%d dirs, %d in-memory tenants)",
                    user_id,
                    neuro_result.get("dirs_removed", 0),
                    neuro_result.get("tenants_evicted", 0),
                )
            else:
                neuro_error = neuro_result.get("error") or "neuro erasure reported incomplete"
        except Exception as exc:
            neuro_error = str(exc)
        if neuro_error:
            logger.warning(
                "GDPR erasure: neuro memory removal failed for user %s: %s", user_id, neuro_error
            )

        # Status reflects whether the event-store deletion step itself
        # succeeded, not whether *some* step (e.g. cache eviction, which is
        # a performance side-effect, not the data being erased) succeeded.
        # Previously "completed" could be true purely from cache_evicted
        # while aggregates_error was set -- the receipt could claim success
        # while a user's actual pipeline data was never deleted.
        #
        # Neuro long-term memory holds the user's prompts and our responses
        # verbatim. If it survived, the erasure is not complete, whatever else
        # succeeded -- saying otherwise is a false compliance record.
        if aggregates_error:
            status = "failed"
        elif not neuro_erased:
            status = "partial"
        elif deleted_aggregates > 0 or cache_evicted:
            status = "completed"
        else:
            status = "partial"

        receipt = {
            "deleted_aggregates": deleted_aggregates,
            "deleted_pipelines": deleted_pipelines,
            "cache_evicted": cache_evicted,
            "neuro_memory_erased": neuro_erased,
            "timestamp": datetime.now(UTC).isoformat(),
            "status": status,
        }
        if neuro_error:
            receipt["neuro_error"] = neuro_error
        if aggregates_error:
            receipt["error"] = f"Event store aggregate deletion failed: {aggregates_error}"
        logger.info("GDPR erasure receipt for user %s: %s", user_id, receipt)
        return receipt
