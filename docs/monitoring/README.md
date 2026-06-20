# Monitoring Reference

This directory contains reference monitoring configurations.

## `alerts-reference.yml`

Prometheus alerting rules for the Reasoner backend. These rules are **not actively deployed** — they serve as a starting point for teams setting up Prometheus + Alertmanager.

### Required Metrics

Before these alerts can fire, the application must export the metrics they reference:

- `reasoner_queries_total` — Counter with labels `tier`, `preset`, `status`
- `reasoner_quota_exceeded_total` — Counter with label `tier`
- `reasoner_query_duration_seconds_bucket` — Histogram with label `preset`
- `reasoner_postgres_pool_free` — Gauge

### Deployment

1. Install Prometheus and Alertmanager in your cluster.
2. Copy `alerts-reference.yml` into your Prometheus configuration.
3. Update notification routing in `alertmanager.yml` (PagerDuty, Slack, email, etc.).
4. Verify alerts load: `promtool check rules alerts-reference.yml`

### Current Status

| Component | Status |
|-----------|--------|
| Metrics endpoint (`/api/metrics`) | ✅ Implemented |
| Prometheus deployment | ❌ Not included in docker-compose |
| Alertmanager deployment | ❌ Not included in docker-compose |
| Alert routing (PagerDuty/Slack) | ❌ Not configured |
