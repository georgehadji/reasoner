---
name: map-tests
description: Folder map of tests/ — 297 pytest files, their thematic groups, the conftest fixtures and utils factories/mocks, markers, and how to run subsets. Use to find existing coverage for a module before writing a new test, or to pick the right marker and fixture.
folders:
  - tests
---

# tests — Folder Map

**Purpose:** The pytest suite. 238 files sit flat in `tests/`, grouped by filename prefix rather than directory; four subdirectories hold the exceptions (`architecture/`, `integration/`, `unit/`, `utils/`). Before writing a new test, look for the prefix group that already covers the module.

## Running

```bash
python -m pytest tests/ -v
```

```bash
python -m pytest tests/ -v -m "not slow and not integration"
```

```bash
pytest tests/ --cov=src/reasoner --cov-report=html
```

`pytest.ini` already sets `-n auto --dist loadscope`, `asyncio_mode = auto`, `pythonpath = src`, and `--durations=10`, so plain `pytest` runs parallel by default.

## Markers

| Marker | Meaning |
|--------|---------|
| `slow` | Long-running; deselect with `-m "not slow"`. |
| `integration` | Needs a live backend or external service. |
| `unit` | Fast isolated unit test. |
| `timeout` | Threshold enforced by pytest-timeout. |
| `docker` | Needs a reachable Docker daemon; auto-skipped otherwise. |

## Fixtures and helpers

| File | What it provides |
|------|------------------|
| `tests/conftest.py` | `auto_clean_state` — autouse cleanup between tests. |
| `tests/integration/conftest.py` | `base_url`, `test_timeout`, `csrf_token`, `api_client` — live-server integration harness. |
| `tests/utils/factories.py` | `create_message`, `create_llm_config`, `create_llm_response`, `create_pipeline_state`, `create_solution_candidate`, `create_critique_score`, `create_decomposition`, `create_final_solution`, `create_pipeline_started_event`, `create_phase_completed_event`. |
| `tests/utils/mocks.py` | `MockLLMProvider`, `MockEventStore`, `MockAuthStore`, `MockNLI`, `MockLLM`, `create_mock_redis`. |
| `tests/utils/async_helpers.py` | `async_run`, `await_all`, `create_future`. |

## Subdirectories

| Directory | Files |
|-----------|-------|
| `architecture/` (7) | `test_layer_boundaries.py`, `test_domain_modules.py`, `test_models_split.py`, `test_event_emission.py`, `test_integration_events.py`, `test_sse_events.py`, `test_regression_bugs.py` — hexagonal boundary and event-contract enforcement. |
| `integration/` (7) | `test_preset_pipeline.py`, `test_provenance_api.py`, `test_call_telemetry_store.py`, `test_sandbox_escape.py`, plus `conftest.py` and `sse_utils.py`. |
| `unit/` (41) | ACR (`test_adaptive_routing`, `test_utility_scorer`, `test_constraints`, `test_capability_registry`, `test_online_learning`, `test_benchmarks`, `test_call_telemetry`, `test_acr_coverage`), watermark (`test_watermark_layer_a`, `_rules`, `_spans`, `_properties`, `_image_png/jpeg/webp/isobmff`, `_image_facade`, `_generated_images`), presets (`test_preset_bloc_diversity`, `test_preset_model_uniqueness`, `test_pricing_resolver`), spend (`test_spend_limits`, `test_spend_cap_enforcement`), Prism (`test_prism_classifier`, `test_prism_research`), language (`test_language_pivot`, `test_language_probe`), plus numbered regressions `test_regression_BUG001-003`. |
| `utils/` (4) | Shared factories, mocks, async helpers (not tests). |

## Top-level groups (238 files)

