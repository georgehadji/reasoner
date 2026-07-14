"""Regression tests for CancelledError handling in BaseLLMProvider (BUG-003)."""

import asyncio
import pytest

from reasoner.infrastructure.llm.ports import BaseLLMProvider, Message, LLMConfig, LLMResponse


class HangingProvider(BaseLLMProvider):
    """Provider that hangs indefinitely to simulate a long-running LLM call."""

    async def _complete_impl(self, messages, config):
        await asyncio.sleep(3600)
        return LLMResponse(content="never", model_used="test")

    async def _complete_stream_impl(self, messages, config):
        yield ""

    @property
    def provider_name(self):
        return "hanging"


class FlakyProvider(BaseLLMProvider):
    """Provider that always raises a retryable error."""

    async def _complete_impl(self, messages, config):
        raise ConnectionError("simulated network failure")

    async def _complete_stream_impl(self, messages, config):
        yield ""

    @property
    def provider_name(self):
        return "flaky"


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

    task = asyncio.create_task(
        provider.complete([Message(role="user", content="test")])
    )
    # Give the task a moment to enter _complete_impl
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
    provider = FlakyProvider(model="test", max_retries=2, base_delay_seconds=0.01)

    with pytest.raises(ConnectionError):
        await provider.complete([Message(role="user", content="test")])

    # Should have attempted: initial + 2 retries = 3 errors
    assert provider._error_count == 3
