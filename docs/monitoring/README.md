# Monitoring Reference

This directory contains active monitoring configurations for the Reasoner backend.

## Files

| File | Purpose |
|------|---------|
| `prometheus.yml` | Prometheus scrape config — targets the backend `/api/metrics` endpoint |
| `alertmanager.yml` | Alertmanager routing — Slack, PagerDuty, or log-only |
| `alerts.yml` | **Active** alerting rules (promoted from `alerts-reference.yml`) |
| `alerts-reference.yml` | Historical reference — replaced by `alerts.yml` |
| `README.md` | This file |

## Deployment

```bash
# With observability stack:
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d

# Verify:
curl -s http://localhost:9090/api/v1/status/config | jq .
curl -s http://localhost:9093/api/v2/status | jq .
curl -s http://localhost:8003/api/metrics | head -20
```

### Prerequisites

1. **Network:** Prometheus must be on the same Docker network as the backend.
2. **IP allowlist:** Add the Docker network range to `METRICS_ALLOWED_IPS` in `.env`:
   ```
   METRICS_ALLOWED_IPS=127.0.0.1,::1,172.16.0.0/12
   ```
3. **Alert routing (optional):** Set these in `.env` for external notifications:
   - `SLACK_WEBHOOK_URL` — Slack incoming webhook
   - `PAGERDUTY_ROUTING_KEY` — PagerDuty Events API v2 key

### Reloading

```bash
# After changing prometheus.yml or alerts.yml:
curl -X POST http://localhost:9090/-/reload

# After changing alertmanager.yml:
docker compose -f docker-compose.observability.yml restart alertmanager
```

## Alert Rules

All rules are defined in `alerts.yml`. Current coverage:

| Alert Name | Severity | Metric Required | Description |
|------------|----------|-----------------|-------------|
| `HighErrorRate` | warning | `reasoner_queries_total` | >0.1 errors/sec for 5m |
| `CriticalErrorRate` | critical | `reasoner_queries_total` | >0.5 errors/sec for 2m |
| `QuotaExceededSpike` | warning | `reasoner_quota_exceeded_total` | >10 quota-exceeds/sec |
| `HighLatency` | warning | `reasoner_query_duration_seconds_bucket` | P95 >60s |
| `PhaseLatencySpike` | warning | `reasoner_phase_duration_seconds_bucket` | P95 >120s |
| `PostgresPoolExhaustion` | critical | `reasoner_postgres_pool_free` | Pool exhausted |
| `PostgresPoolLow` | warning | `reasoner_postgres_pool_free` | <2 free connections |
| `WebhookProcessingFailures` | warning | `reasoner_webhook_processing_failures_total` | Any webhook failure |
| `WebhookProcessingCritical` | critical | `reasoner_webhook_processing_failures_total` | >5/sec |
| `DeadLetterEventsAccumulating` | warning | `reasoner_dead_letter_events_total` | Events in dead-letter |
| `MemoryWarning` | warning | `reasoner_memory_usage_mb` | >3072MB |
| `MemoryCritical` | critical | `reasoner_memory_usage_mb` | >4096MB |
| `CronHeartbeatStale` | warning | `reasoner_cron_heartbeat_timestamp` | >25h since heartbeat |
| `CIHealingHeartbeatStale` | warning | `ci_heartbeat_timestamp` | CI not run >25h |
| `CircuitBreakerOpen` | critical | `reasoner_circuit_breaker_state` | Open >5m |
| `RateLimitRejectionSpike` | warning | `reasoner_rate_limit_rejected_total` | >50/sec |

## Required Metrics

Before these alerts can fire, the application must export the following metrics:

- `reasoner_queries_total` — Counter with labels `tier`, `preset`, `status`
- `reasoner_quota_exceeded_total` — Counter with label `tier`
- `reasoner_query_duration_seconds_bucket` — Histogram with label `preset`
- `reasoner_postgres_pool_free` — Gauge
- `reasoner_webhook_processing_failures_total` — Counter (NEW — Phase 0.1)
- `reasoner_dead_letter_events_total` — Counter (NEW — Phase 0.3)
- `reasoner_memory_usage_mb` — Gauge (NEW — Phase 2.10)
- `reasoner_cron_heartbeat_timestamp` — Gauge (NEW — Phase 1.7)

## Verification

```bash
# Check all rules are valid
promtool check rules alerts.yml

# Simulate alert
amtool alert add alertname=TestAlert severity=critical

# View active alerts
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | {name: .labels.alertname, state: .state}'
```

## Current Status

| Component | Status |
|-----------|--------|
| Metrics endpoint (`/api/metrics`) | ✅ Implemented |
| Prometheus deployment | ✅ `docker-compose.observability.yml` |
| Alertmanager deployment | ✅ `docker-compose.observability.yml` |
| Alert routing (Slack/PagerDuty) | ✅ Configured (env-driven webhooks) |
