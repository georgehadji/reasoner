"""In-process maintenance loop (audit 7, findings 10, 14 and 20).

The job bodies already exist behind admin endpoints, but nothing called them, so
orphaned credit holds, unsettled runs and old dead-letter and feedback rows only
cleared when an operator remembered. One worker per interval takes a Valkey lock
and runs the jobs in turn; the others skip that interval.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from reasoner.core.constants_limits import (
    DEAD_LETTER_RETENTION_DAYS,
    FEEDBACK_RETENTION_DAYS,
    MAINTENANCE_INTERVAL_SECONDS,
)
from reasoner.core.degrade import degraded

logger = logging.getLogger(__name__)

LOCK_KEY = "maintenance:lock"
# Shorter than the interval, so a lock from a worker that died is gone by the next pass.
_LOCK_TTL_SECONDS = MAINTENANCE_INTERVAL_SECONDS - 30


async def _prune_dead_letters() -> dict:
    from reasoner.infrastructure.billing.webhooks import _get_dead_letter_repo

    repo = await _get_dead_letter_repo()
    if repo is None:
        return {"available": False}
    return {"pruned": await repo.prune_older_than(DEAD_LETTER_RETENTION_DAYS)}


async def _prune_feedback() -> dict:
    from reasoner.api.routes.feedback import _feedback_store

    return {"pruned": await _feedback_store.prune_older_than(FEEDBACK_RETENTION_DAYS)}


def _jobs() -> list[tuple[str, Callable[[], Awaitable[dict]]]]:
    from reasoner.api.cron import run_reservation_sweep, run_unsettled_replay

    return [
        ("maintenance.reservation_sweep", run_reservation_sweep),
        ("maintenance.unsettled_replay", run_unsettled_replay),
        ("maintenance.dead_letter_prune", _prune_dead_letters),
        ("maintenance.feedback_prune", _prune_feedback),
    ]


async def _holds_lock() -> bool:
    """Take the interval lock. Valkey down means no coordination is possible, so run:
    every job is idempotent, and skipping would leave the work undone."""
    try:
        from reasoner.infrastructure.valkey.client import get_valkey_pool

        return bool(await get_valkey_pool().set(LOCK_KEY, "1", nx=True, ex=_LOCK_TTL_SECONDS))
    except Exception as exc:
        return degraded("maintenance.lock", True, exc=exc)


async def run_maintenance_once() -> None:
    if not await _holds_lock():
        return
    for site, job in _jobs():
        try:
            logger.info("%s: %s", site, await job())
        except Exception as exc:
            # One failing job must not stop the others.
            degraded(site, None, exc=exc)


async def maintenance_loop() -> None:
    while True:
        await run_maintenance_once()
        await asyncio.sleep(MAINTENANCE_INTERVAL_SECONDS)
