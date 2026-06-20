# Phase 5 Implementation Plan — Docker + Deployment

> **Goal:** Make Reasoner deployable as a single `docker compose up`.  
> **Duration:** 5 working days (Week 6)  
> **Deliverable:** Dockerfiles, Compose stack, nginx reverse proxy, HTTPS via Caddy, health checks.  
> **Constraint:** Production build must not include dev dependencies or source maps.

⚠️ **CRITICAL ENHANCEMENTS (PHASE_ENHANCEMENTS.md 5.1–5.8):**
- 5.1: `--workers 2` with `uvicorn` breaks async lifespan — use `gunicorn` + `UvicornWorker` instead
- 5.2: Backend Dockerfile runs as root — create non-root user (appuser) for security
- 5.3: Hardcoded `POSTGRES_PASSWORD=postgres` in Compose — use Docker Secrets or .env
- 5.4: No `.dockerignore` — builds leak secrets and .git history — add comprehensive .dockerignore
- 5.5: Missing `restart: unless-stopped` in Compose — services crash and stay down
- 5.6: `/api/health` creates new Postgres pool on every check — use app.state singleton
- 5.7: Frontend Dockerfile copies node_modules bloat (800MB) — use multi-stage with standalone output (~150MB)
- 5.8: Caddyfile has `auto_https off` in production template — disable only in dev

---

## 0. Pre-Flight Checklist

```bash
# 1. Verify all prior phases are green
python -m pytest tests/ --tb=short -q

# 2. Install Docker + Docker Compose
docker --version
docker compose version

# 3. Ensure .env is complete and NOT committed
git check-ignore -q .env && echo "OK: .env ignored" || echo "WARNING: .env not ignored"
```

---

## 1. Architecture Overview

```
                    Internet
                       │
                       ▼
              ┌─────────────────┐
              │  Caddy / Nginx  │  ← TLS termination, static files
              │     (:443)      │
              └────────┬────────┘
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐
   │ Next.js  │  │ FastAPI  │  │ SearXNG  │
   │ Frontend │  │ Backend  │  │  Search  │
   │  :3000   │  │  :8000   │  │  :8080   │
   └──────────┘  └────┬─────┘  └──────────┘
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
   ┌──────────┐ ┌──────────┐ ┌──────────┐
   │PostgreSQL│ │  Redis   │ │  Volumes │
   │  :5432   │ │  :6379   │ │ cache/   │
   └──────────┘ └──────────┘ └──────────┘
```

---

## 2. Day-by-Day Implementation Schedule

### Day 1 — Backend Dockerfile

**File:** `Dockerfile`

```dockerfile
# ── Backend Dockerfile ──
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ── Runtime stage ──
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY src/ src/
COPY asgi.py .
COPY main.py .
COPY start_all.py .

# Non-root user (optional but recommended for production)
# RUN useradd -m appuser && chown -R appuser:appuser /app
# USER appuser

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "asgi:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

**Day 1 Acceptance Criteria:**
- [ ] `docker build -t reasoner-backend .` succeeds.
- [ ] `docker run -p 8000:8000 reasoner-backend` responds to `/api/health`.

---

### Day 2 — Frontend Dockerfile

**File:** `ui-next/Dockerfile`

```dockerfile
# ── Frontend Dockerfile ──
FROM node:22-alpine AS builder

WORKDIR /app

COPY package*.json .
RUN npm ci

COPY . .
RUN npm run build

# ── Runtime stage ──
FROM node:22-alpine AS runtime

WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/.next .next
COPY --from=builder /app/node_modules node_modules
COPY --from=builder /app/package.json .
COPY --from=builder /app/public public

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000 || exit 1

CMD ["npm", "start"]
```

**Day 2 Acceptance Criteria:**
- [ ] `docker build -t reasoner-frontend ./ui-next` succeeds.
- [ ] `docker run -p 3000:3000 reasoner-frontend` serves the UI.

---

### Day 3 — Docker Compose + Environment

**File:** `docker-compose.yml`

```yaml
version: "3.9"

