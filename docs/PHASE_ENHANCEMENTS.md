# Phase Enhancement Recommendations
> Top 0.5% — Professional · Safe · Robust · Fast · Secure  
> Severity: 🔴 CRITICAL · 🟠 HIGH · 🟡 MEDIUM · 🟢 LOW

---

## Phase 1 — Foundation: Domain + Ports + Postgres Schema

### 🔴 CRITICAL

**1.1 Deprecated `datetime.utcnow()` throughout domain**  
`User.created_at`, `UsageQuota.updated_at`, and `period_start` all use `datetime.utcnow()`.  
In Python 3.12+ this is deprecated and returns a naïve datetime, which breaks timezone-aware comparisons.

```python
# Replace every occurrence of:
field(default_factory=datetime.utcnow)
# With:
field(default_factory=lambda: datetime.now(timezone.utc))
```

Add `from datetime import datetime, timezone` at the top of `saas.py`.

**1.2 `QuotaService.increment()` is a no-op stub**  
The method has `pass` as its body. This means quota is *never actually incremented* after a successful run. Every query will appear free. Either implement it or raise `NotImplementedError` so the gap is explicit at test time.

```python
async def increment(self, user_id: str, preset: str) -> QuotaResult:
    return await self._repository.check_and_increment(user_id, preset)
```

**1.3 `period_start` calculation silently truncates timezone**  
`datetime.utcnow().replace(day=1, hour=0, ...)` returns a naïve datetime. When compared to timezone-aware `period_start` values from Postgres (`TIMESTAMPTZ`), this raises `TypeError: can't compare offset-naive and offset-aware datetimes`.

```python
period_start: datetime = field(
    default_factory=lambda: datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
)
```

**1.4 Migration uses `uuid_generate_v4()` but Supabase Auth uses its own UUID format**  
`user_profiles.id` should be typed to reference `auth.users(id)` — Supabase's internal auth table. Without this FK the application-layer user_profile table will drift from auth state (orphaned profiles, ghost users).

```sql
-- In 001_saas_init.py upgrade():
sa.Column("id", sa.UUID(), nullable=False),  # Must match auth.users(id) UUID
sa.ForeignKeyConstraint(["id"], ["auth.users.id"], ondelete="CASCADE"),
```

### 🟠 HIGH

**1.5 `Subscription` is mutable but should be frozen**  
`User` and `QuotaResult` are `frozen=True`, but `Subscription` is not. This inconsistency means subscription state can be mutated accidentally anywhere in the codebase, making bugs harder to trace.

```python
@dataclass(frozen=True)
class Subscription:
    ...
    # Replace mutable default fields with:
    stripe_subscription_id: Optional[str] = None
    current_period_end: Optional[datetime] = None
```

**1.6 No `NOT NULL` constraints on critical enum columns**  
`subscriptions.tier` and `subscriptions.status` allow NULL in the schema, but the domain model requires them. This causes silent `None` values to appear after a Postgres round-trip.

```python
sa.Column("tier", sa.Text(), nullable=False),
sa.Column("status", sa.Text(), nullable=False),
```

**1.7 Missing CHECK constraints for enum values**  
Without DB-level CHECK constraints, any string can be stored in `tier`/`status` columns, allowing the Postgres layer to drift from the Python enum definition.

```sql
ALTER TABLE subscriptions
  ADD CONSTRAINT check_tier CHECK (tier IN ('free','pro','enterprise')),
  ADD CONSTRAINT check_status CHECK (status IN ('active','cancelled','past_due','trialing'));
```

**1.8 `query_log` should use a BRIN index instead of B-tree for time-series**  
The `idx_query_log_created` B-tree index on `created_at` is expensive to maintain on an append-only table. Replace with BRIN which is 10x smaller and faster for sequential inserts:

```python
op.execute("CREATE INDEX idx_query_log_created_brin ON query_log USING BRIN (created_at)")
```

**1.9 `get_quota` SELECT-then-INSERT is a TOCTOU race condition**  
Two concurrent requests for a new user can both see `row is None`, both try to INSERT, and the second will hit a unique constraint violation unhandled by the current code.

```sql
-- Use a single statement:
INSERT INTO usage_quotas (user_id, tier, max_queries)
VALUES ($1, $2, $3)
ON CONFLICT (user_id) DO NOTHING
RETURNING *;
-- Then do one SELECT if RETURNING returns nothing
```

### 🟡 MEDIUM

**1.10 `QuotaResult.retry_after` should be timezone-aware seconds, not just a hint**  
Compute this using the actual period_start + 1 month instead of an approximation. Off-by-one errors around month transitions cause incorrect Retry-After headers.

**1.11 `UsageQuota` has no `log_query` field — audit uses a separate table**  
This is fine architecturally, but the domain entity should expose `query_count: int` derived from the log table for dashboard display. Add a read-model helper.

**1.12 Domain imports `from typing import Optional` — use `X | None` syntax**  
Python 3.10+ supports `str | None` which is more readable and slightly faster. Standardize throughout `saas.py`.

**1.13 Missing `__all__` in `src/reasoner/application/ports/__init__.py`**  
Without explicit `__all__`, wildcard imports expose private implementation details.

### 🟢 LOW

**1.14 Consider `__slots__` on frequently-instantiated domain entities**  
`User` and `QuotaResult` are created on every authenticated request. Adding `__slots__` reduces memory overhead by ~30-50 bytes per instance.

**1.15 Add `model_config` / `__eq__` contract tests**  
Tests should verify that two `User` objects with the same fields are equal, and that frozen dataclasses raise `FrozenInstanceError` on mutation attempts.

---

## Phase 2 — Auth Integration: Supabase Adapter + FastAPI Dependencies

### 🔴 CRITICAL

**2.1 Global `_auth_adapter` is not thread-safe**  
`get_auth_adapter()` and `set_auth_adapter()` use a module-level global modified without locks. Under concurrent startup requests in a multi-threaded WSGI or during tests that call `set_auth_adapter`, this is a data race.

```python
import threading
_lock = threading.Lock()
_auth_adapter: Optional[AuthPort] = None

def get_auth_adapter() -> AuthPort:
    global _auth_adapter
    with _lock:
        if _auth_adapter is None:
            _auth_adapter = _create_adapter()
        return _auth_adapter
```

