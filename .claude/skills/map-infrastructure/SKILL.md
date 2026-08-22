---
name: map-infrastructure
description: "Folder map of src/reasoner/infrastructure — adapters implementing core ports: LLM registry/router/providers, ACR constraints and learning, persistence (SQLite + Postgres event stores, repos), Valkey/Redis, search adapters, code-execution sandbox, watermark image scrubbers, widgets, websocket. Use when adding a model or provider, changing routing/fallback, or touching storage."
folders:
  - src/reasoner/infrastructure
---

# src/reasoner/infrastructure — Folder Map

**Purpose:** All driven adapters. Everything that talks to the outside world — LLM APIs, databases, Redis/Valkey, search vendors, Docker, Stripe/PayPal, email — lives here and implements a protocol declared in `core/ports/` or `application/ports/`. Nothing in `domain/` or `application/` may import from this package directly.

## llm/ — model registry, routing, providers

| File | What it does |
|------|--------------|
| `registry.py` (48KB) | **The model whitelist and provider factory.** `build_provider`, `list_models`, `_vendor_of`, `bloc_of`, `resolved_model_of`, `RegistryAdapter` (implements `ModelRegistryPort`). Add a model here. |
| `router.py` (32KB) | `ProviderRouter` (implements `LLMPort`): role-based routing, fallback chain, circuit-breaker wrapping, per-model semaphores, telemetry event emission. |
| `executor.py` (36KB) | `LLMExecutor` — temperature resolution from phase configs, token-aware truncation, retry, response handling. Extracted out of `ReasonerPipeline`. |
| `base.py` | `BaseLLMProvider` + `LLMError`. |
| `ports.py` | Provider-side types: `Message`, `MessageRole`, `LLMResponse`, `DegradedLLMResponse`, `LLMConfig`, `ProviderHealth`, `ProviderInfo`. |
| `exceptions.py` | Infrastructure error taxonomy: auth, rate limit, model-not-found, timeout, unavailable, credits exhausted. |
| `caching.py` | Prompt-caching helpers; distinguishes automatic-cache providers from ones needing explicit `cache_control` breakpoints. |
| `pricing_resolver.py` | Alias-aware pricing lookup — maps registry aliases to served model ids before hitting `domain/pricing.py`. |
| `spend_tracker.py` | In-process monthly spend tracker keyed by billing subject. |
| `capability_registry.py` (17KB) | `CapabilityRegistry` — JSON-backed model capability profiles derived from the OpenRouter catalogue (ACR Phase 2). |
| `image_generation.py` (41KB) | OpenRouter multimodal image generation: prompt enhancement, parallel generation, policy-error detection, base64 normalization. |
| `image_model_catalogue.py` | Capability families + measured price per image model (`FAMILY_VECTOR`, `FAMILY_PHOTOREAL`, …). |
| `extraction/__init__.py` | Vision-LLM image captioning and OCR with an image-hash cache. |
| `utils.py` | Platform patches, strict-JSON heuristics, Perplexity response formatting. |

### llm/providers/

| File | What it does |
|------|--------------|
| `openai_compat.py` | `OpenAICompatibleProvider` and `OpenRouterProvider` — the workhorses. |
| `direct.py` | Direct SDK wrappers: Anthropic, OpenAI, Google Gemini, generic OpenAI-compatible; `build_fallback_provider`. |
| `finetuned.py` | `FineTunedProvider` for custom fine-tuned endpoints. |
| `noop.py` | `NoopProvider` — injected when no API keys are configured so nothing crashes. |

### llm/constraints/ (ACR Phase 4 — routing invariants)

| File | Constraint |
|------|-----------|
| `bloc_diversity.py` | synthesis bloc ≠ scoring bloc; generators must span multiple blocs. |
| `no_repeat_lab.py` | Max share of roles from one lab (default 60%). |
| `budget_ceiling.py` | Total estimated cost ≤ preset tier budget. |
| `circuit_state.py` | Skip models whose circuit breaker is open. |
| `concurrency.py` | Avoid models near their concurrency limit. |

## learning/ and benchmarks/ (ACR Phases 6–7)