services:
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - frontend
      - backend

  backend:
    build: .
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@postgres:5432/reasoner
      - REDIS_URL=redis://redis:6379/0
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_ANON_KEY=${SUPABASE_ANON_KEY}
      - SUPABASE_SERVICE_ROLE_KEY=${SUPABASE_SERVICE_ROLE_KEY}
      - STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY}
      - STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET}
      - ENVIRONMENT=production
      - ENABLE_LEGACY_API_KEY=false
    depends_on:
      - postgres
      - redis
    volumes:
      - ./cache:/app/cache
      - ./history:/app/history
      - ./uploads:/app/uploads

  frontend:
    build: ./ui-next
    environment:
      - NEXT_PUBLIC_API_URL=/api
      - NEXT_PUBLIC_SUPABASE_URL=${SUPABASE_URL}
      - NEXT_PUBLIC_SUPABASE_ANON_KEY=${SUPABASE_ANON_KEY}
    depends_on:
      - backend

  searxng:
    image: searxng/searxng:latest
    volumes:
      - ./searxng-settings.yml:/etc/searxng/settings.yml:ro

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: reasoner
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
  redis_data:
  caddy_data:
  caddy_config:
```

**Day 3 Acceptance Criteria:**
- [ ] `docker compose up --build` starts all services.
- [ ] `docker compose ps` shows all containers healthy.

---

### Day 4 — Caddy / Nginx Reverse Proxy

**File:** `Caddyfile`

```caddy
{
    auto_https off
}

:80 {
    # Health check endpoint (bypass proxy)
    handle /api/health {
        reverse_proxy backend:8000
    }

    # API routes → FastAPI
    handle /api/* {
        reverse_proxy backend:8000
    }

    # WebSocket support (if needed later)
    handle /ws/* {
        reverse_proxy backend:8000
    }

    # Everything else → Next.js
    handle {
        reverse_proxy frontend:3000
    }
}
```

For production with automatic HTTPS:

```caddy
yourdomain.com {
    reverse_proxy /api/* backend:8000
    reverse_proxy frontend:3000
}
```

**File:** `nginx/nginx.conf` (alternative if nginx preferred)

```nginx
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server backend:8000;
    }
    upstream frontend {
        server frontend:3000;
    }

    server {
        listen 80;
        server_name localhost;

        location /api/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        location / {
            proxy_pass http://frontend;
            proxy_set_header Host $host;
        }
    }
}
```

**Day 4 Acceptance Criteria:**
- [ ] `curl http://localhost/api/health` returns 200 via proxy.
- [ ] `curl http://localhost/` returns Next.js HTML.

---

### Day 5 — Health Checks + Graceful Shutdown

**Task 5.5.1 — Extend `/api/health`**

```python
# Add to src/reasoner/api/saas_router.py or api/__init__.py

@app.get("/api/health")
async def health_check():
    checks = {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

    # Postgres check
    try:
        from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository
        from reasoner.core.settings import settings
        repo = PostgresQuotaRepository(settings.DATABASE_URL)
        pool = await repo._get_pool()
        await pool.fetchval("SELECT 1")
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"

    # Redis check
    try:
        from reasoner.infrastructure.redis.client import get_redis
        redis = get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    # Stripe check (optional, don't fail health if Stripe is down)
    try:
        import stripe
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
        if stripe.api_key:
            stripe.Account.retrieve()
            checks["stripe"] = "ok"
    except Exception as e:
        checks["stripe"] = f"error: {e}"

    all_ok = all(v == "ok" for k, v in checks.items() if k not in ("status", "timestamp", "stripe"))
    status_code = 200 if all_ok else 503
    return JSONResponse(content=checks, status_code=status_code)
```

**Task 5.5.2 — Graceful Shutdown**

```python
# In src/reasoner/api/__init__.py

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down gracefully...")
    # Close Redis connection
    from reasoner.infrastructure.redis.client import get_redis
    redis = get_redis()
    await redis.close()
    # Close Postgres pools
    # (handled by asyncpg garbage collection, but explicit is better)
```

**Day 5 Acceptance Criteria:**
- [ ] `docker compose up` → `curl http://localhost/api/health` shows all checks green.
- [ ] `docker compose down` → backend logs show graceful shutdown.

---

## 3. Definition of Done (Phase 5)

- [ ] `docker compose up --build` starts full stack.
- [ ] All services report healthy.
- [ ] `/api/health` reports Postgres, Redis, Stripe status.
- [ ] Frontend loads at `http://localhost`.
- [ ] API routes proxied correctly.
- [ ] Volumes persist data across restarts.
- [ ] Graceful shutdown closes connections.

---

*End of Phase 5 Plan*