**2.2 UUID creation from API key hash can overflow**  
`UUID(int=int(api_key.key_hash[:32], 16))` will raise `ValueError` if the 32-char hex slice exceeds the 128-bit UUID integer range (which it will for many hash values since `key_hash` may be a full hex digest).

```python
import hashlib
user_uuid = UUID(hashlib.sha256(api_key.key_hash.encode()).hexdigest()[:32])
```

**2.3 JWT "looks like a JWT" heuristic is bypassable**  
An attacker can craft an API key containing exactly 2 dots to route it through the JWT path, causing an auth bypass. Use a typed header instead:

```python
# Option A: explicit prefix
if token.startswith("jwt_"):
    return await service.authenticate(token[4:])
# Option B: check length — HS256 JWT segments have predictable minimum lengths
```

**2.4 `LocalAuthAdapter.create_token()` is synchronous, mismatches `authenticate()` contract**  
The `AuthPort` protocol declares `authenticate` as `async`. Any code calling `create_token()` directly in an async context may accidentally block the event loop if the implementation ever does I/O.

```python
async def create_token(self, user_id: str, email: str, ...) -> str:
    return await asyncio.get_event_loop().run_in_executor(
        None, self._create_token_sync, user_id, email, ...
    )
```

### 🟠 HIGH

**2.5 Rate limiter temporary config mutation is not thread-safe**  
`Task 2.5.1` modifies `self.config`, calls `is_allowed()`, then restores. Between save and restore, a concurrent coroutine sees the modified config. Use a separate method with explicit limit parameters instead.

```python
async def is_allowed_for_user(self, user_id: str, multiplier: float) -> tuple[bool, dict]:
    effective_limit = int(self.config.requests_per_minute * multiplier)
    return await self._check_with_limit(user_id, effective_limit)
```

**2.6 No logout token invalidation / revocation list**  
`signOut()` on the frontend calls Supabase, but the JWT remains valid until expiry (typically 1 hour). Add a Redis-backed JWT revocation set:

```python
# On logout:
await redis.setex(f"revoked_jwt:{jti_claim}", expiry_seconds, "1")

# In authenticate():
jti = payload.get("jti")
if jti and await redis.exists(f"revoked_jwt:{jti}"):
    raise AuthenticationError("Token has been revoked", status_code=401)
```

**2.7 `Authorization: Bearer <jwt>` redirect on 401 leaks the current URL**  
`window.location.href = '/login'` in `apiFetch` leaks the current path. Store the intended destination so the user can be redirected back after login:

```typescript
const returnTo = encodeURIComponent(window.location.pathname + window.location.search);
window.location.href = `/login?returnTo=${returnTo}`;
```

**2.8 SUPABASE_SERVICE_ROLE_KEY scope comment missing**  
The service role key bypasses Row Level Security. The code should document that it must NEVER be used for client-side operations. Add a startup assertion:

```python
if os.environ.get("ENVIRONMENT") == "production":
    assert "service_role" not in os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", ""), \
        "FATAL: service role key exposed as public env var"
```

### 🟡 MEDIUM

**2.9 Login/Signup pages have no CSRF protection for form submissions**  
Since the pages use `fetch`, not cookies, CSRF is less critical — but the forms should include rate limiting on the backend (`/api/auth/*`) and a honeypot field.

**2.10 `get_optional_user` silently swallows all exceptions**  
`except Exception: return None` hides malformed tokens, network errors, and misconfigurations. Log the exception at WARNING level so operators can see auth failures:

```python
except Exception as exc:
    logger.warning("Optional auth failed (non-fatal): %s", exc)
    return None
```

**2.11 `providers.tsx` calls `supabase.auth.getSession()` but should use `supabase.auth.getUser()`**  
`getSession()` reads from local storage and does not verify with Supabase server. `getUser()` validates the JWT against the auth server:

```typescript
const { data: { user } } = await supabase.auth.getUser();
setUser(user);
```

**2.12 Missing `httpOnly` flag guidance for session cookies**  
If Supabase SSR cookies are ever used (e.g., for Next.js App Router), the plan should specify `httpOnly: true, sameSite: 'lax', secure: true`.

### 🟢 LOW

**2.13 Auth pages violate the design quality rules**  
The login/signup pages use raw Tailwind utility stacks with no hierarchy, no motion, no intentional typography. These are the first thing users see. They should use the project's design system (dark luxury or Swiss/International direction matching the rest of the UI).

**2.14 `LocalAuthAdapter` should refuse to instantiate in `ENVIRONMENT=production`**

```python
def __init__(self, secret: str | None = None):
    if os.environ.get("ENVIRONMENT") == "production":
        raise RuntimeError("LocalAuthAdapter must never be used in production")
```

---

## Phase 3 — Usage Quotas + Tier Enforcement

### 🔴 CRITICAL

**3.1 `_get_quota_service()` creates a new asyncpg pool on every request**  
The factory function `_get_quota_service()` is called inside FastAPI dependencies on every request. `PostgresQuotaRepository.__init__` stores the DSN and creates the pool lazily, but because a new `PostgresQuotaRepository` is instantiated each time, `self._pool` starts as `None` and a new pool is created. Under load, this opens hundreds of simultaneous asyncpg pools, exhausting database connections.

**Fix:** Use a module-level singleton with `asynccontextmanager` lifespan:

```python
# In api/__init__.py lifespan:
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.quota_repo = PostgresQuotaRepository(settings.DATABASE_URL)
    app.state.quota_service = QuotaService(CachedQuotaRepository(app.state.quota_repo))
    yield
    await app.state.quota_repo.close()  # Close pool on shutdown

# In dependencies.py:
def _get_quota_service(request: Request) -> QuotaService:
    return request.app.state.quota_service
```

**3.2 `check_quota_if_authenticated` calling `check_quota(user)` as a plain function is incorrect**  
`check_quota` is a FastAPI dependency function. Calling it as `await check_quota(user)` bypasses the dependency injection mechanism and injects wrong arguments. This will either raise a `TypeError` at runtime or silently skip the check.

```python
async def check_quota_if_authenticated(
    user: User | None = Depends(get_optional_user),
    request: Request = None,
) -> QuotaResult | None:
    if user is None:
        return None
    service = _get_quota_service(request)
    result = await service.check(str(user.id), SubscriptionTier.FREE)
    if not result.allowed:
        raise HTTPException(status_code=429, detail={...})
    return result
```