| File | What it does |
|------|--------------|
| `learning/online_learner.py` | Background loop updating capability profiles from telemetry batches. |
| `learning/thompson_sampler.py` | Beta posterior per (model, role) for Bayesian selection. |
| `learning/quality_signals.py` | Converts raw call telemetry into a 0–1 reward. |
| `learning/exploration.py` | Exploration-vs-exploitation budget policy and warmup. |
| `benchmarks/engine.py` | `BenchmarkEngine` — runs suites, writes to the capability registry. |
| `benchmarks/runner.py` | Async runner with rate limiting and a cost cap. |
| `benchmarks/suites/*.py` | One suite per capability dimension: reasoning, coding, writing, multilingual, long_context, json_fidelity, critical_thinking, consistency. |

## persistence/

| File | What it does |
|------|--------------|
| `event_store.py` (31KB) | SQLite `EventStore` — durable domain events, aggregate reconstruction, temporal queries. |
| `event_store_connection.py` | SQLite connection management extracted from the store. |
| `postgres_store.py` (44KB) | `PostgreSQLEventStore` — production event persistence with pooling and read replicas. |
| `snapshots.py` | `SnapshotStrategy`, `SnapshotManager`, `ReadModelProjection` — faster aggregate rebuild. |
| `telemetry_store.py` | Per-phase and per-run telemetry tables for cross-run analytics. |
| `error_store.py` | SQLite error persistence + stats. |
| `feedback_store.py` | SQLite feedback store (migrates legacy JSONL on first init). |
| `auth_store.py` | Durable API key storage via aiosqlite. |
| `api_key_repo_postgres.py` / `api_key_repo_memory.py` | `ApiKeyRepository` adapters. |
| `credit_repo_postgres.py` / `credit_repo_memory.py` | `CreditRepository` adapters; Postgres locks the balance row (`SELECT … FOR UPDATE`). |
| `quota_repo_postgres.py` | `QuotaRepository` on asyncpg, transactional writes. |
| `cached_quota_repo.py` / `cached_subscription_repo.py` | Cache-aside Redis decorators (TTL 60s) with invalidation. |
| `subscription_repo.py` | Subscription upserts + quota tier sync. |
| `billing_deadletter_repo.py` | Durable failed-webhook storage for replay. |
| `pipeline_ownership_repo.py` | SQLite `PipelineOwnershipPort` adapter + backfill of the legacy JSON store. |

## Valkey / Redis / state

| File | What it does |
|------|--------------|
| `valkey/client.py` | Canonical shared connection pool (`get_valkey_pool`); `get_redis`/`set_redis` kept as deprecated aliases. |
| `valkey/cache_adapter.py` / `memory_cache_adapter.py` | `SharedCachePort` adapters (Valkey, in-memory fallback). |
| `valkey/state_adapter.py` / `memory_state_adapter.py` | `DistributedStatePort` adapters — Lua for token bucket and circuit state. |
| `redis/client.py` | Older shared Redis pool (superseded by `valkey/client.py`). |
| `redis/run_state.py` | `RunStateManager` — distributed active/cancelled run sets with in-memory fallback. |
| `redis/in_memory.py` | `RunStateStore` — per-run cancellation events for single-process mode. |

## Resilience, auth, billing, email

| File | What it does |
|------|--------------|
| `circuit_breaker.py` (21KB) | `CircuitBreaker` + `RedisCircuitBreaker`, states, stats, registry. |
| `rate_limiter.py` (21KB) | Token-bucket rate limiter with sliding window; in-process with optional Redis backing. |
| `auth_legacy.py` | Legacy API-key auth: `AuthManager`, `APIKey`, `Scope`, `DEFAULT_SCOPES`. |
| `auth/__init__.py` | `get_auth_adapter` factory — picks by environment. |
| `auth/supabase_adapter.py` | Production `AuthPort` (JWT validation against Supabase). |
| `auth/local_adapter.py` | Local JWT signing for dev/tests. |
| `billing/stripe_adapter.py` / `paypal_adapter.py` | `BillingPort` implementations. |
| `billing/webhooks.py` | Stripe/PayPal receivers: signature verification, dedup TTL, DB claim, dead-letter on failure. |
| `email/resend_adapter.py` | `EmailPort` via Resend; degrades gracefully without a key. |

## execution/ — code sandbox

| File | What it does |
|------|--------------|
| `container_sandbox.py` | `ContainerExecutionSandbox` — the approved `CodeExecutorPort`; calls the sandbox worker over HTTP, never touches Docker itself. |
| `noop_executor.py` | Graceful degradation when the sandbox is unavailable. |
| `subprocess_executor.py` | Sandboxed subprocess execution for PoT verification (resource limits, temp dir). |
| `runners/base.py`, `runners/__init__.py`, `runners/python_runner.py` | `LanguageRunner` strategy: builds the fixed image/argv per language; code is base64-encoded into argv, never shell-interpolated. |
| `sandbox_worker/app.py`, `__main__.py`, `docker_runner.py` | The only process with Docker access: token-guarded HTTP API, one hardened job container per request (non-root UID, read-only rootfs, pids limit, tmpfs). |

