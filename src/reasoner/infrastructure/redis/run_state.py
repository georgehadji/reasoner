"""
Distributed run state backed by Redis with in-memory fallback.

Replaces module-level _cancelled_runs and _active_runs dicts
to support multi-worker deployments. Falls back to in-memory
storage when Redis is unavailable (Critical Enhancement 9.7).

Critical Enhancements:
- 9.1: Uses Redis Sets (O(1) per op) instead of SCAN iteration (O(N)).
- 9.2: an idempotency claim is released and completed by Lua compare-and-set on
  the holder's token, never by an unconditional DEL.
- 9.3: No .decode() — Redis client uses decode_responses=True.
- 9.7: Circuit-breaker-style fallback to in-memory on Redis failure.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import TYPE_CHECKING, Any

from reasoner.core.constants_limits import PIPELINE_ABSOLUTE_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from reasoner.infrastructure.redis.in_memory import RunStateStore

logger = logging.getLogger(__name__)

# Redis key names
ACTIVE_SET = "active_runs"
CANCELLED_SET = "cancelled_runs"
TTL_SECONDS = 300  # Auto-cleanup after 5 minutes (cancelled set)
# The active set must outlive the longest run, or a global stop issued after it
# lapses finds an empty set and misses runs still going.
ACTIVE_TTL_SECONDS = int(PIPELINE_ABSOLUTE_TIMEOUT_SECONDS) + 300
# Per-run owner key, so /api/stop on any worker can find a run. Outlives the
# 600s pipeline timeout; remove() deletes it as soon as the run ends.
OWNER_PREFIX = "run_owner:"
OWNER_TTL_SECONDS = 3600

# Owner-checked claim release (9.2): delete only if the key still holds this
# holder's token. A stale release from an earlier run must not free a later
# holder's claim.
_RELEASE_CLAIM_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""

# Mark the holder's claim finished, keeping its TTL, so a retry of a run that
# already ended is told so instead of "in progress".
_COMPLETE_CLAIM_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('SET', KEYS[1], ARGV[2], 'KEEPTTL')
end
return 0
"""


class _RedisUnavailable(Exception):
    """Internal signal that Redis is not reachable."""


