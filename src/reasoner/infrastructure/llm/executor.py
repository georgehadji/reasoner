"""
LLM Executor — infrastructure concern extracted from ReasonerPipeline.

Responsible for:
  - Temperature resolution from phase_configs
  - Token-aware cache lookup and storage
  - Router delegation (ProviderRouter.call)
  - Cost and token accumulation into PipelineState
  - Prompt compression for code-heavy contexts
  - Quality-gated cascading with fail-fast heuristics
"""

from __future__ import annotations

import asyncio
import logging
import re
import time # Ensure time is imported once
from typing import Any, AsyncIterator, ClassVar # Add ClassVar for _LANG_TO_EXT

from reasoner.core.constants import (
    DEFAULT_MAX_TOKENS,
    PHASE_TOKEN_BUDGETS,
    TRUNCATION,
)
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.domain.pipeline_state import PipelineState

# New imports for event emission
from reasoner.core.events.domain_events import LLMGenerationCompleted, PipelineEventType, make_event
from reasoner.core.events.ports import EventPublisher
# get_event_bus imported lazily inside methods to avoid circular import with api/__init__.py

logger = logging.getLogger(__name__)


def _get_event_bus() -> EventPublisher:
    """Lazy import to avoid circular dependency with api/__init__.py."""
    from reasoner.application.event_bus.bus import get_event_bus
    return get_event_bus()

# Regex for fenced code blocks inside prompts
_CODE_FENCE_RE = re.compile(r"```(\w+)?\n(.*?)\n```", re.DOTALL)


