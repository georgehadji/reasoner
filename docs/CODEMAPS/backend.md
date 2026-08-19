<!-- Generated: 2026-08-19 | Files scanned: 523 | Token estimate: ~900 -->

# Backend Structure — Reasoner

> Python 3.12 backend organization post-v3.0 refactoring.

## Package Hierarchy

```
src/reasoner/
├── api/                       # FastAPI HTTP/SSE interface (30+ endpoints)
│   ├── __init__.py            # App factory, CORS, middleware, route mounting, lifespan
│   ├── streaming.py           # Core SSE: run_stream(), run_followup_stream(), run_stream_cached()
│   ├── serializers.py         # Phase-specific SSE serialization (_ser_0 through _ser_5)
│   ├── schemas.py             # Pydantic request/response models (RunRequest, PipelineResponse, etc.)
│   ├── middleware.py          # SecurityHeadersMiddleware, memory limits, timeouts
│   ├── auth_deps.py           # OAuth2/token dependencies with scoped permissions
│   ├── sentry.py              # Error tracking initialization
│   ├── error_handler.py       # Global exception handler registration
│   └── routes/                # 14 modular route handler files
│       ├── pipelines.py       # POST /pipelines/run, /list, /resume, /stop
│       ├── context.py         # POST /context/fetch (fetch + vet external context)
│       ├── health.py          # GET /health (liveness), /health/deep (readiness)
│       ├── estimate.py        # POST /estimate (cost + token pre-estimation)
│       ├── history.py         # GET /history/queries, POST /history/export
│       ├── uploads.py         # POST /uploads (file handling)
│       ├── images.py          # POST /images/analyze (vision LLM), /images/extract (OCR)
│       ├── widgets.py         # POST /widgets/calculator, /widgets/stocks, /widgets/weather
│       ├── websocket.py       # WebSocket /ws (real-time event stream)
│       ├── admin.py           # GET /admin/stats, /admin/users (admin operations)
│       ├── feedback.py        # POST /feedback (user feedback)
│       ├── keys.py            # POST /keys/generate, GET /keys/list (API key management)
│       ├── errors.py          # POST /errors/report (error reporting)
│       └── legacy_widgets.py  # Backward compat widget routes
│
├── application/               # CQRS, orchestration, flows, services, event bus
│   ├── pipeline.py            # ReasonerPipeline (real impl, 16 KB) — phase execution orchestrator
│   ├── orchestrator.py        # PipelineOrchestrator (3-phase: preflight/execute/postflight)
│   ├── event_bus/
│   │   ├── bus.py             # EventBus class, init_default_subscribers(), get_event_bus()
│   │   └── [subscriber impl]  # History, WebSocket, Neuro, Metrics subscribers
│   ├── flows/
│   │   ├── __init__.py        # build_default_flow_registry() — binds 19 methods to ReasonerPipeline
│   │   ├── research_phases.py # Research-specific phase modules (Prism loop)
│   │   └── [19 method modules] # Phase functions for debate, jury, scientific, socratic, etc.
│   ├── handlers/              # CQRS command handlers (RunPipelineCommandHandler, etc.)
│   ├── mixins/                # Method-specific implementations
│   │   ├── debate.py          # Debate method (opening, rebuttal, judge verdict)
│   │   ├── jury.py            # Jury method (generator, critic, verifier)
│   │   ├── research.py        # Research method (Prism + SearXNG RAG)
│   │   ├── writing.py         # Writing method (hallucination guards)
│   │   ├── scientific.py      # Scientific method (hypothesis + falsification)
│   │   ├── socratic.py        # Socratic method (elenchus questioning)
│   │   ├── pre_mortem.py      # Pre-mortem (failure analysis)
│   │   ├── bayesian.py        # Bayesian (prior → likelihood → posterior)
│   │   ├── dialectical.py     # Dialectical (thesis-antithesis-synthesis)
│   │   ├── analogical.py      # Analogical (cross-domain mapping)
│   │   ├── delphi.py          # Delphi (expert consensus)
│   │   ├── cove.py            # CoVE (Chain-of-Verification)
│   │   ├── sot.py             # SoT (Skeleton-of-Thought)
│   │   ├── tot.py             # ToT (Tree-of-Thoughts)
│   │   ├── pot.py             # PoT (Program-of-Thoughts)
│   │   ├── self_discover.py   # Self-Discovery (dynamic composition)
│   │   ├── brainstorming.py   # Brainstorming (divergent ideation)
│   │   └── coding.py          # Coding method (code generation + review)
│   └── services/              # Domain services
│       ├── preset_service.py  # PresetService — preset resolution + validation
│       ├── search_service.py  # SearchService — SearXNG + Perplexity coordination
│       ├── renderer_service.py # RendererService — CLI pretty-printing
│       ├── serializers.py     # Output serialization by phase
│       └── renderers/         # Phase-specific renderers
│           ├── _render_jury.py
│           ├── _render_debate.py
│           └── [method-specific renderers]
│
├── core/                      # Domain core: protocols, constants, events, aggregates
│   ├── constants.py           # Central import hub (re-exports from constants_limits + constants_models)
│   ├── constants_limits.py    # Token budgets, timeouts, HyperGate thresholds, truncation rules
│   ├── constants_models.py    # Model name constants (MODEL_CLAUDE_SONNET, MODEL_GEMINI_FLASH, etc.)
│   ├── settings.py            # Pydantic Settings + .env support (OPENROUTER_API_KEY, etc.)
│   ├── protocol.py            # PhaseConfig, PhaseResult, Phase Protocol
│   ├── ports/                 # Hexagonal ports (abstract interfaces)
│   │   ├── llm_port.py        # LLMProvider Protocol (send_message, stream_message)
│   │   ├── search_port.py     # SearchService Protocol (search, search_with_context)
│   │   ├── file_search_port.py # FileSearchService Protocol
│   │   └── persistence_port.py # PersistenceService Protocol
│   ├── events/                # Event sourcing
│   │   ├── domain_events.py   # 18 event types (PipelineEventType, WidgetEventType, MemoryEventType, SaaSEventType)
│   │   │                      # make_event() factory function
│   │   └── [event store impl] # SQLite persistence (see infrastructure/)
│   ├── aggregates/            # Domain aggregates
│   │   ├── pipeline_aggregate.py # PipelineAggregate (event-sourced state replay)
│   │   └── widget_aggregate.py # WidgetAggregate
│   ├── health_validator.py    # validate_all() — startup health checks
│   └── compression_utils.py   # Text compression for memory efficiency
│
├── domain/                    # Business entities, presets, declarative routing
│   ├── pipeline_state.py      # PipelineState (~60 fields) — canonical state model
│   │                          # MethodState, CostTrackingState, ConversationState
│   ├── core_types.py          # SolutionCandidate, CritiqueScore, FinalSolution, Decomposition, etc.
│   ├── models.py              # TaskType enum, ClaimLabel, PerspectiveType, PerspectiveRegistry
│   ├── preset_core.py         # PipelinePreset dataclass, build_auto_preset(), _KNOWN_ROUTING_ROLES
│   ├── preset_registry.py     # _PRESET_CONFIGS (49 preset configurations with model routing)
│   ├── saas.py                # SubscriptionTier, QuotaTracker, BillingEvent
│   └── validators.py          # Pydantic validators for domain models
│
├── infrastructure/            # Adapters for external systems
│   ├── llm/                   # LLM provider routing and adapters
│   │   ├── registry.py        # _MODEL_WHITELIST (131 models), _REGISTRY, build_provider()
│   │   ├── router.py          # ProviderRouter (role-based routing, fallback chain)
│   │   ├── ports.py           # LLMProvider Protocol, Message, LLMResponse dataclasses
│   │   ├── providers/         # Concrete provider implementations (31+ adapters)
│   │   │   ├── openai_compat.py # OpenAICompatibleProvider, OpenRouterProvider
│   │   │   ├── anthropic.py   # Anthropic direct adapter
│   │   │   ├── google.py      # Google GenAI direct adapter
│   │   │   ├── perplexity.py  # Perplexity search + reasoning adapter
│   │   │   ├── deepseek.py    # DeepSeek direct adapter
│   │   │   ├── mistral.py     # Mistral direct adapter
│   │   │   ├── ollama.py      # Ollama local inference adapter
│   │   │   ├── xai.py         # xAI Grok adapter
│   │   │   ├── qwen.py        # Qwen adapter
│   │   │   ├── kimi.py        # Kimi adapter
│   │   │   ├── glm.py         # Zhipu GLM adapter
│   │   │   └── [other]        # MiniMax, Tencent, Baidu, Laguna, Elephant
│   │   ├── extraction/        # Vision LLM for image analysis/OCR
│   │   └── executor.py        # LLM execution + circuit breaker wrapper
│   ├── persistence/           # State + event storage
│   │   ├── event_store.py     # SQLite event sourcing (append-only events table)
│   │   ├── snapshots.py       # PipelineSnapshot for fast recovery
│   │   ├── postgres_store.py  # PostgreSQL adapters (query_audit_logs, user_settings)
│   │   └── migrations/        # Schema migration scripts
│   ├── websocket/             # Real-time WebSocket streaming
│   │   └── manager.py         # WebSocketManager (broadcast, connect, disconnect)
│   ├── redis/                 # Redis caching + rate limiting
│   │   └── client.py          # RedisClient wrapper (get, set, incr, ttl operations)
│   ├── search/                # Search provider implementations
│   │   ├── discovery.py       # DiscoveryClient (SearXNG + BM25 local search)
│   │   └── perplexity.py      # PerplexitySearchClient (alternative to SearXNG)
│   └── billing/               # SaaS billing integration
│       ├── webhooks.py        # Stripe webhook handlers (charge.succeeded, charge.failed)
│       └── service.py         # SubscriptionManager, QuotaManager
│
├── hypergate/                 # Request pre-router (5 parallel sub-agents + TieBreaker)
│   ├── hyperagent.py          # HyperGateAgent orchestrator
│   │                          # Fast-path patterns: creative, realtime, factual, research
│   ├── models.py              # HyperContext, SubAgentInput, SubAgentOutput dataclasses
│   ├── base_sub_agent.py      # Abstract SubAgent class with LRU caching
│   └── sub_agents/            # 6 specialized sub-agents
│       ├── language_detector.py # Detects language from problem text
│       ├── complexity_estimator.py # Estimates complexity (simple/medium/complex)
│       ├── direct_detector.py # Detects direct-answer opportunities
│       ├── web_detector.py    # Detects real-time web search needs
│       ├── method_classifier.py # Classifies best reasoning method
│       └── tiebreaker.py      # Resolves conflicts between sub-agents
│
├── phases/                    # 32 immutable phase prompt templates
│   ├── _shared.py             # Shared utilities (is_article_request, build_followup_context)
│   ├── _universal.py          # Universal phases (classification, decomposition, synthesis)
│   └── [19 method-specific modules] # Debate, Jury, Research, Scientific, etc.
│
├── subagents/                 # Phase sub-agents for enhancement + decomposition
│   ├── enhancement_agent.py   # Problem enhancement (clarity, context injection)
│   ├── decomposition_agent.py # Multi-level problem decomposition
│   ├── critique_agent.py      # Independent solution scoring + critique
│   ├── synthesis_agent.py     # Final synthesis from candidates
│   └── search_agent.py        # RAG search coordination
│
├── neuro/                     # Long-term episodic memory (L1/L2/L3 tiered)
│   ├── server.py              # NeuroServer + /neuro/recall, /neuro/learn endpoints
│   ├── compression.py         # smart_compress(text, ext, level) — Aggressive/Minimal
│   ├── cache_engines/         # L1 (memory), L2 (disk JSON), L3 (embedding search)
│   └── sessions.py            # Neuro session management per agent_id
│
├── healing/                   # Self-healing CI/CD introspection + test generation
│   ├── introspection_engine.py # Analyze failing tests + logs
│   ├── test_generation_engine.py # Auto-generate missing test coverage
│   └── generated_tests/       # Inventory of auto-generated tests
│
├── security/                  # Auth, encryption, rate limiting
│   ├── auth.py                # Token-based auth with scoped permissions
│   ├── rate_limiter.py        # Token-bucket rate limiter (memory + Redis modes)
│   ├── circuit_breaker.py     # Circuit breaker pattern for provider fallbacks
│   ├── sanitization.py        # Input sanitization (XSS, null-bytes, prompt-injection, NFKC)
│   ├── encryption.py          # Envelope encryption (AES-256-GCM) + blind indexing
│   └── csrf.py                # CSRF token generation + validation (HMAC-SHA256)
│
├── instrumentation/           # Observability: metrics, tracing, logging
│   ├── metrics.py             # Prometheus metrics (cost, tokens, latency, active users)
│   ├── langfuse.py            # Langfuse tracing integration
│   └── logging_utils.py       # SafeLoggingFilter (redacts API keys, tokens, PII)
│
├── models.py                  # Backward-compat shim → domain/pipeline_state.py
├── pipeline.py                # Backward-compat shim → application/pipeline.py
├── api.py                     # Backward-compat shim → api/__init__.py
├── llm.py                     # Backward-compat shim → infrastructure/llm/router.py
├── phases.py                  # Backward-compat shim → phases modules
├── main.py                    # CLI entry point (argparse runner)
├── asgi.py                    # ASGI app factory for uvicorn
├── clients.py                 # External API clients (Stripe, Sentry, Langfuse)
├── gate_agent.py              # GateAgent (legacy, replaced by HyperGate)
├── parsing.py                 # JSON extraction + repair utilities
├── renderer.py                # CLI rendering + pretty-printing
├── scraper.py                 # Web content extraction (BeautifulSoup wrapper)
└── [utility modules]          # exceptions, errors, helpers
```

