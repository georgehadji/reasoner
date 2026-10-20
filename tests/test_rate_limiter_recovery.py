"""The Redis rate limiter recovers, and its Lua script neither leaks keys nor
counts rejected calls (OPS-1).

One Redis error set `_redis_available=False` for the life of the process, and
with fail_closed (the default) every request was then denied until a restart.
The Lua script ZADDed every call before deciding, so a client hammering past
its limit kept its own window full, and no key had a TTL.
See docs/plans/audit-remediation-2026-10-20.md, OPS-1.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

from reasoner.core.constants import RATE_LIMITER_REDIS_RETRY_SECONDS
from reasoner.infrastructure import rate_limiter as rl_mod
from reasoner.infrastructure.rate_limiter import RateLimitConfig, RateLimiter


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now


class _FlakyScript:
    def __init__(self):
        self.down = False
        self.calls = 0

    async def __call__(self, keys, args):
        self.calls += 1
        if self.down:
            raise ConnectionError("valkey went away")
        return [1, 9, 0, "allowed"]


@pytest.fixture
def limiter(monkeypatch):
    monkeypatch.setattr(rl_mod.settings, "RATE_LIMITER_REDIS_FAILURE_MODE", "fail_closed")
    clock = _Clock()
    rl = RateLimiter(RateLimitConfig(), clock=clock)
    rl._redis_client = object()
    rl._redis_script = _FlakyScript()
    rl._redis_available = True
    return rl, clock


@pytest.mark.asyncio
async def test_requests_are_allowed_again_after_the_cooldown(limiter):
    rl, clock = limiter
    script = rl._redis_script

    script.down = True
    assert (await rl.is_allowed("c"))[0] is False  # the failure itself, fail_closed

    script.down = False
    clock.now += RATE_LIMITER_REDIS_RETRY_SECONDS / 2
    allowed, info = await rl.is_allowed("c")
    assert allowed is False and info["reason"] == "rate_limiter_unavailable"
    assert script.calls == 1, "Redis must not be hammered during the cooldown"

    clock.now += RATE_LIMITER_REDIS_RETRY_SECONDS
    assert (await rl.is_allowed("c"))[0] is True, "a recovered Redis must be used again"
    assert rl._redis_available is True


# ── The Lua script, against a real Valkey/Redis ─────────────────────────────

VALKEY = os.environ.get("REASONER_TEST_VALKEY_URL")
_LUA = Path(rl_mod.__file__).parent / "redis" / "scripts" / "rate_limit.lua"


def test_both_lua_copies_are_identical():
    twin = Path(rl_mod.__file__).parent / "valkey" / "scripts" / "rate_limit.lua"
    assert _LUA.read_text(encoding="utf-8") == twin.read_text(encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(not VALKEY, reason="REASONER_TEST_VALKEY_URL not set")
async def test_lua_sets_ttls_and_does_not_count_rejections():
    import valkey.asyncio as aioredis

    client = aioredis.from_url(VALKEY, decode_responses=True)
    rl = RateLimiter(RateLimitConfig(requests_per_minute=3, requests_per_hour=100, burst_size=50))
    rl._redis_client = client
    rl._redis_script = client.register_script(_LUA.read_text(encoding="utf-8"))
    rl._redis_available = True
    cid = f"test-{uuid.uuid4().hex[:8]}"
    keys = [f"rate_limit:{cid}:{s}" for s in ("tokens", "minute", "hour")]
    try:
        results = [(await rl.is_allowed(cid))[0] for _ in range(6)]
        assert results == [True, True, True, False, False, False]
        assert await client.zcard(keys[1]) == 3, "rejections were recorded in the window"
        for key in keys:
            assert await client.pttl(key) > 0, f"{key} has no TTL"
    finally:
        await client.delete(*keys)
        await client.aclose()