class LLMExecutor:
    """
    Stateless (per-call) infrastructure adapter that wraps ProviderRouter with
    token-aware caching and cost tracking.

    Extracted from ReasonerPipeline._call_llm_cached to isolate LLM execution
    concerns from phase-sequencing concerns.
    """

    def __init__(
        self,
        router: ProviderRouter,
        phase_configs: dict,
        token_cache: Any | None,
        caching_enabled: bool,
        cascading_routing: dict[str, list[str]] | None = None,
        cascading_quality_check: bool = True,
        prompt_compression: bool = False,
        event_publisher: EventPublisher | None = None,
    ) -> None:
        self.router = router
        self.phase_configs = phase_configs
        self._token_cache = token_cache
        self._caching_enabled = caching_enabled
        self.cascading_routing = cascading_routing or {}
        self.cascading_quality_check = cascading_quality_check
        self.prompt_compression = prompt_compression
        self._event_publisher = event_publisher
        self._token_lock = asyncio.Lock()  # C1: guard parallel token accumulation

    async def execute(
        self,
        role: str,
        system_prompt: str,
        user_prompt: str,
        state: PipelineState,
        phase_key: str | None = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> tuple[str, dict[str, Any]] | AsyncIterator[str | DegradedLLMResponse]:
        """
        Call the LLM with token-aware caching and cost tracking.

        - Resolves temperature from phase_configs unless already provided.
        - Checks cache before hitting the router (cache hit = 0 cost).
        - Accumulates token usage and cost into state after every call.
        - Stores the response in cache on a miss.
        """
        # ── Temperature resolution (with retry-aware strategy) ──────────
        if "temperature" not in kwargs:
            lookup = phase_key or role
            cfg = None
            if lookup in self.phase_configs:
                cfg = self.phase_configs[lookup]
            else:
                for c in self.phase_configs.values():
                    if c.role == role:
                        cfg = c
                        break

            if cfg:
                base_temp = cfg.temperature
                strategy = getattr(cfg, "temperature_strategy", None)
                attempt = kwargs.get("_retry_attempt", 0)

                if strategy and strategy.value != "fixed":
                    from reasoner.core.protocol import TemperatureStrategy
                    if strategy == TemperatureStrategy.ESCALATE:
                        kwargs["temperature"] = min(base_temp + 0.1 * attempt, 1.0)
                    elif strategy == TemperatureStrategy.DEESCALATE:
                        kwargs["temperature"] = max(base_temp - 0.05 * attempt, 0.0)
                    elif strategy == TemperatureStrategy.SWEEP:
                        sweep_values = [0.1, 0.5, 0.9]
                        kwargs["temperature"] = sweep_values[min(attempt, len(sweep_values) - 1)]
                    else:
                        kwargs["temperature"] = base_temp
                else:
                    kwargs["temperature"] = base_temp

        # ── Cache lookup ──────────────────────────────────────────────────
        # Caching for streaming is complex. For now, disable caching for streaming calls.
        # A robust streaming cache would need to store/retrieve partial streams.
        if stream and self._caching_enabled:
            logger.warning("Caching is currently not supported for streaming LLM calls.")

        if self._token_cache and self._caching_enabled and not stream:
            # For caching, we need a specific model_id. If cascading, we'll cache against the first model.
            # This is a simplification; a more robust cache would handle model cascades explicitly.
            model_id_for_cache = self.cascading_routing.get(role, [self.router.get(role).model])[0]
            cache_prompt = (
                user_prompt
                if role in (
                    "synthesis", "context_vetting", "primary",
                    # Coding roles: each file has a unique prompt body after the
                    # shared problem prefix, so truncating to PROBLEM chars would
                    # produce identical cache keys for all parallel generate calls
                    # and serve the first file's response for every subsequent file.
                    "coding_generate", "coding_spec", "coding_review",
                    "coding_tests", "coding_assemble",
                )
                else user_prompt[: TRUNCATION.PROBLEM]
            )
            cached_response = await self._token_cache.get(
                problem=state.problem,
                phase=role,
                model_id=model_id_for_cache,
                prompt=cache_prompt,
            )
            if cached_response:
                logger.info(f"[CACHE] HIT for {role} (saved ~{len(cached_response)//4} tokens)")
                estimated_input = len(user_prompt) // 4
                estimated_output = len(cached_response) // 4
                await self._accumulate_tokens(state, role, estimated_input, estimated_output, model_id_for_cache)
                token_meta = {
                    "input": estimated_input,
                    "output": estimated_output,
                    "total": estimated_input + estimated_output,
                }
                # Emit Prometheus cache metrics
                try:
                    from reasoner.metrics import CACHE_HITS, TOKEN_SAVINGS_USD
                    CACHE_HITS.labels(phase=role, model=model_id_for_cache).inc()
                    TOKEN_SAVINGS_USD.inc(estimated_output * 0.000001)
                except Exception:
                    pass  # Metrics are best-effort
                
                # Emit LLMGenerationCompleted event for cache hit
                bus = self._event_publisher or _get_event_bus()
                event = make_event(
                    PipelineEventType.LLM_GENERATION_COMPLETED,
                    aggregate_id=state.conversation_id or "unknown",
                    version=1,
                    model_name=model_id_for_cache,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    raw_response=cached_response,
                    prompt_tokens=estimated_input,
                    completion_tokens=estimated_output,
                    total_tokens=estimated_input + estimated_output,
                    cost=0.0, # Cache hit has no cost
                    duration_seconds=0.0, # Instantaneous for cache
                    pipeline_id=state.conversation_id or "unknown",
                    phase_name=phase_key or role,
                    metadata={"cached": True}
                )
                await bus.publish(event)

                return cached_response, {**token_meta, "cost_usd": 0.0, "model": model_id_for_cache, "cached": True}
            else:
                # Emit cache miss metric
                try:
                    from reasoner.metrics import CACHE_MISSES
                    CACHE_MISSES.labels(phase=role, model=model_id_for_cache).inc()
                except Exception:
                    pass

        # ── Prompt compression (code blocks) ──────────────────────────────
        if self.prompt_compression:
            user_prompt = self._compress_prompt_code_blocks(user_prompt, role)

        # ── LLM call (with cascading logic if configured) ──────────────────────
        # Defensive: ensure max_tokens is always set before reaching the provider.
        if "max_tokens" not in kwargs:
            kwargs["max_tokens"] = PHASE_TOKEN_BUDGETS.get(role, DEFAULT_MAX_TOKENS)
            logger.debug(f"[EXECUTOR] defaulted max_tokens={kwargs['max_tokens']} for role={role}")

        cascading_models = self.cascading_routing.get(role)
        
        llm_call_start_time = time.monotonic() # Capture start time for LLM call

        if cascading_models:
            last_error: Exception | None = None
            for model_id in cascading_models:
                try:
                    logger.info(f"[CASCADING] Trying model '{model_id}' for role '{role}'...")
                    from reasoner.infrastructure.llm.registry import build_provider
                    temp_router = ProviderRouter(primary=build_provider(model_id), verbose=False)

                    raw, metadata = await temp_router.call(
                        role="primary",
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        **kwargs,
                    )
                    llm_call_end_time = time.monotonic() # Capture end time for LLM call
                    duration_seconds = llm_call_end_time - llm_call_start_time

                    from reasoner.infrastructure.llm.ports import DegradedLLMResponse
                    if isinstance(raw, DegradedLLMResponse):
                        raise RuntimeError(f"Degraded response from {model_id}: {raw.error}")

                    if not raw or not raw.strip():
                        raise RuntimeError(f"Empty response from {model_id} for role={role}")

                    if role in ("fusion", "classification", "decomposition", "scoring", "meta_evaluator"):
                        try:
                            import json
                            json.loads(raw)
                        except json.JSONDecodeError:
                            raise RuntimeError(f"Malformed JSON from {model_id} for role={role}")

                    # ── Quality gate (fail-fast heuristics) ─────────────────────
                    if self.cascading_quality_check:
                        from reasoner.quality.quick_check import QuickQualityCheck
                        ok, reason = QuickQualityCheck.check_all(role, raw)
                        if not ok:
                            logger.warning(
                                f"[CASCADING] Model '{model_id}' response failed quick quality check: {reason}"
                            )
                            raise RuntimeError(f"Quality check failed: {reason}")

                    logger.info(f"[CASCADING] Model '{model_id}' succeeded for role '{role}'.")
                    if self._token_cache and self._caching_enabled:
                        await self._token_cache.set(
                            problem=state.problem,
                            phase=role,
                            model_id=model_id,
                            prompt=cache_prompt,
                            response=raw,
                            tokens_used=metadata.get("input_tokens", 0) + metadata.get("output_tokens", 0),
                        )
                    await self._accumulate_tokens(state, role, metadata.get("input_tokens", 0), metadata.get("output_tokens", 0), model_id)

                    # Emit LLMGenerationCompleted event for successful cascading call
                    bus = self._event_publisher or _get_event_bus()
                    event = make_event(
                        PipelineEventType.LLM_GENERATION_COMPLETED,
                        aggregate_id=state.conversation_id or "unknown",
                        version=1,
                        model_name=model_id,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        raw_response=raw,
                        prompt_tokens=metadata.get("input_tokens", 0),
                        completion_tokens=metadata.get("output_tokens", 0),
                        total_tokens=metadata.get("input_tokens", 0) + metadata.get("output_tokens", 0),
                        cost=metadata.get("cost_usd", 0.0),
                        duration_seconds=duration_seconds,
                        pipeline_id=state.conversation_id or "unknown",
                        phase_name=phase_key or role,
                        metadata={"cached": False, "cascading": True}
                    )
                    await bus.publish(event)

                    return raw, metadata

                except Exception as exc:
                    last_error = exc
                    logger.warning(f"[CASCADING] Model '{model_id}' failed for role '{role}': {exc}")
            
            if last_error:
                logger.error(f"All cascading models failed for role={role}: {last_error}")
                # Emit LLMGenerationCompleted event for failed cascading
                bus = self._event_publisher or _get_event_bus()
                event = make_event(
                    PipelineEventType.LLM_GENERATION_COMPLETED,
                    aggregate_id=state.conversation_id or "unknown",
                    version=1,
                    model_name="unknown", # Model failed, so unknown
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    raw_response="",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    cost=0.0,
                    duration_seconds=time.monotonic() - llm_call_start_time,
                    pipeline_id=state.conversation_id or "unknown",
                    phase_name=phase_key or role,
                    metadata={"cached": False, "cascading": True, "failed": True, "error": str(last_error)}
                )
                await bus.publish(event)

                return DegradedLLMResponse(
                    text="",
                    error=f"All cascading models failed for role={role}: {last_error}",
                    metadata={},
                ), {}
            else:
                logger.error(f"Unknown error in cascading for role={role}")
                # Emit LLMGenerationCompleted event for unknown cascading error
                bus = self._event_publisher or _get_event_bus()
                event = make_event(
                    PipelineEventType.LLM_GENERATION_COMPLETED,
                    aggregate_id=state.conversation_id or "unknown",
                    version=1,
                    model_name="unknown", 
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    raw_response="",
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    cost=0.0,
                    duration_seconds=time.monotonic() - llm_call_start_time,
                    pipeline_id=state.conversation_id or "unknown",
                    phase_name=phase_key or role,
                    metadata={"cached": False, "cascading": True, "failed": True, "error": f"Unknown error in cascading for role={role}"}
                )
                await bus.publish(event)

                return DegradedLLMResponse(
                    text="",
                    error=f"Unknown error in cascading for role={role}",
                    metadata={},
                ), {}

        else: # No cascading routing, use standard routing
            logger.info(f"[CACHE] MISS for {role}")
            raw, metadata = await self.router.call(
                role=role,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                **kwargs,
            )
            llm_call_end_time = time.monotonic() # Capture end time for LLM call
            duration_seconds = llm_call_end_time - llm_call_start_time

            from reasoner.infrastructure.llm.ports import DegradedLLMResponse
            if isinstance(raw, DegradedLLMResponse):
                logger.error(f"LLM degraded for role={role}: {raw.error}")
                # Emit LLMGenerationCompleted event for degraded response
                bus = self._event_publisher or _get_event_bus()
                event = make_event(
                    PipelineEventType.LLM_GENERATION_COMPLETED,
                    aggregate_id=state.conversation_id or "unknown",
                    version=1,
                    model_name=metadata.get("model", "unknown"), 
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    raw_response=raw.error, # Store error message
                    prompt_tokens=metadata.get("input_tokens", 0),
                    completion_tokens=metadata.get("output_tokens", 0),
                    total_tokens=metadata.get("input_tokens", 0) + metadata.get("output_tokens", 0),
                    cost=metadata.get("cost_usd", 0.0),
                    duration_seconds=duration_seconds,
                    pipeline_id=state.conversation_id or "unknown",
                    phase_name=phase_key or role,
                    metadata={"cached": False, "degraded": True, "error": raw.error}
                )
                await bus.publish(event)

                raise RuntimeError(raw.error)

            if not raw or not raw.strip():
                logger.warning(f"LLM returned empty response for role={role}; possible content filter or API error")
                # Emit LLMGenerationCompleted event for empty response
                bus = self._event_publisher or _get_event_bus()
                event = make_event(
                    PipelineEventType.LLM_GENERATION_COMPLETED,
                    aggregate_id=state.conversation_id or "unknown",
                    version=1,
                    model_name=metadata.get("model", "unknown"), 
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    raw_response=raw,
                    prompt_tokens=metadata.get("input_tokens", 0),
                    completion_tokens=metadata.get("output_tokens", 0),
                    total_tokens=metadata.get("input_tokens", 0) + metadata.get("output_tokens", 0),
                    cost=metadata.get("cost_usd", 0.0),
                    duration_seconds=duration_seconds,
                    pipeline_id=state.conversation_id or "unknown",
                    phase_name=phase_key or role,
                    metadata={"cached": False, "empty_response": True}
                )
                await bus.publish(event)


            cost_usd = metadata.get("cost_usd", 0.0)
            input_tokens = metadata.get("input_tokens", 0)
            output_tokens = metadata.get("output_tokens", 0)
            model = metadata.get("model", "unknown")

            if cost_usd > 0:
                state.total_cost_usd += cost_usd
                state.phase_costs[role] = cost_usd

            await self._accumulate_tokens(state, role, input_tokens, output_tokens, model)

            if self._token_cache and self._caching_enabled:
                model_id = self.router.get(role).model if hasattr(self.router, "get") else "unknown"
                cache_prompt = (
                    user_prompt
                    if role in ("synthesis", "context_vetting", "primary")
                    else user_prompt[: TRUNCATION.PROBLEM]
                )
                await self._token_cache.set(
                    problem=state.problem,
                    phase=role,
                    model_id=model_id,
                    prompt=cache_prompt,
                    response=raw,
                    tokens_used=input_tokens + output_tokens,
                )
            
            # Emit LLMGenerationCompleted event for successful standard call
            bus = self._event_publisher or _get_event_bus()
            event = make_event(
                PipelineEventType.LLM_GENERATION_COMPLETED,
                aggregate_id=state.conversation_id or "unknown",
                version=1,
                model_name=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                raw_response=raw,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                cost=cost_usd,
                duration_seconds=duration_seconds,
                pipeline_id=state.conversation_id or "unknown",
                phase_name=phase_key or role,
                metadata={"cached": False, "cascading": False}
            )
            await bus.publish(event)

            return raw, metadata

    async def execute_stream(
        self,
        role: str,
        system_prompt: str,
        user_prompt: str,
        state: PipelineState,
        phase_key: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str | DegradedLLMResponse]:
        """Streaming variant of execute. Yields chunks as they arrive.

        NOTE: Caching, token accumulation, and cascading are not yet fully
        implemented for streaming.
        """
        if "max_tokens" not in kwargs:
            kwargs["max_tokens"] = PHASE_TOKEN_BUDGETS.get(role, DEFAULT_MAX_TOKENS)

        if self._caching_enabled:
            logger.warning("Caching is currently not supported for streaming LLM calls.")

        cascading_models = self.cascading_routing.get(role)
        if cascading_models:
            last_error: Exception | None = None
            for model_id in cascading_models:
                try:
                    from reasoner.infrastructure.llm.registry import build_provider
                    temp_router = ProviderRouter(primary=build_provider(model_id), verbose=False)
                    full_response_content = []
                    async for chunk_or_degraded in temp_router.call(
                        role="primary",
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        stream=True,
                        **kwargs,
                    ):
                        if isinstance(chunk_or_degraded, DegradedLLMResponse):
                            raise RuntimeError(f"Degraded streaming response from {model_id}: {chunk_or_degraded.error}")
                        full_response_content.append(chunk_or_degraded)
                        yield chunk_or_degraded

                    final_response_str = "".join(full_response_content)
                    if not final_response_str or not final_response_str.strip():
                        raise RuntimeError(f"Empty streaming response from {model_id} for role={role}")
                    return
                except Exception as exc:
                    last_error = exc
                    logger.warning(f"[CASCADING STREAM] Model '{model_id}' failed for role '{role}': {exc}")
            if last_error:
                yield DegradedLLMResponse(
                    text="",
                    error=f"All cascading streaming models failed for role={role}: {last_error}",
                    metadata={},
                )
            else:
                yield DegradedLLMResponse(
                    text="",
                    error=f"Unknown error in streaming cascading for role={role}",
                    metadata={},
                )
            return

        async for chunk_or_degraded in self.router.call(
            role=role,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            stream=True,
            **kwargs,
        ):
            if isinstance(chunk_or_degraded, DegradedLLMResponse):
                yield chunk_or_degraded
                return
            yield chunk_or_degraded

    async def _accumulate_tokens(
        self,
        state: PipelineState,
        role: str,
        input_tokens: int,
        output_tokens: int,
        model: str,
    ) -> None:
        """Update all token and model tracking fields on state. Thread-safe (C1)."""
        async with self._token_lock:
            state.phase_models[role] = model

            prior = state.detailed_token_usage.get(role, {"input": 0, "output": 0, "total": 0})
            state.detailed_token_usage[role] = {
                "input": prior["input"] + input_tokens,
                "output": prior["output"] + output_tokens,
                "total": prior["total"] + input_tokens + output_tokens,
            }

            tracking_key = getattr(state, "_current_phase_key", None)
            if tracking_key:
                if tracking_key not in state.phase_tokens:
                    state.phase_tokens[tracking_key] = {"input": 0, "output": 0}
                state.phase_tokens[tracking_key]["input"] += input_tokens
                state.phase_tokens[tracking_key]["output"] += output_tokens

                if tracking_key not in state.cost_state._phase_models_by_key:
                    state.cost_state._phase_models_by_key[tracking_key] = []
                if model not in state.cost_state._phase_models_by_key[tracking_key]:
                    state.cost_state._phase_models_by_key[tracking_key].append(model)

    # Map common markdown language tags to file extensions
    _LANG_TO_EXT: ClassVar[dict[str, str]] = {
        "python": "py",
        "javascript": "js",
        "typescript": "ts",
        "rust": "rs",
        "go": "go",
        "shell": "sh",
        "bash": "sh",
        "java": "java",
        "c": "c",
        "cpp": "cpp",
        "csharp": "cs",
        "ruby": "rb",
        "php": "php",
        "swift": "swift",
        "kotlin": "kt",
        "scala": "scala",
        "r": "r",
        "sql": "sql",
        "html": "html",
        "css": "css",
        "json": "json",
        "yaml": "yaml",
        "xml": "xml",
    }

    @classmethod
    def _compress_prompt_code_blocks(cls, prompt: str, role: str) -> str:
        """Compress fenced code blocks inside a prompt to save tokens.

        Only compresses for roles that typically carry large code context.
        Uses the existing ContextCompressor from reasoner.neuro.compression.
        """
        # Skip compression for roles that don't typically have code
        code_heavy_roles = {
            "coding_spec", "coding_generate", "coding_review",
            "coding_tests", "coding_assemble", "primary",
            "context_vetting", "deep_read",
        }
        if role not in code_heavy_roles:
            return prompt

        from reasoner.neuro.compression import smart_compress

        def _replace_block(match: re.Match) -> str:
            lang = match.group(1) or ""
            code = match.group(2)
            # Normalize markdown language tag to file extension
            ext = cls._LANG_TO_EXT.get(lang.lower(), lang)
            # Use minimal compression (remove comments/blank lines)
            compressed = smart_compress(code, ext=ext, level="minimal")
            return f"```{lang}\n{compressed}\n```"

        return _CODE_FENCE_RE.sub(_replace_block, prompt)
