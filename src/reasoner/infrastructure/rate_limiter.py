"""
Production-Ready Rate Limiter
Token bucket algorithm with Redis-like sliding window.

ARCHITECTURAL NOTE:
    This implementation stores all state in-memory. In a multi-worker or
    horizontally-scaled deployment each process maintains its own token
    buckets, which means a client can bypass limits by hitting different
    workers. Set RATE_LIMITER_MODE to a shared backend (e.g., 'redis')
    or place a reverse-proxy rate limiter in front of the application
    for production multi-instance deployments.
"""

from __future__ import annotations

import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
import asyncio
import math # Added math for ceil in Lua script error fallback

logger = logging.getLogger(__name__)

import valkey.asyncio as aioredis
from reasoner.infrastructure.redis.client import get_redis
from reasoner.core.constants import MAX_RATE_LIMIT_BUCKETS # Imported MAX_RATE_LIMIT_BUCKETS

from reasoner.core.settings import settings
_REDIS_RATE_LIMITER_ENABLED = settings.RATE_LIMITER_MODE.lower() == "redis"

from reasoner.infrastructure.metrics import REASONER_RATE_LIMIT_REJECTED


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10  # Allow short bursts


@dataclass
class ClientBucket:
    """Token bucket for a client."""
    tokens: float = field(default=0.0)
    last_update: float = field(default_factory=time.monotonic)
    requests_minute: int = 0
    requests_hour: int = 0
    minute_window_start: float = field(default_factory=time.monotonic)
    hour_window_start: float = field(default_factory=time.monotonic)


