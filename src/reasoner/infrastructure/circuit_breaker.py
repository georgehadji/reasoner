"""
Reasoner Pipeline - Circuit Breaker Pattern
Provides fault tolerance for LLM provider calls.

ARCHITECTURAL NOTE:
    The circuit breaker registry stores state in-memory. In a multi-worker
    or horizontally-scaled deployment each process maintains its own circuit
    state, which means a failing provider may not be detected consistently
    across workers. Set CIRCUIT_BREAKER_MODE to a shared backend (e.g.,
    'redis') or accept per-worker degradation for production multi-instance
    deployments.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar

from reasoner.logging_utils import llm_logger

try:
    from reasoner.metrics import (
        REASONER_CIRCUIT_BREAKER_REJECTED,
        REASONER_CIRCUIT_BREAKER_STATE,
    )
    _METRICS_AVAILABLE = True
except Exception:
    _METRICS_AVAILABLE = False

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5          # Failures before opening
    success_threshold: int = 3          # Successes in half-open to close
    timeout_seconds: float = 30.0       # Time before trying half-open
    half_open_max_calls: int = 3        # Max concurrent calls in half-open


@dataclass
class CircuitBreakerStats:
    """Statistics for circuit breaker."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    # Track concurrent calls in HALF_OPEN state to enforce limit
    half_open_current_calls: int = 0