## Core Module Dependencies

| From | To | Purpose | Type |
|------|-----|---------|------|
| `api.streaming` | `application.orchestrator` | Orchestrate pipeline | Required |
| `api.routes.*` | `application.services` | Domain services | Required |
| `application.orchestrator` | `domain.pipeline_state` | State management | Required |
| `application.pipeline` | `domain.core_types` | Solution candidates, scores | Required |
| `application.flows` | `phases.*` | Phase prompt access | Required |
| `application.services` | `infrastructure.llm.router` | LLM routing | Required |
| `core.events` | `infrastructure.persistence.event_store` | Event persistence | Adapter |
| `infrastructure.llm.router` | `infrastructure.llm.providers.*` | Provider selection | Factory |

**Circular Dependency Risks:**
- None (strict layering enforced by imports)

## Phase Execution Pipeline

```
ReasonerPipeline.run(state)
  │
  ├─ _phase_0_classification()
  │   ├─ LLM call: prompt_enhancement role
  │   └─ LLM call: classification role
  │
  ├─ _phase_1_decomposition()
  │   └─ LLM call: decomposition role
  │
  ├─ _phase_2_generation()  [PARALLEL perspectives]
  │   ├─ LLM call: constructive role
  │   ├─ LLM call: destructive role
  │   ├─ LLM call: systemic role
  │   └─ LLM call: minimalist role (optional)
  │
  ├─ _phase_3_critique()
  │   ├─ LLM call: scoring role (independent lab)
  │   └─ Pruning: retain top-k candidates
  │
  ├─ _phase_4_stress_test()
  │   ├─ LLM call: stress_testing role
  │   └─ Generate stress scenarios
  │
  └─ _phase_5_synthesis()
      ├─ LLM call: synthesis role
      ├─ Epistemic labeling (VERIFIED/HYPOTHESIS/UNKNOWN)
      └─ Action blueprint generation
```

## LLM Provider Routing

**Role → Model Selection:**
- `prompt_enhancement` — Speed + JSON capability (Gemini Flash Lite, GLM-Air)
- `classification` — JSON-strict parsing (GPT-5-mini, GLM-Air)
- `decomposition` — Structured reasoning (DeepSeek V3)
- `constructive/destructive/systemic/minimalist` — Diversity across labs
- `scoring` — Independent lab (never scorer's parent lab)
- `stress_testing` — Adversarial reasoning (Mistral Small)
- `synthesis` — High-quality integration (Qwen 3.7-Max)

**Fallback Strategy:**
Primary → Lab equivalent → OpenRouter → Error

## Key Metrics

| Metric | Value |
|--------|-------|
| Python modules | 375 |
| LLM models (whitelist) | 131 |
| Presets | 49 |
| Reasoning methods | 19 |
| Phase modules | 32 |
| API routes | 30+ |
| Domain events | 18 |
| Provider adapters | 31+ |
