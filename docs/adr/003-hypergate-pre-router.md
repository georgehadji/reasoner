# ADR-003: HyperGate Pre-Router

**Status:** Accepted · **Date:** 2026-07-08
**Context:** Implemented as part of pipeline v2.

## Context

Every request to the Reasoner pipeline goes through an LLM call, even trivial ones (e.g., "what's 2+2?"). This wastes tokens and adds latency. Different problems need different routing: direct answer for simple questions, web search for realtime queries, full multi-phase pipeline for complex reasoning.

## Decision

Implement a **HyperGate pre-router** that classifies each request before any pipeline work:

- **5 parallel sub-agents** (language detection, complexity estimation, direct-detection, web-search detection, method classification) run concurrently with a 5-second timeout
- Results are merged by a **TieBreaker** sub-agent
- Three possible actions: `direct` (short LLM call), `web_search` (grounded search), `pipeline` (full multi-phase)
- Fast-path regex checks run before sub-agents to short-circuit obvious cases
- Method names are obfuscated in prompts (letters B–Q instead of real names) to prevent gaming
- The whole gate decision is cached in a shared L2 cache (`SharedCachePort`), keyed on the
  problem hash **and** a fingerprint of the `(role, served model)` pairs that answered it, so
  a routing change cannot serve a stale verdict. Wired in `gate_service.run_gate_cached`
  (W5, 2026-08-30). This line previously read "sub-agent results are LRU-cached"; each
  sub-agent does hold an LRU, but it lives on an instance rebuilt per request, so it has
  never survived one. The gate's own L2 methods were stubs (`return None` / `pass`) from the
  day this ADR was written until W5.

## Consequences

**Positive:**
- Significant token savings for simple/direct questions
- Lower latency for common cases (direct answers in ~2s vs pipeline in ~30s+)
- Graceful degradation: if sub-agents timeout, defaults to pipeline

**Negative:**
- 5 parallel LLM calls per request adds small upfront cost (~5s worst case)
- TieBreaker requires an LLM call — adds latency for complex routing
- Obfuscated prompts reduce prompt-injection surface but complicate debugging
