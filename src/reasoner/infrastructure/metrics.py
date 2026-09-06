"""Prometheus metrics for Reasoner.

Critical Enhancements:
- 7.2: metrics_endpoint is async with asyncio.to_thread()
- 7.6: connection pool metrics for Postgres and Redis
"""

from __future__ import annotations

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
    _PROMETHEUS_AVAILABLE = True
except Exception:  # pragma: no cover
    _PROMETHEUS_AVAILABLE = False

    class _NoOpMetric:
        """Stub metric that silently accepts all operations."""
        def __init__(self, *args, **kwargs):
            pass
        def labels(self, *args, **kwargs):
            return self
        def observe(self, *args, **kwargs):
            pass
        def inc(self, *args, **kwargs):
            pass
        def set(self, *args, **kwargs):
            pass

    Counter = _NoOpMetric
    Histogram = _NoOpMetric
    Gauge = _NoOpMetric

    def generate_latest(*args, **kwargs):
        return b""

    CONTENT_TYPE_LATEST = "text/plain; charset=utf-8"

# Request counters
REASONER_QUERIES_TOTAL = Counter(
    "reasoner_queries_total",
    "Total queries executed",
    ["tier", "preset", "status", "interface"],
)

REASONER_QUOTA_EXCEEDED_TOTAL = Counter(
    "reasoner_quota_exceeded_total",
    "Quota exceeded events",
    ["tier"],
)

REASONER_LLM_ERRORS_TOTAL = Counter(
    "reasoner_llm_errors_total",
    "LLM provider errors",
    ["provider"],
)

STRIPE_WEBHOOK_SIG_FAILURES = Counter(
    "stripe_webhook_signature_failures_total",
    "Stripe webhook signature verification failures",
)

# ── Propagation resistance (docs/MIND_VIRUS_MITIGATION.md) ──
# Injection patterns found in text that is *already inside* the system: replayed
# long-term memory, or prior-turn text supplied by an API caller. Distinct from
# the user-input sanitiser, which guards the front door. A non-zero rate here
# means something got past the front door earlier, or a caller is probing.
REASONER_PROPAGATION_PATTERN_TOTAL = Counter(
    "reasoner_propagation_pattern_total",
    "Injection/propagation patterns sanitised out of system-internal text",
    # neuro_recall | followup_synthesis | followup_history | synthesis_learn
    ["surface"],
)


def count_propagation_pattern(surface: str, count: int = 1) -> None:
    """Record injection patterns found in system-internal text.

    Best-effort by construction: observability must never fail a request, and
    prometheus_client is an optional dependency (Counter degrades to _NoOpMetric
    when it is absent). Callers therefore do not need to guard this.
    """
    try:
        REASONER_PROPAGATION_PATTERN_TOTAL.labels(surface=surface).inc(count)
    except Exception:  # pragma: no cover - observability is never load-bearing
        pass

# Latency histograms
REASONER_QUERY_DURATION = Histogram(
    "reasoner_query_duration_seconds",
    "Pipeline execution duration",
    ["preset"],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
)

# Gauges
REASONER_ACTIVE_USERS = Gauge(
    "reasoner_active_users_total",
    "Unique users in last 24h",
)

# Connection pool metrics (Critical Enhancement 7.6)
REASONER_POSTGRES_POOL_SIZE = Gauge(
    "reasoner_postgres_pool_size",
    "Current Postgres connection pool size",
)

REASONER_POSTGRES_POOL_FREE = Gauge(
    "reasoner_postgres_pool_free",
    "Free connections in Postgres pool",
)

REASONER_REDIS_POOL_SIZE = Gauge(
    "reasoner_redis_pool_size",
    "Current Redis connection pool size",
)

# ═══════════════════════════════════════════════════════════════
# Valkey metrics (successor to Redis metrics — keep both during migration)
# ═══════════════════════════════════════════════════════════════

REASONER_VALKEY_POOL_SIZE = Gauge(
    "reasoner_valkey_pool_size",
    "Current Valkey connection pool size",
)

REASONER_VALKEY_FALLBACK_TOTAL = Counter(
    "reasoner_valkey_fallback_total",
    "Number of times Valkey was unavailable and an in-memory fallback was used",
    ["subsystem"],  # "rate_limiter" | "circuit_breaker" | "run_state" | "cache" | "hypergate"
)

# Cache metrics
REASONER_CACHE_HIT_RATE = Gauge(
    "reasoner_cache_hit_rate",
    "Cache hit rate (0.0–1.0)",
)

REASONER_CACHE_ENTRIES = Gauge(
    "reasoner_cache_entries",
    "Number of cache entries",
)

CACHE_HITS = Counter(
    "reasoner_cache_hits_total",
    "Token cache hits",
    ["phase", "model"],
)

CACHE_MISSES = Counter(
    "reasoner_cache_misses_total",
    "Token cache misses",
    ["phase", "model"],
)

TOKEN_SAVINGS_USD = Counter(
    "reasoner_token_savings_usd",
    "Estimated cost savings from cache",
)

