# Phase 9 Implementation Plan — Performance + Scale Prep

> **Goal:** Resolve architectural smells from the mindmap so the SaaS can scale horizontally.  
> **Duration:** 5 working days (Week 10)  
> **Deliverable:** Redis-backed run state, connection pool tuning, DB optimization, load tests.  
> **Constraint:** Changes must not break single-process local development.

⚠️ **CRITICAL ENHANCEMENTS (PHASE_ENHANCEMENTS.md 9.1–9.8):**
- 9.1: `cancel_all_active` uses `SCAN` iteration — O(N), blocks event loop on 100K keys — use Redis Set instead
- 9.2: `pop_cancelled` is not atomic — another worker can read key between GET and DELETE — use Lua script
- 9.3: `key.decode()` fails when `decode_responses=True` — keys are already strings — remove `.decode()`
- 9.4: `_shared_client` HTTPX pool never closed on shutdown — resource leak, unclosed client warning
- 9.6: `DB_POOL_OVERFLOW` is set but asyncpg has no overflow concept — remove from docs
- 9.7: No circuit breaker for Redis failures — cascading outage if Redis goes down
- 9.8: `EventBus` is in-memory only — scaling gap acknowledged but not addressed — migrate to Redis Pub/Sub

---

## 0. Pre-Flight Checklist

```bash
# 1. Verify Phases 1-8 are complete
python -m pytest tests/ --tb=short -q

# 2. Ensure Redis is configured and running
redis-cli ping

# 3. Baseline load test
python -m pytest tests/test_load.py -v
```

---

## 1. Architecture Overview

```
Before (single-process only):
  _cancelled_runs: dict[str, bool] = {}   # module global
  _active_runs: set[str] = set()          # module global

After (multi-worker compatible):
  ┌─────────────────────────────────────┐
  │  Redis Run State                    │
  │  SET  active_runs:{run_id}          │
  │  SET  cancelled_runs:{run_id}       │
  │  EXPIRE 300s (auto cleanup)         │
  └─────────────────────────────────────┘
```

---

## 2. Day-by-Day Implementation Schedule

### Day 1 — Redis Run State Manager

**Files:**
- `src/reasoner/infrastructure/redis/run_state.py`

**Task 9.1.1 — RunStateManager**

```python
# src/reasoner/infrastructure/redis/run_state.py
"""
Distributed run state backed by Redis.

Replaces module-level _cancelled_runs and _active_runs dicts
to support multi-worker deployments.
"""

from __future__ import annotations

import logging
from reasoner.infrastructure.redis.client import get_redis

logger = logging.getLogger(__name__)
ACTIVE_KEY = "active_runs"
CANCELLED_KEY = "cancelled_runs"
TTL_SECONDS = 300  # Auto-cleanup after 5 minutes


class RunStateManager:
    """Manages pipeline run state in Redis."""

    def __init__(self):
        self._redis = get_redis()

    async def register(self, run_id: str) -> None:
        """Mark a run as active."""
        await self._redis.setex(f"{ACTIVE_KEY}:{run_id}", TTL_SECONDS, "1")

    async def unregister(self, run_id: str) -> None:
        """Remove a run from active set."""
        await self._redis.delete(f"{ACTIVE_KEY}:{run_id}")

    async def is_active(self, run_id: str) -> bool:
        """Check if a run is still active."""
        return await self._redis.exists(f"{ACTIVE_KEY}:{run_id}") > 0

    async def cancel(self, run_id: str) -> None:
        """Request cancellation of a run."""
        await self._redis.setex(f"{CANCELLED_KEY}:{run_id}", TTL_SECONDS, "1")

    async def is_cancelled(self, run_id: str) -> bool:
        """Check if a run has been requested to cancel."""
        return await self._redis.exists(f"{CANCELLED_KEY}:{run_id}") > 0

    async def pop_cancelled(self, run_id: str) -> bool:
        """Atomically check and clear cancellation flag."""
        key = f"{CANCELLED_KEY}:{run_id}"
        pipe = self._redis.pipeline()
        pipe.get(key)
        pipe.delete(key)
        results = await pipe.execute()
        return results[0] is not None

    async def cancel_all_active(self) -> int:
        """Cancel all currently active runs. Returns count."""
        pattern = f"{ACTIVE_KEY}:*"
        keys = []
        async for key in self._redis.scan_iter(match=pattern):
            run_id = key.decode().split(":", 1)[1]
            await self.cancel(run_id)
            keys.append(run_id)
        return len(keys)
```

**Day 1 Acceptance Criteria:**
- [ ] `pytest tests/test_saas_run_state.py` passes.
- [ ] Two separate Python processes can cancel each other's runs via Redis.

---

### Day 2 — Migrate Pipeline to RunStateManager

**Files:**
- `src/reasoner/api/__init__.py` (modification)

**Task 9.2.1 — Replace Globals**

```python
# In src/reasoner/api/__init__.py

# OLD:
# _cancelled_runs: dict[str, bool] = {}
# _active_runs: set[str] = set()

# NEW:
from reasoner.infrastructure.redis.run_state import RunStateManager

_run_state = RunStateManager()
```

Update all usages:

