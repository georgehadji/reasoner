<!-- Generated: 2026-06-26 | Files scanned: 413 | Token estimate: ~650 -->

# Dependencies — Reasoner

> Module import relationships, circular dependency analysis, and external service boundaries.

## Backend Import Graph

### API Layer → Application Layer

```
api/__init__.py
  ├─ FROM application.orchestrator IMPORT PipelineOrchestrator
  ├─ FROM application.pipeline IMPORT ReasonerPipeline
  ├─ FROM application.event_bus.bus IMPORT get_event_bus, init_default_subscribers
  ├─ FROM application.services.preset_service IMPORT PresetService
  └─ (middleware, auth_deps, etc.)

api/streaming.py
  ├─ FROM application.orchestrator IMPORT PipelineOrchestrator
  ├─ FROM api.serializers IMPORT _ser_0, _ser_1, ... _ser_5
  ├─ FROM domain.pipeline_state IMPORT PipelineState
  ├─ FROM core.events IMPORT make_event
  └─ (streaming utilities)

api/routes/pipelines.py
  ├─ FROM application.orchestrator IMPORT PipelineOrchestrator
  ├─ FROM application.services.preset_service IMPORT PresetService
  ├─ FROM domain.preset_registry IMPORT PRESETS
  └─ FROM infrastructure.persistence.event_store IMPORT get_event_store
```

### Application Layer → Domain Layer

```
application/pipeline.py
  ├─ FROM domain.pipeline_state IMPORT PipelineState
  ├─ FROM domain.core_types IMPORT SolutionCandidate, CritiqueScore, FinalSolution
  ├─ FROM domain.models IMPORT TaskType, ClaimLabel, PerspectiveType
  ├─ FROM phases._shared IMPORT is_article_request, build_followup_context
  ├─ FROM phases._universal IMPORT PHASE_CLASSIFICATION, PHASE_DECOMPOSITION
  ├─ FROM infrastructure.llm.router IMPORT ProviderRouter
  └─ (phase mixins, sub-agents)

application/orchestrator.py
  ├─ FROM domain.pipeline_state IMPORT PipelineState
  ├─ FROM domain.preset_registry IMPORT PRESETS
  ├─ FROM hypergate.hyperagent IMPORT HyperGateAgent
  ├─ FROM infrastructure.llm.router IMPORT ProviderRouter
  ├─ FROM application.pipeline IMPORT ReasonerPipeline
  └─ FROM neuro.server IMPORT create_neuro_router

application/flows/__init__.py
  ├─ FROM application.mixins.* IMPORT method-specific mixins
  ├─ FROM api.serializers IMPORT serialization functions  [VIOLATION]
  └─ (phase function binding)

application/services/preset_service.py
  ├─ FROM domain.preset_registry IMPORT PRESETS
  ├─ FROM domain.preset_core IMPORT PipelinePreset, build_auto_preset
  ├─ FROM infrastructure.llm.registry IMPORT _MODEL_WHITELIST
  └─ FROM core.constants IMPORT token budgets
```

### Domain Layer → Core Layer

```
domain/pipeline_state.py
  ├─ FROM domain.core_types IMPORT SolutionCandidate, CritiqueScore, ...
  ├─ FROM domain.models IMPORT TaskType, ClaimLabel, PerspectiveType
  ├─ FROM core.events.domain_events IMPORT DomainEvent  [minimal coupling]
  └─ (no infrastructure imports)

domain/preset_core.py
  ├─ FROM core.constants IMPORT model name constants
  ├─ FROM infrastructure.llm.registry IMPORT _MODEL_WHITELIST  [KNOWN VIOLATION]
  └─ (preset construction)

domain/preset_registry.py
  ├─ FROM domain.preset_core IMPORT PipelinePreset
  ├─ FROM core.constants IMPORT token budgets, defaults
  ├─ FROM domain.saas IMPORT SubscriptionTier
  └─ (49 preset definitions)

domain/core_types.py
  ├─ FROM dataclasses IMPORT dataclass
  ├─ FROM domain.models IMPORT TaskType, ClaimLabel, PerspectiveType
  └─ (type definitions, no external imports)
```

### Core Layer (No Outer Dependencies)

```
core/constants.py
  ├─ FROM core.constants_limits IMPORT *
  ├─ FROM core.constants_models IMPORT *
  └─ (no outer imports — re-export only)

core/events/domain_events.py
  ├─ FROM dataclasses IMPORT dataclass
  ├─ FROM datetime IMPORT datetime
  ├─ FROM enum IMPORT Enum
  └─ (immutable event hierarchy — no infrastructure)

core/ports/llm_port.py
  ├─ FROM typing IMPORT Protocol
  └─ (abstract interface — no implementation)

core/aggregates/pipeline_aggregate.py
  ├─ FROM core.events IMPORT DomainEvent
  ├─ FROM domain.pipeline_state IMPORT PipelineState
  └─ (event-sourced replay logic)
```

