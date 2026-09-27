"""Base LLM provider abstraction and exceptions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from reasoner.core.constants import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
)
from reasoner.core.exceptions import (
    AuthenticationError,
    ModelNotFoundError,
    ProviderCreditsExhaustedError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
    is_retryable,
)

logger = logging.getLogger(__name__)


class LLMError(ProviderError):
    """Raised when an LLM call fails after all retries.

    Descends from ``core.exceptions.ProviderError`` (P2,
    docs/plans/root-cause-remediation-2026-09-07.md). It used to descend
    straight from ``ReasonerError``, making it a *sibling* of the whole
    ``ProviderError`` tree rather than a member: ``ProviderUnavailableError``
    raised by ``providers/openai_compat.py`` was not an ``LLMError``, so the
    router -- which caught ``LLMError`` alone -- never saw it.

    This is now the residual case only: "the adapter could not classify this
    failure any more precisely". Adapters should raise a specific
    ``ProviderError`` subclass wherever the SDK gives them enough to name one.
    """
    retryable = False


def translate_http_status(status: int | None, detail: str, model: str) -> ProviderError | None:
    """Map an HTTP status onto the domain error tree, or None if unmapped.

    The status-to-class table lives here, once, because both adapter families
    need it: ``providers/openai_compat.py`` (OpenRouter lane) and
    ``providers/direct.py`` (Anthropic/OpenAI/Google/httpx lanes). Each keeps
    its own ``_translate`` for the SDK-specific cases the status code cannot
    express, and calls this for the part that is just HTTP.

    Returning None rather than a default keeps the choice of residual class
    with the caller.
    """
    if status is None:
        return None
    if status == 402:
        logger.warning(
            "Credit exhausted for %s: %s. The pipeline will return partial results.",
            model, detail,
        )
        return ProviderCreditsExhaustedError(detail)
    if status == 429:
        return RateLimitError(detail, provider=model)
    if status in (401, 403):
        return AuthenticationError(detail, provider=model)
    if status == 404:
        return ModelNotFoundError(detail, model=model)
    if status >= 500:
        return ProviderUnavailableError(detail)
    return None


def _type_name(obj: object) -> str:
    """Deterministic placeholder for a value ``json`` cannot serialise.

    Deliberately *not* ``repr``/``str``: the default repr of most objects
    embeds the instance's memory address, which makes the enclosing signature
    unique per object and therefore useless as a cache key (every call would
    mint a brand-new entry in an unbounded dict).  ``extra_body`` is an API
    request payload and must be JSON-serialisable to be sent at all, so a
    non-serialisable member is already a configuration bug; recording its type
    keeps the signature stable and lets the bad value surface at call time.
    """
    return f"<{type(obj).__name__}>"


def config_signature(value: Any) -> str:
    """Stable, address-free signature for a provider configuration value."""
    if not value:
        return "0"
    return json.dumps(value, sort_keys=True, default=_type_name)


def secret_digest(secret: str | None) -> str:
    """Short, non-reversible fingerprint of a credential.

    Provider identities are used as keys in a process-global dict; embedding
    the raw API key there would put credentials one stray log line away from
    disclosure.  A digest distinguishes two tenants' keys without carrying
    either of them.
    """
    if not secret:
        return "-"
    return hashlib.sha256(secret.encode("utf-8", "replace")).hexdigest()[:16]


class BaseLLMProvider(ABC):
    def __init__(self, model: str, max_retries: int = 2) -> None:
        self.model = model
        self.max_retries = max_retries

    def routing_identity(self) -> str:
        """Stable key identifying interchangeable provider instances.

        Two providers sharing an identity are behaviourally the same endpoint,
        so the router may hand out either one (see
        ``ProviderRouter._dedupe``).  Subclasses that bake connection settings
        (base URL, credentials) into a client must record a richer identity in
        ``self._routing_identity`` — those settings are invisible from the
        outside once the client exists, and two tenants' providers would
        otherwise collapse onto one entry.

        The identity must be derived from *configured* state only.  In
        particular it must never be recomputed from ``self.extra_body``: the
        router temporarily overwrites that attribute for the duration of a
        call, so a concurrent read would observe a transient value and mint a
        second, permanent entry for the same provider.
        """
        recorded = getattr(self, "_routing_identity", None)
        if recorded:
            return recorded
        # Fallback for providers that carry no connection settings (test
        # doubles, NoopProvider): class + model + whatever extra_body they
        # were constructed with.
        return (
            f"{type(self).__name__}::{self.model}"
            f"::{config_signature(getattr(self, 'extra_body', None))}"
        )

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str: ...

    @abstractmethod
    async def stream_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> AsyncIterator[str]: ...

    def supports_tools(self) -> bool:
        return False

    async def call_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> tuple[str, list[dict[str, Any]]]:
        raise NotImplementedError("This provider does not support native tool calling.")

    async def call_with_tools_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> tuple[str, list[dict[str, Any]]]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await self.call_with_tools(
                    system_prompt, user_prompt, tools, max_tokens, temperature
                )
            except Exception as exc:
                last_error = exc
                # Don't retry non-retryable errors
                if not is_retryable(exc):
                    raise
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 4) + random.uniform(0, 0.5))
        raise LLMError(
            f"{self.__class__.__name__}({self.model}) with tools failed "
            f"after {self.max_retries} retries: {last_error}"
        ) from last_error

    async def complete_once(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        """Single attempt — no retry. Used by the router fallback path.

        The router owns the retry budget; this is a raw single-shot wrapper
        so the fallback doesn't multiply retries (avoiding the dual-layer
        retry problem where provider-level retries + router-level fallbacks
        compound into 6+ LLM calls).
        """
        return await self.complete(system_prompt, user_prompt, max_tokens, temperature)

    async def complete_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await self.complete(
                    system_prompt, user_prompt, max_tokens, temperature
                )
            except Exception as exc:
                last_error = exc
                # A ProviderError has already been classified by the adapter's
                # _translate() at the SDK boundary, and the router owns what
                # happens to it next (fallback to a cross-lab equivalent, which
                # beats sleeping on a model that just rate-limited us). Retrying
                # here as well is the dual-layer retry problem complete_once()
                # exists to avoid.
                #
                # This preserves today's behaviour rather than changing it:
                # every adapter already wrapped its SDK exceptions into the
                # non-retryable LLMError before this loop saw them, so the
                # retry never fired for them. Translating into accurate classes
                # (RateLimitError.retryable is True) would have switched it on
                # as a side effect. Changing the retry topology is a separate
                # decision, not part of P2.
                if isinstance(exc, ProviderError) or not is_retryable(exc):
                    raise
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 4) + random.uniform(0, 0.5))
        raise LLMError(
            f"{self.__class__.__name__}({self.model}) failed "
            f"after {self.max_retries} retries: {last_error}"
        ) from last_error

    async def stream_complete_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            yielded_any = False
            try:
                async for chunk in self.stream_complete(
                    system_prompt, user_prompt, max_tokens, temperature
                ):
                    yielded_any = True
                    yield chunk
                return # Success
            except Exception as exc:
                last_error = exc
                if yielded_any or not is_retryable(exc):
                    raise
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 4) + random.uniform(0, 0.5))
        raise LLMError(
            f"{self.__class__.__name__}({self.model}) stream failed "
            f"after {self.max_retries} retries: {last_error}"
        ) from last_error
