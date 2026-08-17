# Plan: Reasoner — Production SaaS Launch

## Context

Reasoner is a research-grade multi-model reasoning engine with 16 methods, HyperGate auto-routing, and solid infrastructure primitives (rate limiting, circuit breaker, input sanitization). It is currently a single-tenant tool: no user accounts, no billing, no persistent auth, no deployment packaging. This plan describes everything needed to launch it as a fully operational, secure SaaS product.

---

## Current State (what already exists)

| Component | Status |
|-----------|--------|
| FastAPI backend (32 presets, 70+ models) | ✅ Solid |
| HyperGate auto-method selection | ✅ Done |
| Rate limiting (token bucket + sliding window) | ✅ Done |
| Input sanitization + prompt injection defense | ✅ Done |
| Security headers middleware | ✅ Done |
| Circuit breaker + fallback routing | ✅ Done |
| PostgreSQL event store (optional) | ✅ Done |
| Next.js 16 frontend | ✅ Solid |
| User accounts / auth | ❌ Missing |
| Multi-tenancy | ❌ Missing |
| Persistent auth storage | ❌ Missing (in-memory only) |
| Billing / subscriptions | ❌ Missing |
| Coupon system | ❌ Missing |
| Usage quotas per user | ❌ Missing |
| Docker + deployment | ❌ Missing |
| HTTPS enforcement | ❌ Missing |
| Audit logging | ❌ Missing |
| Monitoring / observability | ❌ Missing |

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         INTERNET                                  │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTPS (443)
                    ┌────────▼────────┐
                    │   Nginx / Caddy  │   ← TLS termination, rate limit at edge
                    └────────┬────────┘
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │ Next.js  │  │ FastAPI  │  │ SearXNG  │
        │ Frontend │  │ Backend  │  │  Search  │
        └──────────┘  └────┬─────┘  └──────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │PostgreSQL│ │  Redis   │ │  Stripe  │
        │  (main)  │ │(sessions)│ │ (billing)│
        └──────────┘ └──────────┘ └──────────┘
```

---

## Phase 1 — User Auth + Multi-Tenancy (Week 1–2)

### Tech Stack Choice
- **Auth provider**: [Better Auth](https://www.better-auth.com/) (self-hosted, supports OAuth + email/password + magic links) OR **Supabase Auth** (managed, faster to integrate)
- **Recommendation**: Supabase Auth — handles OAuth (Google/GitHub), email/password, magic links, JWT sessions out of the box. Free tier for dev, no infra to manage.
- **Alternative**: Auth.js (NextAuth v5) in the Next.js layer + custom JWT validation on FastAPI

### Implementation

**Backend — new files:**
```
src/reasoner/
├── auth/
│   ├── __init__.py          # Exports: get_current_user, require_tier
│   ├── supabase_client.py   # Supabase SDK wrapper
│   ├── middleware.py        # FastAPI dependency: validate JWT from Supabase
│   ├── models.py            # User, Subscription, UsageQuota Pydantic models
│   └── dependencies.py     # get_current_user(), require_subscription() deps
```

**Database schema (PostgreSQL — new tables):**
```sql
-- Users (managed by Supabase Auth, we extend with profiles)
CREATE TABLE user_profiles (
  id           UUID PRIMARY KEY REFERENCES auth.users(id),
  display_name TEXT,
  created_at   TIMESTAMPTZ DEFAULT now()
);

-- Subscriptions
CREATE TABLE subscriptions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES user_profiles(id),
  tier            TEXT CHECK (tier IN ('free', 'pro', 'enterprise')),
  status          TEXT CHECK (status IN ('active', 'cancelled', 'past_due', 'trialing')),
  stripe_sub_id   TEXT UNIQUE,
  current_period_end TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT now()
);

-- Usage Quotas (reset monthly)
CREATE TABLE usage_quotas (
  user_id      UUID PRIMARY KEY REFERENCES user_profiles(id),
  tier         TEXT,
  used_queries INT DEFAULT 0,
  max_queries  INT,              -- free: 20, pro: 500, enterprise: unlimited (-1)
  period_start TIMESTAMPTZ DEFAULT date_trunc('month', now()),
  updated_at   TIMESTAMPTZ DEFAULT now()
);

