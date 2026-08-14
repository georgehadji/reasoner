# Go-Live Playbook — Multi-User Deployment + Metrics for Portfolio/Sale

This playbook answers one question: **what to actually do, in order, to put Reasoner
in front of real users and collect the numbers that make it showcasable or sellable.**

It is grounded in what already exists in this repo — most of the hard work is done.
See `DEPLOY.md` for the mechanical deployment steps; this document is the strategy layer above it.

---

## 0. Reality Check — You Are ~90% Deployed Already

| Capability | Status | Where |
|---|---|---|
| Docker packaging (backend + frontend) | ✅ | `Dockerfile`, `ui-next/Dockerfile` |
| Full production stack (Caddy TLS, Postgres, Valkey, mTLS) | ✅ | `docker-compose.yml`, `Caddyfile.prod` |
| Multi-user auth (Supabase JWT + local adapter) | ✅ | `src/reasoner/infrastructure/auth/` |
| Billing (Stripe + PayPal, webhooks, dead-letter) | ✅ | `src/reasoner/infrastructure/billing/`, `api/billing_router.py` |
| Per-user quotas & tiers | ✅ | `infrastructure/persistence/quota_repo_postgres.py` |
| Prometheus metrics endpoint | ✅ | `infrastructure/metrics.py`, `/api/metrics` |
| Observability stack (Prometheus + Alertmanager) | ✅ | `docker-compose.observability.yml`, `docs/monitoring/` |
| Error store + admin endpoint + Sentry hooks | ✅ | `api/routes/errors.py`, `/api/admin/errors` |
| Harness scorecard (cost/duration/quality/fallback per preset) | ✅ | `/api/telemetry/scorecard` |
| GDPR endpoints | ✅ | `api/routes/gdpr.py` |
| DB migrations (Alembic, auto-run on startup) | ✅ | `alembic.ini`, `migrations/`, `docker-entrypoint.sh` |

**What is genuinely missing for the stated goal:**

1. A server + domain (nothing in the repo can substitute for this).
2. Product analytics (funnel: visit → signup → first query → retention). Prometheus measures the *system*; nothing yet measures the *user journey*.
3. A public artifact that displays the numbers (portfolio surface).
4. Spend protection hardening — LLM keys are the one thing that can bankrupt a demo.

---

## 1. Deployment Decision (Do This, Skip the Rest)

**Recommendation: one VPS + the existing Docker Compose stack.**

- Hetzner CPX31 / DigitalOcean 4 GB / Contabo equivalent — €10–25/month. Matches the
  documented minimum specs (2 vCPU / 4 GB) in `DEPLOY.md`.
- Do **not** use Kubernetes, ECS, or serverless. The pipeline holds long-lived SSE
  streams (minutes per run) — serverless timeouts fight you, and K8s adds operational
  surface with zero benefit at this stage. The compose file already has resource
  limits, health checks, log rotation, and restart policies.
- Managed alternative if you never want to SSH: Railway or Fly.io can run the same
  containers, but you lose the mTLS internal network and pay more at equal specs.
  For a portfolio piece, "I ran a hardened single-node production stack" is a
  *stronger* story than "I clicked deploy on a PaaS."

**Concrete sequence (one afternoon):**

1. Buy a domain (`reasoner.yourname.dev` or similar) → point A record at the VPS.
2. `git clone`, `cp .env.example .env`, then
   `python scripts/preflight_check.py --generate` for the secrets and
   `python scripts/preflight_check.py` to confirm nothing required is missing.
   Supabase and the encryption keys are mandatory in production — the backend
   refuses to start without them.
3. Swap in `Caddyfile.prod` with your domain (Step 2).
4. `docker compose up -d --build`, verify `curl https://domain/api/health`.
5. Add the observability overlay:
   `docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d`
   (remember `METRICS_ALLOWED_IPS` must include `172.16.0.0/12` per the file header).
6. Set up Supabase (free tier) for auth; enable Google/GitHub OAuth so signup is one click.
7. Enable off-site Postgres backups: nightly `pg_dump` to object storage (a 5-line cron;
   the command is already in `DEPLOY.md`).

---

## 2. Spend Protection — The One Thing That Can Hurt You

Every query costs real money ($0.02–$0.30 per run). Multi-user + public URL means
strangers spending your API budget. Before sharing the URL anywhere:

- **Hard cap at the provider**: set a monthly spend limit on the OpenRouter key
  (dashboard-level, cannot be bypassed by any bug in your code). Use OpenRouter as
  the only key in production — one cap covers 350+ models.
- **Require login for any pipeline run.** Anonymous visitors get the landing page and
  maybe one sandboxed demo query, never the full pipeline.