```python
# In run_stream:
run_id = str(uuid.uuid4())
await _run_state.register(run_id)
try:
    ...
    if await _run_state.pop_cancelled(run_id):
        yield _event({"type": "cancelled", "message": "Pipeline stopped by user"})
        return
finally:
    await _run_state.unregister(run_id)

# In stop_pipeline:
@app.post("/api/stop")
async def stop_pipeline():
    count = await _run_state.cancel_all_active()
    return {"status": "stop requested", "affected_runs": count}
```

**Day 2 Acceptance Criteria:**
- [ ] `/api/stop` cancels runs via Redis.
- [ ] Existing stop tests pass.

---

### Day 3 — Connection Pool Tuning

**Files:**
- `src/reasoner/infrastructure/persistence/quota_repo_postgres.py`
- `src/reasoner/llm.py` (if connection pools exist)

**Task 9.3.1 — Postgres Pool Sizing**

```python
# In PostgresQuotaRepository.__init__:
self._pool_size = int(os.environ.get("DB_POOL_SIZE", "10"))
self._max_overflow = int(os.environ.get("DB_POOL_OVERFLOW", "5"))
```

**Task 9.3.2 — HTTPX Pool for LLM Providers**

```python
# In OpenRouterProvider or similar:
import httpx

_shared_client: httpx.AsyncClient | None = None

def get_http_client() -> httpx.AsyncClient:
    global _shared_client
    if _shared_client is None:
        limits = httpx.Limits(
            max_connections=50,
            max_keepalive_connections=20,
        )
        _shared_client = httpx.AsyncClient(limits=limits, timeout=httpx.Timeout(60.0))
    return _shared_client
```

**Day 3 Acceptance Criteria:**
- [ ] `DB_POOL_SIZE=20` env var is respected.
- [ ] Load test with 100 concurrent users does not exhaust pools.

---

### Day 4 — Database Query Optimization

**Files:**
- Alembic migration for indexes

**Task 9.4.1 — Add Composite Indexes**

```python
# migrations/versions/002_add_indexes.py
from alembic import op

def upgrade():
    op.create_index("idx_query_log_user_created", "query_log", ["user_id", "created_at DESC"])
    op.create_index("idx_subscriptions_user_status", "subscriptions", ["user_id", "status"])
    op.create_index("idx_usage_quotas_period", "usage_quotas", ["period_start"])

def downgrade():
    op.drop_index("idx_query_log_user_created")
    op.drop_index("idx_subscriptions_user_status")
    op.drop_index("idx_usage_quotas_period")
```

**Task 9.4.2 — Query Plan Verification**

```sql
EXPLAIN ANALYZE
SELECT * FROM query_log
WHERE user_id = '...' AND created_at > NOW() - INTERVAL '7 days'
ORDER BY created_at DESC;
-- Should show Index Scan using idx_query_log_user_created
```

**Day 4 Acceptance Criteria:**
- [ ] Migration applies cleanly.
- [ ] Query plans show index usage.

---

### Day 5 — Load Testing + Documentation

**Files:**
- `tests/test_load.py` (extend)
- `docs/SCALING.md` (new)

**Task 9.5.1 — Load Test with Auth**

```python
# tests/test_load.py
import asyncio
import pytest
from fastapi.testclient import TestClient

@pytest.mark.asyncio
async def test_100_concurrent_authenticated_users(client: TestClient, auth_token: str):
    async def single_request():
        return client.post(
            "/api/run",
            json={"problem": "What is 2+2?", "preset": "multi-perspective-budget"},
            headers={"Authorization": f"Bearer {auth_token}"},
        )

    tasks = [single_request() for _ in range(100)]
    responses = await asyncio.gather(*tasks)

    success_rate = sum(1 for r in responses if r.status_code == 200) / len(responses)
    assert success_rate >= 0.95, f"Success rate too low: {success_rate}"
```

**Task 9.5.2 — Scaling Documentation**

```markdown
# docs/SCALING.md

## Horizontal Scaling

Reasoner supports multi-worker deployments via:

1. **Redis Run State** — Workers share cancellation state.
2. **Postgres Connection Pool** — Configure `DB_POOL_SIZE` per worker.
3. **Redis Quota Cache** — Shared quota reads across workers.

## Recommended Setup

- **Uvicorn workers:** `2-4` per CPU core
- **DB_POOL_SIZE:** `10` per worker
- **Redis:** Single instance (can be replicated for reads)
- **Postgres:** RDS / Cloud SQL with read replicas for analytics

## Known Limits

- EventBus is in-memory only → use Redis pub/sub for multi-worker events.
- Token cache is disk-based → migrate to Redis for shared cache.
```

**Day 5 Acceptance Criteria:**
- [ ] Load test with 100 concurrent users passes.
- [ ] Memory usage < 512MB per worker.
- [ ] `docs/SCALING.md` documents horizontal scaling approach.
- [ ] All existing tests pass.

---

## 3. Definition of Done (Phase 9)

- [ ] `_cancelled_runs` and `_active_runs` replaced by Redis-backed `RunStateManager`.
- [ ] Two uvicorn workers can cancel each other's runs.
- [ ] Postgres connection pool size is configurable.
- [ ] HTTPX client uses shared connection limits.
- [ ] Composite indexes speed up query log reads.
- [ ] Load test passes with 100 concurrent authenticated users.
- [ ] Scaling documentation written.
- [ ] All existing tests pass.

---

*End of Phase 9 Plan*
