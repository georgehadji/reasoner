"""Prometheus metrics for Reasoner.

Critical Enhancements:
- 7.2: metrics_endpoint is async with asyncio.to_thread()
- 7.6: connection pool metrics for Postgres and Redis
"""

from __future__ import annotations

import asyncio
import time

try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
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
    ["tier", "preset", "status"],
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