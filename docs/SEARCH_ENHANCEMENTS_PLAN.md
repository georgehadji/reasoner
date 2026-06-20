# Plan: Multi-Backend Search Enhancements (Gap Closure)

> **Created:** 2026-06-20
> **Prerequisite:** `MULTI_BACKEND_SEARCH_PLAN.md` implemented (brave, tavily, perplexity, routing)
> **Scope:** 2 remaining enhancements that close the plan's 3 documented gaps

---

## Enhancement 1: OpenRouter `web_search` for HyperGate Direct Path

### Current state

When HyperGate classifies a query as `action="web_search"`, the orchestrator returns `decision.action = "web_search"`. Streaming.py responds by calling `_stream_web_search_results()` which hits SearXNG via `SearchService.stream_web_search_results()`.

### Problem

SearXNG is overkill for simple search queries. The HyperGate already runs an LLM call — the `web_search` parameter could inject results directly into the LLM response, eliminating the separate SearXNG roundtrip.

### Target

```python
# streaming.py → _stream_web_search_results (line 289)
# CURRENT:
async for chunk in _search_service.stream_web_search_results(
    req.problem, run_id, num_results=num_results, cancel_event=cancel_event
):

# PROPOSED:
if settings.OPENROUTER_WEB_SEARCH_ENABLED:
    # Delegate to direct-answer path with web_search enabled
    async for chunk in _stream_direct_answer(
        router, req.problem, run_id, cancel_event,
        web_search=True,  # NEW PARAMETER
    ):
        yield chunk
else:
    # Fall back to existing SearXNG streaming path
    async for chunk in _search_service.stream_web_search_results(...):
        yield chunk
```

### Implementation

**Step 1:** Add `web_search_enabled` parameter to `_stream_direct_answer()` in `streaming.py`. When `True`, inject `web_search: true` into the LLM call's `extra_body`.

```python
# streaming.py
async def _stream_direct_answer(
    router, problem, run_id, cancel_event,
    web_search: bool = False,  # NEW
    ...existing params...
):
    ...
    # Inject web_search if enabled and model supports it
    call_kwargs = {}
    if web_search:
        call_kwargs["extra_body"] = {"web_search": True}
    ...
    response, meta = await router.call(
        role="primary",
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        **call_kwargs,  # NEW
    )
```

**Step 2:** Update `_stream_web_search_results` caller in `run_stream()` to check `settings.OPENROUTER_WEB_SEARCH_ENABLED` and route accordingly.

**Files modified:** `streaming.py` only (~20 lines)

**Effort:** S (10 min)

### Architecture compliance

- No new adapter — uses existing `OpenRouterProvider` parameter passthrough
- Feature-flagged via `settings.OPENROUTER_WEB_SEARCH_ENABLED` (already exists)
- Graceful degradation: falls through to SearXNG when flag off or model doesn't support web_search
- Zero-domain changes — this is an API/infrastructure concern

---

## Enhancement 2: Tavily Extract for Deep Read Phase

### Current state

The Deep Read phase in `search_phases.py` operates on individual sources:

```
for each source in vetted_context:
    1. Fetch URL content via httpx.get(url, timeout=10s)   ← per-URL, sequential
    2. Sanitize text
    3. Call LLM with deep_read_prompt(source_text)         ← expensive LLM call per source
```

### Problem

Per-URL scraping is slow (10s timeout per URL × 5 sources = 50s worst case) and fragile (HTML parsing, paywalls, JavaScript-rendered content). Tavily Extract handles all URLs in one API call with cleaned text output.

### Target

```python
# search_phases.py → run_deep_read_phase (line ~270+)
# NEW: if Tavily is available, batch all URLs through Extract
if settings.TAVILY_EXTRACT_ENABLED and settings.TAVILY_API_KEY:
    from reasoner.infrastructure.search.tavily_adapter import TavilyAdapter
    tavily = TavilyAdapter()
    urls_to_extract = [r["url"] for r in sources_to_scrape[:5] if r.get("url")]
    if urls_to_extract:
        extracted = await tavily.extract(urls_to_extract)
        for item in extracted:
            # Use Tavily's cleaned content instead of scraping
            matching_result["summary"] = item.get("content", "")[:2048]
            matching_result["extraction_success"] = True
        return  # skip the per-URL scraping loop
```

### Implementation

**Step 1:** Add a `_tavily_deep_read()` helper to `search_phases.py` that batches URLs through Tavily Extract.

```python
async def _tavily_deep_read(
    urls: list[str],
    state: PipelineState,
    services: WorkflowServices,
) -> list[dict[str, Any]]:
    """Replace per-URL scraping with Tavily Extract batch call."""
    if not settings.TAVILY_API_KEY or not settings.TAVILY_EXTRACT_ENABLED:
        return []

    from reasoner.infrastructure.search.tavily_adapter import TavilyAdapter
    tavily = TavilyAdapter()
    extracted = await tavily.extract(urls)

    results = []
    for item in extracted:
        results.append({
            "url": item.get("url", ""),
            "title": item.get("title", ""),
            "summary": (item.get("content", "") or "")[:4096],
            "key_facts": [],
            "relevant_quotes": [],
            "extraction_success": bool(item.get("content")),
        })
    return results
```

**Step 2:** Call `_tavily_deep_read()` before the per-URL scraping loop. If it returns results, skip the loop.

**Files modified:** `search_phases.py` only (~30 lines)

**Effort:** S (10 min)

### Architecture compliance

- Uses existing `TavilyAdapter` — no new infrastructure
- Feature-flagged via `TAVILY_EXTRACT_ENABLED` (already exists)
- Graceful degradation: falls through to per-URL scraping when flag off
- Same return format as existing scraping loop — consumers unchanged

---

## 3. OpenRouter `web_search` Injection for LLM Calls (general)

### Problem

The `OPENROUTER_WEB_SEARCH_ENABLED` flag exists and the routing chain includes `"openrouter_web"`, but `get_search_client_for_method()` returns `None, source_type` for it. No code actually injects `web_search: true` into LLM calls.

### Fix: router-level parameter passthrough

Extend `ProviderRouter.call()` to accept an optional `extra_body` parameter that gets passed through to the provider.

```python
# router.py
async def call(
    self,
    role: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    temperature: float,
    extra_body: dict[str, Any] | None = None,  # NEW
) -> tuple[str, dict[str, Any]]:
    ...
```

And in `_call_with_circuit_breaker`:
```python
if extra_body:
    coro = provider.complete_with_retry(
        ..., extra_body=extra_body, ...
    )
```

**Files modified:** `router.py` only (~10 lines)

**Effort:** S (5 min)

---

## Summary

| # | Enhancement | Files | Lines | Effort |
|---|------------|-------|-------|--------|
| 1 | HyperGate direct → OpenRouter `web_search` | `streaming.py` | ~20 | S |
| 2 | Tavily Extract → Deep Read phase | `search_phases.py` | ~30 | S |
| 3 | Router `extra_body` passthrough | `router.py` | ~10 | S |
| **Total** | | **3 files** | **~60** | **~25 min** |

All three are gated by existing feature flags. No new adapters, no domain changes, no schema changes.
