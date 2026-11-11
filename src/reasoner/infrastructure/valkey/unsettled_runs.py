"""Valkey adapter for ``UnsettledRunPort`` (audit 6, finding 4, decision D2).

A sorted set rather than a plain list: the score is the record time, so entries older
than ``RETENTION_SECONDS`` are trimmed on every write. They hold a ``user_id``, and an
unreplayed entry must not outlive its use or the GDPR erasure window.

If Valkey is down too, ``record`` raises and the caller falls back to a structured
ERROR log with the same fields, which is the last record there is.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict

from reasoner.core.ports.unsettled_run_port import UnsettledRun
from reasoner.infrastructure.valkey.client import get_valkey_pool

KEY = "unsettled_runs"
RETENTION_SECONDS = 30 * 24 * 3600


def _member(run: UnsettledRun) -> str:
    return json.dumps(asdict(run), sort_keys=True)


class ValkeyUnsettledRunStore:
    async def record(self, run: UnsettledRun) -> None:
        client = get_valkey_pool()
        await client.zadd(KEY, {_member(run): run.recorded_at})
        await client.zremrangebyscore(KEY, 0, time.time() - RETENTION_SECONDS)

    async def list_pending(self, limit: int) -> list[UnsettledRun]:
        members = await get_valkey_pool().zrange(KEY, 0, max(0, limit - 1))
        return [UnsettledRun(**json.loads(m)) for m in members]

    async def remove(self, run: UnsettledRun) -> None:
        await get_valkey_pool().zrem(KEY, _member(run))
