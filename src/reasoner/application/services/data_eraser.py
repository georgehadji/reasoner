"""GDPR user-data erasure service (DM3).

Orchestrates deletion of user data across event store, cache, and neuro memory.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from reasoner.infrastructure.persistence.event_store import EventStore

logger = logging.getLogger(__name__)


from typing import Callable

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

        # 3. Neuro long-term memory.
        #
        # This step used to import SessionManager, never call it, and fall
        # through — so a user's hot/warm/cold session transcripts (their prompts
        # and our responses, verbatim) survived an Article 17 erasure while the
        # receipt still reported "completed". Neuro isolates tenants by agent
        # directory, so erasure is the removal of that directory.
        neuro_erased = False
        neuro_error: str | None = None
        try:
            import shutil

            from reasoner.neuro.config import get_agent_data_dir, load_config

            agent_dir = get_agent_data_dir(load_config(), agent_id=str(user_id))
            if agent_dir.exists():
                # Refuse to remove anything that isn't the per-agent directory —
                # a misconfigured data_dir must not turn erasure into rm -rf.
                if agent_dir.name != str(user_id) or agent_dir.parent.name != "agents":
                    raise RuntimeError(
                        f"refusing to erase unexpected neuro path: {agent_dir}"
                    )
                shutil.rmtree(agent_dir)
                neuro_erased = True
                logger.info("GDPR erasure: removed neuro memory for user %s", user_id)
            else:
                # Nothing stored for this user is a successful erasure, not a
                # failure — there is no memory left to remove.
                neuro_erased = True
        except Exception as exc:
            neuro_error = str(exc)
            logger.warning(
                "GDPR erasure: neuro memory removal failed for user %s: %s", user_id, exc
            )

        # Status reflects whether the event-store deletion step itself
        # succeeded, not whether *some* step (e.g. cache eviction, which is
        # a performance side-effect, not the data being erased) succeeded.
        # Previously "completed" could be true purely from cache_evicted
        # while aggregates_error was set -- the receipt could claim success
        # while a user's actual pipeline data was never deleted.
        if aggregates_error:
            status = "failed"
        elif not neuro_erased:
            # Long-term memory holds the user's prompts and our responses
            # verbatim. If it survived, the erasure is not complete, whatever
            # else succeeded — saying otherwise is a false compliance record.
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
        }
        if neuro_error:
            receipt["neuro_error"] = neuro_error
        if aggregates_error:
            receipt["error"] = f"Event store aggregate deletion failed: {aggregates_error}"
        logger.info("GDPR erasure receipt for user %s: %s", user_id, receipt)
        return receipt