**3.3 `CachedQuotaRepository.get_quota()` deserializes datetime strings as raw strings**  
`json.loads(cached)` returns `period_start` and `updated_at` as ISO strings, but `UsageQuota` expects `datetime` objects. This causes `AttributeError: 'str' object has no attribute 'replace'` when `QuotaService` compares `quota.period_start < current_period_start`.

```python
from datetime import datetime

return UsageQuota(
    user_id=UUID(data["user_id"]),
    tier=SubscriptionTier(data["tier"]),
    used_queries=data["used_queries"],
    max_queries=data["max_queries"],
    period_start=datetime.fromisoformat(data["period_start"]),
    updated_at=datetime.fromisoformat(data["updated_at"]),
)
```

**3.4 `reset_all_quotas_monthly()` is a stub with a comment and no implementation**  
This is the production cron job responsible for resetting all 0 user quotas at month start. Leaving it as a comment means quotas are never reset and every user gets permanently blocked after their first month.

```python
async def reset_all_quotas_monthly() -> None:
    pool = await repo._get_pool()
    result = await pool.execute(
        """
        UPDATE usage_quotas
        SET used_queries = 0,
            period_start = date_trunc('month', NOW()),
            updated_at = NOW()
        WHERE period_start < date_trunc('month', NOW())
        """
    )
    logger.info("Monthly quota reset complete. Rows updated: %s", result)
```

### 🟠 HIGH

**3.5 No idempotency key for quota increment — double-counting on retries**  
If a client retries a `POST /api/run` request (e.g., on network timeout), the quota could be incremented twice. Add a client-provided idempotency key:

```python
# In /api/run:
idempotency_key = request.headers.get("X-Idempotency-Key") or str(uuid4())
# Store in Redis with TTL 24h to detect replays
if await redis.exists(f"idempotent:{idempotency_key}"):
    # Return cached response or 200 without re-running
    ...
await redis.setex(f"idempotent:{idempotency_key}", 86400, "1")
```

**3.6 `UsageBadge` breaks for Enterprise (unlimited) users when `max = -1`**  
`(quota.used / quota.max) * 100` will return a negative percentage for `max_queries = -1`. Add a guard:

```tsx
if (quota.max === -1) {
  return <div className="text-xs font-medium text-green-500">∞ queries</div>;
}
```

**3.7 `useQuota` hook never refreshes after a successful pipeline run**  
The hook fetches on mount and exposes a `refresh` function, but nothing calls `refresh()` after `/api/run` completes. The usage badge will show stale counts until the page is reloaded.

```typescript
// In usePipelineStream.ts, after stream completes:
quotaHook.refresh();
```

**3.8 Quota check uses `SubscriptionTier.FREE` hardcoded — tier never fetched from DB**  
Phase 3 has `user_tier = SubscriptionTier.FREE` as a placeholder in `check_quota`. This means Pro users are always blocked at 20 queries and Enterprise users are always rate-limited. This must be wired before Phase 3 ships, not deferred to Phase 4.

```python
async def check_quota(user: User = Depends(get_current_user)) -> QuotaResult:
    # Fetch actual tier from subscriptions table
    tier = await _get_user_tier(str(user.id))  # Must be implemented in Phase 3
    ...
```

### 🟡 MEDIUM

**3.9 The monthly reset cron needs a distributed lock**  
If multiple workers are running, all may attempt `reset_all_quotas_monthly()` simultaneously. Use a Redis-based distributed lock:

```python
async def reset_all_quotas_monthly() -> None:
    lock_key = "cron:quota_reset"
    acquired = await redis.set(lock_key, "1", ex=300, nx=True)
    if not acquired:
        logger.info("Quota reset already running in another worker, skipping")
        return
    try:
        await _do_reset()
    finally:
        await redis.delete(lock_key)
```

**3.10 No error state in `useQuota` hook**  
If `/api/quota` returns 401 or 500, the hook silently stays in loading state forever. Expose `error: Error | null`.

**3.11 Missing fallback for Redis failures in `CachedQuotaRepository`**  
If Redis is down, `get_quota` will throw an `aioredis.ConnectionError`. Add a circuit-breaker fallback to bypass cache:

```python
try:
    cached = await self._redis.get(cache_key)
except Exception:
    logger.warning("Redis unavailable, bypassing quota cache")
    return await self._underlying.get_quota(user_id)
```

---

## Phase 4 — Billing with Stripe

### 🔴 CRITICAL

**4.1 All Stripe SDK calls are synchronous but called in async context**  
`stripe.checkout.Session.create()`, `stripe.Customer.list()`, etc. are synchronous blocking calls. Calling them directly in an `async def` function blocks the entire event loop for potentially 500ms–2s per call, making the server unresponsive under load.

```python
import asyncio

async def create_checkout_session(self, ...) -> str:
    session = await asyncio.to_thread(
        stripe.checkout.Session.create,
        payment_method_types=["card"],
        ...
    )
    return session.url
```

All Stripe calls in the adapter must be wrapped in `asyncio.to_thread()`.

**4.2 Subscription upsert resets `used_queries = 0` on every subscription event**  
The `_upsert_subscription()` function in Day 3 includes `used_queries = 0` in the `ON CONFLICT DO UPDATE`. This means any webhook event (even a payment succeeded for a renewal) resets the user's monthly query count, effectively giving them a free quota reset on every billing cycle event, not just at month start.

```sql
-- Remove used_queries = 0 from upsert:
ON CONFLICT (stripe_sub_id) DO UPDATE SET
    tier = EXCLUDED.tier,
    status = EXCLUDED.status,
    current_period_end = EXCLUDED.current_period_end
    -- Do NOT reset used_queries here
```

**4.3 Webhook handler returns 400 on invalid payload — causes infinite Stripe retries**  
Stripe retries any non-2xx response. A malformed body should return 400, but a signature verification failure indicates a replay or man-in-the-middle attack — the correct response is 403, not 400. More importantly, parse errors on *valid* Stripe events should return 200 with an error log to prevent Stripe from retrying indefinitely.

```python
except stripe.error.SignatureVerificationError:
    raise HTTPException(status_code=403, detail="Invalid signature")
except Exception as exc:
    logger.error("Webhook processing error: %s", exc)
    return {"status": "error", "detail": str(exc)}  # Always 200 to prevent retries
```

