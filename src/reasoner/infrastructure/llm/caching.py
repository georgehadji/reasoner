"""Provider-level prompt caching helpers.

Two families of providers exist behind OpenRouter:

* **Automatic** — OpenAI, Grok, DeepSeek, Moonshot, Groq, Z.AI and Gemini 2.5
  cache repeated prefixes with no request changes. They need nothing from us
  beyond keeping prompt prefixes byte-stable, which the ``phases`` modules
  already do (no timestamps or UUIDs are interpolated into prompts).
* **Explicit** — Anthropic, Google Gemini and Qwen only cache when the request
  carries a ``cache_control`` breakpoint on a content block.

This module builds the message payload for the second family. Two breakpoints
are placed, both at the end of a segment that is stable across calls:

* the **system prompt**, which is fixed per role; and
* the **stable head of the user prompt** — in practice the conversation-history
  block, published by ``LLMExecutor`` via :func:`user_cache_prefix`. Prompt
  builders put that block ahead of the per-turn question precisely so it can be
  cached; anything after it varies per call and stays outside the prefix.

Below a provider's minimum cacheable prefix the breakpoint is a documented
no-op — nothing is cached and no write premium is charged — so
``MIN_CACHEABLE_CHARS`` only exists to avoid sending structured content blocks
for prompts that could never cache.

TTL: a 5-minute cache costs 1.25x to write and breaks even on the 2nd read; a
1-hour cache costs 2x and needs a 3rd. Reasoner's reuse comes from follow-up
turns in a conversation, which routinely arrive more than five minutes apart, so
the default is 1h — a 5m entry would usually have expired before the follow-up
that would have read it. ``ttl`` is only sent to Anthropic, which documents it;
Gemini and Qwen breakpoints get bare ``ephemeral`` so an unsupported field
cannot 400 the request.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar
from typing import Any

# Minimum cacheable prefix is 1024 tokens on the models we route to that honour
# explicit breakpoints (Anthropic Claude, Gemini 2.5 Flash); Gemini 2.5 Pro needs
# 4096. At the usual ~4 chars/token this is the 1024-token floor — shorter system
# prompts are left as plain strings.
MIN_CACHEABLE_CHARS: int = 4096

# OpenRouter model-ID prefixes whose providers require an explicit breakpoint.
# Everything else either caches automatically or does not cache at all.
_EXPLICIT_CACHE_PREFIXES: tuple[str, ...] = (
    "anthropic/",
    "google/gemini",
    "qwen/",
)

# Bare (non-OpenRouter) model IDs used by the direct provider adapters.
_EXPLICIT_CACHE_BARE_PREFIXES: tuple[str, ...] = (
    "claude-",
    "gemini-",
)

# Only Anthropic documents a configurable cache TTL. Sending `ttl` to a provider
# that does not know the field risks a 400, so it is scoped to that family.
_TTL_CAPABLE_PREFIXES: tuple[str, ...] = ("anthropic/", "claude-")


def breakpoint_marker(model: str) -> dict[str, str]:
    """Build a fresh ``cache_control`` marker for ``model``.

    Returned dicts are never shared — a caller mutating one must not affect any
    other request's payload.
    """
    marker: dict[str, str] = {"type": "ephemeral"}
    if (model or "").lower().startswith(_TTL_CAPABLE_PREFIXES):
        from reasoner.core.settings import settings
        ttl = settings.PROMPT_CACHE_TTL
        if ttl and ttl != "5m":
            marker["ttl"] = ttl
    return marker

# The stable head of the *user* prompt for the current call, published by
# LLMExecutor. Providers that build their own payloads simply never read it, so
# there is nothing that can leak into a request — unlike an in-band sentinel.
_USER_CACHE_PREFIX: ContextVar[str] = ContextVar("user_cache_prefix", default="")


@contextlib.contextmanager
def user_cache_prefix(prefix: str) -> Iterator[None]:
    """Publish the stable head of the user prompt for the duration of a call."""
    token = _USER_CACHE_PREFIX.set(prefix or "")
    try:
        yield
    finally:
        _USER_CACHE_PREFIX.reset(token)


def _split_user_prompt(user_prompt: str) -> tuple[str, str] | None:
    """Split ``user_prompt`` after the published stable prefix, if it pays off.

    Returns ``(head, tail)`` where ``head`` ends with the stable block, or None
    when there is no prefix, it is not present, or the head is too short to
    reach a provider's minimum cacheable size.
    """
    prefix = _USER_CACHE_PREFIX.get()
    if not prefix:
        return None
    idx = user_prompt.find(prefix)
    if idx < 0:
        return None
    cut = idx + len(prefix)
    if cut < MIN_CACHEABLE_CHARS or cut >= len(user_prompt):
        return None
    return user_prompt[:cut], user_prompt[cut:]


def needs_explicit_cache_control(model: str) -> bool:
    """True when ``model``'s provider only caches with a ``cache_control`` breakpoint."""
    m = (model or "").lower()
    return m.startswith(_EXPLICIT_CACHE_PREFIXES) or m.startswith(_EXPLICIT_CACHE_BARE_PREFIXES)


def is_cacheable(text: str) -> bool:
    """True when ``text`` is long enough to plausibly reach a provider cache minimum."""
    return len(text) >= MIN_CACHEABLE_CHARS


def build_messages(
    system_prompt: str,
    user_prompt: str,
    model: str,
    *,
    enabled: bool = True,
) -> list[dict[str, Any]]:
    """Build the ``messages`` payload, adding a cache breakpoint where it pays off.

    Returns plain string content — the shape every provider accepts — unless the
    model needs an explicit breakpoint and the system prompt is large enough to
    cache, in which case the system message carries a single ``cache_control``
    block.
    """
    explicit = enabled and needs_explicit_cache_control(model)

    if explicit and system_prompt and is_cacheable(system_prompt):
        system_content: Any = [
            {"type": "text", "text": system_prompt, "cache_control": breakpoint_marker(model)}
        ]
    else:
        system_content = system_prompt

    user_content: Any = user_prompt
    if explicit:
        split = _split_user_prompt(user_prompt)
        if split is not None:
            head, tail = split
            # Breakpoint sits at the end of the stable head, so the volatile
            # tail stays outside the cached prefix.
            user_content = [
                {"type": "text", "text": head, "cache_control": breakpoint_marker(model)},
                {"type": "text", "text": tail},
            ]

    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def extract_cache_usage(usage: Any) -> dict[str, int]:
    """Pull cache hit/write counts out of an OpenAI-compatible ``usage`` object.

    OpenRouter reports these under ``prompt_tokens_details`` when usage
    accounting is enabled. Returns zeros when the provider omits them.
    """
    details = getattr(usage, "prompt_tokens_details", None)
    if details is None and isinstance(usage, dict):
        details = usage.get("prompt_tokens_details")
    if details is None:
        return {"cache_read_tokens": 0, "cache_write_tokens": 0}

    def _get(name: str) -> int:
        value = (
            details.get(name) if isinstance(details, dict) else getattr(details, name, None)
        )
        return int(value or 0)

    return {
        "cache_read_tokens": _get("cached_tokens"),
        "cache_write_tokens": _get("cache_write_tokens"),
    }
