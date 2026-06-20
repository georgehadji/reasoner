# Phase 7 Implementation Plan — Monitoring + Observability

> **Goal:** Know when things break before users do.  
> **Duration:** 5 working days (Week 8)  
> **Deliverable:** Prometheus metrics, Sentry integration, structured logging, uptime monitoring.  
> **Constraint:** Observability must not add >5% latency overhead.

⚠️ **CRITICAL ENHANCEMENTS (PHASE_ENHANCEMENTS.md 7.1–7.7):**
- 7.1: `REASONER_QUERY_DURATION.labels(...).time()` only measures until first yield in async generator — use explicit timing
- 7.2: `metrics_endpoint()` is sync, not async — will block event loop — use `asyncio.to_thread()`
- 7.3: `REASONER_ACTIVE_USERS` gauge never updated — shows 0 always — implement background update task
- 7.4: Load test uses sync `TestClient` with `asyncio.gather()` — not concurrent — use `httpx.AsyncClient`
- 7.5: `traces_sample_rate=0.1` is too low for early-stage product — start at 1.0, reduce as traffic grows
- 7.6: Missing connection pool metrics for Postgres and Redis — pool exhaustion is common failure mode
- 7.7: No distributed tracing across services — add OpenTelemetry instrumentation

---

## 0. Pre-Flight Checklist

```bash
# 1. Verify Phases 1-6 are complete
python -m pytest tests/ --tb=short -q

# 2. Install observability tools
pip install prometheus-client sentry-sdk
npm install --save @sentry/nextjs

# 3. Create Sentry projects (Python + Next.js) at https://sentry.io
```

---

## 1. Day-by-Day Implementation Schedule

### Day 1 — Prometheus Metrics Endpoint

**Files:**
- `src/reasoner/api/metrics.py` (new)
- `src/reasoner/api/__init__.py` (mount metrics)

**Task 7.1.1 — Metrics Definitions**

```python
# src/reasoner/api/metrics.py
"""Prometheus metrics for Reasoner."""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

# Request counters
REASONER_QUERIES_TOTAL = Counter(
    'reasoner_queries_total',
    'Total queries executed',
    ['tier', 'preset', 'status']
)

REASONER_QUOTA_EXCEEDED_TOTAL = Counter(
    'reasoner_quota_exceeded_total',
    'Quota exceeded events',
    ['tier']
)

REASONER_LLM_ERRORS_TOTAL = Counter(
    'reasoner_llm_errors_total',
    'LLM provider errors',
    ['provider']
)

# Latency histograms
REASONER_QUERY_DURATION = Histogram(
    'reasoner_query_duration_seconds',
    'Pipeline execution duration',
    ['preset'],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0]
)

# Gauges
REASONER_ACTIVE_USERS = Gauge(
    'reasoner_active_users_total',
    'Unique users in last 24h'
)


async def metrics_endpoint() -> Response:
    """Expose Prometheus metrics."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
```

**Task 7.1.2 — Wire Metrics into Pipeline**

```python
# In run_pipeline or run_stream, add:
from reasoner.api.metrics import REASONER_QUERIES_TOTAL, REASONER_QUERY_DURATION

with REASONER_QUERY_DURATION.labels(preset=req.preset).time():
    async for chunk in run_stream_cached(req):
        yield chunk

# On completion:
REASONER_QUERIES_TOTAL.labels(
    tier=user_tier,
    preset=req.preset,
    status="success" if not state.errors else "error"
).inc()
```

**Day 1 Acceptance Criteria:**
- [ ] `GET /api/metrics` returns Prometheus text format.
- [ ] After a query, `reasoner_queries_total` > 0.

---

### Day 2 — Sentry Integration

**Files:**
- `src/reasoner/api/sentry.py` (new)
- `ui-next/sentry.client.config.ts`
- `ui-next/sentry.server.config.ts`

**Task 7.2.1 — Backend Sentry**

