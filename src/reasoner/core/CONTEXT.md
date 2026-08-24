# Context: Core

## Directory: `src/reasoner/core`

## Description
The foundational core of the reasoning framework, containing aggregates, state-machine states, and observability interfaces.

## Files
- **`__init__.py`**: core — shared abstractions for the Reasoner pipeline.
- **`capabilities.py`**: Capability model — names the authorization/metering policy every
- **`code_safety.py`**: Syntax errors are caught by the executor at runtime;
- **`constants.py`**: Single source of truth for all hardcoded constants used across the Reasoner project.
- **`constants_limits.py`**: Single source of truth for all hardcoded constants used across the Reasoner project.
- **`constants_models.py`**: ═════════════════════════════════════════════════════════════════════
- **`constants_prompts.py`**: ═════════════════════════════════════════════════════════════════════
- **`evolution_constants.py`**: Constants for the Evolution Agent (#4) — governed harness mutation.
- **`exceptions.py`**: Don't retry - API key is invalid
- **`exec_constants.py`**: Constants for the code execution sandbox (Code-as-Agent-Harness #1).
- **`health_validator.py`**: ── 1. OpenRouter (gate for Cohere rerank) ──
- **`logging_utils.py`**: Context variables for log context across async calls
- **`memory.py`**: TaggedMemory — lightweight categorized conversation history store.
- **`parsing.py`**: Known provider-injected artifacts that leak into LLM responses.
- **`perspectives.py`**: Data-driven perspective definitions for Phase 2 (Multi-Perspective Analysis).
- **`protocol.py`**: Core abstractions for the Reasoner pipeline.
- **`rerank.py`**: ── Constants ──
- **`sanitization.py`**: Characters that might indicate prompt injection
- **`scorecard_constants.py`**: Constants for the Harness Scorecard (Code-as-Agent-Harness #2).
- **`search.py`**: ── Dependency Injection for core → infrastructure boundary ───────
- **`settings.py`**: Centralized environment-aware settings.
- **`temperatures.py`**: ── Optimal temperatures per reasoning phase ────────────────────────────────
- **`vs_config.py`**: Verbalized Sampling configuration models and vertical registry.
- **`vs_constants.py`**: Verbalized Sampling constants — zero magic numbers outside this file.

## Subfolders
- **`aggregates`**: Domain aggregates grouping entities and enforcing transaction boundaries.
- **`events`**: System event definitions capturing structural changes in reasoning jobs or model outputs.
- **`observability`**: Framework interfaces for performance tracing, spans, and step logging.
- **`ports`**: Core-level abstract interfaces defining adapters for low-level platform features.