**4.4 No Stripe customer ID stored in DB — portal lookup by metadata is unreliable**  
`create_portal_session` does `stripe.Customer.list(metadata={"reasoner_user_id": user_id})`. This is a Stripe API call that can fail silently if the metadata was never set, and the metadata must be set explicitly at checkout. Store the Stripe customer ID in Postgres instead:

```sql
ALTER TABLE subscriptions ADD COLUMN stripe_customer_id TEXT;
CREATE UNIQUE INDEX ON subscriptions (stripe_customer_id);
```

**4.5 `Subscription(id=UUID(int=0), ...)` creates an invalid null-UUID**  
`UUID(int=0)` is `00000000-0000-0000-0000-000000000000`. Using this as a subscription ID means multiple subscription objects will collide on their "identity", breaking any dict/set-based deduplication.

```python
from uuid import uuid4
Subscription(id=uuid4(), ...)  # or make id Optional[UUID] = None for Stripe-synced records
```

### 🟠 HIGH

**4.6 No Stripe error handling — any SDK exception crashes the endpoint**  
The adapter has no `try/except stripe.error.StripeError`. A card decline, rate limit, or temporary Stripe outage will return a 500 to the user instead of a meaningful message.

```python
try:
    session = await asyncio.to_thread(stripe.checkout.Session.create, ...)
except stripe.error.InvalidRequestError as exc:
    raise ValueError(f"Invalid checkout parameters: {exc.user_message}")
except stripe.error.StripeError as exc:
    logger.error("Stripe error: %s", exc)
    raise RuntimeError("Payment service temporarily unavailable")
```

**4.7 No rate limiting on `/api/billing/webhook`**  
The webhook endpoint is public and unauthenticated by design. Without rate limiting, it's a free DDoS vector that exhausts the database connection pool.

```python
# Add to billing_router.py:
from slowapi import Limiter
@router.post("/webhook")
@limiter.limit("100/minute")
async def stripe_webhook(request: Request):
    ...
```

**4.8 Missing idempotency key in checkout session creation**  
Stripe supports idempotency keys on all write operations. Without one, duplicate checkout sessions can be created if the network request is retried.

```python
session = await asyncio.to_thread(
    stripe.checkout.Session.create,
    ...,
    idempotency_key=f"checkout-{user_id}-{tier.value}-{int(time.time() // 3600)}",
)
```

**4.9 Webhook deduplication by `event.id` is missing**  
Stripe guarantees at-least-once delivery. Without deduplication, `checkout.session.completed` can be processed twice, creating two subscriptions for one payment.

```python
# At the start of handle_stripe_webhook:
event_id = event["id"]
already_processed = await redis.set(f"stripe_event:{event_id}", "1", ex=86400, nx=True)
if not already_processed:
    logger.info("Duplicate Stripe event %s, skipping", event_id)
    return {"status": "duplicate"}
```

### 🟡 MEDIUM

**4.10 Pricing page has hardcoded USD prices — must sync with Stripe**  
`'$12/mo'` in the React component will diverge from the actual Stripe price. Fetch prices dynamically:

```python
@router.get("/prices")
async def get_prices():
    prices = await asyncio.to_thread(stripe.Price.list, active=True, expand=["data.product"])
    return [{"tier": p.product.metadata.get("tier"), "amount": p.unit_amount / 100, ...} for p in prices.data]
```

**4.11 No trial period configuration**  
The checkout session creation has no `trial_period_days`. SaaS products typically offer a 14-day trial. Add this as a configurable env var:

```python
STRIPE_TRIAL_DAYS = int(os.environ.get("STRIPE_TRIAL_DAYS", "0"))
# In create_checkout_session:
subscription_data={"trial_period_days": STRIPE_TRIAL_DAYS} if STRIPE_TRIAL_DAYS > 0 else {},
```

**4.12 `_tier_from_price()` uses `os.environ.get()` on every call**  
This does a dict lookup on every webhook event. Cache the mapping at adapter initialization:

```python
def __init__(self, api_key: str | None = None):
    stripe.api_key = api_key or os.environ["STRIPE_SECRET_KEY"]
    self._price_to_tier = {
        os.environ["STRIPE_PRO_PRICE_ID"]: SubscriptionTier.PRO,
        os.environ["STRIPE_ENTERPRISE_PRICE_ID"]: SubscriptionTier.ENTERPRISE,
    }
```

---

## Phase 5 — Docker + Deployment

### 🔴 CRITICAL

**5.1 `--workers 2` with `uvicorn` does not work with async lifespan events**  
`uvicorn --workers 2` spawns multiple processes but doesn't share the asyncpg pool or Redis connections across workers, and lifespan events run per-worker. Use `gunicorn` with `uvicorn` worker class for proper multi-process management:

```dockerfile
CMD ["gunicorn", "asgi:app",
     "--worker-class", "uvicorn.workers.UvicornWorker",
     "--workers", "2",
     "--bind", "0.0.0.0:8000",
     "--timeout", "120",
     "--keep-alive", "5",
     "--max-requests", "1000",
     "--max-requests-jitter", "100"]
```

**5.2 Backend Dockerfile runs as root**  
The commented-out non-root user section is a security risk. A compromised app running as root can modify system files, read secrets, and escape the container more easily.

```dockerfile
RUN useradd --create-home --shell /bin/bash --uid 1001 appuser && \
    chown -R appuser:appuser /app
USER appuser
```

**5.3 Hardcoded `POSTGRES_PASSWORD=postgres` in `docker-compose.yml`**  
This is the default password that automated scanners actively probe for. Use Docker secrets or at minimum a `.env` file that is `.gitignore`d:

```yaml
postgres:
  environment:
    POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
  secrets:
    - postgres_password
```

### 🟠 HIGH

**5.4 No `.dockerignore` — entire working directory is sent to Docker build context**  
Without `.dockerignore`, the `cache/`, `.git/`, `history/`, `__pycache__/`, and any `.env` files are sent to the daemon. This leaks secrets and makes builds slow.

```
# .dockerignore
.git/
.env
.env.*
cache/
history/
__pycache__/
*.pyc
*.pyo
node_modules/
.pytest_cache/
```