-- Query Log (per-user audit + billing)
CREATE TABLE query_log (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID REFERENCES user_profiles(id),
  preset       TEXT,
  method       TEXT,
  tokens_in    INT,
  tokens_out   INT,
  cost_usd     NUMERIC(10,6),
  created_at   TIMESTAMPTZ DEFAULT now()
);
```

**FastAPI changes:**
- Replace current in-memory `AuthManager` with Supabase JWT validation
- Add `get_current_user()` dependency to `/api/run`, `/api/run-followup`
- Add `require_tier(min_tier)` dependency for premium preset enforcement
- Keep rate limiter but tie it to `user_id` instead of IP

**Frontend changes:**
- Add Supabase client SDK (`@supabase/supabase-js`, `@supabase/ssr`)
- Add auth pages: `/login`, `/signup`, `/forgot-password`
- Wrap app in `<SessionProvider>`
- Add user menu (avatar, usage badge, logout) to header

**Key files to modify:**
- `src/reasoner/api/__init__.py` — add auth dependencies to routes
- `src/reasoner/rate_limiter.py` — use user_id as bucket key (not IP)
- `ui-next/src/app/` — add login/signup pages
- `ui-next/src/stores/app-store.ts` — add user/session state

---

## Phase 2 — Usage Quotas + Tier Enforcement (Week 2–3)

### Quota Model

Two self-serve tiers. Enterprise stays a real, billable `SubscriptionTier`
in the backend (quota, spend ceilings, Stripe/PayPal price IDs all support
it) — it's just not sold off a fixed price on `/pricing`. Volume and
custom-deployment terms are negotiated instead: one core plan, one
higher-touch option, and raise price once the workflow is proven rather
than listing three fixed tiers before the niche is proven.

| Tier | Queries/month | Presets available | Priority | Sold how |
|------|--------------|-------------------|---------|---|
| free | 20 | budget only | low | self-serve |
| pro | 500 | all (budget + premium) | high | self-serve |
| enterprise | unlimited | all | highest | contact sales (`/contact?topic=enterprise`) |

### Implementation

**New file: `src/reasoner/quota/manager.py`**
```python
class QuotaManager:
    async def check_and_increment(user_id, preset_name) -> QuotaResult
    async def get_usage(user_id) -> UsageStatus
    async def reset_monthly(user_id)  # cron job
    async def get_remaining(user_id) -> int
```

**Preset access control:**
- Budget presets (`*-budget`): available to free + pro + enterprise
- Premium presets (`*-premium`): pro + enterprise only
- `require_tier("pro")` FastAPI dependency enforces this

**FastAPI flow for `/api/run`:**
```
1. authenticate(request) → user
2. check_quota(user) → ok | 429 with retry-after
3. check_tier(user, preset) → ok | 403 with upgrade_url
4. run_pipeline(...)
5. increment_quota(user)
6. log_query(user, tokens, cost)
```

**UI changes:**
- Usage indicator in sidebar: "14 / 20 queries used"
- Locked preset badges for free users (lock icon + "Upgrade to Pro")
- Upgrade modal when quota exceeded

---

## Phase 3 — Billing with Stripe (Week 3–5)

### Payment Stack
- **Stripe** — subscriptions, one-time payments, coupons, invoicing
- **Stripe Billing Portal** — self-service subscription management (cancel, upgrade)
- **stripe-python** backend + **@stripe/stripe-js** + **@stripe/react-stripe-js** frontend

### Plans to Create in Stripe Dashboard
```
Product: Reasoner Pro
  Price: $12/month (monthly) | $99/year (annual, ~30% discount)

Product: Reasoner Enterprise
  No fixed price — quoted per deal from the sales conversation, then a
  custom Price object is created for that customer's Checkout session.
  STRIPE_ENTERPRISE_PRICE_ID / PAYPAL_ENTERPRISE_PLAN_ID stay as the env
  vars `stripe_adapter.py` / `paypal_adapter.py` read once a rep sets a
  price; there's no catalog price to publish here.
