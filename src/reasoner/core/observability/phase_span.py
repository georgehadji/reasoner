"""
Observability span utilities — wraps pipeline phase execution with Langfuse spans.

Usage in the SSE pipeline runner (api/execution/pipeline.py)::

    from reasoner.core.observability.phase_span import PhaseSpan

    async with PhaseSpan(run_id, phase_name=name, phase_number=num, router=router):
        result = await run_phase_with_keepalive(fn, state, ...)

This creates a Langfuse span inside the active trace, automatically
records duration, tokens, cost, model, and handles error capture.
"""

from __future__ import annotations

import contextlib
import importlib
import logging
import time
from typing import Any

from reasoner.core.degrade import degraded

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def PhaseSpan(
    run_id: str,
    *,
    phase_name: str,
    phase_number: int | float,
    router: Any = None,
    state: Any = None,
):
    """Context manager wrapping a phase execution in a Langfuse span.

    Creates a child span under the active Langfuse trace for this run.
    On exit, updates the span with duration, token counts, cost,
    model information, and any error.

    Gracefully degrades if Langfuse is not configured or unavailable.

    Args:
        run_id: Pipeline run ID (matches Langfuse trace ID).
        phase_name: Human-readable phase name for the span.
        phase_number: Phase step number.
        router: Optional ProviderRouter for model/fallback metadata.
        state: Optional PipelineState for token/cost enrichment on exit.
    """
    span: Any = None
    _langfuse: Any = None
    t0 = time.monotonic()
    # t0 is monotonic, which is right for duration and meaningless as a
    # timestamp: it counts from an arbitrary origin. It was going into the
    # span's own input next to a wall-clock end_time, so every Langfuse span
    # recorded a start seconds-since-boot and an end in epoch seconds.
    t0_wall = time.time()

    try:
        langfuse_subscriber = importlib.import_module(
            "reasoner.infrastructure.observability.langfuse_subscriber"
        )
        _lf_client = getattr(langfuse_subscriber, "_langfuse_client", None)
        _lf_enabled = getattr(langfuse_subscriber, "_is_langfuse_enabled", False)
        if _lf_client and _lf_enabled:
            _langfuse = _lf_client
    except Exception:
        _langfuse = None

    # Capture model info from router on entry
    model_hint = ""
    if router and hasattr(router, 'describe'):
        try:
            model_hint = router.describe()[:100]
        except Exception as exc:
            # An empty model_hint is not "no model" -- it is written into both
            # the span input and the span output, where it is indistinguishable
            # from a phase that genuinely ran without one.
            degraded(
                "observability.phase_span.router_describe",
                None,
                exc=exc,
                state=state,
            )

    # Create span
    if _langfuse is not None:
        try:
            span = _langfuse.span(
                name=f"Phase {phase_number}: {phase_name}",
                trace_id=run_id,
                input={
                    "phase": phase_name,
                    "phase_number": phase_number,
                    "start_time": t0_wall,
                    "model": model_hint,
                },
            )
        except Exception:
            span = None

    try:
        yield
        success = True
        error = None
    except Exception as exc:
        success = False
        error = str(exc)[:200]
        raise
    finally:
        duration = time.monotonic() - t0

        if span is not None and _langfuse is not None:
            try:
                # Enrich with token/cost data from state if available
                phase_key = f"Phase {phase_number}: {phase_name}"
                output: dict[str, Any] = {
                    "success": success,
                    "duration_seconds": round(duration, 3),
                    "error": error,
                    "model": model_hint,
                }

                # Extract token counts from state
                if state is not None:
                    try:
                        tokens = state.phase_tokens.get(phase_key, {}) if hasattr(state, 'phase_tokens') else {}
                        if tokens:
                            output["tokens_in"] = tokens.get("input", 0)
                            output["tokens_out"] = tokens.get("output", 0)
                            output["tokens_total"] = tokens.get("input", 0) + tokens.get("output", 0)
                    except Exception as exc:
                        # A span with no token counts looks like a phase that
                        # made no LLM calls.
                        degraded(
                            "observability.phase_span.tokens",
                            None,
                            exc=exc,
                            state=state,
                        )

                    # Extract cost from state
                    try:
                        if hasattr(state, 'cost_state') and state.cost_state is not None:
                            costs = state.cost_state.phase_costs_by_key if hasattr(state.cost_state, 'phase_costs_by_key') else {}
                            phase_cost = costs.get(phase_key, 0.0) if costs else 0.0
                            if phase_cost:
                                output["cost_usd"] = round(phase_cost, 6)
                    except Exception as exc:
                        # An omitted cost_usd is not zero cost, but every
                        # dashboard summing this field will read it as zero.
                        degraded(
                            "observability.phase_span.cost",
                            None,
                            exc=exc,
                            state=state,
                        )

                    # Extract fallback info from state
                    try:
                        if hasattr(state, 'meta') and state.meta is not None:
                            fallbacks = getattr(state.meta, 'fallback_events', [])
                            if fallbacks:
                                output["fallback_count"] = len(fallbacks)
                    except Exception as exc:
                        # Absent fallback_count reads as "no provider fell
                        # back", which is the opposite of what may have happened.
                        degraded(
                            "observability.phase_span.fallbacks",
                            None,
                            exc=exc,
                            state=state,
                        )

                span.update(output=output, end_time=time.time())
            except Exception as exc:
                # The span was opened and is now never closed: it stays in
                # Langfuse with no duration, no cost and no error, which reads
                # as a phase still running rather than one whose record failed.
                degraded(
                    "observability.phase_span.span_update",
                    None,
                    exc=exc,
                    state=state,
                )
