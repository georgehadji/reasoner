"""LLMExecutor's one-shot retry when a JSON-contract role gets cut off mid-generation.

finish_reason == "length" means the provider hit max_tokens before the model
was done -- for a role whose contract is JSON that means truncated mid-object,
which extract_json() cannot recover from no matter how the prompt is worded.
See docs/plans/article-flow-truncation-remediation.md W0.
"""

from __future__ import annotations

import pytest

from reasoner.core.constants_limits import TRUNCATION_RETRY_MAX_TOKENS
from reasoner.infrastructure.llm.executor import LLMExecutor

_JSON_SYSTEM = "You are a helpful assistant."
_JSON_PROMPT = 'Output JSON: {"task_type": "..."}'
_PROSE_SYSTEM = "You are a synthesizer."
_PROSE_PROMPT = "[SOLUTION]\nWrite prose here.\n[/SOLUTION]"


class _QueueRouter:
    """Stub router returning pre-programmed (raw, metadata) tuples in call order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def call(self, role, system_prompt, user_prompt, **kwargs):
        self.calls.append({"role": role, "max_tokens": kwargs.get("max_tokens")})
        return self._responses.pop(0)


def _executor(router) -> LLMExecutor:
    return LLMExecutor(router=router, phase_configs={}, token_cache=None, caching_enabled=False)


class TestRetryAfterTruncation:
    @pytest.mark.asyncio
    async def test_non_json_role_is_marked_but_not_retried(self):
        """Prose output that runs long is not necessarily broken output."""
        router = _QueueRouter([])  # a retry call would raise IndexError
        executor = _executor(router)
        raw, metadata = await executor._retry_after_truncation(
            "synthesis", _PROSE_SYSTEM, _PROSE_PROMPT,
            {"max_tokens": 2048}, "partial prose that ran out of room",
            {"model": "some-model", "finish_reason": "length"},
        )
        assert raw == "partial prose that ran out of room"
        assert metadata["truncated"] is True
        assert "truncated_retry" not in metadata
        assert router.calls == []

    @pytest.mark.asyncio
    async def test_json_role_retries_at_doubled_budget(self):
        router = _QueueRouter([
            ('{"a": 1}', {"model": "m", "finish_reason": "stop", "cost_usd": 0.01, "input_tokens": 100, "output_tokens": 2048}),
        ])
        executor = _executor(router)
        raw, metadata = await executor._retry_after_truncation(
            "article_sot_skeleton", _JSON_SYSTEM, _JSON_PROMPT,
            {"max_tokens": 2048}, "{\"partial",
            {"model": "m", "finish_reason": "length", "cost_usd": 0.01, "input_tokens": 100, "output_tokens": 2048},
        )
        assert raw == '{"a": 1}'
        assert router.calls == [{"role": "article_sot_skeleton", "max_tokens": 4096}]
        assert metadata["truncated_retry"] is True
        assert metadata["truncated"] is False

    @pytest.mark.asyncio
    async def test_retry_folds_cost_and_tokens_from_both_attempts(self):
        """Spend/cost-cap accounting must reflect what was actually charged,
        not just the retry's numbers -- the wasted first attempt still cost
        real money."""
        router = _QueueRouter([
            ('{"a": 1}', {"model": "m", "finish_reason": "stop", "cost_usd": 0.02, "input_tokens": 100, "output_tokens": 500}),
        ])
        executor = _executor(router)
        _, metadata = await executor._retry_after_truncation(
            "article_critic", _JSON_SYSTEM, _JSON_PROMPT,
            {"max_tokens": 2048}, "{\"partial",
            {"model": "m", "finish_reason": "length", "cost_usd": 0.01, "input_tokens": 100, "output_tokens": 2048},
        )
        assert metadata["cost_usd"] == pytest.approx(0.03)
        assert metadata["input_tokens"] == 200
        assert metadata["output_tokens"] == 2548

    @pytest.mark.asyncio
    async def test_retry_still_truncated_keeps_the_flag_and_the_content(self):
        """A retry that is STILL cut off at the doubled budget is the best
        answer available -- returned as-is, still flagged, not discarded."""
        router = _QueueRouter([
            ('{"still_partial', {"model": "m", "finish_reason": "length", "cost_usd": 0.02, "input_tokens": 100, "output_tokens": 4096}),
        ])
        executor = _executor(router)
        raw, metadata = await executor._retry_after_truncation(
            "article_critic", _JSON_SYSTEM, _JSON_PROMPT,
            {"max_tokens": 2048}, "{\"partial",
            {"model": "m", "finish_reason": "length", "cost_usd": 0.01, "input_tokens": 100, "output_tokens": 2048},
        )
        assert raw == '{"still_partial'
        assert metadata["truncated"] is True
        assert metadata["truncated_retry"] is True

    @pytest.mark.asyncio
    async def test_degraded_retry_keeps_the_original_truncated_answer(self):
        """A retry that times out or errors must not lose the original
        (truncated but present) answer -- never worse than before."""
        from reasoner.infrastructure.llm.ports import DegradedLLMResponse

        router = _QueueRouter([
            (DegradedLLMResponse(text="", error="timed out"), {}),
        ])
        executor = _executor(router)
        raw, metadata = await executor._retry_after_truncation(
            "article_critic", _JSON_SYSTEM, _JSON_PROMPT,
            {"max_tokens": 2048}, "{\"partial",
            {"model": "m", "finish_reason": "length", "cost_usd": 0.01},
        )
        assert raw == '{"partial'
        assert metadata["truncated"] is True
        assert "truncated_retry" not in metadata

    @pytest.mark.asyncio
    async def test_empty_retry_keeps_the_original_truncated_answer(self):
        router = _QueueRouter([("", {"model": "m", "finish_reason": "stop"})])
        executor = _executor(router)
        raw, metadata = await executor._retry_after_truncation(
            "article_critic", _JSON_SYSTEM, _JSON_PROMPT,
            {"max_tokens": 2048}, "{\"partial",
            {"model": "m", "finish_reason": "length", "cost_usd": 0.01},
        )
        assert raw == '{"partial'
        assert "truncated_retry" not in metadata

    @pytest.mark.asyncio
    async def test_no_retry_once_already_at_the_ceiling(self):
        """A role already budgeted at or above the retry ceiling has nowhere
        to grow -- marked truncated, no second call attempted."""
        router = _QueueRouter([])  # a retry call would raise IndexError
        executor = _executor(router)
        raw, metadata = await executor._retry_after_truncation(
            "article_verifier", _JSON_SYSTEM, _JSON_PROMPT,
            {"max_tokens": TRUNCATION_RETRY_MAX_TOKENS}, "{\"partial",
            {"model": "m", "finish_reason": "length"},
        )
        assert raw == '{"partial'
        assert metadata["truncated"] is True
        assert router.calls == []