class CircuitBreaker:
    """
    Circuit breaker implementation for LLM provider calls.

    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Too many failures, calls are rejected immediately
    - HALF_OPEN: Testing recovery, limited calls allowed

    Thread Safety:
    - All state transitions are atomic (protected by _lock)
    - HALF_OPEN state enforces half_open_max_calls limit
    - Concurrent call tracking prevents race conditions
    """

    def __init__(
        self,
        name: str,
        config: CircuitBreakerConfig | None = None,
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()
        self._last_state_change = time.monotonic()

    def _update_metrics(self) -> None:
        """Export circuit state to Prometheus gauges."""
        if not _METRICS_AVAILABLE:
            return
        state_value = {"closed": 0, "half_open": 1, "open": 2}.get(self._state.value, 0)
        REASONER_CIRCUIT_BREAKER_STATE.labels(name=self.name).set(state_value)

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def stats(self) -> CircuitBreakerStats:
        return self._stats

    async def _try_acquire_call(self) -> bool:
        """
        Atomically check availability and acquire call slot if in HALF_OPEN.
        Must be called within _lock context.
        
        Returns:
            bool: True if call is allowed, False if circuit is OPEN or HALF_OPEN at capacity
        """
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            # Check if timeout has passed to transition to half-open
            elapsed = time.monotonic() - self._last_state_change
            if elapsed >= self.config.timeout_seconds:
                # Atomic transition: OPEN → HALF_OPEN
                self._state = CircuitState.HALF_OPEN
                self._last_state_change = time.monotonic()
                self._stats.half_open_current_calls = 0  # Reset counter for new half-open period
                llm_logger.info(
                    f"Circuit '{self.name}' transitioning to HALF_OPEN",
                    extra={"circuit": self.name, "state": "half_open"},
                )
                # Fall through to HALF_OPEN logic
            else:
                return False  # Still OPEN, reject call

        # HALF_OPEN state - enforce concurrent call limit
        if self._state == CircuitState.HALF_OPEN:
            if self._stats.half_open_current_calls >= self.config.half_open_max_calls:
                return False  # At capacity, reject call
            # Acquire slot atomically
            self._stats.half_open_current_calls += 1
            return True

        return False  # Unknown state, reject for safety

    def _release_call(self) -> None:
        """
        Release call slot (decrement half_open_current_calls).
        Must be called within _lock context.
        """
        if self._state == CircuitState.HALF_OPEN:
            self._stats.half_open_current_calls = max(0, self._stats.half_open_current_calls - 1)

    async def call(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Execute function with circuit breaker protection.
        
        Thread Safety:
        - Uses atomic _try_acquire_call to prevent race conditions
        - Properly releases call slot on completion (success or failure)
        - All state transitions protected by _lock
        """
        async with self._lock:
            # Atomically check availability and acquire slot if needed
            if not await self._try_acquire_call():
                self._stats.rejected_calls += 1
                if _METRICS_AVAILABLE:
                    REASONER_CIRCUIT_BREAKER_REJECTED.labels(name=self.name).inc()
                llm_logger.warning(
                    f"Circuit '{self.name}' is OPEN or at HALF_OPEN capacity, rejecting call",
                    extra={
                        "circuit": self.name,
                        "state": self._state.value,
                        "rejected_calls": self._stats.rejected_calls,
                    },
                )
                raise CircuitOpenError(
                    f"Circuit '{self.name}' is open",
                    circuit_name=self.name,
                )
            self._stats.total_calls += 1

        # Execute the call (outside lock to allow concurrent execution)
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            await self._on_success()
            return result

        except Exception:
            await self._on_failure()
            raise

        finally:
            # Always release the call slot (outside lock to avoid deadlock)
            async with self._lock:
                self._release_call()

    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            self._stats.successful_calls += 1
            self._stats.consecutive_successes += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Slot release is handled by _release_call() in the caller's
                # finally block. We do NOT decrement here — doing so would
                # double-free the slot and disable the half_open_max_calls
                # capacity limit. Only transition to CLOSED when threshold met.
                if self._stats.consecutive_successes >= self.config.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._stats.consecutive_successes = 0
                    self._stats.half_open_current_calls = 0  # Reset counter when closing
                    self._last_state_change = time.monotonic()
                    self._update_metrics()
                    llm_logger.info(
                        f"Circuit '{self.name}' CLOSED after recovery",
                        extra={"circuit": self.name, "state": "closed"},
                    )

    async def _on_failure(self) -> None:
        """Handle failed call."""
        async with self._lock:
            self._stats.failed_calls += 1
            self._stats.consecutive_failures += 1
            self._stats.consecutive_successes = 0
            self._stats.last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open goes back to open
                self._state = CircuitState.OPEN
                self._stats.half_open_current_calls = 0  # Reset counter when opening
                self._last_state_change = time.monotonic()
                self._update_metrics()
                llm_logger.warning(
                    f"Circuit '{self.name}' reopened after half-open failure",
                    extra={"circuit": self.name, "state": "open"},
                )
            elif self._state == CircuitState.CLOSED:
                if self._stats.consecutive_failures >= self.config.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._stats.half_open_current_calls = 0  # Reset counter when opening
                    self._last_state_change = time.monotonic()
                    self._update_metrics()
                    llm_logger.warning(
                        f"Circuit '{self.name}' opened after {self._stats.consecutive_failures} failures",
                        extra={
                            "circuit": self.name,
                            "state": "open",
                            "consecutive_failures": self._stats.consecutive_failures,
                        },
                    )

    def get_health_status(self) -> dict[str, Any]:
        """Get health status for monitoring."""
        return {
            "name": self.name,
            "state": self._state.value,
            "stats": asdict(self._stats),
            "config": asdict(self.config),
        }

    async def reset(self) -> None:
        """Manually reset circuit to closed state."""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._stats = CircuitBreakerStats()
            self._last_state_change = time.monotonic()
        llm_logger.info(
            f"Circuit '{self.name}' manually reset",
            extra={"circuit": self.name, "state": "closed"},
        )

    async def can_execute(self) -> bool:
        """Return True if the circuit allows a call right now.

        For use by callers that manage their own execution lifecycle
        (e.g., ProviderRouter) and only need a gate check.
        """
        async with self._lock:
            return await self._try_acquire_call()

    async def record_success(self) -> None:
        """Record a successful call (for manual use outside ``call()``).

        Releases the half-open slot acquired by ``can_execute()``.
        ``_on_success()`` does not release the slot on its own (it defers to
        ``call()``'s finally block), so the manual API must do it here.
        ``_release_call()`` is a no-op when the circuit is CLOSED or OPEN,
        so it is always safe to call after ``_on_success()``.
        """
        await self._on_success()
        async with self._lock:
            self._release_call()

    async def record_failure(self) -> None:
        """Record a failed call (for manual use outside ``call()``).

        Releases the half-open slot acquired by ``can_execute()``.
        ``_on_failure()`` resets ``half_open_current_calls`` when transitioning
        back to OPEN, so ``_release_call()`` is a no-op in that path.
        """
        await self._on_failure()
        async with self._lock:
            self._release_call()


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    def __init__(self, message: str, circuit_name: str):
        super().__init__(message)
        self.circuit_name = circuit_name


class RedisCircuitBreaker:
    """Circuit breaker with Redis-backed shared state across workers.

    Delegates all atomic state transitions to a Lua script executed on the
    Redis server.  Per-worker monitoring counters (total_calls, failed_calls,
    etc.) are kept in-memory only — they are not shared.

    Graceful degradation: if Redis is unreachable, can_execute() returns True
    (fail-open) to never block LLM calls on Redis failure.
    """

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._stats = CircuitBreakerStats()
        self._script = None  # loaded lazily
        # Local fallback state: caches last Redis read for up to _LOCAL_STATE_TTL seconds.
        # On Redis failure, if the last known state was OPEN, we stay blocked rather than
        # blindly failing open and hammering a known-failing provider.
        self._local_state: CircuitState = CircuitState.CLOSED
        self._local_state_updated: float = 0.0
        self._LOCAL_STATE_TTL: float = 60.0

    async def _get_script(self):
        if self._script is None:
            from pathlib import Path

            from reasoner.infrastructure.valkey.client import get_valkey_pool

            valkey = get_valkey_pool()
            script_path = (
                Path(__file__).parent / "valkey" / "scripts" / "circuit_breaker.lua"
            )
            self._script = valkey.register_script(script_path.read_text())
        return self._script

    @property
    def state(self) -> CircuitState:
        """Return the last known circuit state (cached from Redis)."""
        return self._local_state

    @property
    def stats(self) -> CircuitBreakerStats:
        return self._stats

    async def can_execute(self) -> bool:
        """Return True if the circuit allows a call right now."""
        try:
            script = await self._get_script()
            result = await script(
                keys=[f"cb:{self.name}"],
                args=[
                    "can_execute",
                    int(time.time() * 1000),
                    int(self.config.timeout_seconds * 1000),
                    self.config.half_open_max_calls,
                ],
            )
            allowed = bool(result[0])
            # Cache result — used as fallback if Redis becomes unavailable
            self._local_state = CircuitState.CLOSED if allowed else CircuitState.OPEN
            self._local_state_updated = time.monotonic()
            if allowed:
                self._stats.total_calls += 1
            else:
                self._stats.rejected_calls += 1
                if _METRICS_AVAILABLE:
                    REASONER_CIRCUIT_BREAKER_REJECTED.labels(name=self.name).inc()
            return allowed
        except Exception:
            # If we recently observed this circuit as OPEN, honour that state rather
            # than blindly failing open and hammering a known-failing provider.
            local_age = time.monotonic() - self._local_state_updated
            if local_age <= self._LOCAL_STATE_TTL and self._local_state == CircuitState.OPEN:
                llm_logger.warning(
                    f"Redis circuit breaker unavailable for {self.name} — "
                    f"using cached OPEN state (age={local_age:.0f}s), rejecting call",
                )
                self._stats.rejected_calls += 1
                return False
            llm_logger.warning(
                f"Redis circuit breaker unavailable for {self.name} — allowing call (fail-open)",
            )
            self._stats.total_calls += 1
            return True  # fail-open: local state is CLOSED or stale

    async def record_success(self) -> None:
        """Record a successful call."""
        self._stats.successful_calls += 1
        self._stats.consecutive_successes += 1
        self._stats.consecutive_failures = 0
        self._stats.last_success_time = time.monotonic()
        try:
            script = await self._get_script()
            await script(
                keys=[f"cb:{self.name}"],
                args=[
                    "record_success",
                    "",
                    self.config.success_threshold,
                ],
            )
        except Exception:
            llm_logger.warning(
                f"Redis circuit breaker unavailable for {self.name} — success recorded locally only",
            )

    async def record_failure(self) -> None:
        """Record a failed call."""
        self._stats.failed_calls += 1
        self._stats.consecutive_failures += 1
        self._stats.consecutive_successes = 0
        self._stats.last_failure_time = time.monotonic()
        try:
            script = await self._get_script()
            await script(
                keys=[f"cb:{self.name}"],
                args=[
                    "record_failure",
                    int(time.time() * 1000),
                    self.config.failure_threshold,
                ],
            )
        except Exception:
            llm_logger.warning(
                f"Redis circuit breaker unavailable for {self.name} — failure recorded locally only",
            )

    async def reset(self) -> None:
        """Manually reset circuit to closed state."""
        self._stats = CircuitBreakerStats()
        try:
            from reasoner.infrastructure.valkey.client import get_valkey_pool

            valkey = get_valkey_pool()
            await valkey.delete(f"cb:{self.name}")
        except Exception:
            pass

    def get_health_status(self) -> dict[str, Any]:
        """Get health status for monitoring."""
        return {
            "name": self.name,
            "state": self._local_state.value,  # last known state cached from Redis
            "stats": asdict(self._stats),
            "config": asdict(self.config),
        }


# ── Global circuit breaker registries ──────────────────────────────────
# Two registries: memory (existing) and redis (new).
_circuit_breakers: dict[str, CircuitBreaker] = {}
_redis_circuit_breakers: dict[str, RedisCircuitBreaker] = {}
from reasoner.core.constants import MAX_CIRCUIT_BREAKER_REGISTRY_SIZE

_MAX_REGISTRY_SIZE: int = MAX_CIRCUIT_BREAKER_REGISTRY_SIZE
_circuit_breaker_lock = threading.Lock()


def _get_memory_circuit_breaker(name: str) -> CircuitBreaker:
    """Get or create an in-memory circuit breaker by name."""
    with _circuit_breaker_lock:
        if name not in _circuit_breakers:
            if len(_circuit_breakers) >= _MAX_REGISTRY_SIZE:
                oldest = next(iter(_circuit_breakers))
                del _circuit_breakers[oldest]
            _circuit_breakers[name] = CircuitBreaker(name)
        return _circuit_breakers[name]


def _get_redis_circuit_breaker(name: str) -> RedisCircuitBreaker:
    """Get or create a Redis-backed circuit breaker by name."""
    with _circuit_breaker_lock:
        if name not in _redis_circuit_breakers:
            if len(_redis_circuit_breakers) >= _MAX_REGISTRY_SIZE:
                oldest = next(iter(_redis_circuit_breakers))
                del _redis_circuit_breakers[oldest]
            _redis_circuit_breakers[name] = RedisCircuitBreaker(name)
        return _redis_circuit_breakers[name]


def get_circuit_breaker(name: str) -> CircuitBreaker | RedisCircuitBreaker:
    """Get or create a circuit breaker by name.

    Mode is selected by CIRCUIT_BREAKER_MODE setting:
      - "redis" → shared state across workers
      - "memory" (default) → per-worker in-memory state only
    """
    from reasoner.core.settings import settings

    mode = settings.CIRCUIT_BREAKER_MODE.lower()
    if mode in ("redis", "valkey"):
        return _get_redis_circuit_breaker(name)
    return _get_memory_circuit_breaker(name)


# Deprecated alias — use ValkeyCircuitBreaker (same implementation, renamed)
ValkeyCircuitBreaker = RedisCircuitBreaker


def get_all_circuit_breakers() -> dict[str, dict[str, Any]]:
    """Get status of all circuit breakers."""
    with _circuit_breaker_lock:
        memory = {
            name: cb.get_health_status() for name, cb in _circuit_breakers.items()
        }
        redis = {
            name: cb.get_health_status()
            for name, cb in _redis_circuit_breakers.items()
        }
        return {**memory, **redis}


async def reset_all_circuits() -> None:
    """Reset all circuit breakers (both memory and Redis-backed)."""
    with _circuit_breaker_lock:
        memory_cbs = list(_circuit_breakers.values())
        redis_cbs = list(_redis_circuit_breakers.values())
    for cb in memory_cbs:
        await cb.reset()
    for cb in redis_cbs:
        await cb.reset()


# Helper for dataclass
def asdict(obj: Any) -> dict:
    """Simple asdict replacement for dataclasses."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: asdict(v) for k, v in obj.__dict__.items()}
    elif isinstance(obj, dict):
        return {k: asdict(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return type(obj)(asdict(item) for item in obj)
    return obj
