"""Tests for provider-level prompt caching (cache_control breakpoints)."""

from __future__ import annotations

import pytest

from reasoner.infrastructure.llm.caching import (
    MIN_CACHEABLE_CHARS,
    build_messages,
    extract_cache_usage,
    needs_explicit_cache_control,
)

LARGE_SYSTEM = "S" * (MIN_CACHEABLE_CHARS + 1)
SMALL_SYSTEM = "S" * (MIN_CACHEABLE_CHARS - 1)


@pytest.mark.unit
@pytest.mark.parametrize(
    "model",
    ["anthropic/claude-opus-5", "google/gemini-3-pro", "qwen/qwen3.7-max", "claude-sonnet-5"],
)
def test_explicit_cache_providers_detected(model: str) -> None:
    assert needs_explicit_cache_control(model) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "model",
    ["openai/gpt-5.5", "deepseek/deepseek-chat", "x-ai/grok-4", "moonshotai/kimi-k2"],
)
def test_automatic_cache_providers_left_alone(model: str) -> None:
    """Providers that cache automatically must not get structured content blocks."""
    assert needs_explicit_cache_control(model) is False

    messages = build_messages(LARGE_SYSTEM, "u", model)

    assert messages[0]["content"] == LARGE_SYSTEM


@pytest.mark.unit
def test_breakpoint_added_for_large_system_prompt() -> None:
    # Arrange
    model = "anthropic/claude-opus-5"

    # Act
    messages = build_messages(LARGE_SYSTEM, "user text", model)

    # Assert
    system_block = messages[0]["content"][0]
    assert system_block["type"] == "text"
    assert system_block["text"] == LARGE_SYSTEM
    assert system_block["cache_control"]["type"] == "ephemeral"
    # The volatile user turn must stay outside the cached prefix.
    assert messages[1] == {"role": "user", "content": "user text"}


@pytest.mark.unit
def test_no_breakpoint_below_minimum_cacheable_size() -> None:
    """Below the provider minimum a breakpoint cannot cache, so don't send one."""
    messages = build_messages(SMALL_SYSTEM, "u", "anthropic/claude-opus-5")

    assert messages[0]["content"] == SMALL_SYSTEM


@pytest.mark.unit
def test_caching_can_be_disabled() -> None:
    messages = build_messages(LARGE_SYSTEM, "u", "anthropic/claude-opus-5", enabled=False)

    assert messages[0]["content"] == LARGE_SYSTEM


@pytest.mark.unit
def test_cache_control_blocks_are_not_shared_between_calls() -> None:
    """Each breakpoint must be its own dict — a shared one could be mutated."""
    first = build_messages(LARGE_SYSTEM, "u", "anthropic/claude-opus-5")
    second = build_messages(LARGE_SYSTEM, "u", "anthropic/claude-opus-5")

    assert first[0]["content"][0]["cache_control"] is not second[0]["content"][0]["cache_control"]


@pytest.mark.unit
def test_user_prompt_breakpoint_splits_at_published_prefix() -> None:
    """The stable history block is cached; the per-turn question is not."""
    from reasoner.infrastructure.llm.caching import user_cache_prefix

    history = "H" * (MIN_CACHEABLE_CHARS + 10)
    user_prompt = f"lang\n{history}\nProblem: what changed this turn?"

    with user_cache_prefix(history):
        messages = build_messages("sys", user_prompt, "anthropic/claude-opus-5")

    head, tail = messages[1]["content"]
    assert head["cache_control"]["type"] == "ephemeral"
    assert head["text"].endswith(history)
    assert "cache_control" not in tail
    assert tail["text"] == "\nProblem: what changed this turn?"
    # Round-trips losslessly — no prompt text may be dropped.
    assert head["text"] + tail["text"] == user_prompt


@pytest.mark.unit
def test_user_prompt_breakpoint_skipped_when_prefix_too_small() -> None:
    from reasoner.infrastructure.llm.caching import user_cache_prefix

    with user_cache_prefix("tiny"):
        messages = build_messages("sys", "tiny then question", "anthropic/claude-opus-5")

    assert messages[1]["content"] == "tiny then question"


@pytest.mark.unit
def test_user_prompt_breakpoint_not_leaked_to_automatic_providers() -> None:
    """Automatic-cache providers must keep receiving a plain string."""
    from reasoner.infrastructure.llm.caching import user_cache_prefix

    history = "H" * (MIN_CACHEABLE_CHARS + 10)
    prompt = f"{history}\nQ"

    with user_cache_prefix(history):
        messages = build_messages("sys", prompt, "openai/gpt-5.5")

    assert messages[1]["content"] == prompt


@pytest.mark.unit
def test_prefix_does_not_persist_after_context_exits() -> None:
    from reasoner.infrastructure.llm.caching import user_cache_prefix

    history = "H" * (MIN_CACHEABLE_CHARS + 10)
    with user_cache_prefix(history):
        pass

    messages = build_messages("sys", f"{history}\nQ", "anthropic/claude-opus-5")

    assert messages[1]["content"] == f"{history}\nQ"


