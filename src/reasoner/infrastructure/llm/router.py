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

logger = logging.getLogger(__name__)


async def _call_with_circuit(
    provider: BaseLLMProvider,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    effective_timeout: float,
) -> str:
    """Call a provider with circuit-breaker protection."""
    from reasoner.circuit_breaker import get_circuit_breaker

    circuit = get_circuit_breaker(f"llm:{provider.model}")
    if not await circuit.can_execute():
        raise LLMError(f"Circuit open for {provider.model}")
    try:
        coro = provider.complete_with_retry(system_prompt, user_prompt, max_tokens, temperature)
        result = await asyncio.wait_for(coro, timeout=effective_timeout)
        await circuit.record_success()
        return result
    except asyncio.CancelledError:
        # BUG-FIX: Re-raise CancelledError without poisoning the circuit breaker.
        # Task cancellation (client disconnect, timeout from upstream) is not a provider failure.
        raise
    except Exception:
        await circuit.record_failure()
        raise


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

    def get(self, role: str) -> BaseLLMProvider:
        provider = self.routing_table.get(role)
        if provider is None:
            if role != "primary" and self.verbose:
                logger.warning(
                    "Role '%s' not found in routing table — falling back to primary '%s'. "
                    "Check preset routing configuration.",
                    role, self.primary.model
                )
            return self.primary
        return provider

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
                    provider, system_prompt, user_prompt, max_tokens, temperature, effective_timeout
                )
                if not response or not response.strip():
                    raise LLMError(f"Empty response from {provider.model} for role={role}")
                return response, self._build_metadata(actual_provider, response)
            except asyncio.TimeoutError:
                if is_fallback:
                    logger.error(
                        "Role '%s' fallback '%s' timed out after %.0fs; returning degraded response",
                        role, provider.model, effective_timeout,
                    )
                    return DegradedLLMResponse(
                        text="",
                        error=f"{provider.model} timed out",
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
                        text="",
                        error=f"{assigned.model} timed out — no fallback",
                        metadata={"model": assigned.model},
                    ), {}
            except LLMError as exc:
                if is_fallback:
                    logger.error(
                        "Role '%s' fallback '%s' failed (%s); returning degraded response",
                        role, provider.model, exc,
                    )
                    return DegradedLLMResponse(
                        text="",
                        error=str(exc),
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
                        text="",
                        error=str(exc),
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