class RateLimiter:
    """
    Production rate limiter with multiple algorithms.
    
    Features:
    - Token bucket for smooth rate limiting
    - Sliding window for accurate per-minute/hour limits
    - Per-client tracking
    - Async-safe
    """
    
    # MAX_RATE_LIMIT_BUCKETS is now imported at the top
    _MAX_BUCKETS: int = MAX_RATE_LIMIT_BUCKETS

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._redis_client: Optional[aioredis.Redis] = None
        self._redis_script: Any = None
        self._redis_available: bool = False

        is_production = settings.ENVIRONMENT == "production"

        if _REDIS_RATE_LIMITER_ENABLED:
            try:
                self._redis_client = get_redis()
                script_dir = os.path.join(os.path.dirname(__file__), "redis", "scripts")
                script_path = os.path.join(script_dir, "rate_limit.lua")
                if not os.path.isfile(script_path):
                    raise FileNotFoundError(
                        f"Lua rate-limit script not found at {script_path}. "
                        "Check that src/reasoner/infrastructure/redis/scripts/rate_limit.lua exists."
                    )
                with open(script_path, "r", encoding="utf-8") as f:
                    lua_script_content = f.read()
                self._redis_script = self._redis_client.register_script(lua_script_content)
                self._redis_available = True
            except Exception as e:
                error_msg = f"Failed to connect to Redis or load script for rate limiter: {e}"
                if is_production:
                    logger.critical(f"CRITICAL: {error_msg} Failing application startup.")
                    raise RuntimeError(f"Critical rate limiter error: {error_msg}") from e
                else:
                    self._redis_available = False
        else:
            if is_production:
                logger.critical("CRITICAL: RATE_LIMITER_MODE is 'memory' in production. This is unsafe. Failing application startup.")
                raise RuntimeError("Unsafe rate limiter configuration: RATE_LIMITER_MODE=memory in production.")

        # In-memory fallback (always initialized, even if Redis is primary)
        self._buckets: Dict[str, ClientBucket] = defaultdict(ClientBucket)
        self._fallback_lock = asyncio.Lock()

    async def _execute_redis_script(
        self,
        client_id: str,
        refill_rate: float,
        burst_capacity: float,
        requests_per_minute: int,
        requests_per_hour: int,
        requested_tokens: int = 1,
    ) -> tuple[bool, Dict[str, Any]]:
        if not self._redis_available or self._redis_client is None or self._redis_script is None:
            raise ConnectionError("Redis rate limiter not available.")

        current_time_ms = int(time.time() * 1000)
        token_bucket_key = f"rate_limit:{client_id}:tokens"
        minute_window_key = f"rate_limit:{client_id}:minute"
        hour_window_key = f"rate_limit:{client_id}:hour"

        try:
            # KEYS: token_bucket_key, minute_window_key, hour_window_key
            # ARGV: current_time_ms, refill_rate, burst_capacity, requests_per_minute, requests_per_hour, requested_tokens
            result = await self._redis_script(
                keys=[token_bucket_key, minute_window_key, hour_window_key],
                args=[
                    current_time_ms,
                    refill_rate,
                    burst_capacity,
                    requests_per_minute,
                    requests_per_hour,
                    requested_tokens,
                ],
            )
            # Result: [allowed (1/0), tokens_remaining, retry_after_ms, reason_code]
            allowed = bool(result[0])
            tokens_remaining = result[1]
            retry_after_ms = result[2]
            reason = result[3]

            info = {
                "limit_minute": requests_per_minute,
                "limit_hour": requests_per_hour,
                "remaining_minute": 0 if not allowed else requests_per_minute,  # v3.1: Show 0 when rejected (was always showing full limit)
                "remaining_hour": requests_per_hour, # Same as above
                "tokens_remaining": tokens_remaining,
                "retry_after": max(0, retry_after_ms / 1000.0) if retry_after_ms > 0 else None,
                "reason": reason,
            }
            return allowed, info
        except aioredis.RedisError as e:
            print(f"[ERROR] Redis script execution failed: {e}")
            self._redis_available = False # Mark as unavailable for this session
            raise ConnectionError("Redis script execution failed.") from e
        except Exception as e:
            print(f"[ERROR] Unexpected error during Redis rate limiting: {e}")
            self._redis_available = False
            raise ConnectionError("Unexpected Redis error.") from e

    async def _in_memory_is_allowed_for_user(
        self,
        client_id: str,
        multiplier: float = 1.0,
        requested_tokens: int = 1,
    ) -> tuple[bool, Dict[str, Any]]:
        # This is the original in-memory logic, simplified for the fallback.
        # It needs to be self-contained and not rely on self._lock (which is removed).
        async with self._fallback_lock:
            # BUG FIX: Use _in_memory_get_bucket so new clients start with burst_size tokens.
            # Directly accessing self._buckets[client_id] creates a ClientBucket()
            # with tokens=0.0, causing the first request from every client to be rejected.
            self._in_memory_get_bucket(client_id)
            bucket = self._buckets[client_id]
            now = time.monotonic()

            # Refill tokens (in-memory logic)
            elapsed = now - bucket.last_update
            refill_rate = (self.config.requests_per_minute * multiplier) / 60.0
            max_tokens = self.config.burst_size * multiplier
            bucket.tokens = min(max_tokens, bucket.tokens + (elapsed * refill_rate))
            bucket.last_update = now

            # Reset windows if expired (in-memory logic)
            elapsed_minutes = int((now - bucket.minute_window_start) // 60)
            if elapsed_minutes > 0:
                bucket.requests_minute = 0
                bucket.minute_window_start += elapsed_minutes * 60

            elapsed_hours = int((now - bucket.hour_window_start) // 3600)
            if elapsed_hours > 0:
                bucket.requests_hour = 0
                bucket.hour_window_start += elapsed_hours * 3600
            
            rpm = int(self.config.requests_per_minute * multiplier)
            rph = int(self.config.requests_per_hour * multiplier)

            info: dict = {
                "limit_minute": rpm,
                "limit_hour": rph,
                "remaining_minute": rpm - bucket.requests_minute,
                "remaining_hour": rph - bucket.requests_hour,
                "retry_after": None,
            }

            if bucket.requests_minute >= rpm:
                info["retry_after"] = 60 - (time.monotonic() - bucket.minute_window_start)
                info["reason"] = "per_minute_limit_fallback"
                REASONER_RATE_LIMIT_REJECTED.labels(tier="fallback").inc()
                return False, info

            if bucket.requests_hour >= rph:
                info["retry_after"] = 3600 - (time.monotonic() - bucket.hour_window_start)
                info["reason"] = "per_hour_limit_fallback"
                REASONER_RATE_LIMIT_REJECTED.labels(tier="fallback").inc()
                return False, info

            if bucket.tokens < requested_tokens:
                tokens_needed = requested_tokens - bucket.tokens
                refill_rate = (self.config.requests_per_minute * multiplier) / 60.0
                # BUG FIX: Floor retry_after to at least 1 to prevent the confusing
                # "retry_after: 0" case that occurs when tokens refill in <1s.
                info["retry_after"] = max(1.0, tokens_needed / refill_rate)
                # BUG FIX: Show actual remaining tokens (not requests_minute) so the
                # reported remaining reflects the token bucket state, not the clean window.
                info["remaining_minute"] = int(bucket.tokens)
                info["remaining_hour"] = int(bucket.tokens)
                info["reason"] = "burst_limit_fallback"
                REASONER_RATE_LIMIT_REJECTED.labels(tier="fallback").inc()
                return False, info

            bucket.tokens -= requested_tokens
            bucket.requests_minute += 1
            bucket.requests_hour += 1

            info["remaining_minute"] = rpm - bucket.requests_minute
            info["remaining_hour"] = rph - bucket.requests_hour
            return True, info
    
    async def is_allowed(self, client_id: str) -> tuple[bool, Dict[str, Any]]:
        try:
            return await self._execute_redis_script(
                client_id=client_id,
                refill_rate=self.config.requests_per_minute / 60000.0,
                burst_capacity=self.config.burst_size,
                requests_per_minute=self.config.requests_per_minute,
                requests_per_hour=self.config.requests_per_hour,
                requested_tokens=1,
            )
        except ConnectionError:
            if settings.RATE_LIMITER_REDIS_FAILURE_MODE == "fail_closed":
                logger.warning("Rate limiter Redis unavailable — denying request (fail-closed mode)")
                return False, {
                    "limit_minute": self.config.requests_per_minute,
                    "limit_hour": self.config.requests_per_hour,
                    "remaining_minute": 0,
                    "remaining_hour": 0,
                    "retry_after": None,
                    "reason": "rate_limiter_unavailable",
                }
            logger.warning("Redis unavailable, falling back to in-memory rate limiter for is_allowed.")
            return await self._in_memory_is_allowed_for_user(client_id, 1.0, 1)

    async def is_allowed_for_user(
        self,
        client_id: str,
        tier: str = "default",
    ) -> tuple[bool, Dict[str, Any]]:
        tier_multipliers = {
            "default": 1.0,
            "free": 1.0,
            "pro": 2.0,
            "enterprise": 5.0,
        }
        multiplier = tier_multipliers.get(tier, 1.0)
        
        # Calculate tier-specific limits
        rpm_limit = int(self.config.requests_per_minute * multiplier)
        rph_limit = int(self.config.requests_per_hour * multiplier)
        burst_cap = int(self.config.burst_size * multiplier)
        refill_rate_ms = (self.config.requests_per_minute * multiplier) / 60000.0 # tokens per ms

        try:
            return await self._execute_redis_script(
                client_id=client_id,
                refill_rate=refill_rate_ms,
                burst_capacity=burst_cap,
                requests_per_minute=rpm_limit,
                requests_per_hour=rph_limit,
                requested_tokens=1,
            )
        except ConnectionError:
            if settings.RATE_LIMITER_REDIS_FAILURE_MODE == "fail_closed":
                logger.warning(
                    "Rate limiter Redis unavailable — denying request for %s tier=%s (fail-closed mode)",
                    client_id, tier,
                )
                rpm_limit = int(self.config.requests_per_minute * multiplier)
                rph_limit = int(self.config.requests_per_hour * multiplier)
                return False, {
                    "limit_minute": rpm_limit,
                    "limit_hour": rph_limit,
                    "remaining_minute": 0,
                    "remaining_hour": 0,
                    "retry_after": None,
                    "reason": "rate_limiter_unavailable",
                }
            logger.warning(
                "Redis unavailable, falling back to in-memory rate limiter for user %s (tier: %s).",
                client_id, tier,
            )
            return await self._in_memory_is_allowed_for_user(client_id, multiplier, 1)

    async def record_request(self, client_id: str) -> None:
        # With Redis, the token is consumed by is_allowed, so this method is mostly redundant.
        # However, for consistency with the in-memory fallback, we can keep a no-op or
        # adjust it if specific logging/metrics are needed outside of the main check.
        pass

    async def get_client_stats(self, client_id: str) -> dict:
        if not self._redis_available or self._redis_client is None:
            # Fallback for stats if Redis is not available
            async with self._fallback_lock:
                bucket = self._buckets[client_id]
                self._in_memory_refill_tokens(bucket, 1.0) # Ensure current state
                self._in_memory_reset_windows_if_needed(bucket)
                return {
                    "tokens": bucket.tokens,
                    "requests_minute": bucket.requests_minute,
                    "requests_hour": bucket.requests_hour,
                    "limit_minute": self.config.requests_per_minute,
                    "limit_hour": self.config.requests_per_hour,
                }
        
        token_bucket_key = f"rate_limit:{client_id}:tokens"
        minute_window_key = f"rate_limit:{client_id}:minute"
        hour_window_key = f"rate_limit:{client_id}:hour"
        current_time_ms = int(time.time() * 1000)

        try:
            # Re-run refill logic to get current token count without consuming
            bucket_info = await self._redis_client.hmget(token_bucket_key, 'tokens', 'last_refill_time_ms')
            tokens = float(bucket_info[0]) if bucket_info[0] else self.config.burst_size
            last_refill_time_ms = float(bucket_info[1]) if bucket_info[1] else current_time_ms
            
            elapsed_time_ms = current_time_ms - last_refill_time_ms
            refill_rate = (self.config.requests_per_minute) / 60000.0
            refilled_tokens = math.floor(elapsed_time_ms * refill_rate)
            
            current_tokens = min(self.config.burst_size, tokens + refilled_tokens)

            # Get counts for windows (no request added)
            await self._redis_client.zremrangebyscore(minute_window_key, 0, current_time_ms - 60000)
            count_minute = await self._redis_client.zcard(minute_window_key)

            await self._redis_client.zremrangebyscore(hour_window_key, 0, current_time_ms - 3600000)
            count_hour = await self._redis_client.zcard(hour_window_key)

            return {
                "tokens": current_tokens,
                "requests_minute": count_minute,
                "requests_hour": count_hour,
                "limit_minute": self.config.requests_per_minute,
                "limit_hour": self.config.requests_per_hour,
            }
        except Exception as e:
            print(f"[ERROR] Failed to get Redis client stats: {e}")
            return {
                "tokens": 0, "requests_minute": 0, "requests_hour": 0,
                "limit_minute": self.config.requests_per_minute, "limit_hour": self.config.requests_per_hour,
                "error": str(e)
            }

    async def reset_client(self, client_id: str) -> None:
        if not self._redis_available or self._redis_client is None:
            async with self._fallback_lock:
                self._buckets.pop(client_id, None)
            return

        token_bucket_key = f"rate_limit:{client_id}:tokens"
        minute_window_key = f"rate_limit:{client_id}:minute"
        hour_window_key = f"rate_limit:{client_id}:hour"
        try:
            await self._redis_client.delete(token_bucket_key, minute_window_key, hour_window_key)
        except Exception as e:
            print(f"[ERROR] Failed to reset client {client_id} in Redis: {e}")
    
    async def reset_all(self) -> None:
        if not self._redis_available or self._redis_client is None:
            async with self._fallback_lock:
                self._buckets.clear()
            return
        
        # Danger zone: This will delete ALL keys matching the pattern. Use with caution.
        try:
            async for key in self._redis_client.scan_iter("rate_limit:*"):
                await self._redis_client.delete(key)
        except Exception as e:
            print(f"[ERROR] Failed to reset all rate limits in Redis: {e}") # Fixed double f-string

    # In-memory helpers for fallback mode
    def _in_memory_get_bucket(self, client_id: str) -> ClientBucket:
        if client_id not in self._buckets:
            if len(self._buckets) >= self._MAX_BUCKETS:
                oldest = next(iter(self._buckets))
                del self._buckets[oldest]
            bucket = ClientBucket()
            bucket.tokens = self.config.burst_size # Start with full burst
            self._buckets[client_id] = bucket
        return self._buckets[client_id]
    
    def _in_memory_refill_tokens(self, bucket: ClientBucket, multiplier: float = 1.0) -> None:
        now = time.monotonic()
        elapsed = now - bucket.last_update
        refill_rate = (self.config.requests_per_minute * multiplier) / 60.0
        max_tokens = self.config.burst_size * multiplier
        bucket.tokens = min(max_tokens, bucket.tokens + (elapsed * refill_rate))
        bucket.last_update = now
    
    def _in_memory_reset_windows_if_needed(self, bucket: ClientBucket) -> None:
        now = time.monotonic()
        elapsed_minutes = int((now - bucket.minute_window_start) // 60)
        if elapsed_minutes > 0:
            bucket.requests_minute = 0
            bucket.minute_window_start += elapsed_minutes * 60
        
        elapsed_hours = int((now - bucket.hour_window_start) // 3600)
        if elapsed_hours > 0:
            bucket.requests_hour = 0
            bucket.hour_window_start += elapsed_hours * 3600

# Global rate limiter instance
# NOTE: This is a per-process singleton. For horizontal scaling
# (multi-worker/multi-process), each worker maintains its own token bucket.
# A client can bypass limits by hitting different workers. Replace with a
# Redis-backed sliding window or external rate-limiting service.
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter(config: Optional[RateLimitConfig] = None) -> RateLimiter:
    """Get or create global rate limiter."""
    global _rate_limiter
    if _rate_limiter is None: # Removed conditional for _REDIS_RATE_LIMITER_ENABLED as RateLimiter handles it internally
        _rate_limiter = RateLimiter(config)
    return _rate_limiter
