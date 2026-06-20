# Plan: Multi-Backend Search — Replace SearXNG with Tiered Alternatives

> **Created:** 2026-06-20
> **Status:** DRAFT / not started
> **Scope:** 4 new search adapters behind existing `SearchServicePort` Protocol
> **Prerequisite:** `CODE_AS_HARNESS_ENHANCEMENT_PLAN.md` P0–P4 complete (executor, evidence, federation all live)

---

## 0. Current State Audit

### Backend routing

```
get_discovery_client(source_type)
    │
    ├─ SearXNG circuit allows? ──► DiscoveryClient → SearXNGAdapter (JSON API)
    │
    └─ SearXNG fails + OPENROUTER_API_KEY set? ──► PerplexitySearchClient (single answer)

    Fallback: SearXNG anyway (caller handles errors)
```

**Problems with current state:**

1. **SearXNG is single-point-of-failure** — Docker-dependent, circuit-breaker gated. Local dev without Docker gets no search.
2. **Perplexity fallback is underpowered** — uses `sonar` (cheapest tier) with `search_context_size: low`. Returns a single synthesized result, not multi-source discovery.
3. **No tiering** — premium presets pay the same as budget for search. Article/research methods that need high-quality multi-source context get the same backend as a quick fact-check.
4. **No freshness differentiation** — all search uses the same recency model. The plan's `SEMANTIC_RERANK_VETTING` flag exists but has no per-method search routing.

### Which methods hit SearXNG (and when)

| Method | Phase | SearXNG usage | Criticality |
|--------|-------|---------------|-------------|
| **Multi-perspective** | Context Vetting (1.25) | Query decomposition → multi-source discovery → rerank → LLM vetting | High — search quality directly affects perspective quality |
| **Article** | Retrieve Sources (2) | Source discovery for long-form writing | High — article quality depends on source breadth |
| **Research** | Deep Research (2) | Multi-round iterative search with refinement | Critical — research method IS search |
| **Prism Research** | Web/Academic/Discussion | Categorized search with source-type routing | Medium — used when Prism classification triggers |
| **HyperGate direct** | Web search action | Quick search results bypassing pipeline | Low — simple queries, low quality bar |
| **Deep Read** | Fallback | Searches when primary sources are sparse | Low — fallback path only |

---

## 1. Architecture Constraints (NON-NEGOTIABLE)

All new adapters must comply with:

| Principle | Rule |
|-----------|------|
| **Hexagonal DDD** | Every new search backend is an `Infrastructure` adapter implementing `SearchServicePort` from `core/ports/search_port.py`. Phases/flows depend ONLY on the port, never on concrete adapters. |
| **Feature flags** | Each backend gateable via `settings.py` env var. Budget runs remain byte-identical when flags are off. |
| **Tiering** | Per-method tier assignment (budget/premium) gates which backend each method uses. Premium methods get Perplexity Deep Research / Brave; budget methods get Perplexity Sonar / Tavily. |
| **Graceful degradation** | If a premium backend fails, fall through to budget backend, then to existing Perplexity fallback, then to no-search. Never crash. |
| **Circuit breaker** | Each new backend gets its own circuit breaker instance. Existing `CircuitBreaker` pattern reused. |
| **`--resume` safety** | No state schema changes. Search results flow into `state.vetted_context`, `state.web_discovery_results` — same keys, same types. |
| **No magic numbers** | All tier mappings, timeouts, and backend URLs in constants files. |

---

## 2. New Backend Adapters (4 total)

### 2.1 Perplexity Sonar Pro (upgrade existing)

**Effort:** 1 line

```
current: "sonar" → "perplexity/sonar", extra_body: {"search_context_size": "low"}
upgrade:  "sonar-pro" → "perplexity/sonar-pro", extra_body: {"search_context_size": "medium"}
```

Add a second entry for Research method:

```python
# registry.py
"sonar-deep-research": {"model": "perplexity/sonar-deep-research", "extra_body": {"reasoning_effort": "medium"}},
```

**Why:** Perplexity is already integrated. Upgrading from `sonar` to `sonar-pro` gives richer citations and better answer quality. Deep Research model handles iterative multi-query search natively — replaces the pipeline's query decomposition logic for the Research method.

**Cost:** `sonar-pro` ≈ $0.006/query (budget tier). Deep Research ≈ $0.41–$1.32/query (premium tier only).

**Feature flag:** `PERPLEXITY_SEARCH_TIER: str = os.getenv("PERPLEXITY_SEARCH_TIER", "sonar-pro")`

