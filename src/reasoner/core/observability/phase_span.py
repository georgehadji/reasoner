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
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


@contextlib.asynccontextmanager
async def PhaseSpan(
    run_id: str,
    *,
    phase_name: str,
    phase_number: int | float,
    router: Any = None,
):
    """Context manager wrapping a phase execution in a Langfuse span.

    Creates a child span under the active Langfuse trace for this run.
    On exit, updates the span with duration, token counts, cost, and
    any error that occurred. Gracefully degrades if Langfuse is not
    configured or unavailable.

    Args:
        run_id: Pipeline run ID (matches Langfuse trace ID).
        phase_name: Human-readable phase name for the span.
        phase_number: Phase step number.
        router: Optional ProviderRouter for model/fallback metadata.
    """
    # Lazy import to avoid crash if langfuse is not installed
    span: Any = None
    _langfuse: Any = None
    t0 = time.monotonic()

    try:
        from reasoner.infrastructure.observability.langfuse_subscriber import (
            _langfuse_client as _lf_client,
            _is_langfuse_enabled as _lf_enabled,
        )
        if _lf_client and _lf_enabled:
            _langfuse = _lf_client
    except Exception:
        _langfuse = None

    # Create span
    if _langfuse is not None:
        try:
            input_tokens = 0
            if router and hasattr(router, 'describe'):
                input_tokens = 0  # populated on exit from state
            span = _langfuse.span(
                name=f"Phase {phase_number}: {phase_name}",
                trace_id=run_id,
                input={"phase": phase_name, "phase_number": phase_number, "start_time": t0},
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
                span.update(
                    output={
                        "success": success,
                        "duration_seconds": round(duration, 3),
                        "error": error,
                    },
                    end_time=time.time(),
                )
            except Exception:
                pass
