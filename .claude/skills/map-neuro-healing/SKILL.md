---
name: map-neuro-healing
description: Folder map of src/reasoner/neuro (L1/L2/L3 long-term memory, compression, recall/learn endpoints, sessions) and src/reasoner/healing (introspection, autonomous test generation, evolution agent). Use when touching memory, context compression, or the self-healing loop.
folders:
  - src/reasoner/neuro
  - src/reasoner/healing
---

# src/reasoner/neuro and src/reasoner/healing — Folder Map

**Purpose:** Two support subsystems. `neuro/` is the persistent memory engine — a tiered cache with embedding search, its own provider abstraction, and an internal API mounted into the app. `healing/` is the self-healing loop — it introspects the codebase, generates missing tests, and runs a governed evolution cycle.

## neuro/ — persistent memory engine

| File | What it does |
|------|--------------|
| `__init__.py` | Package doc — memory co-processor architecture. |
| `cache.py` | The tier hierarchy: `L1Cache` (memory), `L2Index` (disk JSON), `l3_scan` (LTM embedding search), `ContextChunk`, `cosine_similarity`, persona-aware similarity thresholds. |
| `compression.py` | "Neuro-Squeeze" token reduction: `smart_compress(text, ext, level)`, `CompressionLevel` (Aggressive keeps only signatures, Minimal is general cleanup), `ContextCompressor`. |
| `config.py` (14KB) | Multi-tenant config: provider fallback chains, `PersonaConfig` + `DEFAULT_PERSONAS`, storage/cache/server/agent config, `NeuroConfig`. |
| `providers.py` (21KB) | Pluggable reasoning + embedding backends (Ollama, OpenAI-compatible) behind `CircuitBreaker` and `Resilient*` fallback wrappers. |
| `server.py` (25KB) | The internal API: `/neuro/recall`, `/neuro/learn`, audit, health; compression cache. Mounted via `create_neuro_router()`. |
| `sessions.py` (21KB) | "The Live Wire" — `SessionManager` captures every prompt/response as it happens; no manual save. |
| `cli.py` | `neuro` CLI: status, start. |

## healing/ — self-healing loop

| File | What it does |
|------|--------------|
| `introspection_engine.py` (31KB) | `CodebaseIntrospector` — function inventory with complexity scores, dependency graph, dead code, type-coverage gaps, error-handling gaps → `IntrospectionReport`. |
| `test_generation_engine.py` (13KB) | `TestGenerationEngine` — writes tests for untested paths, zero-coverage functions first. |
| `evolution_agent.py` | `EvolutionAgent` — five-stage observe → diagnose → propose → evaluate → promote loop (governed mutation). |
| `telemetry_exporter.py` | Dumps recent telemetry to `healing_context.json` for the static healing scripts. |
| `run_healing.py` | Orchestrator wiring the stages into one pipeline (static loop → runtime → evolutionary). |

## Key entry points & gotchas

- Memory tiers: L1 = process memory, L2 = disk JSON, L3 = Neuro LTM with embedding search. A recall walks them in order.
- Tenant isolation is by `agent_id` in Neuro requests → `~/.neuro/agents/<id>`. Always pass it for multi-tenant work.
- Recall is auto-called during a pipeline run; `/neuro/learn` saves the final synthesis at the end.
- The app talks to memory through `core/ports/memory_port.py` — the neuro package is the adapter. Application code should depend on the port, not import neuro directly.
- Healing runs in CI via `.github/workflows/self-healing-ci.yml`; coverage gates are 60% fail / 80% warn.
- `run_healing.py` shells out to scripts — check `HEALING_DIR` / `PROJECT_ROOT` before assuming paths.