### 2.2 Brave Search API

**New file:** `src/reasoner/infrastructure/search/brave_adapter.py`

```python
class BraveSearchAdapter:
    """Implements SearchServicePort for Brave Search API."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.BRAVE_SEARCH_API_KEY
        self.circuit = get_circuit_breaker("brave_search")

    async def search(
        self, query: str, num_results: int = 10,
        source_type: str = "general", domain: str | None = None,
    ) -> list[SearchResult]: ...

    async def close(self) -> None: ...
```

**Key features:**
- Calls `api.search.brave.com/res/v1/web/search` with `X-Subscription-Token` header
- Source-type mapping: `academic` → adds `+site:arxiv.org OR site:scholar.google.com` to query; `news` → adds `&freshness=pm` (past month); `code` → adds `+site:github.com OR site:stackoverflow.com`
- LLM Context endpoint (`/res/v1/web/llm_context`) returns RAG-optimized snippets for direct LLM consumption — used by Article and Research methods
- Circuit breaker: `failure_threshold=3`, `timeout_seconds=30`
- Rate limit handling: checks `X-RateLimit-Reset` header, backs off

**Cost:** $5/1K queries. 1,000 free/month. No API key → adapter returns empty (graceful degradation).

**Feature flag:** `BRAVE_SEARCH_ENABLED: bool = os.getenv("BRAVE_SEARCH_ENABLED", "true").lower() == "true"`

### 2.3 Tavily Search + Extract

**New file:** `src/reasoner/infrastructure/search/tavily_adapter.py`

```python
class TavilyAdapter:
    """Implements SearchServicePort for Tavily API."""

    async def search(self, query, num_results=10, source_type="general", domain=None):
        # POST api.tavily.com/search with structured output
        ...

    async def extract(self, urls: list[str]) -> list[dict]:
        # POST api.tavily.com/extract — raw content from URLs
        ...
```

**Key features:**
- Structured output: each result has `title`, `url`, `content` (cleaned text), `score`, `raw_content`
- Extract mode: replaces Deep Read's per-URL scraping with a single API call
- 180ms p50 latency — fastest of all options
- Source-type routing: `include_domains` / `exclude_domains` parameters
- Free tier: 1,000 queries/month

**Cost:** Free tier sufficient for dev. Paid tiers for production.

**Feature flag:** `TAVILY_SEARCH_ENABLED: bool = os.getenv("TAVILY_SEARCH_ENABLED", "true").lower() == "true"`

### 2.4 OpenRouter `web_search` (inline search)

**No new adapter — parameter injection on existing `OpenRouterProvider`.**

```python
# router.py or openai_compat.py
if role == "primary" and getattr(state, "web_search_enabled", False):
    kwargs["extra_body"]["web_search"] = True
```

**Key features:**
- No separate API call — the LLM call includes `web_search: true` in the request body. OpenRouter proxies the search internally and injects results into the model's context.
- Only works with models that support it: `google/gemini-3.5-flash`, `anthropic/claude-fable-5`
- Replaces the HyperGate direct-search path entirely
- $0.01–$0.014/search surcharge

**Feature flag:** `OPENROUTER_WEB_SEARCH_ENABLED: bool = os.getenv("OPENROUTER_WEB_SEARCH_ENABLED", "true").lower() == "true"`

---

## 3. Per-Method Routing Table

Each method gets a **search tier** (budget/premium) based on `get_preset_price_tier()`. The tier determines which backend chain is tried.

| Method | Tier | Primary | Fallback 1 | Fallback 2 |
|--------|------|---------|------------|------------|
| **Multi-perspective / budget** | budget | Perplexity Sonar Pro | Tavily Search | existing Perplexity |
| **Multi-perspective / premium** | premium | Perplexity Sonar Pro | Brave Search + LLM Context | Tavily |
| **Article / budget** | budget | Brave Search | Tavily | existing SearXNG |
| **Article / premium** | premium | Brave Search + LLM Context | Perplexity Deep Research | Tavily |
| **Research / budget** | budget | Perplexity Sonar Pro (multi-query) | Brave Search | Tavily |
| **Research / premium** | premium | Perplexity Deep Research | Brave Search + LLM Context | Tavily |
| **Prism Research** | budget | Tavily (structured output) | Brave Search | Perplexity |
| **HyperGate direct** | budget | OpenRouter `web_search` on Gemini Flash | Tavily | Perplexity |
| **Deep Read fallback** | budget | Tavily Extract | Brave Search | — |