```

### New Backend Files

```
src/reasoner/billing/
├── __init__.py
├── stripe_client.py     # Stripe SDK wrapper
├── webhooks.py          # Handle subscription events
├── models.py            # Invoice, Payment Pydantic models
└── router.py            # FastAPI router: /api/billing/*
```

**Billing API routes (`/api/billing/`):**
```
POST /api/billing/checkout          # Create Stripe Checkout session
POST /api/billing/portal            # Create Billing Portal session (self-service)
POST /api/billing/webhook           # Stripe webhook (signed, public endpoint)
GET  /api/billing/subscription      # Get current subscription status
GET  /api/billing/invoices          # List invoices
```

**Webhook events to handle:**
```python
checkout.session.completed       → activate subscription
customer.subscription.updated   → change tier
customer.subscription.deleted   → downgrade to free
invoice.payment_failed          → set status = past_due, notify user
invoice.payment_succeeded       → reset quota for new period
```

**Frontend — new pages:**
```
/pricing          # Plans comparison table with Stripe Checkout
/dashboard        # Usage stats, current plan, query history
/billing          # Stripe Billing Portal redirect
/upgrade          # Direct upgrade flow (from locked presets)
```

---

## Phase 4 — Coupon System (Week 5)

### Approach: Stripe Coupons (native)

Stripe has a built-in coupon system — no custom code needed for the billing side.

**Stripe Dashboard: create coupons:**
- `LAUNCH50` — 50% off first 3 months
- `YEARLY30` — 30% off annual plan
- `BETA100` — 100% off for 1 month (beta testers)

**Frontend checkout flow:**
```tsx
// In /pricing page, Stripe Checkout supports coupon input natively
const session = await stripe.checkout.sessions.create({
  allow_promotion_codes: true,   // shows coupon field in checkout
  ...
})
```

**Backend validation (if custom coupons needed beyond Stripe):**
```
src/reasoner/billing/coupons.py
```
```sql
CREATE TABLE coupons (
  code        TEXT PRIMARY KEY,
  discount_pct INT,              -- 0–100
  max_uses    INT,
  used_count  INT DEFAULT 0,
  valid_until TIMESTAMPTZ,
  created_at  TIMESTAMPTZ DEFAULT now()
);
```

---

## Phase 5 — Docker + Deployment (Week 6–7)

### Files to Create

**`Dockerfile` (backend):**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY asgi.py .
EXPOSE 8000
CMD ["uvicorn", "asgi:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

**`ui-next/Dockerfile` (frontend):**
```dockerfile
FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json .
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next .next
COPY --from=builder /app/node_modules node_modules
COPY --from=builder /app/package.json .
EXPOSE 3000
CMD ["npm", "start"]
```

**`docker-compose.yml` (full stack):**
```yaml
services:
  nginx:        # TLS termination + static files
  backend:      # FastAPI
  frontend:     # Next.js
  searxng:      # Search
  postgres:     # Primary database
  redis:        # Session cache + rate limit state
