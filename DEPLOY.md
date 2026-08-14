# Production Deployment Guide — Reasoner

## Architecture Overview

```
Internet
    |
    v
[Caddy :80/:443]  ← Reverse proxy, auto HTTPS, security headers
    |--- /api/*, /ws/* → [Backend :8000]  ← FastAPI + Gunicorn + Uvicorn
    |--- /*          → [Frontend :3000]  ← Next.js standalone
    |
[Postgres :5432]  ← Database (persistent volume)
[Redis :6379]     ← Cache / sessions (persistent volume)
```

| Service | External Port | Internal Port | Purpose |
|---------|--------------|---------------|---------|
| Caddy | 80, 443 | — | Reverse proxy + TLS termination |
| Backend | — | 8000 | FastAPI ASGI app |
| Frontend | — | 3000 | Next.js SSR |
| Postgres | — | 5432 | PostgreSQL database |
| Redis | — | 6379 | Redis cache |

All inter-service communication uses **mTLS** (auto-generated internal certificates).

---

## Prerequisites

- **Server**: Ubuntu 22.04/24.04 LTS (or any Linux with Docker)
- **Docker + Docker Compose** (v2+)
- **Domain name** pointing to your server (for auto HTTPS)
- **Minimum specs**: 2 vCPU, 4 GB RAM, 20 GB SSD
- **Recommended**: 4 vCPU, 8 GB RAM, 40 GB SSD

---

## Step 1 — Environment Variables

Copy `.env.example` to `.env` and fill in ALL required values:

```bash
cp .env.example .env
```

### Required for production:

```bash
# ── Critical Security ──
ADMIN_API_KEY=              # Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
CSRF_SECRET=                # Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"
ENCRYPTION_KEY=             # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
BLIND_INDEX_KEY=            # Generate the same way as ENCRYPTION_KEY
ENVIRONMENT=production
DEBUG=false

# ── Database ──
POSTGRES_PASSWORD=          # Strong random password

# ── LLM Access (at least ONE) ──
OPENROUTER_API_KEY=sk-or-v1-...   # Recommended: single key for 346+ models
# OR individual provider keys...

# ── SaaS Auth (REQUIRED in production) ──
# Without these the app falls back to LocalAuthAdapter (HS256), which
# infrastructure/auth/__init__.py refuses to use when ENVIRONMENT=production.
SUPABASE_URL=https://...
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...

# ── Billing (optional) ──
STRIPE_SECRET_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRO_PRICE_ID=...
STRIPE_ENTERPRISE_PRICE_ID=...

# ── Search ──
BRAVE_SEARCH_API_KEY=             # Brave Search API key (web/image/video)
TAVILY_API_KEY=                   # Optional secondary search backend

# ── Optional: Monitoring ──
SENTRY_DSN=...
LANGFUSE_PUBLIC_KEY=              # LLM tracing; needs: pip install "langfuse>=1.14.0,<2.0.0"
LANGFUSE_SECRET_KEY=
```

**Never commit `.env`.** It is already in `.gitignore`.

Generate every secret at once, then validate the result before bringing the
stack up — a missing variable otherwise surfaces as a crash-looping container:

```bash
python scripts/preflight_check.py --generate   # prints all five secrets
python scripts/preflight_check.py              # exits 1 on any blocking gap
```

To confirm the code itself is releasable without waiting on GitHub Actions
(a private repo out of billed minutes fails every job in ~2s with no runner
assigned, which is indistinguishable from a real failure), run the same gates
locally:

```bash
./scripts/verify_ci.sh              # every gate
./scripts/verify_ci.sh --backend    # skip the frontend gates
./scripts/verify_ci.sh --fast       # skip the coverage re-run
```

The check flags empty values, unedited `.env.example` placeholders, malformed
Fernet keys, `DEBUG=true`, `RATE_LIMITER_MODE=memory`, and localhost origins
left in `CORS_ORIGINS`.

> **Observability gate.** `docker-compose.yml` sets `ENVIRONMENT=production`, and
> in production the app refuses to start with no observability backend at all.
> `prometheus-client` is a hard dependency in `requirements.txt`, so `/api/metrics`
> satisfies the gate on a default install and neither Sentry nor Langfuse is
> required to boot. Both are recommended additions, not prerequisites.