**5.5 No restart policies in `docker-compose.yml`**  
Services should restart automatically after crashes:

```yaml
services:
  backend:
    restart: unless-stopped
  frontend:
    restart: unless-stopped
  postgres:
    restart: unless-stopped
  redis:
    restart: unless-stopped
```

**5.6 `/api/health` creates a new Postgres pool on every health check call**  
`PostgresQuotaRepository(settings.DATABASE_URL)` in the health handler creates a new pool per call. This exhausts connections during aggressive health checks (Kubernetes does 10s intervals).

Use the singleton pool established in the lifespan context (see Phase 3, item 3.1):

```python
@app.get("/api/health")
async def health_check(request: Request):
    pool = request.app.state.db_pool
    await pool.fetchval("SELECT 1")
```

**5.7 Frontend Dockerfile copies entire `node_modules` including dev dependencies**  
`npm ci` installs all dependencies including `devDependencies`. The runtime stage should exclude them:

```dockerfile
FROM node:22-alpine AS builder
RUN npm ci  # All deps needed for build

FROM node:22-alpine AS runtime
# Only copy prod deps:
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
CMD ["node", "server.js"]
```

This requires `output: 'standalone'` in `next.config.js` and reduces the image size from ~800MB to ~150MB.

**5.8 Caddy `auto_https off` is in the production Caddyfile template**  
The Day 4 template shows `auto_https off` at the top. This disables HTTPS globally and should never appear in the production config. Move it to a `Caddyfile.dev` only.

### 🟡 MEDIUM

**5.9 No resource limits in Compose**  
Without `mem_limit` and `cpus`, a runaway LLM stream can consume all available memory and OOM-kill other containers:

```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 1G
        reservations:
          memory: 256M
```

**5.10 `docker-compose.yml` uses deprecated `version: "3.9"` key**  
Docker Compose v2 (bundled with Docker Desktop 4.1+) ignores the `version` key. Remove it to avoid deprecation warnings:

```yaml
# Remove: version: "3.9"
services:
  ...
```

**5.11 Missing `--init` for proper PID 1 signal handling**  
Without `init: true`, `CMD` runs as PID 1 and may not handle `SIGTERM` correctly. This causes slow container shutdowns (30s timeout):

```yaml
services:
  backend:
    init: true
```

**5.12 SearXNG service has no health check or resource limits**  
SearXNG can consume significant memory. Add a health check and resource limit.

---

## Phase 6 — Security Hardening + GDPR

### 🔴 CRITICAL

**6.1 `/api/metrics` endpoint (Phase 7) is exposed publicly**  
Prometheus metrics expose internal counters, user counts, error rates, and timing data. This is an information-disclosure vulnerability that helps attackers enumerate usage patterns.

```python
# In metrics endpoint (add to Phase 6 security hardening):
@app.get("/api/metrics")
async def metrics(request: Request, _: None = Depends(require_internal_token)):
    ...

# Or restrict by IP in Caddy:
handle /api/metrics {
    @external not remote_ip 10.0.0.0/8 172.16.0.0/12
    respond @external "Forbidden" 403
    reverse_proxy backend:8000
}
```

**6.2 GDPR `/api/account/delete` lacks Stripe subscription cancellation**  
Deleting from `user_profiles` CASCADE-deletes from `subscriptions`, but the Stripe subscription remains active. The user will continue to be charged after "deletion".

```python
@router.post("/account/delete")
async def delete_account(user: User = Depends(get_current_user)):
    # 1. Cancel Stripe subscription first
    stripe_sub = await pool.fetchval(
        "SELECT stripe_sub_id FROM subscriptions WHERE user_id = $1 AND status = 'active'",
        str(user.id)
    )
    if stripe_sub:
        await asyncio.to_thread(stripe.Subscription.modify, stripe_sub, cancel_at_period_end=True)
    # 2. Delete from Supabase Auth
    supabase.auth.admin.delete_user(str(user.id))
    # 3. Delete from local DB (CASCADE handles rest)
    await pool.execute("DELETE FROM user_profiles WHERE id = $1", str(user.id))
    return {"status": "deleted"}
```

**6.3 `grep -r "eyJ.*eyJ"` is insufficient for secret detection**  
This pattern only catches base64-encoded JWTs. Use a proper secrets scanner in CI:

```yaml
# .github/workflows/security.yml
- name: Secret scanning
  uses: trufflesecurity/trufflehog@main
  with:
    path: ./
    base: main
    extra_args: --only-verified
```

**6.4 Rate limiting missing on `/api/account/delete` and `/api/account/export`**  
These endpoints do expensive DB queries across all tables. Without rate limiting they are a DoS vector. A user can export 100MB of data on every request:

```python
@router.get("/account/export")
@limiter.limit("3/hour")  # 3 exports per hour maximum
async def export_data(...):
```

For large datasets, make it async (trigger background job, email download link) rather than synchronous.

### 🟠 HIGH

**6.5 Missing Content Security Policy (CSP) header**  
The Caddy config adds HSTS but not CSP. A missing CSP header means any injected script runs with full page access:

```
header {
    Content-Security-Policy "default-src 'self'; script-src 'self' 'nonce-{RANDOM}' https://js.stripe.com; frame-src https://js.stripe.com; img-src 'self' data:; connect-src 'self' https://*.supabase.co wss://*.supabase.co;"
}
```

**6.6 Audit middleware logs full URL path which may contain PII**  
`request.url.path` can contain user IDs, emails, or other sensitive data in query parameters. Sanitize before logging:

```python
# Scrub query parameters from logged URL:
safe_path = request.url.path  # Path only, no query string
```

**6.7 GDPR data export is synchronous and unbounded**  
`pool.fetch("SELECT * FROM query_log WHERE user_id = $1")` can return millions of rows, loading them all into memory and causing an OOM crash. Add pagination:

```python
queries = await pool.fetch(
    "SELECT * FROM query_log WHERE user_id = $1 ORDER BY created_at DESC LIMIT 10000",
    str(user.id)
)
export["truncated"] = len(queries) == 10000
```

**6.8 Missing `Subresource Integrity` for external CDN assets**  
Any external CSS/JS (Stripe.js, fonts) should use `integrity` attributes to prevent supply-chain attacks:

```html
<script src="https://js.stripe.com/v3/" 
        integrity="sha384-..." 
        crossorigin="anonymous"></script>
```

