---
name: map-reasoner-root
description: Folder map of src/reasoner top-level files (which are backward-compat shims and which are real modules like main.py, headless.py, presets.py, start_all.py) plus the small packages security/, quality/, utils/, documents/, vs_vertical_configs/. Use to tell a shim from an implementation before editing.
folders:
  - src/reasoner/*
  - src/reasoner/security
  - src/reasoner/quality
  - src/reasoner/utils
  - src/reasoner/documents
  - src/reasoner/shared
  - src/reasoner/vs_vertical_configs
---

# src/reasoner (top level) and small packages — Folder Map

**Purpose:** The package root is mostly **backward-compatibility shims** left over from the hexagonal refactor: a one-line `from x import *` re-export pointing at the real module. Editing a shim is almost always wrong — follow it to the target. Four files here are real: `main.py`, `headless.py`, `start_all.py`, and `presets.py` (a shim that still carries live logic).

## Real modules

| File | What it does |
|------|--------------|
| `__init__.py` | Wires `SafeLoggingFilter` at package level so every entry point (API, CLI, tests) gets secret redaction. |
| `main.py` (19KB) | **CLI entry point.** `parse_args`, `main`, `cmd_list_models`; builds `PipelineOrchestrator` + adaptive routing. Backs `python main.py --problem ... --preset ...`. |
| `headless.py` (9.5KB) | In-process API for host apps — `ask()`, `HeadlessResult`, `shutdown()`; runs the pipeline without FastAPI/uvicorn. |
| `start_all.py` (15KB) | Launches API (:8003) and Neuro memory server (:50001): preflight checks, port probing, health wait, process supervision. |
| `presets.py` (5.7KB) | Mostly re-export of `domain/preset_core` + `domain/preset_registry`, but still owns live helpers: `resolve_preset_name`, `is_valid_preset_name`, `get_preset`, `_derive_method_from_preset_name`, custom-routing builders. `PRESETS` is materialized at import here. |
| `models.py` | Re-export shim for domain types **plus** real `load` / `save` helpers for state files. |

## Pure shims (edit the target, not these)

| File | Points at |
|------|-----------|
| `auth.py` | `infrastructure/auth_legacy.py` |
| `circuit_breaker.py` | `infrastructure/circuit_breaker.py` |
| `clients.py` | `infrastructure/clients.py` |
| `exceptions.py` | `core/exceptions.py` |
| `gate_agent.py` | `hypergate/gate_agent.py` |
| `llm.py` | `infrastructure/llm/` (base, providers, registry) |
| `logging_utils.py` | `core/logging_utils.py` |
| `metrics.py` | `infrastructure/metrics.py` |
| `parsing.py` | `core/parsing.py` |
| `phases.py` | `phases/_shared.py` and friends |
| `pipeline.py` | `application/pipeline.py` |
| `pricing.py` | `domain/pricing.py` |
| `rate_limiter.py` | `infrastructure/rate_limiter.py` |
| `renderer.py` | `infrastructure/renderer.py`, itself a shim to `application/services/renderers` |
| `sanitization.py` | `core/sanitization.py` |
| `scraper.py` | `infrastructure/scraper.py` |
| `server_check.py` | `infrastructure/server_check.py` |
| `suggestions.py` | `application/services/suggestions.py` |
| `token_cache.py` | `infrastructure/token_cache.py` |
| `uploader.py` | `infrastructure/uploader.py` |
| `vs_config.py` | `core/vs_config.py` |
| `widgets.py` | `infrastructure/widgets_legacy.py` |
| `reasoner_persuasion_defense.py` | `security/persuasion_defense.py` |
| `reasoner_verbalized_sampling.py` | `infrastructure/verbalized_sampling.py` |
| `reasoner_vs_constants.py` | `core/vs_constants.py` |

Several shims emit a `DeprecationWarning` on import: `circuit_breaker`, `exceptions`, `logging_utils`, `pipeline`, `rate_limiter`.

## security/ — leaf package, no reasoner-internal imports

| File | What it does |
|------|--------------|
| `encryption.py` (16KB) | At-rest authenticated encryption (Fernet / AES-GCM), key derivation, keyed blind indexes so encrypted fields stay searchable; `EncryptionService`, `get_encryption_service`. |
| `persuasion_defense.py` (39KB) | Hallucination-mitigation and prompt-persuasion defense: `PersuasionTactic`, `FrictionAction`, `ExtractedClaim`, `TaintRecord`, coverage checks. |
| `url_validator.py` | `is_safe_url` — SSRF guard blocking private ranges, metadata endpoints, internal hostnames. Used by the scraper and image downloaders. |

## quality/ — phase quality monitoring

| File | What it does |
|------|--------------|
| `criteria.py` (15KB) | Rule-based per-phase checks (`_check_classification`, `_check_decomposition`, `_check_perspectives`, `_check_critique`, ...), `PhaseQualityResult`, state reset. |
| `monitor.py` (11KB) | `PhaseMonitor` — hybrid rules plus LLM judge; judge model and threshold come from `core/constants`. |
| `quick_check.py` | `QuickQualityCheck` — pure-heuristic gate before accepting a cascaded response, no LLM calls. |

## Other small packages

| File | What it does |
|------|--------------|
| `utils/json_safe.py` | `safe_json_loads` with depth limits; `JSONDepthExceededError`. |
| `documents/vector_store.py` | `DocumentVectorStore` — per-session chunking, Neuro embeddings, cosine retrieval over uploaded files. |
| `vs_vertical_configs/` | Verbalized Sampling verticals: `radiology_config.py`, `legal_config.py`, `aerospace_config.py`, each setting k and tail thresholds. |
| `shared/` | Empty package marker. |

## Runtime artifacts in this directory (do not edit or commit)

`errors.db`, `feedback.db`, `.upload_hash_index.json`, and the `cache/`, `logs/`, `history/`, `uploads/`, `graphify-out/` subdirectories are generated at runtime.

## Key entry points & gotchas

- Import from the real module in new code. Shims exist so older state files and external callers keep working.
- `presets.py` is the exception: it still holds resolution logic and materializes `PRESETS` at import, which is why `domain/preset_core.py` needs its one accepted import-linter exception.
- `security/` sits below `core/` in the layer stack — do not add reasoner-internal imports to it.
- CLI, headless, and API each build their own orchestrator and must call `set_model_registry_port()`; a new entry point has to wire that too.