---

## Step 2 — Production Caddyfile

Rename the production Caddyfile and set your domain:

```bash
mv Caddyfile Caddyfile.dev
mv Caddyfile.prod Caddyfile
```

Edit `Caddyfile` — replace `yourdomain.com` and `your-email@example.com`:

```caddy
yourdomain.com {
    redir https://{host}{uri}
}

yourdomain.com:443 {
    tls your-email@example.com

    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "geolocation=(), microphone=(), camera=()"
    }

    handle /api/health {
        reverse_proxy https://backend:8000 {
            transport http { tls_insecure_skip_verify }
        }
    }

    handle /api/* {
        reverse_proxy https://backend:8000 {
            transport http { tls_insecure_skip_verify }
        }
    }

    handle /ws/* {
        reverse_proxy https://backend:8000 {
            transport http { tls_insecure_skip_verify }
        }
    }

    handle {
        reverse_proxy https://frontend:3000 {
            transport http { tls_insecure_skip_verify }
        }
    }
}
```

Caddy automatically obtains and renews Let's Encrypt certificates.

---

## Step 3 — Deploy

```bash
# Pull latest images and start everything
docker compose up -d --build

# Watch logs
docker compose logs -f

# Check all services are healthy
docker compose ps
```

First startup takes ~3–5 minutes (frontend build + certificate generation).

---

## Step 4 — Verify

```bash
# Health check
curl https://yourdomain.com/api/health

# Check all containers
docker compose ps

# Check logs for errors
docker compose logs backend --tail 50
docker compose logs frontend --tail 50
```

---

## Step 5 — Database Migrations

Migrations run automatically on startup (`RUN_MIGRATIONS_ON_STARTUP=true` in `docker-entrypoint.sh`).

To run manually:

```bash
docker compose exec backend alembic upgrade head
```

---

## Useful Commands

```bash
# Restart a single service
docker compose restart backend

# Rebuild after code changes
docker compose up -d --build backend
docker compose up -d --build frontend

# View resource usage
docker stats

# Backup database
docker compose exec postgres pg_dump -U postgres reasoner > backup.sql

# Restore database
cat backup.sql | docker compose exec -T postgres psql -U postgres -d reasoner

# Scale backend workers (edit UVICORN_WORKERS in .env, then restart)
docker compose up -d --build backend
```

---

## Firewall Rules

Only these ports need to be open to the internet:

| Port | Protocol | Purpose |
|------|----------|---------|
| 22 | TCP | SSH (lock down to your IP) |
| 80 | TCP | HTTP → auto-redirects to HTTPS |
| 443 | TCP | HTTPS (Caddy) |

**Do NOT expose**: 8000 (backend), 3000 (frontend), 5432 (postgres), 6379 (redis).

---

## Troubleshooting

### Caddy won't start — port 80/443 in use
```bash
sudo ss -tlnp | grep -E ':80|:443'
sudo systemctl stop apache2 nginx  # If installed
```

### Frontend build fails
```bash
cd ui-next && npm run build
# Fix any TypeScript errors, then redeploy
```

### Database connection errors
Check `.env` has `POSTGRES_PASSWORD` set. The Docker Compose sets:
```
DATABASE_URL=postgresql+asyncpg://postgres:${POSTGRES_PASSWORD}@postgres:5432/reasoner?sslmode=require
```

### Web search returns no results
Search requires at least one backend key. Verify `BRAVE_SEARCH_API_KEY`,
`TAVILY_API_KEY` or `OPENROUTER_API_KEY` (Perplexity Sonar) is set:
```bash
docker compose exec backend env | grep -E 'BRAVE|TAVILY|OPENROUTER'
```

---

## Updating to a New Version

```bash
git pull
docker compose down
docker compose up -d --build
```

Persistent data (Postgres, Redis, Caddy certs) is stored in Docker volumes and survives rebuilds.

---

## Monitoring & Error Observability

Reasoner has built-in error capture on both backend and frontend. Every unhandled exception, API error, and client-side crash is logged with correlation IDs for traceability.

