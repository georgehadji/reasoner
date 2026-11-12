"""Valkey adapter for ``UnsettledRunPort`` (audit 6, finding 4, decision D2).

A sorted set rather than a plain list: the score is the record time, so entries older
than ``RETENTION_SECONDS`` are trimmed on every write. They hold a ``user_id``, and an
unreplayed entry must not outlive its use or the GDPR erasure window.

If Valkey is down too, ``record`` raises and the caller falls back to a structured
ERROR log with the same fields, which is the last record there is.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict

from reasoner.core.ports.unsettled_run_port import UnsettledRun
from reasoner.infrastructure.valkey.client import get_valkey_pool

logger = logging.getLogger(__name__)

KEY = "unsettled_runs"
RETENTION_SECONDS = 30 * 24 * 3600


def _member(run: UnsettledRun) -> str:
    return json.dumps(asdict(run), sort_keys=True)


class ValkeyUnsettledRunStore:
    async def record(self, run: UnsettledRun) -> None:
        client = get_valkey_pool()
        await client.zadd(KEY, {_member(run): run.recorded_at})
        dropped = await client.zremrangebyscore(KEY, 0, time.time() - RETENTION_SECONDS)
        if dropped:
            # By design (GDPR): the trim stays, but a dropped entry is an unsettled
            # run nobody replayed, so say how many.
            logger.warning(
                "unsettled_runs: dropped %d entries older than %d days without replay",
                dropped, RETENTION_SECONDS // 86400,
            )

    async def list_pending(self, limit: int) -> list[UnsettledRun]:
        members = await get_valkey_pool().zrange(KEY, 0, max(0, limit - 1))
        return [UnsettledRun(**json.loads(m)) for m in members]

    async def remove(self, run: UnsettledRun) -> None:
        await get_valkey_pool().zrem(KEY, _member(run))

    async def erase_user(self, user_id: str) -> None:
        """Drop every entry for one account (data erasure).

        shortcut: scans the whole set. It holds at most 30 days of failed settlements,
        so it is small; index by user if it ever is not.
        """
        client = get_valkey_pool()
        for member in await client.zrange(KEY, 0, -1):
            if json.loads(member).get("user_id") == user_id:
                await client.zrem(KEY, member)
