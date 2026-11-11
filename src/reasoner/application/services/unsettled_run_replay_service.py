"""Replay runs whose settlement failed (audit 6, finding 4).

``run_metering`` records a run it served but could not bill. Once the ledger is
back, an admin replays them here. Each replay is ``CreditService.true_up_run`` with the
original ``reference_id``, which the ledger treats as an idempotency key, so a replay
of a run that did settle (a timeout can hide a write that landed) moves nothing, and
two admins replaying at once cannot double-charge.
"""

from __future__ import annotations

import logging

from reasoner.core.ports.unsettled_run_port import UnsettledRunPort
from reasoner.application.services.credit_service import CreditService

logger = logging.getLogger(__name__)


class UnsettledRunReplayService:
    def __init__(self, store: UnsettledRunPort, credits: CreditService):
        self._store = store
        self._credits = credits

    async def replay(self, limit: int = 50) -> dict[str, int]:
        """Settle up to ``limit`` pending runs, oldest first.

        An entry is removed only after its ledger write returns, so a crash or a
        still-down ledger leaves it for the next replay.
        """
        replayed = failed = 0
        for run in await self._store.list_pending(limit):
            try:
                await self._credits.true_up_run(
                    run.user_id,
                    reserved_credits=run.reserved_credits,
                    cost_usd=run.cost_usd,
                    reference_id=run.reference_id,
                    preset=run.preset,
                )
            except Exception:
                failed += 1
                logger.warning(
                    "Unsettled run replay failed for user %s run %s",
                    run.user_id, run.reference_id, exc_info=True,
                )
                continue
            await self._store.remove(run)
            replayed += 1
        return {"replayed": replayed, "failed": failed}