TRUNCATED_RESPONSES = Counter(
    "reasoner_truncated_responses_total",
    "LLM responses that hit max_tokens mid-generation (finish_reason=length)",
    ["phase", "model"],
)

OBSERVABILITY_EVENTS_DROPPED_TOTAL = Counter(
    "reasoner_observability_events_dropped_total",
    "Total observability events dropped due to client being disabled or unreachable",
)

# Phase latency histograms
PHASE_DURATION = Histogram(
    "reasoner_phase_duration_seconds",
    "Phase execution time",
    ["phase", "method", "preset"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
)

# Phase quality scores (v3.4)
PHASE_QUALITY_SCORE = Histogram(
    "reasoner_phase_quality_score",
    "LLM judge quality score per phase (0-10)",
    ["phase", "passed"],
    buckets=[0.0, 2.0, 4.0, 6.0, 7.0, 8.0, 9.0, 10.0],
)

# Circuit breaker metrics
REASONER_CIRCUIT_BREAKER_STATE = Gauge(
    "reasoner_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half_open, 2=open)",
    ["name"],
)

REASONER_CIRCUIT_BREAKER_REJECTED = Counter(
    "reasoner_circuit_breaker_rejected_total",
    "Rejected calls due to open circuit",
    ["name"],
)

# Rate limiter metrics
REASONER_RATE_LIMIT_REJECTED = Counter(
    "reasoner_rate_limit_rejected_total",
    "Rate limited requests",
    ["tier"],
)

# WebSocket metrics
REASONER_WEBSOCKET_CONNECTIONS = Gauge(
    "reasoner_websocket_connections",
    "Active WebSocket connections",
)

# Memory usage gauge (Phase 2.10 — exported by MemoryLimitMiddleware)
REASONER_MEMORY_USAGE_MB = Gauge(
    "reasoner_memory_usage_mb",
    "Current process memory usage in MB",
)

# Cron heartbeat gauge (Phase 1.7 — set by nightly compaction/archive tasks)
REASONER_CRON_HEARTBEAT_TIMESTAMP = Gauge(
    "reasoner_cron_heartbeat_timestamp",
    "Unix timestamp of last successful nightly cron run",
)

# Webhook processing failures (Phase 0.1 — billing dead-letter)
WEBHOOK_PROCESSING_FAILURES = Counter(
    "reasoner_webhook_processing_failures_total",
    "Webhook processing failures that were silently dropped",
    ["provider", "event_type"],
)

# Dead-letter events counter (Phase 0.3 — EventBus dead-letter queue)
DEAD_LETTER_EVENTS = Counter(
    "reasoner_dead_letter_events_total",
    "Events written to dead-letter queue after handler retry exhaustion",
    ["event_type"],
)

# Quota-check failures (E-policy). check_quota fails open on any backend
# error, returning a small emergency allowance. That is a deliberate
# availability choice, but it made a total quota outage indistinguishable from
# every user simply having quota: the PostgreSQL defect found on 2026-09-01 had
# get_quota raising on every call for an unknown length of time, and the only
# trace was a logger.warning nobody reads. Alert on this being non-zero.
REASONER_QUOTA_CHECK_FAILURES = Counter(
    "reasoner_quota_check_failures_total",
    "Quota checks that fell back to the emergency allowance after a backend error",
    ["reason"],
)

# Run cost gauge (P1.9 — current pipeline run USD cost)
REASONER_RUN_COST_USD = Gauge(
    "reasoner_run_cost_usd",
    "Accumulated USD cost of the current pipeline run",
)

# Spend cap exceeded counter (P1.9 — spend cap violations)
REASONER_SPEND_CAP_EXCEEDED_TOTAL = Counter(
    "reasoner_spend_cap_exceeded_total",
    "Pipeline runs halted due to spend cap being exceeded",
    ["cap_type"],  # "per_run" | "monthly"
)

# ── ACR Phase 1: Call-Level Telemetry Metrics ─────────────────────────────────

LLM_CALL_DURATION = Histogram(
    "reasoner_llm_call_duration_seconds",
    "Per-call LLM latency by model and role",
    ["model", "role", "preset"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

LLM_CALL_SUCCESS = Counter(
    "reasoner_llm_call_success_total",
    "Successful LLM calls by model and role",
    ["model", "role"],
)

LLM_CALL_FAILURE = Counter(
    "reasoner_llm_call_failure_total",
    "Failed LLM calls by model and role",
    ["model", "role", "reason"],
)

LLM_CALL_COST = Counter(
    "reasoner_llm_call_cost_usd_total",
    "Cumulative cost by model and role",
    ["model", "role"],
)

# HyperGate had no total-request ceiling at all before
# docs/plans/gate-and-registry-remediation.md W3b -- LLM_CALL_FAILURE only
# covers a single provider call, not the whole gate decision (five sub-agents,
# TieBreaker if it fires). A rising rate here means HYPERGATE_TOTAL_BUDGET_SECONDS
# is too tight for real traffic, not that any one call is failing.
HYPERGATE_BUDGET_EXCEEDED_TOTAL = Counter(
    "reasoner_hypergate_budget_exceeded_total",
    "Gate decisions that exceeded the total request budget and fell back to pipeline",
)
