"""PRV-1: the breaker answers "is the provider unhealthy?", not "did this call fail?".

`_call_with_circuit` recorded a failure for every exception, including the
400 and 422 a caller earns with an oversized or malformed request
(`translate_http_status` returns None for them, so they surface as a residual
`LLMError`). One user's bad request could open `llm:<model>` for every tenant
on every worker.
"""

from __future__ import annotations

import httpx
import pytest

from reasoner.core.exceptions import (
    AuthenticationError,
    ModelNotFoundError,
    ProviderCreditsExhaustedError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
)
from reasoner.infrastructure.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from reasoner.infrastructure.llm import router as router_mod
from reasoner.infrastructure.llm.base import LLMError, is_provider_fault

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("exc", "counts"),
    [
        (ProviderTimeoutError("t"), True),
        (TimeoutError(), True),
        (ProviderUnavailableError("5xx"), True),
        (httpx.ConnectError("down"), True),
        (RateLimitError("429", provider="m"), True),
        (ProviderCreditsExhaustedError("402"), True),
        (AuthenticationError("401", provider="m"), True),
        (ModelNotFoundError("404", model="m"), True),
        (LLMError("400: context length exceeded"), False),
        (RuntimeError("something we have never seen"), True),
    ],
)
def test_is_provider_fault_table(exc: BaseException, counts: bool) -> None:
    assert is_provider_fault(exc) is counts


def _wrapped(cause: BaseException) -> LLMError:
    """What complete_with_retry raises once its retries are spent."""
    try:
        raise LLMError("failed after 2 retries") from cause
    except LLMError as exc:
        return exc


def test_exhausted_retries_are_judged_by_their_cause() -> None:
    assert is_provider_fault(_wrapped(ProviderTimeoutError("slow"))) is True
    assert is_provider_fault(_wrapped(httpx.ReadTimeout("slow"))) is True
    assert is_provider_fault(_wrapped(LLMError("400"))) is False


class _Failing:
    """A provider that always raises the given error."""

    def __init__(self, model: str, exc: Exception) -> None:
        self.model = model
        self.extra_body: dict = {}
        self._exc = exc

    async def complete_with_retry(self, *args, **kwargs):
        raise self._exc


def _breaker() -> CircuitBreaker:
    return CircuitBreaker("t", CircuitBreakerConfig(failure_threshold=5, timeout_seconds=30))


async def _fail_n(monkeypatch, exc: Exception, n: int) -> CircuitBreaker:
    cb = _breaker()
    monkeypatch.setattr("reasoner.circuit_breaker.get_circuit_breaker", lambda name: cb)
    provider = _Failing("m-classify", exc)
    for _ in range(n):
        with pytest.raises(type(exc)):
            await router_mod._call_with_circuit(provider, "s", "u", 10, 0.0, 5.0)
    return cb


async def test_five_client_errors_leave_the_breaker_closed(monkeypatch) -> None:
    cb = await _fail_n(monkeypatch, LLMError("400: bad request"), 5)

    assert cb.state is CircuitState.CLOSED
    assert await cb.can_execute()


async def test_five_provider_timeouts_open_the_breaker(monkeypatch) -> None:
    cb = await _fail_n(monkeypatch, ProviderTimeoutError("slow"), 5)

    assert cb.state is CircuitState.OPEN
