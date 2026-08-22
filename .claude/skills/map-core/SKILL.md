---
name: map-core
description: Folder map of src/reasoner/core — constants, settings, hexagonal ports, domain events, aggregates, parsing, sanitization, exceptions. Use when touching token budgets/timeouts, env settings, port protocols, event sourcing, JSON extraction, or input sanitization.
folders:
  - src/reasoner/core
---

# src/reasoner/core — Folder Map

**Purpose:** The shared kernel. Holds pure abstractions and single-sources-of-truth that every other layer depends on: constants, settings, the hexagonal `ports/` protocols, domain events and aggregates, LLM response parsing, sanitization, and the exception taxonomy. Nothing here may import from `infrastructure/` or `api/`.

## Root files

| File | What it does |
|------|--------------|
| `__init__.py` | Re-exports `Phase`, `PhaseResult`, `PhaseConfig`, `make_phase_result`. |
| `protocol.py` | `Phase`, `PhaseConfig` (max_tokens/temperature/timeout/role), immutable `PhaseResult`, `TemperatureStrategy`. |
| `constants.py` | Thin re-export hub → `constants_limits` + `constants_models`. Import from here. |
| `constants_limits.py` (21KB) | Pure constants: `Timeouts`, `TruncationLimits`, token budgets, phase retry budgets, quality-judge model/threshold, `get_phase_timeout`. No I/O, no env. |
| `constants_models.py` | Model-name constants used across routing/presets. |
| `constants_prompts.py` | System prompts + image-generation prompt text, split out to keep large blocks isolated. |
| `settings.py` (25KB) | `Settings` — the **only** module that reads process env / loads `.env`. |
| `temperatures.py` | Per-phase temperature + reasoning-effort: `temperature_for`, `reasoning_extra_body`. |
| `parsing.py` (29KB) | Robust LLM output handling: `extract_json`, `extract_json_list`, reasoning/think-tag stripping, Perplexity citation and provider-artifact stripping, prose-preamble stripping. |
| `sanitization.py` | `InputSanitizer`, `sanitize_problem`, `sanitize_for_prompt`, `clean_llm_artifacts`, `sanitize_for_logging`. |
| `exceptions.py` | Full exception taxonomy: `ReasonerError` root, `ErrorCode`, parse/provider/auth/rate-limit/model-not-found families. |
| `logging_utils.py` | Structured JSON logging, correlation IDs, queue logging, automatic secret redaction (`redact_sensitive`, `redact_dict`). |
| `health_validator.py` | Startup validation of API keys/dependencies; auto-disables features. `validate_all`, `HealthReport`. |
| `capabilities.py` | `Capability` / `CapabilityPolicy` — declares the auth+metering policy a costing route must state. |
| `code_safety.py` | AST-based sandbox guard: SAFE / SUSPICIOUS / DANGEROUS / BLOCKED tiers (`check_code_safety`). |
| `exec_constants.py` | Safety-tier constants for the code execution sandbox. |
| `evolution_constants.py` | Constants for the governed-mutation Evolution Agent. |
| `scorecard_constants.py` | Harness Scorecard constants. |
| `perspectives.py` | Typed `PerspectiveDefinition` data for Phase 2 multi-perspective generation. |
| `memory.py` | `TaggedMemory` — lightweight tag-indexed conversation history (method/preset/outcome). |
| `rerank.py` | Cross-encoder reranking (Cohere via OpenRouter or direct) with its own circuit breaker. |
| `search.py` | Internal web-discovery tool for context enrichment; result filtering (off-topic, low-signal, blob/extension rejects). |
| `vs_config.py` | Verbalized Sampling config models + vertical registry. |
| `vs_constants.py` | All VS magic numbers (`VS_K_*` sample counts per phase). |

## ports/ (hexagonal port protocols — infrastructure implements these)

| File | Port |
|------|------|
| `__init__.py` | Package doc: ports = abstract interfaces the application depends on. |
| `llm_port.py` | `LLMPort` — implemented by `ProviderRouter`. |
| `model_registry_port.py` | `ModelRegistryPort` + `set_/get_model_registry_port` DI hooks. |
| `search_port.py` | `SearchServicePort`. |
| `file_search_port.py` | `FileSearchPort`, `FileChunk` — semantic search over uploaded chunks. |
| `memory_port.py` | `MemoryPort` + setter/getter; neuro package provides the adapter. |
| `circuit_breaker_port.py` | `CircuitBreakerPort`, `CircuitBreakerConfig`, `ProviderRegistryPort`. |
| `crypto_port.py` | `EncryptionPort`, `CipherSuite` — at-rest encryption. |
| `code_executor.py` | `CodeExecutorPort`, `ExecutionResult`, `ExecutionLimits`. |
| `credit_repository.py` | `CreditRepository` — credit-ledger persistence contract. |
| `api_key_repository.py` | `ApiKeyRepository` — user-owned key persistence. |
| `capability_registry_port.py` | `CapabilityRegistryPort` — model capability profiles (ACR Phase 2). |
| `routing_constraint_port.py` | `RoutingConstraintPort`, `ConstraintViolation` — accept/reject role→model assignments (ACR Phase 4). |
| `distributed_state_port.py` | `DistributedStatePort` — atomic ops + Lua (Valkey adapter). |
| `shared_cache_port.py` | `SharedCachePort` — KV cache with TTL. |
| `telemetry_port.py` | `TelemetryStorePort`, `CallTelemetryPort`. |
| `translation_port.py` | `TranslationPort`, `TranslationResult`. |
| `watermark_port.py` | `ImageMarkScrubberPort`, `PixelScrubberPort` + report/finding types. |

## events/, aggregates/, observability/

| File | What it does |
|------|--------------|
| `events/domain_events.py` (15KB) | Frozen `DomainEvent` hierarchy + event-type enums (pipeline, widget, memory, SaaS); `PipelineStarted`, `PhaseStarted/Completed/Failed`, `PipelineCompleted`, … |
| `events/ports.py` | `EventPublisher` port — decouples the app event bus from infrastructure. |
| `aggregates/pipeline.py` (15KB) | `Aggregate` base, `PipelineAggregate` + `PipelineStateData`, `WidgetAggregate` + `WidgetStateData` — event-sourced replay. |
| `observability/phase_span.py` | `PhaseSpan` — wraps phase execution in Langfuse spans; used by `api/execution/pipeline.py`. |

## Key entry points & gotchas

- `settings.py` is the only env reader. Do not call `os.environ` elsewhere.
- Never `json.loads` an LLM response — use `parsing.extract_json`.
- All user text must pass `sanitization.sanitize_for_prompt()` before entering a prompt.
- New constants go in `constants_limits.py` (pure) or `constants_prompts.py` (text), then re-export via `constants.py`.
- Adding an adapter? Define the protocol here in `ports/` first; infrastructure imports core, never the reverse.
- Event classes are frozen — add a new event type rather than mutating an existing one, or replay of old streams breaks.
