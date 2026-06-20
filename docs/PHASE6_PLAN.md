# Phase 6 Implementation Plan — Security Hardening + GDPR

> **Goal:** Production-grade security and compliance.  
> **Duration:** 5 working days (Week 7)  
> **Deliverable:** HTTPS enforcement, secrets management, audit logging, GDPR endpoints, dependency scanning.  
> **Constraint:** No secrets in code. All changes are additive or configuration-only.

⚠️ **CRITICAL ENHANCEMENTS (PHASE_ENHANCEMENTS.md 6.1–6.8):**
- 6.1: `/api/metrics` endpoint (Phase 7) is exposed publicly — authenticate or restrict by IP
- 6.2: GDPR `/api/account/delete` doesn't cancel Stripe subscription — user continues to be charged
- 6.3: Secret scanner (`grep -r "eyJ"`) is insufficient — use Truffle Hog or native Git hooks
- 6.4: No rate limiting on `/api/account/delete` and `/api/account/export` — DoS vectors
- 6.5: Missing CSP header — any injected script runs with full page access
- 6.6: Audit middleware logs full URL path with PII in query params — sanitize before logging
- 6.7: GDPR export is synchronous and unbounded — can OOM on large datasets
- 6.8: Missing Subresource Integrity (SRI) for external CDN assets — supply-chain attack surface

---

## 0. Pre-Flight Checklist

```bash
# 1. Verify Phases 1-5 are complete
python -m pytest tests/ --tb=short -q

# 2. Install security tools
pip install pip-audit bandit
npm install -g npm-audit

# 3. Verify Caddy/nginx TLS is working
curl -I https://yourdomain.com/api/health
```

---

## 1. Day-by-Day Implementation Schedule

### Day 1 — HTTPS Enforcement + HSTS

**Files:**
- `Caddyfile` or `nginx/nginx.conf`
- `src/reasoner/api/__init__.py`

**Task 6.1.1 — Caddy HTTPS Auto**

```caddy
yourdomain.com {
    # Redirect HTTP to HTTPS
    redir https://{host}{uri}
}

yourdomain.com:443 {
    # TLS with Let's Encrypt (automatic)
    tls your-email@example.com

    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "geolocation=(), microphone=(), camera=()"
    }

    reverse_proxy /api/* backend:8000
    reverse_proxy frontend:3000
}
```

**Task 6.1.2 — Production CORS**

```python
# In src/reasoner/api/__init__.py
import os

env = os.environ.get("ENVIRONMENT", "development")
if env == "production":
    allowed_origins = [os.environ["APP_URL"]]
else:
    allowed_origins = ["http://localhost:3000", "http://localhost:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=CORS_MAX_AGE_SECONDS,
)
```

**Day 1 Acceptance Criteria:**
- [ ] HTTP requests redirect to HTTPS.
- [ ] HSTS header present on all responses.
- [ ] CORS rejects unknown origins in production.

---

### Day 2 — Secrets Management

**Files:**
- `.env.example` (update)
- `docker-compose.yml` (use Docker secrets or env file)

**Task 6.2.1 — Docker Secrets (optional but recommended)**

```yaml
# docker-compose.yml additions
secrets:
  stripe_secret:
    file: ./secrets/stripe_secret_key.txt
  supabase_service_key:
    file: ./secrets/supabase_service_role_key.txt

services:
  backend:
    secrets:
      - stripe_secret
      - supabase_service_key
    environment:
      - STRIPE_SECRET_KEY=/run/secrets/stripe_secret
      - SUPABASE_SERVICE_ROLE_KEY=/run/secrets/supabase_service_key
```

**Task 6.2.2 — Validate No Secrets in Code**

```bash
# Add to CI pipeline
grep -r "sk_live_" src/ || echo "No live Stripe keys in source"
grep -r "eyJ.*eyJ" src/ || echo "No JWTs in source"
```

**Day 2 Acceptance Criteria:**
- [ ] `.env` is in `.gitignore` and never committed.
- [ ] `docker-compose.yml` does not contain hardcoded secrets.

---

### Day 3 — Audit Logging

**Files:**
- `src/reasoner/application/services/audit_service.py` (refinement)
- `src/reasoner/api/dependencies.py` (add audit middleware)