## search/, scraper, uploads, prism

| File | What it does |
|------|--------------|
| `search/discovery.py` (16KB) | `DiscoveryClient` / `get_search_client` — multi-backend factory, Perplexity client, query decomposition with cache. |
| `search/brave_adapter.py` | Brave Search (web, LLM-context, images, videos). |
| `search/tavily_adapter.py` | Tavily search + extract. |
| `scraper.py` | Deep read: fetch page, convert HTML to markdown. |
| `uploader.py` (24KB) | File upload + text extraction (PDF/TXT/DOCX), encryption at rest, hash index dedupe. |
| `prism/file_search.py` | `FileSearchPort` over Neuro embeddings and upload sidecars. |

## watermark/ (image + Layer B)

| File | What it does |
|------|--------------|
| `scrubber.py` | `ImageMarkScrubber` — the `ImageMarkScrubberPort`: detect, strip, re-inspect. |
| `data_url.py` | data-URL to bytes codec at the adapter boundary. |
| `rewriter.py` | Layer B rewrite prompts + non-origin model selection. |
| `image/detect.py` | Magic-byte format detection (PNG/JPEG/WebP/AVIF/HEIC). |
| `image/png.py`, `jpeg.py`, `webp.py`, `isobmff.py` | Per-format C2PA/AI-provenance inspect + strip, pure byte walks. |
| `image/markers.py` | Shared C2PA marker vocabulary. |
| `image/registry.py` | Format to scrubber-module dispatch. |
| `pixel/noop.py` | Null-object `PixelScrubberPort` (real pixel-domain removal not bound). |

## widgets/, websocket/, observability, misc

| File | What it does |
|------|--------------|
| `widgets/protocol.py` | `Widget`, `BaseWidget`, `WidgetType`, `WidgetResult`, `WidgetDetectionResult` — the port. |
| `widgets/registry.py` | `WidgetRegistry`: discovery, execution, lifecycle, default registrations. |
| `widgets/weather.py`, `stocks.py`, `calculator.py`, `discover.py`, `image_search.py`, `video_search.py` | Individual widgets (Open-Meteo, Yahoo Finance, asteval, trending, multi-backend media search). |
| `widgets_legacy.py` (21KB) | Older monolithic widget engine with its own safe-expression evaluator. |
| `websocket/manager.py` (22KB) | `WebSocketManager`, sessions, event-bus integration, pipeline authorization. |
| `websocket/ws_security.py` | Pre-accept Origin validation and per-IP connect rate limiting. |
| `observability/langfuse_subscriber.py` | Maps `LLMGenerationCompleted` events to Langfuse traces. |
| `metrics.py` | Prometheus metric definitions (queries, quota, LLM errors, durations, pool stats). |
| `token_cache.py` (17KB) | Semantic cache keyed by (problem hash, phase) with token-based eviction. |
| `translation/composite.py`, `deepl_client.py`, `llm_translator.py` | `TranslationPort`: DeepL → LLM → identity fallback chain. |
| `verbalized_sampling.py` | VS primitives: build prompt, parse response, sample, entropy. |
| `telemetry/call_telemetry_store.py` | SQLite per-call telemetry (ACR Phase 1). |
| `clients.py` | Shared pooled HTTP clients (neuro client lifecycle). |
| `renderer.py` | Thin shim → `application/services/renderers`. |
| `server_check.py` | Startup component verification script. |

## Key entry points & gotchas

- **Adding a model:** `llm/registry.py` whitelist first, then presets in `domain/preset_registry.py`. `bloc_of` / `_vendor_of` must classify it or the bloc-diversity constraint will reject routings.
- **Adding a provider:** subclass `BaseLLMProvider` (usually via `openai_compat.py`), register in the registry factory, then test with `--sequential` to avoid rate limits.
- Fallbacks are cross-lab by design; never fall back blindly to the preset primary.
- Two event stores exist (SQLite default, Postgres production) — check `settings` before assuming which one a test hits.
- Valkey is the canonical shared-state backend; `redis/` modules are the older path kept for compatibility.
- The sandbox worker is the only Docker-privileged surface; the backend must reach code execution through `container_sandbox.py`, never by invoking Docker itself.
