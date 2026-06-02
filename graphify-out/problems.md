# Problems Identified by Graphify Analysis

> Generated from graphify exploration of the Reasoner codebase.
> Graph stats: 9,343 nodes · 25,188 edges · 787 communities

---

## Table of Contents

1. [Critical Runtime Issues](#1-critical-runtime-issues)
2. [Architectural Gaps](#2-architectural-gaps)
3. [Extraction Artifacts](#3-extraction-artifacts)
4. [Cross-Cutting Coupling](#4-cross-cutting-coupling)
5. [Isolated Subsystems](#5-isolated-subsystems)
6. [VS Complexity](#6-vs-complexity)
7. [Test Infrastructure Issues](#7-test-infrastructure-issues)

---

## 1. Critical Runtime Issues

### 1.1 Phantom DeepSeek Model IDs

**Problem:** The codebase references `deepseek-v4-pro` and `deepseek-v4-flash` model IDs that do not exist on OpenRouter.

**Evidence:** Graph extracted a rationale node: `"# NOTE: deepseek-v4-pro and deepseek-v4-flash do not exist on OpenRouter."`

**Impact:** 30-90 second timeouts when these model IDs are selected by the provider router.

**Suggested Fix:** Replace with verified model IDs (Gemini 2.5 Flash Lite / Gemini 2.5 Pro as noted in `model_replacement_research.md`).

---

### 1.2 Self-Healing Loops Are Disconnected

**Problem:** The documented "3-loop self-healing architecture" (static → runtime → evolutionary) consists of 3 independent scripts with zero code-level connections between them.

**Evidence:**
- `introspection_engine.py` (13 nodes, isolated)
- `test_generation_engine.py` (2 nodes: TestGenerationEngine + main)
- `instrumentation_injection.py` (only connected via `Self-Healing System` rationale node)
- Graph search found **0 direct edges** between introspection nodes and test generation nodes

**Impact:** The "loops" don't actually loop. Introspection generates reports; test generation reads them (maybe); instrumentation patches code. There is no feedback mechanism.

**Suggested Fix:** Either connect the engines through a shared data structure (e.g., `IntrospectionReport` → `TestGenerationEngine.load_report()`) or stop calling it a "3-loop architecture."

---

### 1.3 WebSocket Errors Can Affect Circuit Breaker State

**Problem:** `_broadcast_ws()` calls `.warning()` which connects to circuit breaker internals (`retry_with_backoff()`, `._on_failure()`, `record_failure()`).

**Evidence:**
```
_broadcast_ws() → .warning() → retry_with_backoff() → get_circuit_breaker() → CircuitBreaker
_broadcast_ws() → .warning() → .call() → ._on_failure() → record_failure() → CircuitBreaker
```

**Impact:** WebSocket client connectivity errors could theoretically contribute to circuit breaker state transitions, even though these are completely different failure domains.

**Suggested Fix:** Separate logging channels by domain — streaming warnings should not flow through the same path as provider health signals.

---

## 2. Architectural Gaps

### 2.1 PipelineState Is a Massive Blast Radius

**Problem:** `PipelineState` has 562 edges across 13 communities. Any schema change affects 544 functions.

**Evidence:**
- 464 edges in Article Pipeline (Community 0)
- 18 edges in Pipeline Control (Community 13)
- 15 edges in Reasoning Phase Prompts (Community 14)
- 12 edges in Auth & Security (Community 1)
- Bleeds into 9 more communities

**Impact:** Highest structural dependency in the system. A single field addition/removal could break tests, serializers, widgets, auth, and event sourcing.

**Suggested Fix:** Consider splitting into phase-specific state objects or using a more rigid schema with versioning.

---

### 2.2 VSFeatureFlags Is a Single Point of Failure

**Problem:** `VSFeatureFlags` has 155 edges, with 154 (99%) in Community 3 (Verbalized Sampling). It gates every VS phase.

**Evidence:**
- 114 `uses` edges
- 38 `calls` edges (test code calling `enabled_flags()`, `flags()`)
- Connected to every VS stage: probe generation, decomposition, generation, calibration, claim extraction, conflict surfacing, coverage audit, verification routing, behavioral audit

**Impact:** One config object change affects the entire VS subsystem. If the flags schema changes, 154 concepts break.

**Suggested Fix:** Consider per-phase feature flags rather than a monolithic config object.

---

### 2.3 Circuit Breaker Is Not Embedded Per Provider

**Problem:** `CircuitBreaker` and `Provider` nodes have zero direct edges in the graph.

**Evidence:** Graph search for edges between `CircuitBreaker` nodes and `Provider` nodes returned **0 results**.

**Impact:** The documented "automatic fallback when providers fail" is orchestrated through `ProviderHealthChecker` (22 edges), not embedded in each provider call. This adds an indirection layer that may miss rapid failure modes.

**Suggested Fix:** Consider embedding circuit breaker state directly in `BaseLLMProvider` or `OpenAICompatibleProvider`.

---

### 2.4 Neuro Memory Has Zero PipelineState Integration

**Problem:** The Neuro long-term memory system has **0 direct edges** to `PipelineState` and **0 edges** to Event Sourcing.

**Evidence:**
- `PipelineState` connects to Neuro via 2 rationale nodes only (no code edges)
- `run_stream()` connects via `_recall_neuro_context()` and `get_neuro_client()`
- Neuro's 7 core modules (server, cache, compression, sessions, config, providers, cli) are internally connected but isolated from the pipeline

**Impact:** Neuro is fire-and-forget. If it fails, the pipeline continues without memory. There's no guarantee that memory context is actually loaded before reasoning begins.

**Suggested Fix:** Add explicit `PipelineState.neuro_context` field or event type to make memory loading a first-class pipeline concern.

---

## 3. Extraction Artifacts

### 3.1 GET() Is a False God Node

**Problem:** `GET()` is ranked #1 God Node with 622 edges, but this is an AST extraction artifact.

**Evidence:**
- Edge metadata shows `_src` = decorated function, `_tgt` = `route_get`
- FastAPI `@app.get()` decorator syntax is misinterpreted as "function calls GET()"
- Semantically backwards: the decorator is applied TO the function, not called BY it

**Impact:** Misleading centrality analysis. The true #1 hub is `PipelineState` (562 edges).

**Suggested Fix:** Filter decorator-application edges in downstream analysis, or fix the AST extractor to tag decorator edges separately.

---

### 3.2 Python Builtins Inflate Degrees

**Problem:** `str` (203 edges, 24 communities), `Enum` (73 edges, 11 communities), and `ValueError` (55 edges, 15 communities) appear as major hubs.

**Evidence:** These are Python standard library types that appear in type hints across the codebase.

**Impact:** Builtins drown out domain-specific hubs in centrality rankings.

**Suggested Fix:** Filter stdlib types from God Node analysis, or treat them as a separate category.

---

### 3.3 Auto-Generated Tests Are Orphaned

**Problem:** 7 auto-generated test files in `src/reasoner/healing/generated_tests/` all have degree 2.

**Evidence:**
- `test_config_load_config_auto.py` (2 edges)
- `test_event_store_get_aggregate_state_auto.py` (2 edges)
- `test_event_store_get_events_auto.py` (2 edges)
- And 4 more event store test files

**Impact:** Generated tests are leaf nodes with no downstream connections. They don't integrate with the test suite structure.

**Suggested Fix:** Auto-generated tests should import from or be imported by test suite runners to establish structural links.

---

## 4. Cross-Cutting Coupling

### 4.1 AlertManager Doesn't Bridge Streaming and Resilience

**Problem:** The documented "AlertManager bridges streaming and resilience" pattern doesn't exist in code.

**Evidence:**
- `AlertManager` node has **0 streaming-side neighbors** and **0 resilience-side neighbors**
- The actual bridge is `.warning()` (logger), not `AlertManager`
- `_broadcast_ws() → .warning() → CircuitBreaker` path exists
- `_broadcast_ws() → AlertManager` path does not exist

**Impact:** Documentation describes an architectural pattern that the code doesn't implement.

**Suggested Fix:** Either implement the documented pattern (AlertManager explicitly handles streaming alerts and circuit breaker state) or update the docs.

---

### 4.2 Auth Is a Hidden Dependency of Every Test

**Problem:** 147 cross-community edges connect Article Pipeline (Community 0) to Auth (Community 1).

**Evidence:**
- `AuthManager` appears in regression tests, neuro persistence tests, cache clearing tests
- Every article pipeline test needs auth setup
- `PipelineState` has 12 edges into Auth

**Impact:** The pipeline cannot run without identity context, even for tests that don't explicitly test auth.

**Suggested Fix:** Consider a test auth bypass or mock that doesn't require full AuthManager setup.

---

### 4.3 Shared Logging Creates False Bridges

**Problem:** `.warning()` (90 edges, 20 communities) and `.info()` (73 edges, 19 communities) connect otherwise unrelated subsystems.

**Evidence:**
- `.warning()` bridges Article Pipeline (0) to Image Generation (9): 93 edges
- `.warning()` bridges Auth (1) to Image Generation (9): 92 edges
- These connections are through structured logger calls, not semantic dependencies

**Impact:** The graph shows coupling where none exists — these are observability signals, not architectural dependencies.

**Suggested Fix:** Filter logging edges from cross-community coupling analysis, or tag them as `OBSERVABILITY`.

---

## 5. Isolated Subsystems

### 5.1 Image Generation Is a Leaf

**Problem:** Image Generation (Community 9) has minimal cross-community connections.

**Evidence:**
- 257 nodes, mostly internal
- 23 edges to Redis & Cache
- 5 edges to Auth
- 6 edges to Article Pipeline

**Impact:** Could be removed without structural impact on the rest of the system.

**Suggested Fix:** Consider whether image generation should be a separate service rather than a community within the monolith.

---

### 5.2 Test Infrastructure Appears More Central Than Production Code

**Problem:** Mock methods have higher degrees than some production concepts.

**Evidence:**
- `MockEventStore.append()`: 286 edges, 25 communities
- `MockAuthStore.set()`: 75 edges, 17 communities
- `FakeProvider`: 10 edges

**Impact:** Test doubles dominate centrality rankings, making it hard to identify true production hubs.

**Suggested Fix:** Filter `test_` and `mock_` prefixed nodes from production architecture analysis.

---

## 6. VS Complexity

### 6.1 Vertical Configs Use Different VS Subsets

**Problem:** Each vertical domain (radiology, aerospace, legal) uses a different subset of VS stages, with no unified interface.

**Evidence:**
| Vertical | VS Stages Used |
|----------|---------------|
| Radiology | Decomposition + Claim Extraction + Probe Generation + Generation + Verification Routing |
| Aerospace | Probe Generation + Generation |
| Legal | Generation + Verification Routing |

**Impact:** Adding a new VS stage requires updating each vertical config individually. No guarantee that all verticals use consistent validation.

**Suggested Fix:** Define a `VSVerticalProfile` that explicitly declares which stages are active, with a common validation harness.

---

### 6.2 Perplexity Is the Only Embedding Provider for Neuro

**Problem:** Neuro's embedding search depends solely on `PerplexityEmbedding` (18 edges).

**Evidence:**
- `test_neuro_perplexity_provider.py` (9 edges)
- `TestCreateEmbedding`, `TestPerplexityEmbedding`
- No fallback embedding provider found in graph

**Impact:** If Perplexity changes its embed API or pricing, Neuro's long-term memory breaks with no fallback.

**Suggested Fix:** Add OpenAI-compatible embedding fallback or local embedding option.

---

## 7. Test Infrastructure Issues

### 7.1 OpenRouter Provider Lacks Individual Model Testing

**Problem:** Strong preset/registry testing (13 edges) but weak individual provider testing.

**Evidence:**
- `test_openrouter.py`: validates registry contains models, format is correct
- `TestModelListing`: 5 edges
- `TestBackwardCompatibility`: 4 edges
- No tests for individual model behavior, token limits, or error modes

**Impact:** Registry may list 70+ models, but only a handful are tested. New model additions are not validated.

**Suggested Fix:** Add smoke tests that call each model with a minimal prompt to verify availability.

---

### 7.2 VS Vertical Tests Duplicate Mock Setup

**Problem:** Each vertical E2E test (radiology, aerospace, legal) has its own `MockLLM` and `MockNLI` instances.

**Evidence:**
- `test_vs_pipeline_radiology`: MockLLM (12 edges), MockNLI (12 edges)
- `test_vs_pipeline_aerospace`: MockLLM (9 edges), MockNLI (9 edges)
- `test_vs_pipeline_legal`: MockLLM (8 edges), MockNLI (8 edges)

**Impact:** 6 mock objects where 2 shared fixtures would suffice. Test maintenance burden increases with each vertical.

**Suggested Fix:** Extract shared `MockLLM` and `MockNLI` fixtures into `tests/conftest.py`.

---

## Summary by Severity

| Severity | Count | Issues |
|----------|-------|--------|
| **Critical** | 3 | Phantom DeepSeek models, disconnected self-healing loops, WebSocket → circuit breaker coupling |
| **High** | 4 | PipelineState blast radius, VSFeatureFlags SPOF, Neuro isolation, circuit breaker not embedded |
| **Medium** | 5 | AlertManager gap, auth test dependency, vertical config inconsistency, Perplexify-only embedding, image generation leaf |
| **Low** | 5 | Graph extraction artifacts (GET(), builtins), orphaned generated tests, logging false bridges, test infra centrality, OpenRouter model testing |

---

*Generated by graphify analysis on 2026-05-04*
