"""Direct answer streaming execution.

Imperative shell for the HyperGate DIRECT / WEB_SEARCH routes: turns a
prompt (built by ``reasoner.phases.direct``, pure) into an SSE stream by
calling the LLM through ``ProviderRouter`` — never a bare provider — so this
path gets the same circuit breaker, cost accounting, and prompt caching as
every other LLM call in the pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from reasoner.api.sse_utils import _event
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.phases.direct import (
    DIRECT_WEB_SEARCH_SYSTEM,
    DirectProfile,
    build_direct_prompt,
    select_direct_profile,
)

logger = logging.getLogger(__name__)


async def _call_with_model_fallback(
    router: ProviderRouter,
    models: tuple[str, ...],
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict[str, Any]]:
    """Try each preferred model in order, falling back to ``router``'s own routing.

    Every attempt goes through a ``ProviderRouter.call`` (never a bare
    provider) so circuit breaker, telemetry, and prompt-cache breakpoints
    apply uniformly regardless of which model answers.
    """
    from reasoner.infrastructure.llm.registry import build_provider

    last_error: Exception | None = None
    for model_id in models:
        try:
            temp_router = ProviderRouter(primary=build_provider(model_id), verbose=False)
            response, meta = await temp_router.call(
                role="primary",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if isinstance(response, str) and response.strip():
                return response, meta
            last_error = RuntimeError(f"empty response from {model_id}")
        except Exception as exc:
            last_error = exc
            logger.warning("Direct answer: model %s failed, trying next: %s", model_id, exc)

    if models:
        logger.warning("Direct answer: all preferred models failed (%s), using router primary", last_error)

    response, meta = await router.call(
        role="primary",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if not isinstance(response, str):
        # DegradedLLMResponse — every provider in the chain failed.
        raise RuntimeError(getattr(response, "error", "all providers failed") or "all providers failed")
    return response, meta


async def _stream_direct_answer(
    router: ProviderRouter,
    problem: str,
    run_id: str,
    cancel_event: asyncio.Event | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    previous_synthesis: str = "",
    turn_number: int = 1,
    preset_name: str = "",
    web_search: bool = False,
) -> AsyncGenerator[str, None]:
    """Stream a direct LLM answer as a virtual single-phase pipeline for UI compatibility."""
    yield _event({"type": "start"})

    if cancel_event and cancel_event.is_set():
        yield _event({"type": "cancelled", "message": "Pipeline stopped by user"})
        return

    yield _event({"type": "phase_start", "phase": 0, "name": "Direct Response"})
    phase_start = time.monotonic()

    user_prompt = build_direct_prompt(problem, conversation_history, previous_synthesis, turn_number)

    if web_search:
        profile = DirectProfile(
            system_prompt=DIRECT_WEB_SEARCH_SYSTEM,
            max_tokens=2048,
            temperature=0.7,
            models=(),  # resolved via PERPLEXITY_SEARCH_TIER below, not the generic fallback chain
        )
    else:
        profile = select_direct_profile(problem, preset_name)

    try:
        if web_search:
            from reasoner.core.settings import settings
            response, meta = await _call_with_model_fallback(
                router, (settings.PERPLEXITY_SEARCH_TIER,),
                profile.system_prompt, user_prompt, profile.max_tokens, profile.temperature,
            )
        else:
            response, meta = await _call_with_model_fallback(
                router, profile.models,
                profile.system_prompt, user_prompt, profile.max_tokens, profile.temperature,
            )
    except Exception as exc:
        logger.error("Direct answer failed: %s", exc)
        err_msg = f"{type(exc).__name__}: {str(exc)[:120]}"
        yield _event({"type": "phase_error", "phase": 0, "error": err_msg})
        yield _event({
            "type": "done",
            "errors": [err_msg],
            "total_tokens": {"input": 0, "output": 0, "total": 0},
            "duration": time.monotonic() - phase_start,
        })
        return

    duration = time.monotonic() - phase_start
    input_tokens = meta.get("input_tokens", 0)
    output_tokens = meta.get("output_tokens", 0)

    yield _event({
        "type": "phase_complete",
        "phase": 0,
        "name": "Direct Response",
        "data": {
            "solution": response,
            "tokens": {"input": input_tokens, "output": output_tokens},
            "duration": duration,
        },
    })
    yield _event({
        "type": "done",
        "errors": [],
        "total_tokens": {
            "input": input_tokens,
            "output": output_tokens,
            "total": input_tokens + output_tokens,
        },
        "duration": duration,
    })