### 🟡 MEDIUM

**6.9 `bandit` without `-l` flag reports low-severity issues as errors**  
Run with severity filter to focus on real issues:

```bash
bandit -r src/ -l HIGH -i HIGH  # Only HIGH severity issues fail CI
```

**6.10 Missing `SECURITY.md` and responsible disclosure policy**  
Add `SECURITY.md` at repo root describing how to report vulnerabilities privately (email, not public issues):

```markdown
# Security Policy
Please report security vulnerabilities to security@yourcompany.com.
Do not create public GitHub issues for security vulnerabilities.
We aim to respond within 48 hours.
```

**6.11 No 2FA / MFA enforcement for account deletion**  
The GDPR delete endpoint is protected by JWT only. Add a re-authentication step (confirm password or email OTP) before deleting an account, to prevent account hijacking via stolen token.

**6.12 `X-Request-ID` header missing for distributed tracing correlation**

```python
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
```

---

## Phase 7 — Monitoring + Observability

### 🔴 CRITICAL

**7.1 `REASONER_QUERY_DURATION.labels(...).time()` blocks the event loop**  
Prometheus's `.time()` context manager is synchronous and uses `time.time()`. When wrapping an `async for` generator, it only measures the time until the first `yield`, not the total streaming duration. Use explicit start/end timing:

```python
start = time.perf_counter()
try:
    async for chunk in run_stream_cached(req):
        yield chunk
    status = "success"
except Exception:
    status = "error"
    raise
finally:
    duration = time.perf_counter() - start
    REASONER_QUERY_DURATION.labels(preset=req.preset).observe(duration)
    REASONER_QUERIES_TOTAL.labels(tier=user_tier, preset=req.preset, status=status).inc()
```

**7.2 `metrics_endpoint` is a plain function, not `async def`**  
FastAPI routes must be `async def` or `def` (sync). `generate_latest()` is CPU-bound and should be run in a thread pool to avoid blocking the event loop:

```python
async def metrics_endpoint() -> Response:
    content = await asyncio.to_thread(generate_latest)
    return Response(content=content, media_type=CONTENT_TYPE_LATEST)
```

**7.3 `REASONER_ACTIVE_USERS` gauge is defined but never updated**  
This metric will always show 0, giving a false impression of the system being idle. Remove it or implement it:

```python
# In a background task running every 5 minutes:
async def update_active_users_metric():
    count = await pool.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM query_log WHERE created_at > NOW() - INTERVAL '24 hours'"
    )
    REASONER_ACTIVE_USERS.set(count)
```

### 🟠 HIGH

**7.4 Load test uses `asyncio.gather` on synchronous `TestClient`**  
`TestClient` is synchronous (based on `requests`). Wrapping it with `asyncio.gather` does NOT make it concurrent — all 50 requests run sequentially. Use `httpx.AsyncClient` for actual concurrency:

```python
@pytest.mark.asyncio
async def test_concurrent_queries_with_metrics():
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        tasks = [
            client.post("/api/run", json={"problem": "2+2", "preset": "multi-perspective-budget"})
            for _ in range(50)
        ]
        responses = await asyncio.gather(*tasks)
    assert all(r.status_code == 200 for r in responses)
```

**7.5 `traces_sample_rate=0.1` is too low for a production system in early stage**  
At 10% sampling, you will miss the majority of slow/erroring requests during the first weeks of production. Start at 1.0 (100%) and reduce as traffic grows:

```python
sentry_sdk.init(
    traces_sample_rate=float(os.environ.get("SENTRY_TRACES_RATE", "1.0")),
)
```

**7.6 Missing connection pool metrics for Postgres and Redis**  
Database pool exhaustion is a common production failure. Instrument it:

```python
REASONER_DB_POOL_SIZE = Gauge('reasoner_db_pool_size', 'Postgres pool size')
REASONER_DB_POOL_ACQUIRED = Gauge('reasoner_db_pool_acquired', 'Active Postgres connections')

# Update in health check or background task:
REASONER_DB_POOL_SIZE.set(pool.get_size())
REASONER_DB_POOL_ACQUIRED.set(pool.get_size() - pool.get_idle_size())
```

**7.7 No distributed tracing — correlated logs across services are impossible**  
Add OpenTelemetry for end-to-end trace correlation across FastAPI, Redis, and Postgres:

```bash
pip install opentelemetry-sdk opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-asyncpg
```

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)
```

### 🟡 MEDIUM

**7.8 `AlertManager` rules reference wrong metric name**  
`reasoner_queries_total{status="error"}` won't match the label `status="error"` unless the pipeline explicitly sets this label on failures. Add an explicit error counter:

```python
REASONER_ERRORS_TOTAL = Counter('reasoner_errors_total', 'Pipeline errors', ['preset', 'error_type'])
# On LLM timeout:
REASONER_ERRORS_TOTAL.labels(preset=req.preset, error_type="llm_timeout").inc()
```

**7.9 `set_log_context()` uses `contextvars` but is never cleaned up**  
`ContextVar` values persist for the lifetime of the task/request. If a request fails before `set_log_context` is called, the previous request's context bleeds into the next. Use a middleware that resets context on each request:

```python
class LogContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        _log_context.set({})  # Reset for each request
        response = await call_next(request)
        return response
```

**7.10 Missing SLO / error budget tracking**  
Define explicit SLOs (e.g., 99.5% success rate, p95 latency < 5s) and track burn rate:

```yaml
# alerts.yml
- alert: SLOErrorBudgetBurning
  expr: |
    (1 - (sum(rate(reasoner_queries_total{status="success"}[1h])) /
           sum(rate(reasoner_queries_total[1h])))) > 0.005
  for: 5m
  annotations:
    summary: "Error budget burning too fast (>0.5% error rate over 1h)"
