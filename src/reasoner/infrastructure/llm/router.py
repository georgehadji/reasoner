"""Provider router with fallback logic."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

from reasoner.core.constants import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    ROLE_TIMEOUTS,
    TIMEOUTS,
)
from reasoner.infrastructure.llm.base import BaseLLMProvider, LLMError
from reasoner.infrastructure.llm.registry import build_provider
from reasoner.infrastructure.llm.ports import DegradedLLMResponse

# Multi-provider fallback (v3.4) — retry OpenRouter failures via direct API keys
_FALLBACK_PROVIDER_CHAIN: list[str] = ["anthropic", "openai", "google"]


async def _try_direct_fallback(
    role: str,
    system_prompt: str,
    user_prompt: str,
    original_error: Exception,
    max_tokens: int,
    temperature: float,
    extra_body: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Try direct API providers when OpenRouter fails.

    Returns (response, metadata) on success, None if all fallbacks fail.
    Only active when MULTI_PROVIDER_FALLBACK_ENABLED is true.
    """
    try:
        from reasoner.core.settings import settings
        if not settings.MULTI_PROVIDER_FALLBACK_ENABLED:
            return None
    except Exception:
        return None  # Settings not available — skip silently

    from reasoner.infrastructure.llm.providers.direct import build_fallback_provider

    for provider_name in _FALLBACK_PROVIDER_CHAIN:
        try:
            provider = build_fallback_provider(provider_name)
            logger.warning(
                "Multi-provider fallback: trying %s for role '%s' after: %s",
                provider_name, role, original_error,
            )
            response = await provider.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if not response or not response.strip():
                logger.warning("Multi-provider fallback %s returned empty — trying next", provider_name)
                continue
            metadata: dict[str, Any] = {"model": f"{provider_name}:{provider.model}", "is_fallback": True}
            logger.info("Multi-provider fallback %s succeeded for role '%s'", provider_name, role)
            return response, metadata
        except Exception as e:
            logger.warning("Multi-provider fallback %s failed for role '%s': %s", provider_name, role, e)
            continue

    logger.error("All multi-provider fallbacks exhausted for role '%s'", role)
    return None

logger = logging.getLogger(__name__)


async def _call_with_circuit(
    provider: BaseLLMProvider,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    effective_timeout: float,
    extra_body: dict[str, Any] | None = None,
    single_attempt: bool = False,
) -> str:
    """Call a provider with circuit-breaker protection and concurrency bounding.

    When ``single_attempt=True`` (used by the router fallback path), the call
    uses ``provider.complete_once()`` — zero retries — instead of the default
    ``provider.complete_with_retry()`` (2 retries). This avoids the dual-layer
    retry problem where provider-level retries * router-level fallbacks
    compound into 6+ LLM calls for one logical request.

    Args:
        extra_body: Optional additional body params to merge into the API call.
                    Used for web_search: true injection on supported providers.
        single_attempt: If True, skip retry — one shot only.
    """
    from reasoner.circuit_breaker import get_circuit_breaker

    circuit = get_circuit_breaker(f"llm:{provider.model}")

    # Check circuit BEFORE acquiring the semaphore (lightweight check).
    if not await circuit.can_execute():
        raise LLMError(f"Circuit open for {provider.model}")

    semaphore = _get_llm_semaphore(provider.model)
    async with semaphore:
        # Mutate extra_body INSIDE the per-model semaphore so concurrent
        # calls to this provider model are serialized — no concurrent
        # caller sees mutated state. Save/restore is still needed for
        # the try/except/finally within this critical section.
        _saved_extra = None
        if extra_body and hasattr(provider, "extra_body") and provider.extra_body is not None:
            _saved_extra = dict(provider.extra_body)
            provider.extra_body = {**provider.extra_body, **extra_body}
        elif extra_body and hasattr(provider, "extra_body"):
            provider.extra_body = dict(extra_body)
        try:
            if single_attempt:
                coro = provider.complete_once(system_prompt, user_prompt, max_tokens, temperature)
            else:
                coro = provider.complete_with_retry(system_prompt, user_prompt, max_tokens, temperature)
            result = await asyncio.wait_for(coro, timeout=effective_timeout)
            await circuit.record_success()
            return result
        except asyncio.CancelledError:
            raise
        except Exception:
            await circuit.record_failure()
            raise
        finally:
            # Restore original extra_body
            if _saved_extra is not None and hasattr(provider, "extra_body"):
                provider.extra_body = _saved_extra
            elif extra_body and hasattr(provider, "extra_body"):
                provider.extra_body = {}


