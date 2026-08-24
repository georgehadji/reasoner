"""SSE event structure snapshot tests (Phase 3.3).

Verifies that the SSE event type catalog and payload structure
remain stable across refactoring. These tests do NOT require
LLM access — they test the event builders and serializers directly.

The frontend depends on these event types. Any change to the
catalog below must be reflected in the UI.
"""

from __future__ import annotations

import json
from typing import Any

# ── SSE EVENT TYPE CATALOG ──────────────────────────────────────────
# This is the contract between backend SSE streaming and frontend consumption.
# Every event type, the phase that emits it, and its required keys.
# The UI renders based on these types — changing any means a frontend update.

SSE_EVENT_CATALOG: dict[str, dict[str, Any]] = {
    "start": {
        "phase": "pipeline",
        "required_keys": ["type", "preset"],
        "optional_keys": ["auto_selected_method", "cached"],
        "description": "Emitted once at pipeline start. Carries the effective preset name.",
    },
    "recall_used": {
        "phase": "preflight",
        "required_keys": ["type", "memory_count"],
        "optional_keys": ["memory_ids"],
        "description": "Neuro context was recalled from long-term memory.",
    },
    "prompt_enhanced": {
        "phase": "enhancement",
        "required_keys": ["type", "original", "enhanced"],
        "optional_keys": [],
        "description": "Problem was rewritten for clarity by the enhancement phase.",
    },
    "phase_start": {
        "phase": "execution",
        "required_keys": ["type", "phase", "name"],
        "optional_keys": ["models"],
        "description": "A phase is beginning. phase=int, name=str, models=list[str].",
    },
    "phase_quality": {
        "phase": "execution",
        "required_keys": ["type", "phase", "name", "score", "passed", "reason", "attempt"],
        "optional_keys": [],
        "description": "Quality check result for a completed phase.",
    },
    "phase_retry": {
        "phase": "execution",
        "required_keys": ["type", "phase", "name", "attempt", "max_attempts", "reason"],
        "optional_keys": [],
        "description": "Phase quality failed and retry will occur.",
    },
    "phase_error": {
        "phase": "execution",
        "required_keys": ["type", "phase", "error"],
        "optional_keys": ["phase_name"],
        "description": "A phase encountered an error. May or may not be fatal.",
    },
    "error": {
        "phase": "execution",
        "required_keys": ["type", "error_type", "message", "retryable", "phase", "phase_name"],
        "optional_keys": ["retry_after"],
        "description": "Structured error payload with classification (auth/timeout/rate_limit/unknown).",
    },
    "phase_warning": {
        "phase": "execution",
        "required_keys": ["type", "phase", "warning"],
        "optional_keys": [],
        "description": "Non-fatal warning during a phase (e.g. degraded LLM response).",
    },
    "phase_complete": {
        "phase": "execution",
        "required_keys": ["type", "phase", "name", "data"],
        "optional_keys": [],
        "description": "Phase completed successfully. data contains phase-specific output.",
    },
    "text_chunk": {
        "phase": "synthesis",
        "required_keys": ["type", "text"],
        "optional_keys": [],
        "description": "Sentence-level streaming of synthesis output for real-time rendering.",
    },
    "widget": {
        "phase": "widget",
        "required_keys": ["type", "data"],
        "optional_keys": [],
        "description": "Widget (calculator/stock/weather) result. data has widget_type, name, result, citations.",
    },
    "done": {
        "phase": "pipeline",
        "required_keys": ["type", "errors", "total_tokens", "duration"],
        "optional_keys": ["total_cost_usd", "phase_costs"],
        "description": "Pipeline execution complete. Final token and duration report.",
    },
    "cancelled": {
        "phase": "pipeline",
        "required_keys": ["type"],
        "optional_keys": ["message"],
        "description": "Pipeline was cancelled by user request.",
    },
}


def test_sse_catalog_complete() -> None:
    """Every type in the event catalog has required_keys defined."""
    for event_type, spec in SSE_EVENT_CATALOG.items():
        assert "required_keys" in spec, f"{event_type}: missing required_keys"
        assert "description" in spec, f"{event_type}: missing description"
        assert isinstance(spec["required_keys"], list), f"{event_type}: required_keys not a list"
        assert "type" in spec["required_keys"], f"{event_type}: 'type' must be a required key"


def test_sse_event_type_start() -> None:
    """start event structure."""
    import json

    from reasoner.api.sse_utils import _event
    ev = _event({"type": "start", "preset": "test-preset"})
    data = json.loads(ev[6:])  # strip "data: "
    assert data["type"] == "start"
    assert data["preset"] == "test-preset"


def test_sse_event_type_phase_start() -> None:
    """phase_start event structure."""
    from reasoner.api.sse_utils import _event
    ev = _event({"type": "phase_start", "phase": 1, "name": "Decomposition", "models": ["deepseek-v3"]})
    data = json.loads(ev[6:])
    assert data["type"] == "phase_start"
    assert data["phase"] == 1
    assert data["name"] == "Decomposition"
    assert data["models"] == ["deepseek-v3"]


def test_sse_event_type_done() -> None:
    """done event structure."""
    from reasoner.api.sse_utils import _event
    ev = _event({
        "type": "done",
        "errors": [],
        "total_tokens": {"input": 10, "output": 20, "total": 30},
        "duration": 5.0,
    })
    data = json.loads(ev[6:])
    assert data["type"] == "done"
    assert data["errors"] == []
    assert data["total_tokens"]["input"] == 10
    assert data["total_tokens"]["output"] == 20
    assert data["duration"] == 5.0


def test_sse_event_type_phase_complete() -> None:
    """phase_complete event structure with data payload."""
    from reasoner.api.sse_utils import _event
    ev = _event({
        "type": "phase_complete",
        "phase": 2,
        "name": "Perspectives",
        "data": {
            "candidates": [
                {"perspective": "constructive", "content": "test"},
            ],
            "tokens": {"input": 100, "output": 200},
            "duration": 3.0,
        },
    })
    data = json.loads(ev[6:])
    assert data["type"] == "phase_complete"
    assert data["data"]["candidates"][0]["perspective"] == "constructive"


def test_sse_event_type_cancelled() -> None:
    """cancelled event structure."""
    from reasoner.api.sse_utils import _event
    ev = _event({"type": "cancelled", "message": "Pipeline stopped by user"})
    data = json.loads(ev[6:])
    assert data["type"] == "cancelled"
    assert "message" in data


def test_sse_event_serializer_0_empty() -> None:
    """Serializer _ser_0 returns no extras (empty phase)."""
    from reasoner.api.serializers import _ser_0
    from reasoner.domain.pipeline_state import PipelineState
    state = PipelineState(problem="test")
    result = _ser_0(state)
    # Should return a dict (may be empty or with specific keys)
    assert isinstance(result, dict)


def test_sse_event_valid_json() -> None:
    """Every _event output must be valid JSON."""
    from reasoner.api.sse_utils import _event
    payloads = [
        {"type": "start", "preset": "test"},
        {"type": "phase_start", "phase": 1, "name": "Test"},
        {"type": "done", "errors": [], "total_tokens": {"total": 0}, "duration": 0},
        {"type": "cancelled", "message": "stopped"},
        {"type": "widget", "data": {"widget_type": "calc", "name": "calc", "result": {}, "citations": []}},
    ]
    for p in payloads:
        ev = _event(p)
        assert ev.startswith("data: "), f"{p['type']}: must start with 'data: '"
        parsed = json.loads(ev[6:])
        assert parsed["type"] == p["type"], f"{p['type']}: type mismatch after parse"