**Task 6.3.1 — Auth Audit Log Table**

```sql
CREATE TABLE auth_audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES user_profiles(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,  -- login, logout, password_reset, api_key_created
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_auth_audit_user ON auth_audit_log(user_id, created_at DESC);
```

**Task 6.3.2 — Audit Middleware**

```python
# src/reasoner/api/middleware.py (new)

class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Log mutating requests
        if request.method in ("POST", "DELETE", "PUT"):
            user = getattr(request.state, "user", None)
            await log_audit_event(
                user_id=str(user.id) if user else None,
                event_type=f"{request.method.lower()}_{request.url.path}",
                ip=request.client.host if request.client else None,
                user_agent=request.headers.get("User-Agent"),
            )

        return response
```

**Day 3 Acceptance Criteria:**
- [ ] Every POST/DELETE to `/api/run`, `/api/billing/*` is logged.
- [ ] Auth events (login, logout) are logged.

---

### Day 4 — GDPR Endpoints

**Files:**
- `src/reasoner/api/saas_router.py` (add endpoints)

**Task 6.4.1 — Data Export**

```python
@router.get("/account/export")
async def export_data(user: User = Depends(get_current_user)):
    """Export all personal data as JSON (GDPR Article 20)."""
    from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository
    from reasoner.core.settings import settings

    repo = PostgresQuotaRepository(settings.DATABASE_URL)
    pool = await repo._get_pool()

    profile = await pool.fetchrow("SELECT * FROM user_profiles WHERE id = $1", str(user.id))
    subscriptions = await pool.fetch("SELECT * FROM subscriptions WHERE user_id = $1", str(user.id))
    quotas = await pool.fetchrow("SELECT * FROM usage_quotas WHERE user_id = $1", str(user.id))
    queries = await pool.fetch("SELECT * FROM query_log WHERE user_id = $1", str(user.id))

    return {
        "profile": dict(profile) if profile else {},
        "subscriptions": [dict(s) for s in subscriptions],
        "quota": dict(quotas) if quotas else {},
        "queries": [dict(q) for q in queries],
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }
```

**Task 6.4.2 — Hard Delete**

```python
@router.post("/account/delete")
async def delete_account(user: User = Depends(get_current_user)):
    """Hard delete user and all data (GDPR Article 17)."""
    from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository
    from reasoner.core.settings import settings

    repo = PostgresQuotaRepository(settings.DATABASE_URL)
    pool = await repo._get_pool()

    # Cascade delete handled by ON DELETE CASCADE in schema
    await pool.execute("DELETE FROM user_profiles WHERE id = $1", str(user.id))

    # Also clear from Supabase Auth
    # (requires service role key)

    return {"status": "deleted", "user_id": str(user.id)}
```

**Day 4 Acceptance Criteria:**
- [ ] `GET /api/account/export` returns complete user data JSON.
- [ ] `POST /api/account/delete` removes all rows for user.

---

### Day 5 — Dependency Scanning + Security Tests

**Files:**
- `.github/workflows/security.yml` (new CI workflow)

**Task 6.5.1 — GitHub Actions Security Workflow**

```yaml
name: Security Scan

on: [push, pull_request]

jobs:
  python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install pip-audit bandit
      - run: pip-audit --requirement requirements.txt
      - run: bandit -r src/

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - run: cd ui-next && npm audit --audit-level high
```

**Day 5 Acceptance Criteria:**
- [ ] `pip-audit` returns zero high-severity vulnerabilities.
- [ ] `bandit` returns no high-severity issues.
- [ ] `npm audit` returns zero high-severity issues.

---

## 2. Definition of Done (Phase 6)

- [ ] HTTPS enforced with HSTS.
- [ ] CORS restricted to production domain.
- [ ] No secrets committed to repository.
- [ ] All auth and billing events are audit-logged.
- [ ] `GET /api/account/export` returns complete user data.
- [ ] `POST /api/account/delete` hard-deletes all user data.
- [ ] CI runs `pip-audit`, `bandit`, and `npm audit`.
- [ ] All existing tests pass.

---

*End of Phase 6 Plan*