async def _call_with_tools_circuit(
    provider: BaseLLMProvider,
    system_prompt: str,
    user_prompt: str,
    tools: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    effective_timeout: float,
    extra_body: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Call a provider with tools using circuit-breaker protection and concurrency bounding."""
    from reasoner.circuit_breaker import get_circuit_breaker

    circuit = get_circuit_breaker(f"llm:{provider.model}")

    if not await circuit.can_execute():
        raise LLMError(f"Circuit open for {provider.model}")

    semaphore = _get_llm_semaphore(provider.model)
    async with semaphore:
        # Mutate extra_body inside the per-model critical section
        _saved_extra = None
        if extra_body and hasattr(provider, "extra_body") and provider.extra_body is not None:
            _saved_extra = dict(provider.extra_body)
            provider.extra_body = {**provider.extra_body, **extra_body}
        elif extra_body and hasattr(provider, "extra_body"):
            provider.extra_body = dict(extra_body)
        try:
            coro = provider.call_with_tools_with_retry(system_prompt, user_prompt, tools, max_tokens, temperature)
            result = await asyncio.wait_for(coro, timeout=effective_timeout)
            await circuit.record_success()
            return result
        except asyncio.CancelledError:
            raise
        except Exception:
            await circuit.record_failure()
            raise
        finally:
            # Restore original extra_body
            if _saved_extra is not None and hasattr(provider, "extra_body"):
                provider.extra_body = _saved_extra
            elif extra_body and hasattr(provider, "extra_body"):
                provider.extra_body = {}


_GLOBAL_RESOLVED_CACHE: dict[str, BaseLLMProvider] = {}
_PER_MODEL_SEMAPHORES: dict[str, asyncio.Semaphore] = {}
_SEMAPHORE_CONFIG: dict[str, int] | None = None

def _parse_semaphore_config() -> dict[str, int]:
    """Parse LLM_CONCURRENCY_LIMIT_PER_MODEL env var into a model→limit dict.

    Format: ``"claude-sonnet:10,gpt-5:15,*:10"`` — models not listed use ``*``
    default.  If the env var is not set, all models default to 30.
    """
    import os
    raw = os.environ.get("LLM_CONCURRENCY_LIMIT_PER_MODEL", "")
    if not raw:
        return {}  # all models use the fallback below
    config: dict[str, int] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" not in entry:
            continue
        model, limit_str = entry.split(":", 1)
        try:
            config[model.strip()] = int(limit_str.strip())
        except ValueError:
            continue
    return config


def _get_model_limit(model_name: str) -> int:
    """Return the concurrency limit for a given model name."""
    global _SEMAPHORE_CONFIG
    if _SEMAPHORE_CONFIG is None:
        _SEMAPHORE_CONFIG = _parse_semaphore_config()
    if model_name in _SEMAPHORE_CONFIG:
        return _SEMAPHORE_CONFIG[model_name]
    # Wildcard fallback
    if "*" in _SEMAPHORE_CONFIG:
        return _SEMAPHORE_CONFIG["*"]
    # Default: 30 (original single-semaphore value)
    return int(os.environ.get("LLM_CONCURRENCY_LIMIT", "30"))


def _get_llm_semaphore(model_name: str) -> asyncio.Semaphore:
    """Get or create a per-model concurrency semaphore.

    Each model has its own limit so slow providers (e.g. claude-sonnet
    with rate-limit retries) can't starve fast providers (e.g. gpt-5-nano).
    Limits are configured via ``LLM_CONCURRENCY_LIMIT_PER_MODEL`` env var.
    """
    if model_name not in _PER_MODEL_SEMAPHORES:
        limit = _get_model_limit(model_name)
        _PER_MODEL_SEMAPHORES[model_name] = asyncio.Semaphore(limit)
    return _PER_MODEL_SEMAPHORES[model_name]

class ProviderRouter:
    """
    Routes pipeline phases to appropriate providers.
    Falls back to primary for any unspecified role.
    """

    def __init__(
        self, primary: BaseLLMProvider, routing_table: dict[str, BaseLLMProvider] | None = None, fallback_table: dict[str, BaseLLMProvider] | None = None, verbose: bool = False, cascading_routing: dict[str, list[str]] | None = None,
        on_fallback: "None | (str, str, str, str) -> None" = None,
        ) -> None:
        self.primary = primary
        self.routing_table: dict[str, BaseLLMProvider] = routing_table or {}
        # Explicit per-role fallbacks. Roles absent here fall back to primary automatically.
        self.fallback_table: dict[str, BaseLLMProvider] = fallback_table or {}
        self.cascading_routing: dict[str, list[str]] = cascading_routing or {}
        self.verbose = verbose
        self.on_fallback = on_fallback

    def resolve(self, role: str) -> BaseLLMProvider:
        """Return the provider for a role, with global process-level caching."""
        # Use provider string keys for global cache to avoid collisions between identical roles but different preset configurations
        provider = self.routing_table.get(role)
        if provider is None:
            provider = self.primary
        
        # We don't want to re-instantiate identical providers, but we don't have
        # a unique preset string here. We can just use the memory id of the config or model.
        # Actually, the routing_table already holds instances.
        # But if ProviderRouter is created multiple times per request,
        # self.routing_table contains NEW instances.
        # So we can cache by the provider's model and type.
        cache_key = f"{type(provider).__name__}::{provider.model}"
        
        if cache_key not in _GLOBAL_RESOLVED_CACHE:
            _GLOBAL_RESOLVED_CACHE[cache_key] = provider
            
        return _GLOBAL_RESOLVED_CACHE[cache_key]

    def get(self, role: str) -> BaseLLMProvider:
        return self.resolve(role)

    def _timeout_for_role(self, role: str, override: float | None) -> float:
        if override is not None:
            return override
        attr = ROLE_TIMEOUTS.get(role)
        return getattr(TIMEOUTS, attr) if attr else TIMEOUTS.LLM_CALL

    def _build_metadata(self, provider: BaseLLMProvider, response: str) -> dict[str, Any]:
        """Build metadata dict for the LLM call."""
        metadata = {
            "model": provider.model,
        }
        if hasattr(provider, "last_input_tokens"):
            metadata["input_tokens"] = provider.last_input_tokens
        if hasattr(provider, "last_output_tokens"):
            metadata["output_tokens"] = provider.last_output_tokens
        if hasattr(provider, "last_cost_usd"):
            metadata["cost_usd"] = provider.last_cost_usd
        return metadata

    async def call(
        self,
        role: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        timeout_seconds: float | None = None,
        stream: bool = False,
        extra_body: dict[str, Any] | None = None,
    ) -> tuple[str | DegradedLLMResponse, dict[str, Any]] | AsyncIterator[str | DegradedLLMResponse]:
        """
        Call LLM for role. On LLMError or timeout, tries a fallback provider:
          1. Explicit fallback from fallback_table (if defined and different)
          2. Primary (if role was using a non-primary model)
          3. Re-raises original error if no fallback available

        Returns:
            Tuple of (response_text, metadata_dict) if not streaming.
            AsyncIterator of (response_chunk | DegradedLLMResponse) if streaming.
        """
        assigned = self.get(role)
        effective_timeout = self._timeout_for_role(role, timeout_seconds)

        # Resolve fallback: explicit > primary > none.
        # Skip any fallback that resolves to the same model as the failing provider —
        # retrying an identical endpoint after a timeout is guaranteed to waste time.
        explicit = self.fallback_table.get(role)
        if explicit is None and assigned is self.primary:
            explicit = self.fallback_table.get("primary")

        candidates: list[BaseLLMProvider] = []
        if explicit and explicit is not assigned:
            candidates.append(explicit)
        if self.primary is not assigned and self.primary not in candidates:
            candidates.append(self.primary)
        # Filter out same-model duplicates so we never retry a timed-out endpoint
        fallback: BaseLLMProvider | None = next(
            (p for p in candidates if p.model != assigned.model), None
        )

        async def _execute_call(provider: BaseLLMProvider, is_fallback: bool = False):
            actual_provider = provider
            try:
                response = await _call_with_circuit(
                    provider, system_prompt, user_prompt, max_tokens, temperature,
                    effective_timeout, extra_body=extra_body,
                    single_attempt=is_fallback,
                )
                if not response or not response.strip():
                    raise LLMError(f"Empty response from {provider.model} for role={role}")
                return response, self._build_metadata(actual_provider, response)
            except asyncio.TimeoutError as exc:
                if is_fallback:
                    logger.error(
                        "Role '%s' fallback '%s' timed out after %.0fs; trying direct fallback...",
                        role, provider.model, effective_timeout,
                    )
                    direct = await _try_direct_fallback(
                        role, system_prompt, user_prompt, original_error=exc,
                        max_tokens=max_tokens, temperature=temperature, extra_body=extra_body,
                    )
                    if direct:
                        return direct
                    return DegradedLLMResponse(
                        text="", error=f"{provider.model} timed out — primary and fallback both failed",
                        metadata={"model": provider.model},
                    ), {}
                logger.warning(
                    "Role '%s' provider '%s' timed out after %.0fs — retrying with fallback '%s'",
                    role, provider.model, effective_timeout, fallback.model if fallback else "N/A",
                )
                if fallback:
                    if self.on_fallback:
                        self.on_fallback(role, assigned.model, fallback.model, "timeout")
                    return await _execute_call(fallback, is_fallback=True)
                else:
                    return DegradedLLMResponse(
                        text="", error=f"{assigned.model} timed out — no fallback",
                        metadata={"model": assigned.model},
                    ), {}
            except LLMError as exc:
                if is_fallback:
                    logger.error(
                        "Role '%s' fallback '%s' failed (%s); trying direct fallback...",
                        role, provider.model, exc,
                    )
                    direct = await _try_direct_fallback(
                        role, system_prompt, user_prompt, original_error=exc,
                        max_tokens=max_tokens, temperature=temperature, extra_body=extra_body,
                    )
                    if direct:
                        return direct
                    return DegradedLLMResponse(
                        text="", error=str(exc),
                        metadata={"model": provider.model},
                    ), {}
                logger.warning(
                    "Role '%s' provider '%s' failed (%s) — retrying with fallback '%s'",
                    role, provider.model, exc, fallback.model if fallback else "N/A",
                )
                if fallback:
                    if self.on_fallback:
                        self.on_fallback(role, assigned.model, fallback.model, "llm_error")
                    return await _execute_call(fallback, is_fallback=True)
                else:
                    return DegradedLLMResponse(
                        text="", error=str(exc),
                        metadata={"model": assigned.model},
                    ), {}

        async def _execute_stream(provider: BaseLLMProvider, is_fallback: bool = False):
            from reasoner.circuit_breaker import get_circuit_breaker
            circuit = get_circuit_breaker(f"llm:{provider.model}")
            if not await circuit.can_execute():
                yield DegradedLLMResponse(
                    text="",
                    error=f"Circuit open for {provider.model}",
                    metadata={"model": provider.model},
                )
                return
            try:
                semaphore = _get_llm_semaphore(provider.model)
                async with semaphore:
                    async for chunk in provider.stream_complete_with_retry(
                        system_prompt, user_prompt, max_tokens, temperature
                    ):
                        yield chunk
                await circuit.record_success()
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                await circuit.record_failure()
                if is_fallback:
                    yield DegradedLLMResponse(
                        text="",
                        error=f"{provider.model} timed out",
                        metadata={"model": provider.model},
                    )
                    return
                if fallback:
                    async for chunk in _execute_stream(fallback, is_fallback=True):
                        yield chunk
                else:
                    yield DegradedLLMResponse(
                        text="",
                        error=f"{assigned.model} timed out — no fallback",
                        metadata={"model": assigned.model},
                    )
            except LLMError as exc:
                await circuit.record_failure()
                if is_fallback:
                    direct = await _try_direct_fallback(
                        role, system_prompt, user_prompt, original_error=exc,
                        max_tokens=max_tokens, temperature=temperature, extra_body=extra_body,
                    )
                    if direct:
                        yield direct
                        return
                    yield DegradedLLMResponse(
                        text="",
                        error=str(exc),
                        metadata={"model": provider.model},
                    )
                    return
                if fallback:
                    async for chunk in _execute_stream(fallback, is_fallback=True):
                        yield chunk
                else:
                    yield DegradedLLMResponse(
                        text="",
                        error=str(exc),
                        metadata={"model": assigned.model},
                    )

        if stream:
            return _execute_stream(assigned)
        else:
            return await _execute_call(assigned)

    def describe(self) -> dict[str, str]:
        result = {"[primary]": self.primary.model}
        for role, p in self.routing_table.items():
            explicit_fb = self.fallback_table.get(role)
            auto_fb = self.primary if self.primary is not p else None
            fb = explicit_fb or auto_fb
            suffix = f" -> {fb.model}" if fb else ""
            result[role] = f"{p.model}{suffix}"
        return result

    def supports_tools(self) -> bool:
        """True if the primary provider supports native tool calling."""
        return self.primary.supports_tools()

    async def call_with_tools(
        self,
        role: str,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        timeout_seconds: float | None = None,
    ) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
        """Call a provider with tools using circuit-breaker protection and fallback logic."""
        assigned = self.get(role)
        effective_timeout = self._timeout_for_role(role, timeout_seconds)

        # Fallback resolution logic: explicit > primary > none.
        explicit = self.fallback_table.get(role)
        if explicit is None and assigned is self.primary:
            explicit = self.fallback_table.get("primary")

        candidates: list[BaseLLMProvider] = []
        if explicit and explicit is not assigned:
            candidates.append(explicit)
        if self.primary is not assigned and self.primary not in candidates:
            candidates.append(self.primary)
        fallback: BaseLLMProvider | None = next(
            (p for p in candidates if p.model != assigned.model), None
        )

        async def _execute_tool_call(provider: BaseLLMProvider, is_fallback: bool = False):
            try:
                content, tool_calls = await _call_with_tools_circuit(
                    provider, system_prompt, user_prompt, tools, max_tokens, temperature,
                    effective_timeout,
                )
                return content, self._build_metadata(provider, content), tool_calls
            except Exception as exc:
                if is_fallback:
                    raise exc
                logger.warning(
                    "Role '%s' provider '%s' failed tool call (%s) — retrying with fallback '%s'",
                    role, provider.model, exc, fallback.model if fallback else "N/A",
                )
                if fallback:
                    if self.on_fallback:
                        self.on_fallback(role, assigned.model, fallback.model, "llm_error")
                    return await _execute_tool_call(fallback, is_fallback=True)
                else:
                    raise exc

        return await _execute_tool_call(assigned)

    @classmethod
    def from_model_ids(
        cls,
        primary_id: str,
        routing: dict[str, str] | None = None,
        fallback_routing: dict[str, str] | None = None,
        cascading_routing: dict[str, list[str]] | None = None,
        verbose: bool = False,
    ) -> "ProviderRouter":
        """Build router from model ID strings."""
        primary = build_provider(primary_id)
        table = {role: build_provider(mid) for role, mid in (routing or {}).items()}
        fallback_table = {role: build_provider(mid) for role, mid in (fallback_routing or {}).items()}
        return cls(primary=primary, routing_table=table, fallback_table=fallback_table, cascading_routing=cascading_routing, verbose=verbose)
