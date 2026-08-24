"""Domain value objects for per-call LLM telemetry (ACR Phase 1)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMCallTelemetry:
    """Per-call telemetry event — immutable value object.

    Records every LLM call's identity, performance, quality signals,
    and circuit-breaker state for adaptive routing analytics.
    """

    # Call identity
    call_id: str                        # UUID
    run_id: str                         # Pipeline run ID
    timestamp: str                      # ISO-8601 UTC

    # Model & routing identity
    model_id: str                       # e.g. "claude-sonnet"
    role: str                           # e.g. "constructive", "scoring"
    preset_id: str                      # e.g. "multi-perspective-budget"
    method: str                         # e.g. "multi-perspective"
    phase: int                          # 0-5

    # Performance
    latency_ms: float                   # Wall-clock time in milliseconds
    input_tokens: int
    output_tokens: int
    cost_usd: float

    # Quality / outcome
    success: bool                       # Non-empty, parseable response
    json_valid: bool | None = None      # If JSON was expected, did it parse?
    is_fallback: bool = False           # Was this a fallback call?
    fallback_reason: str | None = None  # "timeout", "error", "empty"

    # Circuit state
    circuit_state: str = "closed"       # "closed", "half_open", "open"

    # Phase-specific quality (filled post-phase)
    critique_score: float | None = None  # Phase 3 critique score (0-10)
    stress_test_pass: bool | None = None  # Phase 4 pass/fail

    # Bloc metadata
    vendor: str = ""
    bloc: str = ""                      # "US", "CN", "EU", "OTHER"


@dataclass(frozen=True)
class ModelRoleStats:
    """Aggregated telemetry for a (model, role) pair over a time window."""

    model_id: str
    role: str
    total_calls: int = 0
    successful_calls: int = 0
    fallback_calls: int = 0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    avg_input_tokens: int = 0
    avg_output_tokens: int = 0
    avg_cost_usd: float = 0.0
    total_cost_usd: float = 0.0
    success_rate: float = 0.0
    json_valid_rate: float | None = None
    avg_critique_score: float | None = None
    stress_test_pass_rate: float | None = None
    vendor: str = ""
    bloc: str = ""
    sample_count: int = 0               # For confidence weighting


__all__ = [
    "LLMCallTelemetry",
    "ModelRoleStats",
]
