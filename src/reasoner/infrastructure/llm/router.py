"""Provider router with fallback logic."""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, AsyncIterator

if TYPE_CHECKING:
    from reasoner.domain.telemetry import LLMCallTelemetry

from reasoner.core.constants import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    ROLE_TIMEOUTS,
    TIMEOUTS,
)
from reasoner.infrastructure.llm.base import BaseLLMProvider, LLMError
from reasoner.infrastructure.llm.registry import build_provider
from reasoner.infrastructure.llm.ports import DegradedLLMResponse

try:
    from reasoner.core.ports.telemetry_port import CallTelemetryPort
    _HAS_TELEMETRY_PORT = True
except Exception:
    _HAS_TELEMETRY_PORT = False

try:
    from reasoner.infrastructure.metrics import (
        LLM_CALL_DURATION,
        LLM_CALL_SUCCESS,
        LLM_CALL_FAILURE,
        LLM_CALL_COST,
    )
    _HAS_ACR_METRICS = True
except Exception:
    _HAS_ACR_METRICS = False

# Multi-provider fallback (v3.4/P3.4) — retry OpenRouter failures via direct API keys
# Chain includes Big-3 (key-only, no SDK needed) plus OpenAI-compatible providers.
# The chain tries providers in order; first successful response wins.
_FALLBACK_PROVIDER_CHAIN: list[str] = [
    "anthropic", "openai", "google",           # Big-3 (SDK-based)
    "mistral", "perplexity", "deepseek",       # OpenAI-compatible
    "xai", "qwen",                             # OpenAI-compatible
]


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


