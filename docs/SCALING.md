# Scaling Guide — Reasoner (ARA Pipeline)

## Horizontal Scaling

Reasoner supports multi-worker deployments via the following shared-state backends:

1. **Redis Run State** — Workers share cancellation state via Redis Sets with automatic in-memory fallback (Critical Enhancement 9.1–9.3, 9.7).
2. **Postgres Connection Pool** — Configure `DB_POOL_SIZE` per worker (default: 10).
3. **Redis Quota Cache** — Shared quota reads across workers via `CachedQuotaRepository`.
4. **Redis Circuit Breaker** — Set `CIRCUIT_BREAKER_MODE=redis` for shared circuit state across workers.
5. **Redis Rate Limiter** — Set `RATE_LIMITER_MODE=redis` for shared rate-limit state across workers.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_POOL_SIZE` | `10` | Postgres connections per worker |
| `RATE_LIMITER_MODE` | `memory` | `memory` or `redis` |
| `CIRCUIT_BREAKER_MODE` | `memory` | `memory` or `redis` |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `UVICORN_WORKERS` | `1` | Number of uvicorn worker processes |

## Recommended Setup

- **Uvicorn workers:** `2–4` per CPU core
- **DB_POOL_SIZE:** `10` per worker (e.g., 4 workers × 10 = 40 total DB connections)
- **Redis:** Single instance (can be replicated for reads)
- **Postgres:** RDS / Cloud SQL with read replicas for analytics

## Run State Architecture

```
Before (single-process only):
  _cancelled_runs: dict[str, bool] = {}   # module global
  _active_runs: set[str] = set()          # module global

After (multi-worker compatible):
  ┌─────────────────────────────────────┐
  │  Redis Run State                    │
  │  SET  active_runs                   │  O(1) SADD/SREM/SISMEMBER
  │  SET  cancelled_runs                │  O(1) SADD/SREM/SISMEMBER
  │  EXPIRE 300s (auto cleanup)         │
  └─────────────────────────────────────┘
          │
          ▼  Redis unavailable?
  ┌─────────────────────────────────────┐
  │  In-Memory Fallback (RunStateStore) │
  │  Same API, local to process         │
  └─────────────────────────────────────┘
```

## Critical Enhancements

- **9.1** — `cancel_all_active` uses Redis `SMEMBERS` (O(1) per member) instead of `SCAN` iteration (O(N)).
- **9.2** — `pop_cancelled` uses atomic Lua script instead of non-atomic GET+DELETE pipeline.
- **9.3** — No `.decode()` calls; Redis client uses `decode_responses=True`.
- **9.7** — Circuit-breaker-style fallback to in-memory store when Redis fails, preventing cascading outages.

## Known Limits

- **EventBus** is in-memory only. For multi-worker event propagation, migrate to Redis Pub/Sub (acknowledged in Phase 9, planned for future).
- **Token cache** is disk-based. Migrate to Redis for shared caching across workers.
- **WebSocket subscriptions** are in-memory. Use Redis Pub/Sub for broadcast across workers.

## Database Indexes

Run migration `003_add_indexes.sql` for composite indexes:

```bash
psql $DATABASE_URL -f migrations/003_add_indexes.sql
```

Indexes added:
- `idx_query_log_user_created` — speeds up user data export
- `idx_subscriptions_user_status` — speeds up subscription lookups
- `idx_usage_quotas_period` — speeds up quota period queries

## Load Testing

```bash
# 50 concurrent unauthenticated queries
python -m pytest tests/test_load.py::test_concurrent_queries_with_metrics -v

# 100 concurrent authenticated queries (slow)
python -m pytest tests/test_load.py::test_100_concurrent_authenticated_users -v --run-slow
```