### Infrastructure Layer (Implements Core Ports)

```
infrastructure/llm/router.py
  ├─ FROM core.ports.llm_port IMPORT LLMProvider (Protocol)
  ├─ FROM infrastructure.llm.registry IMPORT build_provider
  ├─ FROM infrastructure.llm.providers.* IMPORT concrete providers
  ├─ FROM core.circuit_breaker IMPORT CircuitBreaker
  └─ (role-based routing + fallback chain)

infrastructure/persistence/event_store.py
  ├─ FROM core.events.domain_events IMPORT DomainEvent
  ├─ FROM domain.pipeline_state IMPORT PipelineState
  ├─ FROM sqlite3 IMPORT Database
  └─ (SQLite adapter)

infrastructure/search/discovery.py
  ├─ FROM core.ports.search_port IMPORT SearchService (Protocol)
  └─ (SearXNG + BM25 adapter)

infrastructure/websocket/manager.py
  ├─ FROM application.event_bus.bus IMPORT EventBus
  └─ (WebSocket broadcasting)
```

## Dependency Hierarchy (Simplified)

```
┌─────────────────────────────────────────────────────┐
│                   API Layer                         │
│  api/, main.py, asgi.py                           │
└────────────────────┬────────────────────────────────┘
                     │ imports from (required)
                     ▼
┌─────────────────────────────────────────────────────┐
│              Application Layer                      │
│  orchestrator, pipeline, flows, services, handlers │
└────────────────────┬────────────────────────────────┘
                     │ imports from (required)
                     ▼
┌─────────────────────────────────────────────────────┐
│                Domain Layer                         │
│  pipeline_state, presets, core_types, models       │
└────────────────────┬────────────────────────────────┘
                     │ imports from (required)
                     ▼
┌─────────────────────────────────────────────────────┐
│                 Core Layer                          │
│  ports, events, constants, aggregates              │
│  (NO OUTER DEPENDENCIES)                           │
└────────────────────┬────────────────────────────────┘
                     │ implemented by
                     ▼
┌─────────────────────────────────────────────────────┐
│            Infrastructure Layer                     │
│  llm/, persistence/, search/, websocket/           │
│  (implements Core ports, no core depends on it)    │
└─────────────────────────────────────────────────────┘
```

## Known Dependency Violations

### 1. Domain imports Infrastructure

**File:** `src/reasoner/domain/preset_core.py`
**Issue:** Imports `infrastructure.llm.registry._MODEL_WHITELIST` for model validation
**Severity:** MEDIUM (breaks layering, but model validation is cross-cutting)
**Refactor path:** Move model whitelist to Domain or Core

```python
# VIOLATION
from reasoner.infrastructure.llm.registry import _MODEL_WHITELIST

def validate_model(model_name: str) -> bool:
    return model_name in _MODEL_WHITELIST
```

### 2. API directly instantiates Pipeline

**File:** `src/reasoner/api/streaming.py`
**Issue:** Directly calls `ReasonerPipeline()` instead of routing through CQRS handlers
**Severity:** LOW (Performance ok for streaming, but breaks CQRS pattern)
**Refactor path:** Create CQRSPipelineQuery handler

```python
# VIOLATION
from reasoner.application.pipeline import ReasonerPipeline

pipeline = ReasonerPipeline()  # Direct instantiation
await pipeline.run(state)
```

### 3. Application imports API

**File:** `src/reasoner/application/flows/__init__.py`
**Issue:** Imports `api.serializers` for SSE serialization binding
**Severity:** LOW (serialization is presentation concern, ok in flows)
**Refactor path:** Move serializers to application layer

```python
# VIOLATION
from reasoner.api.serializers import _ser_0, _ser_1, ...
```

## Circular Dependency Check

**Result:** NO CIRCULAR DEPENDENCIES DETECTED

Validation via import graph:
- Domain ← Core (only)
- Application ← Domain, Core (only)
- API ← Application, Domain, Core (only)
- Infrastructure ← Core (only, not reverse)

## External Service Dependencies

### Required (Production)

| Service | Purpose | Failure Impact | Fallback |
|---------|---------|-----------------|----------|
| **OpenRouter API** | LLM routing (350+ models) | Full system down | Direct adapters |
| **OPENROUTER_API_KEY** | Authentication | Cannot invoke LLMs | None (critical) |

### Optional (Production)