| Prefix | Count | Covers |
|--------|------:|--------|
| `test_vs_*` | 18 | Verbalized Sampling: calibration, claim extraction, conflict surfacing, coverage audit, decomposition, generation invariants and strategies, probe generation, verification routing, observability, per-vertical pipelines (radiology/legal/aerospace), global invariants, all-flags-disabled. |
| `test_saas_*` | 16 | Quota (service, repo, cached, integration), subscriptions, Stripe adapter + webhooks, auth integration, rate limiting per user, run state, stop ownership, preset tier enforcement, IP anonymization, history. |
| `test_api_*` | 11 | Auth deps, middleware, schemas validation, exception handling, gate SSE, presets/models, widget execute, caches, phase errors, API keys. |
| `test_arch_*` | 9 | Architectural risks: dead letter, fallback masking, streaming closure, pipeline-state resilience, system-prompt drift, worker mode, mixin migration, registry consistency, integration methods. |
| `test_article_*` | 8 | Article pipeline: adapters, parsing, router, presets, follow-up scoping, golden set, regressions. |
| `test_pipeline_*` | 8 | Flow and DAG, field descriptor, state split, resume, ownership repo, service contract, fixes. |
| `test_e2e_*` | 7 | Budget presets (real + mock), comprehensive, real API, real pipeline, relationships, article discovery. |
| `test_event_*` | 7 | Event bus (backpressure, isolation), event store (concurrency, GDPR ownership), emission service, event types. |
| `test_neuro_*` | 6 | Agent-id isolation, cache wiring, CLI, fallback providers, Perplexity provider, safe indexing. |
| `test_websocket_*` / `test_ws_*` | 6 | Auth, authz, manager, sharding, security, tickets. |
| `test_auth_*` | 4 | Concurrency, rate limiter deps, LRU, security. |
| `test_bugfix*_` / `test_bug0*` / `test_defect_hunt_fixes` | 12 | Named regression cases (enum resume, JSON repair, language preservation, token-cache clock, circuit-breaker half-open, truncated JSON, runstate eviction, rounds 1-3, defect-hunt fixes). |
| `test_core_*`, `test_constants`, `test_temperature*` | 6 | Constants, protocol, temperatures and strategy. |
| `test_image_*`, `test_images_metering`, `test_ocr` | 5 | Image generation, routes, model selection, metering, OCR. |
| `test_rate_limiter_*`, `test_circuit_breaker` | 4 | Concurrency, edge cases, sharding, breaker states. |
| `test_search_*`, `test_brave_media_search`, `test_perplexity_*`, `test_deep_read`, `test_context_vetting`, `test_cohere_rerank` | 8 | Search clients, media search, vetting, deep read, reranking. |
| `test_security`, `test_sanitization*`, `test_prompt_injection`, `test_io_security`, `test_encryption`, `test_persuasion_defense`, `test_csrf_clock_jump`, `test_error_store_sql_safety` | 10 | Security surface. |
| `test_mind_virus_resistance` | 1 | Propagation resistance (docs/MIND_VIRUS_MITIGATION.md): prompt hardening, external-content wrapping, Neuro recall rendering, resistance routing, shape detection. Two tests fail closed on invariants that hold by *omission* — recalled memory never entering a system prompt, and Phase-2 generators staying blind to each other. Read the linked section before relaxing either. |
| `test_code_execution_safety`, `test_container_sandbox`, `test_sandbox_worker` | 3 | Sandbox execution and escape hardening. |
| `test_synthesis_*`, `test_perspective*`, `test_multi_perspective_budget`, `test_mixins_*`, `test_methods*` | 11 | Phase behavior per reasoning method. |
| Singletons | ~60 | One file each: `test_hypergate`, `test_headless`, `test_mcp_tools`, `test_sdk_contract`, `test_cqrs_parity`, `test_idempotency`, `test_run_metering`, `test_credits`, `test_presets`, `test_preset_validation`, `test_models`, `test_parsing*`, `test_aggregates`, `test_domain_events`, `test_load`, `test_acceptance`, `test_codebase_audit`, `test_site_capabilities_sync`, and similar. |

## Key gotchas

- `CSRF_ENFORCE_BACKEND=false` in CI environments — no `CSRF_SECRET` is available there.
- Tests run parallel with `--dist loadscope`; anything touching a shared SQLite file or module-level singleton needs the `auto_clean_state` fixture or its own temp path.
- Real-API tests (`test_e2e_real_*`) cost money and need keys — they are marked and normally deselected.
- `unit/` holds the newer ACR and watermark work; older subsystem tests live flat in `tests/`. Check both before concluding something is untested.
- Coverage config lives in `pytest.ini` (`[coverage:run]`), which omits `healing/generated_tests/`. Self-healing CI gates at 60% fail / 80% warn.
