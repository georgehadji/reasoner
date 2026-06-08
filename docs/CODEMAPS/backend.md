<!-- Generated: 2026-06-08 | Files scanned: 375 | Token estimate: ~900 -->

# Backend Architecture

## API Routes (FastAPI)

### Core pipeline
```
POST /api/run              → streaming.run_stream()           → ARAPipeline.run()
POST /api/followup         → streaming.run_followup_stream()  → ARAPipeline.followup()
GET  /api/run/{id}/cached  → streaming.run_stream_cached()
```

### Pipelines / history
```
api/routes/pipelines.py    → GET/POST /api/pipelines, /api/pipelines/{id}
api/routes/history.py      → GET /api/history, /api/history/{id}
api/history.py             → pipeline owner tracking (pipeline_owners.json)
```

### Uploads / context
```
api/routes/uploads.py      → POST /api/upload  (PDF, DOCX, images via uploader.py)
api/routes/context.py      → POST /api/context  (inline text context)
api/routes/images.py       → GET /api/images/{id}
```

### Widgets
```
api/routes/widgets.py      → GET /api/widgets/{type}  (stocks, weather, calc, image, video)
api/routes/legacy_widgets.py → legacy compat
```

### Auth / SaaS
```
api/routes/keys.py         → GET/POST /api/keys  (API key management)
api/billing_router.py      → POST /api/billing/* (Stripe checkout, portal, webhooks)
api/saas_router.py         → GET /api/quota, /api/subscription
```

### WebSocket / metrics
```
api/routes/websocket.py    → WS /ws/{session_id}
api/metrics.py             → GET /api/metrics
api/cron.py                → internal cron endpoints
```

## Middleware Chain
```
api/__init__.py app factory
  ├─ middleware.py           → security headers, memory limits, timeouts
  ├─ rate_limiter.py         → token-bucket per IP
  ├─ auth.py / auth_deps.py  → token-based auth with scoped permissions
  └─ api/csrf.py             → HMAC-SHA256 CSRF tokens
```

## Core Orchestration
```
pipeline.py (ARAPipeline)
  ├─ application/mixins/debate_mixin.py
  ├─ application/mixins/jury_mixin.py
  ├─ application/mixins/perspective_mixin.py
  ├─ application/mixins/research_mixin.py
  ├─ application/mixins/delphi_mixin.py
  ├─ application/mixins/dialectical_mixin.py
  ├─ application/mixins/cognitive_mixin.py
  ├─ application/mixins/recovery_mixin.py
  ├─ application/mixins/search_mixin.py
  ├─ application/mixins/writing_mixin.py
  └─ application/mixins/article_pipeline.py
```

## HyperGate Pre-Router
```
hypergate/hyperagent.py
  ├─ sub_agents/language.py       → language detection
  ├─ sub_agents/complexity.py     → complexity estimation
  ├─ sub_agents/direct.py         → direct answer detection
  ├─ sub_agents/web_search.py     → web search need detection
  ├─ sub_agents/method.py         → method classification (opaque B–Q)
  └─ sub_agents/tie_breaker.py    → conflict resolution
```

## Application Layer (CQRS)
```
application/handlers/handlers.py        → RunPipelineCommandHandler, ResumePipelineCommandHandler
application/flows/pipeline_flow.py      → build_default_flow_registry() (binds 17 methods)
application/event_bus/bus.py            → in-process event bus
application/ports/                      → AuthPort, BillingPort, QuotaRepository (interfaces)
application/services/preset_service.py → preset lookup/validation
application/services/search_service.py → SearXNG + Perplexity orchestration
application/services/billing_service.py→ Stripe billing operations
application/services/quota_service.py  → quota enforcement
application/services/renderers/        → 17 method-specific CLI renderers
```

## Key Supporting Modules
```
parsing.py          → extract_json() — all LLM response parsing
sanitization.py     → sanitize_for_prompt() — XSS strip, null-byte, prompt-injection
circuit_breaker.py  → automatic provider fallback
token_cache.py      → L1/L2 token caching layer
scraper.py          → web content extraction
uploader.py         → file ingestion pipeline
start_all.py        → dev launcher; Docker daemon health checked before compose up (timeout=5s)
```

## Notable Constants (core/constants.py)
```
PHASE_TIMEOUTS — per-phase timeout overrides including:
  "Synthesize (SoT)": 180.0  ← writing flow composite phase (skeleton + parallel + assembly)
  default: 90.0
```

## Recent Fixes
- `core/search.py` — removed fallback to raw results when SearXNG returns empty refined set