```

**`nginx/nginx.conf`:**
- HTTPS on 443 (Let's Encrypt / Caddy handles cert)
- HTTP → HTTPS redirect
- Proxy `/api/*` → backend:8000
- Proxy `/*` → frontend:3000
- Rate limiting at edge (nginx `limit_req_zone`)
- Security headers (HSTS, CSP, X-Frame-Options)

### Deployment Targets

**Option A: VPS (Hetzner/DigitalOcean/Vultr) — recommended for MVP**
- Ubuntu 24.04 LTS
- Docker Compose
- Caddy for automatic HTTPS (Let's Encrypt)
- ~€15–25/month for CX22 (2 vCPU, 4GB RAM)

**Option B: Railway / Render — fastest to deploy**
- Push code → auto-deploy
- PostgreSQL, Redis managed services included
- Zero DevOps for launch
- ~$25–40/month

**Option C: AWS/GCP/Azure — for scale**
- ECS + RDS + ElastiCache
- Higher ops overhead, more control

### Environment Variables (production additions)

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/reasoner

# Redis
REDIS_URL=redis://redis:6379/0

# Auth (Supabase)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...  # backend only, never expose to frontend

# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRO_PRICE_ID=price_...
STRIPE_ENTERPRISE_PRICE_ID=price_...

# App
APP_URL=https://reasoner.yourdomain.com
SECRET_KEY=<64-char random hex>
ENVIRONMENT=production
```

---

## Phase 6 — Security Hardening (Week 7–8)

### Critical Changes

1. **HTTPS enforcement** — force HTTP→HTTPS redirect in nginx + HSTS header (already in middleware, needs nginx)
2. **Secrets management** — use Docker secrets or environment injection (never commit secrets)
3. **CORS update** — change from localhost to production domain in `api/__init__.py`
4. **Stripe webhook signature** — verify `stripe-signature` header on every webhook
5. **Rate limiting per user** — already in rate_limiter.py structure, wire to user_id
6. **Audit logging** — log all auth events, quota checks, billing events to separate table
7. **SQL injection** — use asyncpg parameterized queries only (already done)
8. **Redis session encryption** — encrypt session tokens at rest
9. **Database backups** — daily automated backups (pg_dump + S3)
10. **Dependency scanning** — add `pip-audit` + `npm audit` to CI

### GDPR Compliance
```
POST /api/account/delete  # Hard delete: user + all query_log + usage_quota
GET  /api/account/export  # Export all personal data as JSON
```

---

## Phase 7 — Monitoring & Observability (Week 8)

| Tool | Purpose | Cost |
|------|---------|------|
| **Sentry** | Error tracking (Python + Next.js) | Free tier |
| **Grafana + Prometheus** | Metrics dashboard | Self-hosted free |
| **Uptime Robot** | Uptime monitoring + alerts | Free tier |
| **Loki** | Log aggregation | Self-hosted with Grafana |

**Metrics to expose (`/api/metrics` — Prometheus format):**
```
reasoner_queries_total{tier, preset, status}
reasoner_query_duration_seconds{preset}
reasoner_active_users_total
reasoner_quota_exceeded_total{tier}
reasoner_llm_errors_total{provider}
```

---

## Implementation Order (Sprints)

| Sprint | Work | Deliverable |
|--------|------|-------------|
| 1 (1w) | Supabase Auth + Next.js login/signup | Users can register and log in |
| 2 (1w) | JWT validation on FastAPI + quota tables | Auth flows end-to-end |
| 3 (1w) | Quota enforcement + tier checks on presets | Free tier works with limits |
| 4 (1w) | Stripe checkout + subscription webhooks | Pro upgrade works |
| 5 (0.5w) | Coupon support in checkout | Promo codes work |
| 6 (1w) | Docker Compose + nginx + Caddy HTTPS | Deploys on a VPS |
| 7 (0.5w) | CORS update + secrets hardening + audit log | Production-safe |
| 8 (0.5w) | Sentry + Prometheus + Uptime Robot | Observability live |
| 9 (1w) | Dashboard page + usage indicator + billing portal | Full user self-service |

**Total: ~7–8 weeks to MVP SaaS**

---

## Critical Files to Modify

| File | Change |
|------|--------|
| `src/reasoner/api/__init__.py` | Add auth deps to `/api/run`, update CORS |
| `src/reasoner/rate_limiter.py` | Use user_id as bucket key |
| `src/reasoner/auth.py` | Replace in-memory with Supabase JWT validation |
| `src/reasoner/presets.py` | Tag presets with required_tier |
| `ui-next/src/app/page.tsx` | Add auth gate, usage badge |
| `ui-next/src/stores/app-store.ts` | Add user/session state |
| `.env.example` | Add Supabase, Stripe, Redis vars |

## New Files to Create

| File | Purpose |
|------|---------|
| `src/reasoner/auth/supabase_client.py` | Supabase JWT validation |
| `src/reasoner/auth/dependencies.py` | FastAPI deps: get_current_user, require_tier |
| `src/reasoner/quota/manager.py` | Per-user quota enforcement |
| `src/reasoner/billing/stripe_client.py` | Stripe wrapper |
| `src/reasoner/billing/webhooks.py` | Stripe event handlers |
| `src/reasoner/billing/router.py` | /api/billing/* routes |
| `src/reasoner/billing/coupons.py` | Custom coupon logic (optional) |
| `migrations/` | Alembic migrations for new tables |
| `Dockerfile` | Backend container |
| `ui-next/Dockerfile` | Frontend container |
| `docker-compose.yml` | Full stack |
| `nginx/nginx.conf` | TLS + proxy config |
| `ui-next/src/app/login/page.tsx` | Login page |
| `ui-next/src/app/signup/page.tsx` | Signup page |
| `ui-next/src/app/pricing/page.tsx` | Plans page |
| `ui-next/src/app/dashboard/page.tsx` | Usage dashboard |

---

## Verification

1. `docker compose up` → all services healthy
2. Visit `https://yourdomain.com` → HTTPS, no mixed content
3. Register → confirm email → log in → session persists
4. Submit 20 free queries → 21st returns 429 with upgrade prompt
5. Click upgrade → Stripe checkout → pay test card → tier upgrades
6. Premium preset now available, quota raises to 500
7. Enter coupon `LAUNCH50` → 50% off applied in checkout
8. Cancel subscription from billing portal → tier downgrades to free
9. `GET /api/health` → all systems green
10. Sentry receives test error → alert fires