### Routing implementation

Extend `get_discovery_client()` → `get_search_client_for_method(method, tier)`:

```python
def get_search_client_for_method(
    method: str,
    tier: str = "budget",
    source_type: str = "general",
) -> SearchServicePort:
    """Return the best search client for a method and tier.

    Tries primary → fallback 1 → fallback 2 → existing Perplexity.
    Each backend gates on its feature flag + circuit breaker + API key.
    """
    backends = _METHOD_SEARCH_CHAINS.get(method, {}).get(tier, [])
    for backend_name in backends:
        client = _try_backend(backend_name, source_type)
        if client:
            return client
    return _try_backend("perplexity", source_type)  # ultimate fallback
```

---

## 4. File Manifest

| File | Change | Lines |
|------|--------|-------|
| `src/reasoner/infrastructure/search/brave_adapter.py` | **New** — Brave Search adapter | ~120 |
| `src/reasoner/infrastructure/search/tavily_adapter.py` | **New** — Tavily Search + Extract adapter | ~100 |
| `src/reasoner/infrastructure/search/discovery.py` | Extend `get_discovery_client` → method-tier routing | +40 |
| `src/reasoner/infrastructure/llm/registry.py` | Add `sonar-pro`, `sonar-deep-research` entries | +6 |
| `src/reasoner/core/settings.py` | 4 new feature flags + 2 API key settings | +12 |
| `src/reasoner/core/constants_limits.py` | Method-tier search chain mappings, backend timeouts | +30 |
| `src/reasoner/core/ports/search_port.py` | No change — existing Protocol covers all | 0 |
| `src/reasoner/api/__init__.py` | No change — DI injects via existing `get_search_service` | 0 |
| `src/reasoner/application/flows/search_phases.py` | Replace direct `get_discovery_client` with method-aware `get_search_client_for_method` | ~10 |
| `src/reasoner/application/flows/article_phases.py` | Same | ~5 |
| `src/reasoner/application/flows/research_phases.py` | Same | ~5 |
| `src/reasoner/application/flows/prism_research.py` | Same | ~5 |
| **Total** | | **~333 lines** |

---

## 5. Implementation Order

| Step | File | Description | Effort |
|------|------|-------------|--------|
| **1** | `settings.py` + `registry.py` | Feature flags + Perplexity upgrade entries | S (5 min) |
| **2** | `brave_adapter.py` | Brave Search adapter | M (30 min) |
| **3** | `tavily_adapter.py` | Tavily adapter | M (30 min) |
| **4** | `constants_limits.py` | Method-tier search chains + backend config | S (15 min) |
| **5** | `discovery.py` | `get_search_client_for_method()` routing | M (20 min) |
| **6** | `search_phases.py` et al. | Wire method-aware client into all 4 call sites | S (10 min) |
| **7** | Verify | `curl` each method with `web_search: true` | M (20 min) |

**Total: ~2 hours**

---

## 6. Verification

```bash
# 1. All adapters implement SearchServicePort
python -c "
from reasoner.core.ports.search_port import SearchServicePort
from reasoner.infrastructure.search.brave_adapter import BraveSearchAdapter
assert isinstance(BraveSearchAdapter(), SearchServicePort)
print('Brave: OK')
"

# 2. Method-tier routing resolves
python -c "
from reasoner.infrastructure.search.discovery import get_search_client_for_method
client = get_search_client_for_method('multi_perspective', 'budget')
print(f'Budget multi-perspective → {type(client).__name__}')
"

# 3. No import errors on cold start
python -c "from reasoner.application.pipeline import ReasonerPipeline; print('OK')"

# 4. Budget preset still works with SearXNG disabled
SEARXNG_URL= BRAVE_SEARCH_ENABLED=false TAVILY_SEARCH_ENABLED=false \
  curl -s http://localhost:8003/api/run -d '{"problem":"test","preset":"multi-perspective-budget"}' \
  | grep '"type":"done"'
```

---

## 7. Future (out of scope v1)

- **Search quality telemetry** — per-backend latency/cost/result-count telemetry into `TelemetryStore` for Scorecard diagnosis
- **Auto-tier selection** — Evolution Agent (#4) can propose backend swaps based on cost/quality Scorecard data
- **Search caching** — cache identical queries across runs using `TokenAwareCache` infrastructure
- **Parallel multi-backend** — fire all backends simultaneously for fast-fail + result merging (HyperGate pattern)
