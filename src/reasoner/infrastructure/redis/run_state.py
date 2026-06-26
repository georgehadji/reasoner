"""
Distributed run state backed by Redis with in-memory fallback.

Replaces module-level _cancelled_runs and _active_runs dicts
to support multi-worker deployments. Falls back to in-memory
storage when Redis is unavailable (Critical Enhancement 9.7).

Critical Enhancements:
- 9.1: Uses Redis Sets (O(1) per op) instead of SCAN iteration (O(N)).
- 9.2: pop_cancelled uses atomic Lua script instead of non-atomic GET+DELETE.
- 9.3: No .decode() — Redis client uses decode_responses=True.
- 9.7: Circuit-breaker-style fallback to in-memory on Redis failure.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Redis key names
ACTIVE_SET = "active_runs"
CANCELLED_SET = "cancelled_runs"
TTL_SECONDS = 300  # Auto-cleanup after 5 minutes

# Lua script for atomic pop-cancelled (9.2)
# Returns 1 if the run_id was in the cancelled set, 0 otherwise.
_POP_CANCELLED_LUA = """
local was_member = redis.call('SISMEMBER', KEYS[1], ARGV[1])
if was_member == 1 then
    redis.call('SREM', KEYS[1], ARGV[1])
end
return was_member
"""


class _RedisUnavailable(Exception):
    """Internal signal that Redis is not reachable."""


class RunStateManager:
    """Manages pipeline run state in Redis with in-memory fallback."""

    def __init__(self) -> None:
        self._redis: Any | None = None
        self._fallback: "RunStateStore | None" = None
        self._redis_ok: bool = True
        self._redis_last_fail: float = 0.0
        self._redis_cooldown_seconds: float = 5.0
        self._lock = asyncio.Lock()
        self._pop_cancelled_sha: str | None = None

    def _get_redis(self) -> Any:
        """Lazy-load Redis client."""
        if self._redis is None:
            from reasoner.infrastructure.redis.client import get_redis
            self._redis = get_redis()
        return self._redis

    async def _ensure_lua(self) -> None:
        """Load the atomic pop-cancelled Lua script once."""
        if self._pop_cancelled_sha is not None:
            return
        redis = self._get_redis()
        self._pop_cancelled_sha = await redis.script_load(_POP_CANCELLED_LUA)

    def _should_try_redis(self) -> bool:
        """Circuit-breaker style: don't hammer Redis if it's down."""
        if self._redis_ok:
            return True
        return time.monotonic() - self._redis_last_fail > self._redis_cooldown_seconds

    async def _redis_op(self, coro_factory) -> Any:
        """Execute a Redis coroutine factory, falling back to memory on failure.

        Uses a factory (callable) instead of a pre-created coroutine to avoid
        'never awaited' warnings when the circuit breaker rejects early.
        """
        if not self._should_try_redis():
            raise _RedisUnavailable("Redis cooldown active")
        try:
            result = await coro_factory()
            if not self._redis_ok:
                self._redis_ok = True
                logger.info("Redis run-state recovered")
            return result
        except Exception as exc:
            self._redis_ok = False
            self._redis_last_fail = time.monotonic()
            logger.warning("Redis run-state failed (%s), falling back to memory", exc)
            raise _RedisUnavailable(str(exc))

    def _get_fallback(self) -> "RunStateStore":
        """Lazy-create the in-memory fallback store.
        In production, this should not be used for correctness.
        """
        from reasoner.core.settings import settings
        if settings.ENVIRONMENT == "production":
            raise RuntimeError("In-memory fallback for run state is disabled in production (requires Redis).")
            
        if self._fallback is None:
            logger.warning("Using in-memory fallback for run state (safe only for single-worker/dev).")
            from reasoner.infrastructure.redis.in_memory import RunStateStore
            self._fallback = RunStateStore()
        return self._fallback

    # ── Public API ──

    async def try_register(self, client_run_id: str, ttl: int = 3600) -> bool:
        """Atomically register a run. Returns True if newly created, False if already exists.

        Uses Redis SET NX for atomic check-and-register (C2). In-memory fallback
        uses a plain set check (not atomic under concurrency, but acceptable for
        single-worker deployments where the race window does not exist).
        """
        try:
            return await self._redis_op(lambda: self._try_register_redis(client_run_id, ttl))
        except _RedisUnavailable:
            return self._get_fallback().try_register(client_run_id, ttl)

    async def _try_register_redis(self, client_run_id: str, ttl: int) -> bool:
        redis = self._get_redis()
        # SET NX returns None if key already exists (not created)
        result = await redis.set(f"run:{client_run_id}", "1", nx=True, ex=ttl)
        return result is not None  # True = newly created, False = already exists

    async def add(self, run_id: str, user_id: str | None = None) -> asyncio.Event:
        """Register a new run and return its cancel event."""
        try:
            await self._redis_op(lambda: self._add_redis(run_id))
        except _RedisUnavailable:
            pass
        return await self._get_fallback().add(run_id, user_id=user_id)

    async def _add_redis(self, run_id: str) -> None:
        redis = self._get_redis()
        await redis.sadd(ACTIVE_SET, run_id)
        await redis.expire(ACTIVE_SET, TTL_SECONDS)
        await redis.expire(CANCELLED_SET, TTL_SECONDS)

    async def remove(self, run_id: str) -> None:
        """Clean up a run's state."""
        try:
            await self._redis_op(lambda: self._remove_redis(run_id))
        except _RedisUnavailable:
            pass
        await self._get_fallback().remove(run_id)

    async def _remove_redis(self, run_id: str) -> None:
        redis = self._get_redis()
        await redis.srem(ACTIVE_SET, run_id)
        await redis.srem(CANCELLED_SET, run_id)

    async def get_cancel_event(self, run_id: str) -> asyncio.Event | None:
        """Get the cancel event for a run."""
        return await self._get_fallback().get_cancel_event(run_id)

    async def request_cancel(self, run_id: str) -> bool:
        """Signal cancellation for a run."""
        try:
            await self._redis_op(lambda: self._cancel_redis(run_id))
        except _RedisUnavailable:
            pass
        return await self._get_fallback().request_cancel(run_id)

    # Alias for compatibility with plan examples
    cancel = request_cancel

    async def _cancel_redis(self, run_id: str) -> None:
        redis = self._get_redis()
        await redis.sadd(CANCELLED_SET, run_id)
        await redis.expire(CANCELLED_SET, TTL_SECONDS)

    async def request_cancel_all(self) -> list[str]:
        """Signal cancellation for all active runs."""
        try:
            targets = await self._redis_op(self._cancel_all_redis)
        except _RedisUnavailable:
            targets = []
        fallback_targets = await self._get_fallback().request_cancel_all()
        seen = set(targets)
        for rid in fallback_targets:
            if rid not in seen:
                targets.append(rid)
                seen.add(rid)
        return targets

    async def _cancel_all_redis(self) -> list[str]:
        """Cancel all active runs in Redis using SMEMBERS (O(1) per member, not SCAN)."""
        redis = self._get_redis()
        run_ids = await redis.smembers(ACTIVE_SET)
        if run_ids:
            pipe = redis.pipeline()
            for rid in run_ids:
                pipe.sadd(CANCELLED_SET, rid)
            pipe.delete(ACTIVE_SET)
            await pipe.execute()
        return list(run_ids)

    def is_active(self, run_id: str) -> bool:
        """Check if a run is currently active (non-locking, best-effort)."""
        return self._get_fallback().is_active(run_id)

    def get_owner(self, run_id: str) -> str | None:
        """Return the user_id that owns a run, or None if anonymous/not found."""
        return self._get_fallback().get_owner(run_id)

    @property
    def active_runs(self) -> set[str]:
        """Return a snapshot of active run IDs."""
        return self._get_fallback().active_runs

    async def reset(self) -> None:
        """Clear all state (for test isolation)."""
        try:
            redis = self._get_redis()
            await redis.delete(ACTIVE_SET, CANCELLED_SET)
        except Exception:
            pass
        if self._fallback is not None:
            await self._fallback.reset()

    # ── New atomic methods for the streaming layer ──

    async def register(self, run_id: str) -> None:
        """Mark a run as active (idempotent)."""
        await self.add(run_id)

    async def unregister(self, run_id: str) -> None:
        """Remove a run from active set."""
        await self.remove(run_id)

    async def is_cancelled(self, run_id: str) -> bool:
        """Check if a run has been requested to cancel."""
        try:
            return await self._redis_op(lambda: self._is_cancelled_redis(run_id))
        except _RedisUnavailable:
            pass
        event = await self._get_fallback().get_cancel_event(run_id)
        return event is not None and event.is_set()

    async def _is_cancelled_redis(self, run_id: str) -> bool:
        redis = self._get_redis()
        return await redis.sismember(CANCELLED_SET, run_id)

    async def pop_cancelled(self, run_id: str) -> bool:
        """Atomically check and clear cancellation flag (9.2: Lua script)."""
        try:
            return await self._redis_op(lambda: self._pop_cancelled_redis(run_id))
        except _RedisUnavailable:
            pass
        event = await self._get_fallback().get_cancel_event(run_id)
        if event is not None and event.is_set():
            event.clear()
            return True
        return False

    async def _pop_cancelled_redis(self, run_id: str) -> bool:
        redis = self._get_redis()
        await self._ensure_lua()
        result = await redis.evalsha(
            self._pop_cancelled_sha,  # type: ignore[arg-type]
            1,
            CANCELLED_SET,
            run_id,
        )
        return bool(result)

    async def cancel_all_active(self) -> int:
        """Cancel all currently active runs. Returns count."""
        targets = await self.request_cancel_all()
        return len(targets)


# Module-level singleton — shared across the API layer.
_run_state_manager = RunStateManager()