```python
# src/reasoner/api/sentry.py
"""Sentry initialization for FastAPI."""

import os
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

def init_sentry():
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("ENVIRONMENT", "development"),
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
        ],
        traces_sample_rate=0.1,  # 10% sampling
        profiles_sample_rate=0.05,
    )
```

**Task 7.2.2 — Frontend Sentry**

```typescript
// ui-next/sentry.client.config.ts
import * as Sentry from '@sentry/nextjs';

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  tracesSampleRate: 0.1,
});
```

**Day 2 Acceptance Criteria:**
- [ ] Sentry receives a test exception from backend within 5s.
- [ ] Sentry receives a test exception from frontend.

---

### Day 3 — Structured Logging Enrichment

**Files:**
- `src/reasoner/logging_utils.py` (modification)

**Task 7.3.1 — Enrich Logs with User Context**

```python
# In src/reasoner/logging_utils.py, modify StructuredLogEntry:

@dataclass
class StructuredLogEntry:
    timestamp: str
    level: str
    source: str
    message: str
    correlation_id: str
    extra: dict[str, Any]
    user_id: str | None = None   # NEW
    tier: str | None = None      # NEW
    preset: str | None = None    # NEW
```

Add a helper to set request-scoped context:

```python
# src/reasoner/logging_utils.py
import contextvars

_log_context = contextvars.ContextVar("log_context", default={})

def set_log_context(user_id: str | None = None, tier: str | None = None, preset: str | None = None):
    _log_context.set({"user_id": user_id, "tier": tier, "preset": preset})
```

**Day 3 Acceptance Criteria:**
- [ ] Every log line includes `user_id`, `tier`, and `preset` when available.

---

### Day 4 — Uptime Monitoring + Alerting

**Files:**
- `docker-compose.yml` (add Uptime Kuma or external)

**Task 7.4.1 — Health Check Endpoint for Monitors**

Use existing `/api/health`. Configure Uptime Robot or Uptime Kuma to ping every 60s.

**Task 7.4.2 — Alert Rules**

```yaml
# alerts.yml (for Prometheus Alertmanager)
groups:
  - name: reasoner
    rules:
      - alert: HighErrorRate
        expr: rate(reasoner_queries_total{status="error"}[5m]) > 0.1
        for: 5m
        annotations:
          summary: "High error rate detected"

      - alert: QuotaExceededSpike
        expr: rate(reasoner_quota_exceeded_total[5m]) > 10
        for: 1m
        annotations:
          summary: "Quota exceeded spike — possible abuse"
```

**Day 4 Acceptance Criteria:**
- [ ] Uptime monitor alerts when `/api/health` returns non-200.
- [ ] Prometheus alert fires on high error rate.

---

### Day 5 — Load Testing + Performance Baseline

**Files:**
- `tests/test_load.py` (extend existing)

**Task 7.5.1 — Load Test with Metrics**

```python
# tests/test_load.py additions
import asyncio
import time

async def test_concurrent_queries_with_metrics(client):
    start = time.time()
    tasks = [client.post("/api/run", json={"problem": "2+2", "preset": "multi-perspective-budget"}) for _ in range(50)]
    responses = await asyncio.gather(*tasks)
    elapsed = time.time() - start

    assert all(r.status_code == 200 for r in responses)
    assert elapsed < 60  # 50 queries in under 60s
```

**Day 5 Acceptance Criteria:**
- [ ] Baseline metrics captured for p50, p95, p99 latency.
- [ ] Memory usage stays under 512MB per worker.

---

## 2. Definition of Done (Phase 7)

- [ ] `/api/metrics` exposes Prometheus format.
- [ ] Sentry receives backend + frontend errors.
- [ ] Logs include `user_id`, `tier`, `preset`.
- [ ] Uptime monitor alerts on health check failure.
- [ ] Load test passes with 50 concurrent users.
- [ ] All existing tests pass.

---

*End of Phase 7 Plan*