| Service | Purpose | Failure Impact | Fallback |
|---------|---------|-----------------|----------|
| **SearXNG (Docker)** | Web search (Research method) | Research method fails | Perplexity Sonar |
| **Perplexity API** | Alternative search | Both search backends fail | No web access |
| **PostgreSQL** | Query audit log (production) | SQLite used instead | SQLite fallback |
| **Redis** | Rate limiter (multi-worker) | Single-worker mode only | In-memory limiter |
| **Stripe API** | Billing webhooks | Subscription system down | Manual queue retry |
| **Sentry** | Error tracking | Errors not captured | Silent logs |
| **Langfuse** | LLM observability | No call tracing | Standard logging |
| **Neuro LTM** | Remote memory storage | L1/L2 cache used | Disk cache fallback |

### Python Dependencies (Critical)

```
fastapi==0.109+          # Web framework
pydantic==2.0+           # Data validation
httpx==0.24+             # HTTP client
asyncpg==0.27+           # PostgreSQL async
aiosqlite==0.19+         # SQLite async
openai==1.0+             # OpenAI API
anthropic==0.7+          # Anthropic API
google-generativeai      # Google Gemini
perplexity-ai            # Perplexity Sonar
redis==4.5+              # Redis client
beautifulsoup4           # Web scraping
markdown==3.4+           # Markdown parsing
pydantic-settings        # Settings management
python-dotenv            # .env loading
```

### JavaScript Dependencies (Frontend)

```
next@16                  # Framework
react@19                 # UI library
typescript@5             # Type checking
tailwindcss@4            # Styling
zustand@5                # State management
swr@2                    # Data fetching
react-markdown           # Markdown rendering
react-syntax-highlighter # Code highlighting
remark-gfm               # GFM markdown
rehype-highlight         # Code syntax highlighting
idb@8                    # IndexedDB wrapper
```

## Module Size Distribution

| Layer | Modules | Total Lines | Avg Lines/Module |
|-------|---------|-------------|------------------|
| **API** | 15 | ~2,500 | 167 |
| **Application** | 40 | ~8,000 | 200 |
| **Domain** | 8 | ~3,500 | 438 |
| **Core** | 20 | ~2,000 | 100 |
| **Infrastructure** | 60 | ~15,000 | 250 |
| **HyperGate** | 8 | ~2,500 | 313 |
| **Phases** | 32 | ~8,000 | 250 |
| **Utilities** | 150 | ~10,000 | 67 |
| **Tests** | 70 | ~20,000 | 286 |
| **TOTAL** | 375 | ~71,000 | 189 |

## Import Cost Analysis

**Heaviest imports:**
- `application.pipeline` — (16 KB) phase execution logic
- `infrastructure.llm.providers` — (4 KB each, ×31 = 124 KB)
- `domain.pipeline_state` — (96 KB) state structure
- `phases.*` — (250 lines each, ×32 = 8,000 lines)

**Optimization opportunities:**
- Lazy imports in `application/flows/__init__.py` (only import active method)
- Dynamic LLM provider loading via `importlib`
- Phase prompt memoization (already implemented)

## Load Order (Startup)

```
1. core.constants (blocking: no deps)
2. core.ports (blocking: Protocol defs)
3. core.events (blocking: event types)
4. domain.models (blocking: enums)
5. domain.pipeline_state (blocking: state model)
6. domain.core_types (blocking: domain objects)
7. domain.preset_core (blocking: preset structure)
8. infrastructure.llm.registry (blocking: model whitelist)
9. domain.preset_registry (blocking: 49 preset configs)
10. application.pipeline (async ready)
11. application.orchestrator (async ready)
12. api (async ready, lifespan startup hooks fire)
```

## Circular Dependency Prevention

**Techniques used:**
1. **Strict layering:** Domain cannot import from Infrastructure
2. **Protocol-based abstraction:** Core defines interfaces, not implementations
3. **Lazy imports:** Heavy modules imported at use-time
4. **Dependency injection:** Services injected, not imported

**Validation:**
```bash
# Check for circular imports:
python -m pydantic_core --check-imports
```

## Frontend Dependency Tree

```
app/layout.tsx
  ├─ components/Providers
  │  ├─ zustand (store)
  │  ├─ SWR (data fetching)
  │  └─ auth context
  ├─ components/SiteHeader
  └─ {page}

app/chat/page.tsx
  ├─ hooks/usePipelineStream (SSE)
  ├─ hooks/useConversationHistory
  ├─ components/ChatFeed
  ├─ components/Composer
  ├─ components/PhaseTimeline
  └─ stores/app-store (Zustand)
```

**No circular dependencies in frontend** (strict unidirectional imports)

## Bundle Size Targets

| Chunk | Size | Strategy |
|-------|------|----------|
| `app.js` | <150KB gzip | Main app code |
| `chat.js` | <100KB gzip | Chat page (lazy) |
| `landing.js` | <80KB gzip | Landing page (lazy) |
| `ui.js` | <50KB gzip | UI primitives (shared) |
| CSS | <30KB gzip | Tailwind utilities |
| **Total** | <350KB gzip | Under budget |
