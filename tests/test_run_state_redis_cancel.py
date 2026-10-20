"""Stop reaches a run when Redis is healthy (RUN-2).

With Redis up, ``RunStateManager.add`` and ``request_cancel`` each built a
throwaway in-memory store. The run's cancel Event lived only in the first
one, so ``request_cancel`` could never set it, and ``is_active`` read a store
that raises in production. The existing suites run without Redis and only
saw the fallback path.
See docs/plans/audit-remediation-2026-10-20.md, RUN-2.
"""

from __future__ import annotations

import pytest

from reasoner.core.settings import settings
from reasoner.infrastructure.redis.run_state import RunStateManager


class _FakeRedis:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.sets: dict[str, set[str]] = {}

    def _check(self):
        if self.fail:
            raise ConnectionError("redis down")

    async def sadd(self, key, member):
        self._check()
        self.sets.setdefault(key, set()).add(member)

    async def srem(self, key, member):
        self._check()
        self.sets.setdefault(key, set()).discard(member)

    async def sismember(self, key, member):
        self._check()
        return member in self.sets.get(key, set())

    async def expire(self, key, ttl):
        self._check()


def _manager(redis: _FakeRedis) -> RunStateManager:
    mgr = RunStateManager()
    mgr._redis = redis
    return mgr


@pytest.mark.asyncio
async def test_stop_sets_the_run_cancel_event_with_redis_up():
    redis = _FakeRedis()
    mgr = _manager(redis)

    event = await mgr.add("run-1", user_id="u1")
    assert mgr.is_active("run-1")
    assert mgr.get_owner("run-1") == "u1"

    assert await mgr.request_cancel("run-1") is True
    assert event.is_set(), "the run's own cancel event must fire"
    assert "run-1" in redis.sets["cancelled_runs"], "other workers see the flag"

    await mgr.remove("run-1")
    assert not mgr.is_active("run-1")


@pytest.mark.asyncio
async def test_stop_works_in_production_when_redis_is_down(monkeypatch):
    """The local events never needed Redis; only idempotency does."""
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    mgr = _manager(_FakeRedis(fail=True))

    event = await mgr.add("run-2")
    assert mgr.is_active("run-2")
    assert await mgr.request_cancel("run-2") is True
    assert event.is_set()


@pytest.mark.asyncio
async def test_idempotency_still_refuses_the_fallback_in_production(monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    mgr = _manager(_FakeRedis(fail=True))
    mgr._redis_ok = False
    with pytest.raises(RuntimeError):
        await mgr.try_register("client-1")
