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
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypeVar

from reasoner.logging_utils import llm_logger

try:
    from reasoner.metrics import (
        REASONER_CIRCUIT_BREAKER_STATE,
        REASONER_CIRCUIT_BREAKER_REJECTED,
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

        except Exception as e:
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
        """Record a successful call (for manual use outside ``call()``)."""
        await self._on_success()

    async def record_failure(self) -> None:
        """Record a failed call (for manual use outside ``call()``)."""
        await self._on_failure()


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""
    def __init__(self, message: str, circuit_name: str):
        super().__init__(message)
        self.circuit_name = circuit_name


# Global circuit breaker registry
# NOTE: This is a per-process registry. For horizontal scaling, circuit state
# should be externalized (e.g., Redis) or per-worker degradation accepted.
_circuit_breakers: dict[str, CircuitBreaker] = {}
from reasoner.core.constants import MAX_CIRCUIT_BREAKER_REGISTRY_SIZE
_MAX_REGISTRY_SIZE: int = MAX_CIRCUIT_BREAKER_REGISTRY_SIZE
_circuit_breaker_lock = threading.Lock()


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """Get or create a circuit breaker by name."""
    with _circuit_breaker_lock:
        if name not in _circuit_breakers:
            if len(_circuit_breakers) >= _MAX_REGISTRY_SIZE:
                # Evict oldest entry to prevent unbounded growth
                oldest = next(iter(_circuit_breakers))
                del _circuit_breakers[oldest]
            _circuit_breakers[name] = CircuitBreaker(name)
        return _circuit_breakers[name]


def get_all_circuit_breakers() -> dict[str, dict[str, Any]]:
    """Get status of all circuit breakers."""
    with _circuit_breaker_lock:
        return {name: cb.get_health_status() for name, cb in _circuit_breakers.items()}


async def reset_all_circuits() -> None:
    """Reset all circuit breakers."""
    with _circuit_breaker_lock:
        cbs = list(_circuit_breakers.values())
    for cb in cbs:
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