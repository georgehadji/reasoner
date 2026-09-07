"""Regression tests for CancelledError handling in BaseLLMProvider (BUG-003).

Retargeted from ``ports.BaseLLMProvider`` to ``base.BaseLLMProvider`` in P2
(docs/plans/root-cause-remediation-2026-09-07.md). The ports class was the
second, unused provider base -- ``complete(messages, config) -> LLMResponse``,
no ``complete_with_retry`` -- and was deleted. These guarantees matter on the
class the router actually drives, which is the one exercised here.
"""

import asyncio
from collections.abc import AsyncIterator

import pytest

from reasoner.infrastructure.llm.base import BaseLLMProvider


class _Provider(BaseLLMProvider):
    """Minimal concrete provider; subclasses override complete()."""

    async def stream_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        yield ""


class HangingProvider(_Provider):
    """Provider that hangs indefinitely to simulate a long-running LLM call."""

    async def complete(self, system_prompt, user_prompt, max_tokens=2048, temperature=0.7):
        await asyncio.sleep(3600)
        return "never"


class _Retryable(Exception):
    """An untranslated transport error, i.e. what an adapter that forgot to
    call its ``_translate`` would still raise. ``core.is_retryable`` reads
    ``status_code`` on non-ReasonerError exceptions, so this one retries."""
    status_code = 429


class FlakyProvider(_Provider):
    """Provider that always raises a retryable error."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attempts = 0

    async def complete(self, system_prompt, user_prompt, max_tokens=2048, temperature=0.7):
        self.attempts += 1
        raise _Retryable("simulated network failure")


@pytest.mark.asyncio
async def test_cancelled_error_not_swallowed():
    """
    When an LLM call is cancelled (e.g., client disconnect or shutdown),
    the CancelledError must propagate immediately and NOT be retried.

    Without the fix: the broad 'except Exception' catches CancelledError,
    treats it as a retryable failure, sleeps with backoff, and retries.
    With the fix: CancelledError is re-raised instantly.
    """
    provider = HangingProvider(model="test")

    task = asyncio.create_task(provider.complete_with_retry("s", "u"))
    # Give the task a moment to enter complete()
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_retryable_error_still_retries():
    """
    Non-cancellation retryable errors must still be retried.
    This ensures the fix is narrow and doesn't break existing retry logic.
    """
    provider = FlakyProvider(model="test", max_retries=2)

    with pytest.raises(Exception):
        await provider.complete_with_retry("s", "u")

    # Should have attempted: initial + 2 retries = 3 calls
    assert provider.attempts == 3


@pytest.mark.asyncio
async def test_translated_provider_error_is_not_retried_here():
    """A ProviderError has already been classified at the adapter boundary.

    The router owns what happens next (fallback to a cross-lab equivalent).
    Retrying here as well is the dual-layer retry problem that complete_once()
    exists to avoid, and it is what translating into accurate classes would
    have switched on by accident: RateLimitError.retryable is True.
    """
    from reasoner.core.exceptions import RateLimitError

    class RateLimited(_Provider):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.attempts = 0

        async def complete(self, system_prompt, user_prompt, max_tokens=2048, temperature=0.7):
            self.attempts += 1
            raise RateLimitError("429", provider="test")

    provider = RateLimited(model="test", max_retries=2)
    with pytest.raises(RateLimitError):
        await provider.complete_with_retry("s", "u")
    assert provider.attempts == 1
