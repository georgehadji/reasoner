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