```

---

## Phase 8 — Frontend Self-Service UI

### 🔴 CRITICAL

**8.1 `window.location.href = data.checkout_url` is an open redirect**  
If `checkout_url` is ever controlled by an attacker (e.g., via a MITM, a compromised backend, or XSS), this redirects users to an arbitrary URL. Validate the URL before redirecting:

```typescript
const url = new URL(data.checkout_url);
if (url.hostname !== 'checkout.stripe.com') {
  throw new Error('Unexpected checkout URL');
}
window.location.href = data.checkout_url;
```

**8.2 `err: any` throughout auth pages suppresses TypeScript safety**  
Using `catch (err: any)` disables all TypeScript type checking on the error object. Use proper error typing:

```typescript
import { AuthError } from '@supabase/supabase-js';

} catch (err) {
  if (err instanceof AuthError) {
    setError(err.message);
  } else {
    setError('An unexpected error occurred');
    console.error(err);
  }
}
```

**8.3 Auth pages have no loading state on form submit**  
A user who double-clicks "Sign In" will submit the form twice, creating race conditions and confusing UX. Disable the button during submission:

```typescript
const [submitting, setSubmitting] = useState(false);
const handleSubmit = async (e) => {
  e.preventDefault();
  if (submitting) return;
  setSubmitting(true);
  try {
    await signInWithEmail(email, password);
  } finally {
    setSubmitting(false);
  }
};
<button disabled={submitting}>...</button>
```

### 🟠 HIGH

**8.4 `forgot-password` page has no email format validation before calling Supabase**  
Supabase's `resetPasswordForEmail()` will always return success (to prevent email enumeration), but sending requests with obviously invalid emails wastes API quota. Add client-side validation:

```typescript
const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
if (!emailRegex.test(email)) {
  setError('Please enter a valid email address');
  return;
}
```

**8.5 `UpgradeModal` has no error handling on the checkout fetch**  
If `/api/billing/checkout` returns 500, the modal hangs in loading state with no feedback:

```typescript
const handleUpgrade = async () => {
  setLoading(true);
  setError('');
  try {
    const res = await apiFetch('/api/billing/checkout', {...});
    if (!res.ok) throw new Error(`Checkout failed: ${res.status}`);
    const data = await res.json();
    const url = new URL(data.checkout_url);
    if (url.hostname !== 'checkout.stripe.com') throw new Error('Invalid URL');
    window.location.href = data.checkout_url;
  } catch (err) {
    setError(err instanceof Error ? err.message : 'Checkout unavailable');
  } finally {
    setLoading(false);
  }
};
```

**8.6 Preset lock uses hardcoded string `'pro'` instead of the tier enum**  
```tsx
// Wrong:
const tier = user ? 'pro' : 'free';
const locked = p.tier === 'premium' && tier !== 'pro';

// Correct: fetch actual tier from /api/billing/subscription
const { subscription } = useSubscription();
const locked = p.requiredTier === 'pro' && subscription?.tier !== 'pro';
```

**8.7 Dashboard `useEffect` has no AbortController for cleanup**  
The `apiFetch('/api/history')` call in `useEffect` can complete after the component unmounts, causing a state update on an unmounted component:

```typescript
useEffect(() => {
  const controller = new AbortController();
  apiFetch('/api/history', { signal: controller.signal })
    .then(r => r.json())
    .then(data => setHistory(data.history || []))
    .catch(err => { if (!controller.signal.aborted) console.error(err); });
  return () => controller.abort();
}, []);
```

### 🟡 MEDIUM

**8.8 No Suspense boundaries or loading skeletons**  
`quota`, `subscription`, and `history` are all `null` on first render, showing blank space. Add skeleton loaders:

```tsx
{quota ? (
  <StatCard title="Queries" value={`${quota.used} / ${quota.max}`} />
) : (
  <div className="h-16 bg-gray-100 animate-pulse rounded" />
)}
```

**8.9 Auth pages violate design quality standards**  
Per `web/design-quality.md`, pages must not look like "default card grids with uniform spacing." The login/signup forms need intentional design direction (suggested: dark luxury or Swiss/International matching the reasoning UI).

**8.10 Missing `aria-*` attributes throughout all new components**  
`UpgradeModal`, `UsageBadge`, `UserMenu`, and `PresetSelector` have no ARIA labels. Screen readers cannot describe them. Add `role`, `aria-label`, `aria-disabled`, and `aria-live` where appropriate.

**8.11 Playwright E2E test fills Stripe iframe incorrectly**  
Stripe's card input is in an iframe. `page.fill('input[name="cardnumber"]')` won't work — Playwright requires `frameLocator`:

```typescript
const stripeFrame = page.frameLocator('iframe[name^="__privateStripeFrame"]');
await stripeFrame.locator('[placeholder="Card number"]').fill('4242424242424242');
```

---

## Phase 9 — Performance + Scale Prep

### 🔴 CRITICAL

**9.1 `cancel_all_active` uses `scan_iter` — O(N) with no upper bound**  
`SCAN` iterates all Redis keys. On a production instance with 100K keys, this blocks the event loop for hundreds of milliseconds and can time out. Use a Redis Set instead:

```python
# In register():
await asyncio.gather(
    self._redis.setex(f"{ACTIVE_KEY}:{run_id}", TTL_SECONDS, "1"),
    self._redis.sadd("active_run_ids", run_id),
    self._redis.expire("active_run_ids", TTL_SECONDS),
)

# In cancel_all_active():
run_ids = await self._redis.smembers("active_run_ids")
for run_id in run_ids:
    await self.cancel(run_id)
await self._redis.delete("active_run_ids")
return len(run_ids)
```

**9.2 `pop_cancelled` is not atomic under concurrent workers**  
The pipeline + DELETE pattern is not atomic. Between `pipe.get(key)` and `pipe.delete(key)`, another worker can read the same key. Use a Lua script for true atomicity:

```python
_POP_SCRIPT = """
local val = redis.call('GET', KEYS[1])
if val then
    redis.call('DEL', KEYS[1])
    return 1
else
    return 0
end
"""

async def pop_cancelled(self, run_id: str) -> bool:
    result = await self._redis.eval(_POP_SCRIPT, 1, f"{CANCELLED_KEY}:{run_id}")
    return bool(result)
```

**9.3 `key.decode()` in `cancel_all_active` fails when `decode_responses=True`**  
`get_redis()` creates the client with `decode_responses=True`, which means keys are already strings. `.decode()` on a string raises `AttributeError`.

```python
# Remove .decode() — keys are already strings when decode_responses=True:
run_id = key.split(":", 1)[1]
```

**9.4 `_shared_client` HTTPX pool is never closed on shutdown**  
The global HTTPX client is never closed, causing "ResourceWarning: Unclosed client session" on shutdown and potential connection leaks in tests:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    global _shared_client
    if _shared_client:
        await _shared_client.aclose()
        _shared_client = None
```