# Process-wide de-duplication of equivalent provider instances (every request
# builds a fresh ProviderRouter, so without this each run mints a new
# AsyncOpenAI wrapper per role).  Bounded and LRU-ordered: the key space grows
# with distinct (class, model, base_url, credential, extra_body) tuples, which
# is unbounded in a multi-tenant deployment.  Eviction is safe — the entry is
# only a shortcut, and every router holds its own reference to the providers it
# was built with.
_RESOLVED_CACHE_MAX = 512
_GLOBAL_RESOLVED_CACHE: "OrderedDict[str, BaseLLMProvider]" = OrderedDict()
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
        telemetry: "CallTelemetryPort | None" = None,
        run_id: str = "",
        preset_id: str = "",
        method: str = "",
        ) -> None:
        self.primary = primary
        self.routing_table: dict[str, BaseLLMProvider] = routing_table or {}
        # Explicit per-role fallbacks. Roles absent here fall back to primary automatically.
        self.fallback_table: dict[str, BaseLLMProvider] = fallback_table or {}
        self.cascading_routing: dict[str, list[str]] = cascading_routing or {}
        # Raw model-ID arguments as passed to from_model_ids(). The tables above
        # hold built providers, so a caller that rebuilds this router (the ACR
        # reroute in PipelineOrchestrator.preflight) cannot recover the IDs from
        # them. Without these the rebuild silently drops every preset fallback
        # and cascade.
        self.routing_ids: dict[str, str] = {}
        self.fallback_routing_ids: dict[str, str] = {}
        self.cascading_routing_ids: dict[str, list[str]] = dict(cascading_routing or {})
        self.primary_id: str = getattr(primary, "model", "")
        self.verbose = verbose
        self.on_fallback = on_fallback
        # ACR telemetry (Phase 1)
        self.telemetry = telemetry
        self.run_id = run_id
        self.preset_id = preset_id
        self.method = method

    @staticmethod
    def _dedupe(provider: BaseLLMProvider) -> BaseLLMProvider:
        """Collapse behaviourally identical providers onto one shared instance.

        Every request builds a fresh router, so ``routing_table`` holds new
        instances each time; without this, a long-lived process accumulates a
        distinct AsyncOpenAI wrapper per role per run.  The identity comes from
        the provider itself (:meth:`BaseLLMProvider.routing_identity`) so
        connection settings that are invisible from out here — base URL,
        credentials — still separate two providers that merely share a model.

        Everything that resolves a provider must go through this, including
        ``self.primary``: a router's own ``primary`` object is not the instance
        this returns once another router has warmed the entry, so an ``is``
        comparison against the raw attribute silently stops matching.

        Providers are duck-typed here -- the router only ever needs ``.model``
        and the call methods, and objects that never subclass
        ``BaseLLMProvider`` (test doubles, out-of-tree adapters) are legitimate.
        One that declares no identity is returned untouched rather than being
        forced into the cache: de-duplication is an optimisation, so failing to
        apply it must never be fatal, and an object that cannot state what makes
        it interchangeable is exactly one that must not be shared process-wide.
        """
        identify = getattr(provider, "routing_identity", None)
        if not callable(identify):
            return provider
        key = identify()
        cached = _GLOBAL_RESOLVED_CACHE.get(key)
        if cached is not None:
            _GLOBAL_RESOLVED_CACHE.move_to_end(key)
            return cached
        _GLOBAL_RESOLVED_CACHE[key] = provider
        while len(_GLOBAL_RESOLVED_CACHE) > _RESOLVED_CACHE_MAX:
            _GLOBAL_RESOLVED_CACHE.popitem(last=False)
        return provider

    def resolve(self, role: str) -> BaseLLMProvider:
        """Return the provider for a role, with global process-level caching."""
        provider = self.routing_table.get(role)
        if provider is None:
            provider = self.primary
        return self._dedupe(provider)

    def resolve_primary(self) -> BaseLLMProvider:
        """Return the primary provider as :meth:`resolve` would hand it back.

        Use this — never the raw ``self.primary`` attribute — whenever the
        result is compared by identity against something ``resolve()``
        produced.
        """
        return self._dedupe(self.primary)

    def get(self, role: str) -> BaseLLMProvider:
        return self.resolve(role)

    def _resolve_fallback(self, role: str, assigned: BaseLLMProvider) -> BaseLLMProvider | None:
        """Pick the fallback provider for *role*: explicit > primary > none.

        Any candidate resolving to the same model as the failing provider is
        dropped — re-issuing an identical request against an endpoint that just
        timed out only burns the remaining budget.
        """
        primary = self.resolve_primary()
        explicit = self.fallback_table.get(role)
        if explicit is None and assigned is primary:
            explicit = self.fallback_table.get("primary")
        if explicit is not None:
            explicit = self._dedupe(explicit)

        candidates: list[BaseLLMProvider] = []
        if explicit is not None and explicit is not assigned:
            candidates.append(explicit)
        if primary is not assigned and primary not in candidates:
            candidates.append(primary)
        return next((p for p in candidates if p.model != assigned.model), None)

    def _timeout_for_role(self, role: str, override: float | None) -> float:
        if override is not None:
            return override
        attr = ROLE_TIMEOUTS.get(role)
        return getattr(TIMEOUTS, attr) if attr else TIMEOUTS.LLM_CALL

    async def _attempt_call_and_record(
        self,
        role: str,
        provider: BaseLLMProvider,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        temperature: float,
        effective_timeout: float,
        extra_body: dict[str, Any] | None = None,
        single_attempt: bool = False,
    ) -> str:
        """Call a provider via circuit breaker, recording telemetry and timing."""
        start = time.perf_counter()
        try:
            result = await _call_with_circuit(
                provider, system_prompt, user_prompt, max_tokens, temperature,
                effective_timeout, extra_body=extra_body,
                single_attempt=single_attempt,
            )
            latency = (time.perf_counter() - start) * 1000
            # Successful call — emit telemetry asynchronously (best-effort)
            if self.telemetry or _HAS_ACR_METRICS:
                await self._emit_telemetry(
                    role=role, provider=provider, success=True,
                    latency_ms=latency, is_fallback=single_attempt,
                    circuit_state="closed",
                )
            return result
        except Exception:
            latency = (time.perf_counter() - start) * 1000
            # Determine circuit state
            from reasoner.circuit_breaker import get_circuit_breaker
            cb = get_circuit_breaker(f"llm:{provider.model}")
            circuit_state = cb.state if hasattr(cb, "state") else "closed"
            if self.telemetry or _HAS_ACR_METRICS:
                await self._emit_telemetry(
                    role=role, provider=provider, success=False,
                    latency_ms=latency, is_fallback=single_attempt,
                    fallback_reason="error",
                    circuit_state=circuit_state,
                )
            raise

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
        # Provider-side prompt cache accounting (OpenRouter usage.include).
        # Absent for providers that do not report it.
        if hasattr(provider, "last_cache_read_tokens"):
            metadata["cache_read_tokens"] = provider.last_cache_read_tokens
        if hasattr(provider, "last_cache_write_tokens"):
            metadata["cache_write_tokens"] = provider.last_cache_write_tokens
        return metadata

    async def _emit_telemetry(
        self,
        role: str,
        provider: BaseLLMProvider,
        success: bool,
        latency_ms: float,
        is_fallback: bool = False,
        fallback_reason: str | None = None,
        circuit_state: str = "closed",
    ) -> None:
        """Emit call-level telemetry and Prometheus metrics (ACR Phase 1)."""
        if not self.telemetry and not _HAS_ACR_METRICS:
            return

        from reasoner.infrastructure.llm.registry import bloc_of, _vendor_of

        input_tokens = getattr(provider, "last_input_tokens", 0) or 0
        output_tokens = getattr(provider, "last_output_tokens", 0) or 0
        cost_usd = getattr(provider, "last_cost_usd", 0.0) or 0.0

        # Emit Prometheus metrics
        if _HAS_ACR_METRICS:
            LLM_CALL_DURATION.labels(
                model=provider.model, role=role, preset=self.preset_id,
            ).observe(latency_ms / 1000.0)
            if success:
                LLM_CALL_SUCCESS.labels(model=provider.model, role=role).inc()
            else:
                LLM_CALL_FAILURE.labels(
                    model=provider.model, role=role,
                    reason=fallback_reason or "error",
                ).inc()
            LLM_CALL_COST.labels(model=provider.model, role=role).inc(cost_usd)

        # Emit telemetry event
        if self.telemetry:
            vendor = _vendor_of(provider.model)
            bloc = bloc_of(provider.model)

            event = _build_telemetry_event(
                call_id=str(uuid.uuid4()),
                run_id=self.run_id,
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                model_id=provider.model,
                role=role,
                preset_id=self.preset_id,
                method=self.method,
                phase=0,
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                success=success,
                is_fallback=is_fallback,
                fallback_reason=fallback_reason,
                circuit_state=circuit_state,
                vendor=vendor,
                bloc=bloc,
            )
            try:
                await self.telemetry.record_call(event)
            except Exception:
                logger.debug("Failed to record telemetry event", exc_info=True)

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
        fallback: BaseLLMProvider | None = self._resolve_fallback(role, assigned)

        async def _execute_call(provider: BaseLLMProvider, is_fallback: bool = False):
            actual_provider = provider
            try:
                response = await self._attempt_call_and_record(
                    role, provider, system_prompt, user_prompt, max_tokens, temperature,
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
            # Whether the consumer has already received content from THIS
            # provider. Once it has, switching to a fallback would replay that
            # provider's full answer on top of the partial one, so the stream
            # can only be closed out with a degraded frame.
            delivered = False
            timed_out = False
            failure: Exception | None = None
            try:
                semaphore = _get_llm_semaphore(provider.model)
                async with semaphore:
                    async for chunk in provider.stream_complete_with_retry(
                        system_prompt, user_prompt, max_tokens, temperature
                    ):
                        delivered = True
                        yield chunk
                await circuit.record_success()
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError as exc:
                timed_out = True
                failure = exc
            except Exception as exc:
                # Deliberately broad. A provider is only *contractually* bound
                # to raise LLMError once its retry budget is exhausted;
                # stream_complete_with_retry re-raises the raw transport error
                # (httpx.ReadError, ConnectionError, ...) whenever it declines
                # to retry — after a partial yield, or for a non-retryable
                # failure. Catching LLMError alone let those escape the router
                # entirely: no circuit.record_failure(), so a flapping provider
                # never tripped the breaker; no fallback; and the consumer got
                # a raw exception instead of a DegradedLLMResponse frame.
                failure = exc
                if not isinstance(exc, LLMError):
                    logger.error(
                        "Role '%s' provider '%s' raised %s mid-stream",
                        role, provider.model, type(exc).__name__, exc_info=True,
                    )

            if failure is None:
                return

            await circuit.record_failure()

            if timed_out:
                reason = f"{provider.model} timed out"
                no_fallback_reason = f"{assigned.model} timed out — no fallback"
            else:
                reason = str(failure) or type(failure).__name__
                no_fallback_reason = reason

            if delivered:
                # Partial content is already in the consumer's hands.
                yield DegradedLLMResponse(
                    text="",
                    error=f"{reason} — stream truncated after partial output",
                    metadata={"model": provider.model, "partial": True},
                )
                return

            if is_fallback:
                # Timeouts skip the direct-provider chain here, as before: the
                # role has already spent two full timeout windows.
                if not timed_out:
                    direct = await _try_direct_fallback(
                        role, system_prompt, user_prompt, original_error=failure,
                        max_tokens=max_tokens, temperature=temperature, extra_body=extra_body,
                    )
                    if direct:
                        yield direct
                        return
                yield DegradedLLMResponse(
                    text="",
                    error=reason,
                    metadata={"model": provider.model},
                )
                return

            if fallback:
                async for chunk in _execute_stream(fallback, is_fallback=True):
                    yield chunk
            else:
                yield DegradedLLMResponse(
                    text="",
                    error=no_fallback_reason,
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
        fallback: BaseLLMProvider | None = self._resolve_fallback(role, assigned)

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
        telemetry: "CallTelemetryPort | None" = None,
        run_id: str = "",
        preset_id: str = "",
        method: str = "",
    ) -> "ProviderRouter":
        """Build router from model ID strings."""
        primary = build_provider(primary_id)
        table = {role: build_provider(mid) for role, mid in (routing or {}).items()}
        fallback_table = {role: build_provider(mid) for role, mid in (fallback_routing or {}).items()}
        router = cls(
            primary=primary, routing_table=table, fallback_table=fallback_table,
            cascading_routing=cascading_routing, verbose=verbose,
            telemetry=telemetry, run_id=run_id, preset_id=preset_id, method=method,
        )
        # Preserve the ID-level view for callers that rebuild this router.
        router.primary_id = primary_id
        router.routing_ids = dict(routing or {})
        router.fallback_routing_ids = dict(fallback_routing or {})
        router.cascading_routing_ids = dict(cascading_routing or {})
        return router


def _build_telemetry_event(
    call_id: str,
    run_id: str,
    timestamp: str,
    model_id: str,
    role: str,
    preset_id: str,
    method: str,
    phase: int,
    latency_ms: float,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    success: bool,
    is_fallback: bool = False,
    fallback_reason: str | None = None,
    circuit_state: str = "closed",
    vendor: str = "",
    bloc: str = "",
) -> "LLMCallTelemetry":
    """Build an LLMCallTelemetry event from raw fields.

    Defined at module level to avoid circular imports inside ProviderRouter.
    """
    # Lazy import to avoid circular dependency at module level
    from reasoner.domain.telemetry import LLMCallTelemetry

    return LLMCallTelemetry(
        call_id=call_id,
        run_id=run_id,
        timestamp=timestamp,
        model_id=model_id,
        role=role,
        preset_id=preset_id,
        method=method,
        phase=phase,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        success=success,
        is_fallback=is_fallback,
        fallback_reason=fallback_reason,
        circuit_state=circuit_state,
        vendor=vendor,
        bloc=bloc,
    )
