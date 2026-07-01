# Perplexity Sonar Enhancement Plan

**Date:** 2026-07-01  
**Scope:** Leverage Perplexity Sonar API features (domain filters, recency, Pro Search tools, embeddings) within Reasoner's LLM registry and search infrastructure  
**Architecture constraint:** All changes must flow through the central registry (`src/reasoner/infrastructure/llm/registry.py`), the OpenRouter-compatible provider (`openai_compat.py`), and the preset system (`preset_registry.py`). No hardcoding in pipeline or phase code.

---

## Enhancement Map

| # | Enhancement | Perplexity Feature | Reasoner Files | Effort | Impact |
|---|------------|-------------------|----------------|--------|--------|
| E1 | **Academic-only search filter** | `search_domain_filter` | `registry.py` (extra_body), `research` presets | 2 lines | 🔥 Eliminates Reddit/Facebook/blog spam from research |
| E2 | **Search recency filter** | `search_recency_filter` | `registry.py` (extra_body) | 2 lines | Keeps results within 6-12 months |
| E3 | **Source-type labeling** | `search_results[].source` | `registry.py` (extra_body) + `search_port.py` | ~10 lines | Labels result source (web/academic/news) |
| E4 | **Pro Search tools exposure** | `return_images`, `return_related_questions` | `registry.py` (extra_body) + `openai_compat.py` | ~15 lines | Enables image/media results in research |
| E5 | **Embedding provider** | Perplexity embeddings API | New provider in `llm/providers/` + `registry.py` | ~40 lines | Alternative to OpenAI embeddings for vector store |

---

## E1 — Academic-only Search Filter

### Problem
Research presets return Reddit, Facebook, and blog spam alongside legitimate sources. The budget research test found 24 sources but included `reddit.com/r/Physics`, `facebook.com/groups`, and `patsnap.com` blog posts.

### Fix
Add `search_domain_filter` to Perplexity model `extra_body` in the registry. Use allowlist mode for premium (peer-reviewed domains), denylist mode for budget (exclude noise).

**File:** `src/reasoner/infrastructure/llm/registry.py`

```python
# Perplexity — search-grounded models
"sonar": {
    "model": "perplexity/sonar",
    "extra_body": {
        "web_search_options": {"search_context_size": "low"},
        "search_domain_filter": ["-reddit.com", "-facebook.com", "-pinterest.com", "-quora.com"],
    },
},
"sonar-pro-search": {
    "model": "perplexity/sonar-pro-search",
    "extra_body": {
        "web_search_options": {"search_context_size": "high"},
        "search_domain_filter": ["-reddit.com", "-facebook.com", "-pinterest.com", "-quora.com"],
    },
},
"sonar-pro": {
    "model": "perplexity/sonar-pro",
    "extra_body": {
        "web_search_options": {"search_context_size": "high"},
        "search_domain_filter": ["-reddit.com", "-facebook.com", "-pinterest.com", "-quora.com"],
    },
},
"sonar-reasoning-pro": {
    "model": "perplexity/sonar-reasoning-pro",
    "extra_body": {
        "web_search_options": {"search_context_size": "high"},
        "search_domain_filter": ["-reddit.com", "-facebook.com", "-pinterest.com", "-quora.com"],
    },
},
"sonar-deep-research": {
    "model": "perplexity/sonar-deep-research",
    "extra_body": {
        "reasoning_effort": "high",
        "search_domain_filter": ["-reddit.com", "-facebook.com", "-pinterest.com", "-quora.com"],
    },
},
```

### Architecture note
`search_domain_filter` is pass-through in the OpenRouter API. `OpenRouterProvider` already forwards `extra_body` to the underlying provider. No provider code changes needed — it's passed via `**kwargs` in the chat completions call.

### Acceptance criteria
- Research presets no longer return results from `reddit.com`, `facebook.com`, `pinterest.com`, `quora.com`
- Existing tests pass (filter is additive, not breaking)
- Domain filter visible in debug logs via `extra_body` inspection

---

## E2 — Search Recency Filter

### Problem
Research returns results from 2020 (retracted Nature paper, outdated Wikipedia entries). Historical context is useful but should not dominate "latest breakthroughs" queries.

### Fix
Add `search_recency_filter` to `extra_body`. Use `"month"` for premium (cutting-edge), `"year"` for budget (balanced).

**File:** `src/reasoner/infrastructure/llm/registry.py`

```python
# Premium Perplexity models — recent results
"sonar-reasoning-pro": {
    ...
    "extra_body": {
        ...
        "search_recency_filter": "month",  # Last 30 days
    },
},
"sonar-deep-research": {
    ...
    "extra_body": {
        ...
        "search_recency_filter": "month",
    },
},
"sonar-pro-search": {
    ...
    "extra_body": {
        ...
        "search_recency_filter": "year",   # Last 12 months
    },
},

# Budget models — balanced
"sonar": {
    ...
    "extra_body": {
        ...
        "search_recency_filter": "year",
    },
},
"sonar-pro": {
    ...
    "extra_body": {
        ...
        "search_recency_filter": "year",
    },
},
```