### 🟠 HIGH

**9.5 Load test uses synchronous `TestClient` with `asyncio.gather` — not actually concurrent**  
`asyncio.gather` on sync coroutines runs them sequentially in the event loop. Use `httpx.AsyncClient` for genuine concurrency (same fix as Phase 7, item 7.4).

**9.6 `DB_POOL_OVERFLOW` is set but asyncpg has no overflow concept**  
asyncpg pools have `min_size` and `max_size`, not overflow. The parameter is silently ignored. Remove it from the docs to prevent confusion:

```python
self._pool = await asyncpg.create_pool(
    self._dsn,
    min_size=2,
    max_size=self._pool_size,
    command_timeout=30,  # Prevent runaway queries
    max_inactive_connection_lifetime=300,  # Return idle connections to OS
)
```

**9.7 No circuit breaker for Redis failures**  
If Redis goes down, every request that touches quota or run state throws `ConnectionError`, cascading into a full outage. Add a circuit breaker pattern:

```python
from circuitbreaker import circuit

class RunStateManager:
    @circuit(failure_threshold=5, recovery_timeout=30)
    async def is_cancelled(self, run_id: str) -> bool:
        return await self._redis.exists(f"{CANCELLED_KEY}:{run_id}") > 0
    
    # Fallback: if Redis is down, assume not cancelled
    async def is_cancelled_safe(self, run_id: str) -> bool:
        try:
            return await self.is_cancelled(run_id)
        except Exception:
            return False
```

**9.8 `EventBus` is in-memory only — known scaling gap not addressed**  
Phase 9 mentions this as a known limit but provides no migration path. Add a concrete recommendation:

```python
# src/reasoner/infrastructure/event_bus/redis_bus.py
import redis.asyncio as aioredis

class RedisEventBus(EventBus):
    """Redis Pub/Sub-backed EventBus for multi-worker deployments."""
    
    async def publish(self, event: DomainEvent) -> None:
        channel = f"events:{event.event_type.value}"
        await self._redis.publish(channel, event.json())
    
    async def subscribe(self, event_type: EventType, handler: Callable) -> None:
        async def _listen():
            pubsub = self._redis.pubsub()
            await pubsub.subscribe(f"events:{event_type.value}")
            async for message in pubsub.listen():
                if message["type"] == "message":
                    event = DomainEvent.parse_raw(message["data"])
                    await handler(event)
        asyncio.create_task(_listen())
```

### 🟡 MEDIUM

**9.9 Composite index `idx_query_log_user_created` misses `DESC` in Alembic**  
`op.create_index("idx_query_log_user_created", "query_log", ["user_id", "created_at DESC"])` — Alembic's `create_index` doesn't accept column expressions with `DESC`. Use raw SQL:

```python
op.execute(
    "CREATE INDEX idx_query_log_user_created ON query_log (user_id, created_at DESC)"
)
```

**9.10 Missing connection retry for asyncpg pool creation at startup**  
If Postgres is still initializing when the backend starts (common in `docker compose up`), `asyncpg.create_pool()` will immediately fail. Add a retry loop:

```python
async def _create_pool_with_retry(dsn: str, retries: int = 10) -> asyncpg.Pool:
    for attempt in range(retries):
        try:
            return await asyncpg.create_pool(dsn, min_size=2, max_size=10)
        except Exception:
            if attempt == retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

**9.11 Token cache is disk-based — creates a distributed cache miss problem**  
Phase 9's `SCALING.md` acknowledges this but does not address it. Each worker maintains its own disk cache, so cached tokens from worker A are not visible to worker B. Migrate the token cache to Redis:

```python
# In cache.py:
class RedisTokenCache:
    async def get(self, key: str) -> Optional[str]:
        return await redis.get(f"token_cache:{key}")
    
    async def set(self, key: str, value: str, ttl: int = 3600) -> None:
        await redis.setex(f"token_cache:{key}", ttl, value)
```

---

## Cross-Cutting Enhancements (All Phases)

### Security

- **Structured output validation**: All LLM-generated JSON passed to users should be validated with Pydantic before being returned. Never pass raw LLM output to API responses.
- **Input length limits**: Add `max_length` validation to all user-submitted `problem` strings (e.g., 10,000 chars) to prevent prompt injection amplification.
- **Dependency pinning**: Use `pip-compile` to pin all transitive dependencies in `requirements.txt`. Unpinned transitive deps are a supply-chain risk.
- **Secret rotation procedure**: Document how to rotate `STRIPE_WEBHOOK_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, and `JWT_SECRET_KEY` without downtime.

### Performance

- **Asyncpg prepared statements**: Frequently-executed queries (`check_and_increment`, `get_quota`) should use asyncpg prepared statements for 2-5x speedup:
  ```python
  stmt = await conn.prepare("SELECT ... FROM usage_quotas WHERE user_id = $1 FOR UPDATE")
  row = await stmt.fetchrow(user_id)
  ```
- **Response compression**: Add `GZipMiddleware` to FastAPI to reduce SSE payload size for long reasoning outputs.
- **HTTP/2**: Configure Caddy to use HTTP/2 by default for multiplexed SSE connections.

### Robustness

- **Graceful degradation when Stripe is down**: If Stripe is unreachable, allow authenticated free-tier users to continue using the product (don't block quota checks on billing status).
- **Dead letter queue for failed events**: The `EventBus` should route failed-handler events to a dead letter queue for manual replay, not silently drop them.
- **Database migration strategy**: Add a `--check` mode to Alembic that validates migrations are applied without running them (useful in health checks for zero-downtime deploys).

### Testing

- **Test containers**: Replace all "assumes Redis/Postgres is running" comments with `testcontainers-python` so tests are self-contained:
  ```python
  from testcontainers.postgres import PostgresContainer
  from testcontainers.redis import RedisContainer
  ```
- **Contract testing**: Add Pact contract tests between the frontend API client and FastAPI to catch breaking API changes before deployment.
- **Mutation testing**: Run `mutmut` on the quota enforcement logic to verify that tests actually catch off-by-one bugs in the quota counter.

---

*Generated by Claude Sonnet 4.6 — 2026-04-19*