- **Free tier = budget presets only, small monthly quota** (the quota repo and
  `require_tier` machinery already exist — configure, don't build).
- Keep the per-IP rate limiter on *in addition to* per-user quotas (already wired).
- Alert on spend: the `QuotaExceededSpike` rule in `docs/monitoring/alerts-reference.yml`
  is your abuse tripwire; add a daily OpenRouter spend check to taste.

---

## 3. Measurement Plan — What to Capture and Where It Lives

Think of it as four dashboards; three are already instrumented.

### 3.1 System performance (exists — Prometheus)
`reasoner_query_duration_seconds` (P50/P95 latency per preset), `reasoner_queries_total`
(by tier/preset/status → error rate), `reasoner_llm_errors_total`,
`reasoner_valkey_fallback_total`, circuit-breaker state, pool gauges, uptime.
**Action:** add Grafana to the observability overlay (one service block) and build one
dashboard. Grafana screenshots are the single highest-value portfolio asset here.

### 3.2 Unit economics (exists — Postgres `query_log` + scorecard)
Cost per query (`cost_usd`, `tokens_in/out` per run), cost per preset/method, and the
`/api/telemetry/scorecard` aggregate (cost, duration, quality pass rate, fallback rate
per preset over N days). This is what a buyer asks for first: **gross margin per tier**
= subscription price − (avg queries/user × avg cost/query).

### 3.3 Reasoning quality (exists — scorecard + feedback store)
Quality pass rate per preset, fallback rate (how often cross-lab routing saved a run),
epistemic label distribution (VERIFIED/HYPOTHESIS/UNKNOWN ratios), user feedback
(`feedback.db`, retained indefinitely). No other portfolio project has "my router's
fallback chain rescued 4% of runs" — this is the differentiating story.

### 3.4 Product / user journey (MISSING — add one tool)
Signups, activation (first completed query), DAU/WAU, week-1 retention, queries per
active user, preset popularity, conversion to paid.
**Action:** add **PostHog** (cloud free tier: 1M events/mo, or self-host it as another
compose service). Instrument ~6 events in `ui-next`:
`landing_view`, `signup`, `first_query_started`, `query_completed` (with preset/method
properties), `upgrade_clicked`, `subscription_started`. That's an afternoon of work in
`usePipelineStream` + the auth pages, and it completes the funnel picture.

### Metrics that sell (collect from day one)

| Audience | Numbers that matter |
|---|---|
| Portfolio reviewer / employer | P95 latency under load, error rate <1%, uptime %, architecture + observability screenshots, "N users, M queries served" |
| Buyer / acquirer | MRR (even $30 counts), retention curve, cost per query vs. price, quota-abuse defenses, GDPR endpoints, churn |
| Both | Growth over time — capture snapshots from week 1, because the *trend line* is the exhibit, and you cannot backfill it |

---

## 4. Portfolio & Sale Packaging

1. **Public metrics page** — a `/stats` route (or static page regenerated daily) showing
   live totals: queries served, models orchestrated, avg latency, uptime. Public proof
   beats claims.
2. **90-second demo video** — one hard question through the Debate preset, showing the
   phase-by-phase SSE stream. This is what people actually watch.
3. **Case-study writeup** — the deployment story itself (mTLS internal network, circuit
   breakers, cross-lab fallback, quota enforcement) with Grafana screenshots. Publish it;
   link it from the landing page and your CV.
4. **Diligence folder for a sale** — `ARCHITECTURE_MINDMAP.md`, test suite (~197 files) +
   coverage report, the scorecard export, `SAAS.md` roadmap, and a monthly P&L
   (infra ~€20 + LLM spend vs. revenue). A buyer pays for *demonstrated* revenue and
   retention, so even 10 paying users at $5/mo materially changes the asking price.

---

## 5. Launch Sequence

| Week | Goal | Done when |
|---|---|---|
| 1 | Live at a domain | Health check green over HTTPS, Supabase login works, backups cron running |
| 1 | Spend-safe | OpenRouter hard cap set, login required for runs, free-tier quota enforced |
| 2 | Observable | Grafana dashboard up, Alertmanager notifying you, PostHog funnel events firing |
| 3 | First users | Share with 10–20 people (communities where hard-question answering matters: research, strategy, dev forums). Watch the funnel, fix the biggest drop-off |
| 4 | Monetizable | Stripe live keys, Pro tier purchasable, first metrics snapshot archived |
| ongoing | Evidence | Weekly snapshot of scorecard + PostHog + Grafana → `docs/metrics-snapshots/` |

The order matters: **spend protection before sharing the URL, analytics before first
users** (you can't backfill a funnel), monetization only after the funnel shows people
completing queries.