@pytest.mark.unit
def test_history_block_head_is_stable_across_turns() -> None:
    """Turn N+1's block must extend turn N's byte-for-byte, or nothing caches."""
    from reasoner.phases._shared import build_followup_context

    turn1 = [{"role": "user", "content": "first question"},
             {"role": "assistant", "content": "first answer"}]
    turn2 = turn1 + [{"role": "user", "content": "second question"},
                     {"role": "assistant", "content": "second answer"}]

    block1 = build_followup_context(turn1, turn_number=1)
    block2 = build_followup_context(turn2, turn_number=2)

    assert block1 != block2
    # The earlier turns must still be a literal prefix of the later block.
    shared = block1[: block1.rindex("---\n")]
    assert block2.startswith(shared), "per-turn value in the block head breaks caching"
    assert "Turn 1" not in block1 and "Turn 2" not in block2


@pytest.mark.unit
def test_anthropic_breakpoint_carries_configured_ttl() -> None:
    """Follow-ups usually land >5min later, so the default entry must outlive that."""
    from reasoner.core.settings import settings
    from reasoner.infrastructure.llm.caching import breakpoint_marker

    marker = breakpoint_marker("anthropic/claude-opus-5")

    assert marker["type"] == "ephemeral"
    if settings.PROMPT_CACHE_TTL == "5m":
        assert "ttl" not in marker, "5m is the provider default and is sent implicitly"
    else:
        assert marker["ttl"] == settings.PROMPT_CACHE_TTL


@pytest.mark.unit
@pytest.mark.parametrize("model", ["google/gemini-3-pro", "qwen/qwen3.7-max"])
def test_ttl_not_sent_to_providers_that_do_not_document_it(model: str) -> None:
    """Only Anthropic documents ttl; an unknown field risks a 400 elsewhere."""
    marker = build_messages(LARGE_SYSTEM, "u", model)[0]["content"][0]["cache_control"]

    assert marker == {"type": "ephemeral"}


@pytest.mark.unit
def test_extract_cache_usage_reads_openrouter_fields() -> None:
    usage = {"prompt_tokens_details": {"cached_tokens": 10318, "cache_write_tokens": 42}}

    assert extract_cache_usage(usage) == {
        "cache_read_tokens": 10318,
        "cache_write_tokens": 42,
    }


@pytest.mark.unit
def test_extract_cache_usage_defaults_to_zero_when_absent() -> None:
    """Providers without usage accounting omit the block entirely."""
    assert extract_cache_usage({}) == {"cache_read_tokens": 0, "cache_write_tokens": 0}
    assert extract_cache_usage(None) == {"cache_read_tokens": 0, "cache_write_tokens": 0}


@pytest.mark.unit
def test_openrouter_provider_enables_usage_accounting() -> None:
    """Without usage.include OpenRouter omits cost and prompt_tokens_details."""
    from reasoner.infrastructure.llm.providers.openai_compat import OpenRouterProvider

    provider = OpenRouterProvider(model="anthropic/claude-opus-5", api_key="test-key")

    assert provider.extra_body["usage"] == {"include": True}


@pytest.mark.unit
def test_stream_complete_forwards_extra_body_and_temperature_rules() -> None:
    """Streaming dropped extra_body, losing the per-phase reasoning effort."""
    import asyncio

    from reasoner.infrastructure.llm.providers.openai_compat import OpenAICompatibleProvider

    captured: dict[str, object] = {}

    class _FakeStream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def __aiter__(self):
            async def _gen():
                return
                yield  # pragma: no cover - empty stream
            return _gen()

    class _FakeCompletions:
        # `async def` on purpose: openai's AsyncCompletions.create is a coroutine
        # function, and the awaited result is the async context manager. A sync
        # stub here hid a missing `await` in stream_complete() that made every
        # real streaming call raise TypeError.
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeStream()

    provider = OpenAICompatibleProvider(model="anthropic/claude-opus-5", api_key="k")
    provider.extra_body = {"reasoning": {"effort": "low"}}
    provider.client = type(
        "C", (), {"chat": type("Ch", (), {"completions": _FakeCompletions()})()}
    )()

    async def _drain():
        async for _ in provider.stream_complete("sys", "user", 512, 0.3):
            pass

    asyncio.run(_drain())

    assert captured["extra_body"] == {"reasoning": {"effort": "low"}}
    # claude-opus is on the fixed-temperature denylist — sending it would 400.
    assert "temperature" not in captured
    assert captured["max_tokens"] == 512


@pytest.mark.unit
def test_openrouter_provider_preserves_caller_extra_body() -> None:
    from reasoner.infrastructure.llm.providers.openai_compat import OpenRouterProvider

    provider = OpenRouterProvider(
        model="anthropic/claude-opus-5",
        api_key="test-key",
        extra_body={"reasoning": {"effort": "high"}},
    )

    assert provider.extra_body["usage"] == {"include": True}
    assert provider.extra_body["reasoning"] == {"effort": "high"}