### Backend Error Logging

**Structured JSON logs** are emitted to stdout for every error:

```bash
# View recent backend errors
docker compose logs backend --tail 100 | grep ERROR

# Follow errors in real-time
docker compose logs -f backend | grep ERROR
```

**SQLite error store** (`errors.db`) persists errors with full context:

```bash
# Query recent errors directly
docker compose exec backend sqlite3 /app/errors.db \
  "SELECT timestamp, level, source, message, path FROM errors ORDER BY timestamp DESC LIMIT 20;"
```

**Admin endpoint** (`GET /api/admin/errors`) returns aggregated error stats and recent entries:

```bash
curl -H "Authorization: Bearer $JWT_TOKEN" \
     -H "X-Admin-Key: $ADMIN_API_KEY" \
     "https://yourdomain.com/api/admin/errors?hours=24"
```

Response includes:
- `errors[]` — recent error entries with timestamp, level, source, message, path, user_id, correlation_id
- `stats` — aggregated counts by level, source, 1h/24h/7d windows, unique paths

### Frontend Error Reporting

Client-side errors are automatically captured via:

1. **React Error Boundary** (`error.tsx`) — catches render errors, reports to backend
2. **Global Error Handler** (`global-error.tsx`) — catches root-level failures
3. **API Error Capture** — all 5xx responses from backend are reported

Errors are sent to `POST /api/error-report` (no auth required, rate-limited by IP).

### Sentry Integration (Optional but Recommended)

Set these environment variables before deployment:

```bash
# Backend
SENTRY_DSN=https://... sentry.io/...

# Frontend (build-time)
NEXT_PUBLIC_SENTRY_DSN=https://... sentry.io/...
```

With Sentry configured, errors are reported to both your SQLite store **and** Sentry simultaneously.

### Prometheus Metrics

The `/api/metrics` endpoint exposes Prometheus-compatible metrics (IP-restricted):

```bash
curl "https://yourdomain.com/api/metrics"
```

Key metrics:
- `reasoner_queries_total` — total queries by tier/preset/status
- `reasoner_llm_errors_total` — LLM provider errors
- `reasoner_query_duration_seconds` — pipeline latency histogram
- `reasoner_rate_limit_rejected_total` — rate-limited requests
- `reasoner_circuit_breaker_state` — circuit breaker health

To scrape with Prometheus, add this job to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'reasoner'
    static_configs:
      - targets: ['yourdomain.com']
    metrics_path: '/api/metrics'
```

### Health Check

```bash
curl https://yourdomain.com/api/health
```

Returns subsystem status: postgres, redis, memory, circuit breakers, cache, stripe.

### Alerting Rules (Prometheus)

Reference rules are in `docs/monitoring/alerts-reference.yml`:

- **HighErrorRate** — >10% error rate over 5min
- **QuotaExceededSpike** — >10 quota violations/min (possible abuse)
- **HighLatency** — P95 latency >60s
- **PostgresPoolExhaustion** — no free connections

Deploy with Prometheus + Alertmanager for automatic notifications.

### Log Retention

- **Docker logs**: rotated at 100MB × 3 files per service (configured in `docker-compose.yml`)
- **Error store**: auto-pruned to 30 days (configurable via `ERROR_RETENTION_DAYS`)
- **Feedback store**: retained indefinitely

### Quick Diagnostic Commands

```bash
# 1. Is the backend healthy?
curl -s https://yourdomain.com/api/health | jq .

# 2. Recent errors (last hour)
curl -s -H "Authorization: Bearer $JWT" -H "X-Admin-Key: $KEY" \
  "https://yourdomain.com/api/admin/errors?hours=1" | jq '.stats'

# 3. Error count by path (last 24h)
docker compose exec backend sqlite3 /app/errors.db \
  "SELECT path, COUNT(*) FROM errors WHERE datetime(timestamp) > datetime('now', '-24 hours') GROUP BY path ORDER BY COUNT(*) DESC;"

# 4. Check Sentry for frontend errors
# Open your Sentry project dashboard

# 5. View real-time metrics
curl -s https://yourdomain.com/api/metrics | grep reasoner_queries_total
```