class RunStateManager:
    """Manages pipeline run state in Redis with in-memory fallback."""

    def __init__(self) -> None:
        self._redis: Any | None = None
        # Process-local store for the per-run cancel Events. An asyncio.Event
        # only exists in this process, so the local store is the source of
        # truth for cancelling a run here, whether or not Redis is up. Redis
        # mirrors membership and flags for other workers.
        self._local: RunStateStore | None = None
        self._warned_fallback = False
        self._redis_ok: bool = True
        self._redis_last_fail: float = 0.0
        self._redis_cooldown_seconds: float = 5.0
        self._lock = asyncio.Lock()

    def _get_redis(self) -> Any:
        """Lazy-load Redis client."""
        if self._redis is None:
            from reasoner.infrastructure.valkey.client import get_valkey_pool
            self._redis = get_valkey_pool()
        return self._redis

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
            raise _RedisUnavailable(str(exc)) from exc

    def _store(self) -> RunStateStore:
        """The process-local store (lazy: in_memory imports would cycle at load)."""
        if self._local is None:
            from reasoner.infrastructure.redis.in_memory import RunStateStore
            self._local = RunStateStore()
        return self._local

    def _get_fallback(self) -> RunStateStore:
        """The local store standing in for Redis in ``try_register``.

        Only idempotency needs Redis for correctness, because the local set
        cannot dedupe across workers. In production that is refused instead.
        Cancel events always use the local store via ``_store()``. They used
        to come from here, and with Redis healthy each call built a throwaway
        store, so a Stop never reached the run
        (docs/plans/audit-remediation-2026-10-20.md RUN-2).
        """
        from reasoner.core.settings import settings
        if settings.ENVIRONMENT == "production":
            raise RuntimeError("In-memory fallback for run state is disabled in production (requires Redis).")
        if not self._warned_fallback:
            self._warned_fallback = True
            logger.warning("Using in-memory fallback for run state (safe only for single-worker/dev).")
        return self._store()

    # ── Public API ──

    async def is_authoritative(self) -> bool:
        """True if the manager holds an authoritative (Redis) connection.

        Callers that need atomic idempotency gating MUST check this before
        calling try_register(). When not authoritative, try_register() will
        raise RuntimeError — the caller is expected to respond with a 503
        (or equivalent backpressure) rather than silently accepting duplicates.
        """
        # Fast path: we know Redis is OK from a recent operation
        if self._redis_ok:
            return True
        # Probe: if we haven't checked lately, try a lightweight round-trip
        if self._should_try_redis():
            try:
                redis = self._get_redis()
                await redis.ping()
                self._redis_ok = True
                self._redis_last_fail = 0.0
                return True
            except Exception:
                self._redis_ok = False
                self._redis_last_fail = time.monotonic()

        # If in development/non-production, we can proceed with fallback
        from reasoner.core.settings import settings
        if settings.ENVIRONMENT != "production":
            return True

        return False

    async def try_register(self, client_run_id: str, ttl: int = 3600, token: str = "1") -> bool:
        """Atomically register a run. Returns True if newly created, False if already exists.

        Uses Redis SET NX for atomic check-and-register (C2).

        Raises RuntimeError if the backing store is non-authoritative (in-memory
        fallback). Callers MUST gate behind is_authoritative() and respond with
        503 unless they explicitly accept the lack of atomicity.
        """
        from reasoner.core.settings import settings
        is_prod = settings.ENVIRONMENT == "production"

        if not self._redis_ok:
            if not is_prod:
                return self._get_fallback().try_register(client_run_id, ttl, token)
            raise RuntimeError(
                "RunStateManager is in fallback mode — try_register() cannot guarantee "
                "atomic idempotency. Call is_authoritative() first and respond 503 when "
                "it returns False."
            )
        try:
            return await self._redis_op(lambda: self._try_register_redis(client_run_id, ttl, token))
        except _RedisUnavailable:
            if not is_prod:
                return self._get_fallback().try_register(client_run_id, ttl, token)
            raise

    async def _try_register_redis(self, client_run_id: str, ttl: int, token: str) -> bool:
        redis = self._get_redis()
        # SET NX returns None if key already exists (not created)
        result = await redis.set(f"run:{client_run_id}", token, nx=True, ex=ttl)
        return result is not None  # True = newly created, False = already exists

    async def release(self, client_run_id: str, token: str) -> None:
        """Drop the claim ``try_register`` took, so a failed run can be retried.

        Only the holder's ``token`` releases it: a stale release is a no-op.
        Raises when Redis cannot be reached in production: the claim then
        expires at its TTL, which the caller reports as degraded.
        """
        from reasoner.core.settings import settings

        try:
            await self._redis_op(
                lambda: self._get_redis().eval(
                    _RELEASE_CLAIM_LUA, 1, f"run:{client_run_id}", token
                )
            )
        except _RedisUnavailable:
            if settings.ENVIRONMENT == "production":
                raise
        if settings.ENVIRONMENT != "production":
            self._store().release(client_run_id, token)

    async def complete(self, client_run_id: str, token: str) -> None:
        """Mark the holder's claim finished, keeping its TTL. Raises like ``release``."""
        from reasoner.core.settings import settings
        from reasoner.infrastructure.redis.in_memory import CLAIM_DONE

        try:
            await self._redis_op(
                lambda: self._get_redis().eval(
                    _COMPLETE_CLAIM_LUA, 1, f"run:{client_run_id}", token, CLAIM_DONE
                )
            )
        except _RedisUnavailable:
            if settings.ENVIRONMENT == "production":
                raise
        if settings.ENVIRONMENT != "production":
            self._store().complete(client_run_id, token)

    async def claim_finished(self, client_run_id: str) -> bool:
        """True when the claim's run ended and ``complete`` marked it."""
        from reasoner.infrastructure.redis.in_memory import CLAIM_DONE

        try:
            value = await self._redis_op(lambda: self._get_redis().get(f"run:{client_run_id}"))
        except _RedisUnavailable:
            return self._store().claim_finished(client_run_id)
        return value == CLAIM_DONE

    async def add(self, run_id: str, user_id: str | None = None) -> asyncio.Event:
        """Register a new run and return its cancel event."""
        with contextlib.suppress(_RedisUnavailable):
            await self._redis_op(lambda: self._add_redis(run_id, user_id))
        return await self._store().add(run_id, user_id=user_id)

    async def _add_redis(self, run_id: str, user_id: str | None = None) -> None:
        redis = self._get_redis()
        await redis.set(f"{OWNER_PREFIX}{run_id}", user_id or "", ex=OWNER_TTL_SECONDS)
        # A stop that landed after the previous run with this id ended (resume
        # reuses the id) must not cancel this one: only a stop made while it
        # is registered counts.
        await redis.srem(CANCELLED_SET, run_id)
        await redis.sadd(ACTIVE_SET, run_id)
        await redis.expire(ACTIVE_SET, ACTIVE_TTL_SECONDS)
        await redis.expire(CANCELLED_SET, TTL_SECONDS)

    async def remove(self, run_id: str) -> None:
        """Clean up a run's state."""
        with contextlib.suppress(_RedisUnavailable):
            await self._redis_op(lambda: self._remove_redis(run_id))
        await self._store().remove(run_id)

    async def _remove_redis(self, run_id: str) -> None:
        redis = self._get_redis()
        await redis.delete(f"{OWNER_PREFIX}{run_id}")
        await redis.srem(ACTIVE_SET, run_id)
        await redis.srem(CANCELLED_SET, run_id)

    async def get_cancel_event(self, run_id: str) -> asyncio.Event | None:
        """Get the cancel event for a run."""
        event = await self._store().get_cancel_event(run_id)
        if event is None:
            # No in-memory event yet — check Redis for pre-existing cancellation
            try:
                cancelled = await self._redis_op(lambda: self._is_cancelled_redis(run_id))
                if cancelled:
                    await self._store().request_cancel(run_id)
                    event = await self._store().get_cancel_event(run_id)
            except _RedisUnavailable:
                pass
        return event

    async def request_cancel(self, run_id: str) -> bool:
        """Signal cancellation for a run."""
        with contextlib.suppress(_RedisUnavailable):
            await self._redis_op(lambda: self._cancel_redis(run_id))
        return await self._store().request_cancel(run_id)

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
        fallback_targets = await self._store().request_cancel_all()
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
        return self._store().is_active(run_id)

    async def lookup(self, run_id: str) -> tuple[bool, str | None]:
        """``(active, owner)`` for a run on any worker.

        is_active()/get_owner() only see this worker's runs, so /api/stop that
        landed on another worker answered "not found" and the run kept going.
        """
        if self._store().is_active(run_id):
            return True, self._store().get_owner(run_id)
        try:
            owner = await self._redis_op(lambda: self._get_redis().get(f"{OWNER_PREFIX}{run_id}"))
        except _RedisUnavailable:
            return False, None
        return (owner is not None), (owner or None)

    def get_owner(self, run_id: str) -> str | None:
        """Return the user_id that owns a run, or None if anonymous/not found."""
        return self._store().get_owner(run_id)

    @property
    def active_runs(self) -> set[str]:
        """Return a snapshot of active run IDs."""
        return self._store().active_runs

    async def reset(self) -> None:
        """Clear all state (for test isolation)."""
        try:
            redis = self._get_redis()
            await redis.delete(ACTIVE_SET, CANCELLED_SET)
        except Exception:
            pass
        if self._local is not None:
            await self._local.reset()

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
            cancelled = await self._redis_op(lambda: self._is_cancelled_redis(run_id))
            if cancelled:
                # Propagate to in-memory fallback so local cancel_event fires
                await self._store().request_cancel(run_id)
            return cancelled
        except _RedisUnavailable:
            pass
        event = await self._store().get_cancel_event(run_id)
        return event is not None and event.is_set()

    async def _is_cancelled_redis(self, run_id: str) -> bool:
        redis = self._get_redis()
        return await redis.sismember(CANCELLED_SET, run_id)

    async def cancel_all_active(self) -> int:
        """Cancel all currently active runs. Returns count."""
        targets = await self.request_cancel_all()
        return len(targets)


# Module-level singleton — shared across the API layer.
_run_state_manager = RunStateManager()