### Acceptance criteria
- Results older than the filter window are excluded
- Budget presets get 12-month window, premium gets 30-day window

---

## E3 — Source-type Labeling

### Problem
The Prism classifier already classifies queries into `academic_search`, `discussion_search`, `personal_search`. But the search results themselves don't carry source-type labels, making it impossible to filter by source quality downstream.

### Fix
Add `return_sources` to `extra_body` and parse `search_results[].source` field in the search response parser.

**File:** `src/reasoner/infrastructure/llm/registry.py`
```python
"sonar-deep-research": {
    ...
    "extra_body": {
        ...
        "return_sources": True,
    },
},
```

**File:** `src/reasoner/core/ports/search_port.py`
```python
@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    source_type: str = "web"  # NEW: "web", "academic", "news", "video"
    date: str | None = None
```

**File:** `src/reasoner/infrastructure/search/discovery.py`
Parse the `source` field from Perplexity search results and populate `SearchResult.source_type`.

### Acceptance criteria
- Search results carry `source_type` field
- Prism classifier's `academic_search` flag can influence domain filter on-the-fly

---

## E4 — Pro Search Tools (Images & Related Questions)

### Problem
Perplexity Pro Search (`sonar-pro`, `sonar-reasoning-pro`, `sonar-deep-research`) supports `return_images` and `return_related_questions`. Reasoner never requests these, missing visual context for research queries.

### Fix
Add to `extra_body` and handle in the response parser.

**File:** `src/reasoner/infrastructure/llm/registry.py`
```python
"sonar-deep-research": {
    ...
    "extra_body": {
        ...
        "return_images": True,
        "return_related_questions": True,
    },
},
```

**File:** `src/reasoner/infrastructure/llm/providers/openai_compat.py`
Parse `images` and `related_questions` from streaming response chunks (they appear in `reasoning_steps` and final chunks). Store in provider metadata.

### Acceptance criteria
- Research responses include image URLs from credible sources
- Related questions appear in synthesis phase as "open questions"

---

## E5 — Perplexity Embeddings Provider

### Problem
Reasoner uses OpenAI embeddings for vector store. Perplexity offers standard and contextualized embeddings at lower cost with native web-search awareness — potentially better for document retrieval.

### Fix
Add a new lightweight provider + registry entry.

**File:** `src/reasoner/infrastructure/llm/providers/perplexity_embeddings.py` (NEW)
```python
class PerplexityEmbeddingProvider:
    """Embeddings via Perplexity API (OpenAI-compatible)."""
    def __init__(self, api_key: str, model: str = "perplexity/llama-3.1-sonar-large-128k-online"):
        self.client = httpx.AsyncClient(
            base_url="https://api.perplexity.ai",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self.model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        r = await self.client.post("/embeddings", json={
            "model": self.model,
            "input": texts,
        })
        return [d["embedding"] for d in r.json()["data"]]
```

**File:** `src/reasoner/infrastructure/llm/registry.py`
```python
"perplexity-embed": {
    "cls": "perplexity_embed",
    "model": "perplexity/llama-3.1-sonar-large-128k-online",
    "env": "PERPLEXITY_API_KEY",
},
```

**File:** `src/reasoner/core/settings.py`
```python
PERPLEXITY_API_KEY: str | None = os.getenv("PERPLEXITY_API_KEY")
```

### Acceptance criteria
- `perplexity-embed` registry key resolves to `PerplexityEmbeddingProvider`
- Embeddings endpoint returns 1024-dim vectors (standard) or adaptive-dim (contextualized)
- Vector store can switch between OpenAI and Perplexity embeddings via config

---

## Implementation Order (by impact/effort ratio)

| Order | Enhancement | Lines | Risk | Priority |
|-------|------------|-------|------|----------|
| **1** | E1 — Domain filter (denylist) | 2 per model entry | None | 🔴 Now |
| **2** | E2 — Recency filter | 1 per model entry | None | 🔴 Now |
| **3** | E1 — Domain filter (allowlist for premium) | 2 entries | Low — may miss valid .org sources | 🟡 Next |
| **4** | E3 — Source type labeling | ~10 lines across 2 files | Low | 🟡 Next |
| **5** | E4 — Pro Search tools | ~15 lines across 2 files | Med — response parsing | 🟢 Later |
| **6** | E5 — Embeddings provider | ~40 lines across 3 files | Med — new provider class | 🟢 Later |

## Rollback
All changes are additive to `extra_body` dicts in the registry. Reverting is one commit: remove the added keys. No pipeline, phase, or provider code is touched for E1-E2.

## Verification
- E1-E2: Run `research-budget` preset — verify no Reddit/Facebook/Pinterest results appear in web_discovery_results
- E3: Check `source_type` field populated in SearchResult objects
- E4: Verify `images` and `related_questions` appear in synthesis output
- E5: Unit test `PerplexityEmbeddingProvider.embed()` with mock API response
