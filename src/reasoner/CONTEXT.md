# Context: Reasoner

## Directory: `src/reasoner`

## Description
The main Python package containing the Reasoner framework architecture.

## Files
- **`__init__.py`**: Reasoner — AI Reasoning Platform.
- **`auth.py`**: backward-compat shim — real module: reasoner.infrastructure.auth_legacy
- **`circuit_breaker.py`**: backward-compat shim — real module: reasoner.infrastructure.circuit_breaker
- **`clients.py`**: backward-compat shim — real module: reasoner.infrastructure.clients
- **`exceptions.py`**: backward-compat shim — real module: reasoner.core.exceptions
- **`gate_agent.py`**: backward-compat shim — real module: reasoner.hypergate.gate_agent
- **`headless.py`**: Once, at the HOST app's own shutdown (not per-call — see shutdown()):
- **`llm.py`**: Reasoner Pipeline — Multi-Provider LLM Abstraction
- **`logging_utils.py`**: backward-compat shim — real module: reasoner.core.logging_utils
- **`main.py`**: List all available presets + key status:
- **`metrics.py`**: backward-compat shim — real module: reasoner.infrastructure.metrics
- **`models.py`**: Reasoner Pipeline — Core Data Models (backward-compat re-export shim).
- **`parsing.py`**: backward-compat shim — real module: reasoner.core.parsing
- **`phases.py`**: Backward-compatible shim — all content moved to reasoner.phases package
- **`pipeline.py`**: backward-compat shim — real module: reasoner.application.pipeline
- **`presets.py`**: Re-export PRESETS as a dict for backward compatibility with main.py
- **`pricing.py`**: backward-compat shim — real module: reasoner.domain.pricing
- **`rate_limiter.py`**: backward-compat shim — real module: reasoner.infrastructure.rate_limiter
- **`reasoner_persuasion_defense.py`**: backward-compat shim — real module: reasoner.security.persuasion_defense
- **`reasoner_verbalized_sampling.py`**: backward-compat shim — real module: reasoner.infrastructure.verbalized_sampling
- **`reasoner_vs_constants.py`**: backward-compat shim — real module: reasoner.core.vs_constants
- **`renderer.py`**: backward-compat shim — real module: reasoner.infrastructure.renderer
- **`sanitization.py`**: backward-compat shim — real module: reasoner.core.sanitization
- **`scraper.py`**: backward-compat shim — real module: reasoner.infrastructure.scraper
- **`server_check.py`**: backward-compat shim — real module: reasoner.infrastructure.server_check
- **`start_all.py`**: ─────────────────────────────────────────────────────────────────────
- **`suggestions.py`**: backward-compat shim — real module: reasoner.application.services.suggestions
- **`token_cache.py`**: backward-compat shim — real module: reasoner.infrastructure.token_cache
- **`uploader.py`**: backward-compat shim — real module: reasoner.infrastructure.uploader
- **`vs_config.py`**: backward-compat shim — real module: reasoner.core.vs_config
- **`widgets.py`**: backward-compat shim — real module: reasoner.infrastructure.widgets_legacy

## Subfolders
- **`api`**: FastAPI endpoints, middleware, websocket routers, and API server entry points.
- **`application`**: Application-level orchestrators, workflow commands, event bus definitions, and core system services.
- **`core`**: The foundational core of the reasoning framework, containing aggregates, state-machine states, and observability interfaces.
- **`documents`**: Document management and extraction modules for structuring parsed source data.
- **`domain`**: Domain logic models, entities, value objects, and business validation rules.
- **`healing`**: Self-healing algorithms and parsing repair protocols for correcting malformed model outputs on-the-fly.
- **`hypergate`**: Advanced multi-agent routing gateways and sub-orchestrators for managing parallel reasoning routes.
- **`infrastructure`**: Platform and infrastructure adapters implementing the abstract application ports (databases, search, cache).
- **`neuro`**: Neuro-symbolic recall, cognitive map synthesis, and memory recall systems of the agent.
- **`phases`**: Orchestrated prompts, inputs, and validation logic for each of the 8 reasoning pipeline phases.
- **`quality`**: Validators, checks, and quality-assurance systems evaluating model responses.
- **`security`**: Security utilities, payload sanitizers, and encryption/decryption routines for protecting cache and databases.
- **`shared`**: Shared types, exceptions, and constants shared across backend packages.
- **`subagents`**: Task-focused LLM subagents used in specific stages of the reasoning process.
- **`utils`**: Helper modules for date-time handling, UUIDs, model parsing, and environment variables.
- **`vs_vertical_configs`**: Vertical configuration specifications for specialized model alignments and presets.
