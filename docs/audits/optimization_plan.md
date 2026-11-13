# Reasoner Pipeline Optimization Plan — v2.2

> **Status-aware implementation roadmap.** Each optimization is annotated with:
> - **EXISTING** — Already implemented in the codebase; may need refinement
> - **PARTIAL** — Partially implemented; gaps identified and specified
> - **NEW** — Not yet implemented; requires new code

---

## Phase 1: Streaming & Real-Time UX

### 1.1 Phase-Level Streaming for Long-Running Generators **[PARTIAL]**

**Current State:**
- `ProviderRouter.call()` supports `stream=True` returning `AsyncIterator` (`src/reasoner/infrastructure/llm/router.py`, lines 80–217)
- `LLMExecutor.execute_stream()` exists as a dedicated streaming variant (`src/reasoner/infrastructure/llm/executor.py`, lines 226–297)
- `run_stream()` in `src/reasoner/api/streaming.py` streams the *overall pipeline* via SSE, but individual phase LLM calls inside mixins use the blocking `_call_llm_cached()` → `execute()` path
- Synthesis already emits sentence-by-sentence chunks after the full LLM response is received (post-hoc chunking, not true streaming)

**Gap:** No phase streams tokens as they arrive from the LLM. The frontend waits for entire phase completion before seeing any output.

**Implementation:**

1. **Add `_call_llm_stream()` to `ReasonerPipeline`** (`src/reasoner/pipeline.py`):
   ```python
   async def _call_llm_stream(
       self, role: str, system_prompt: str, user_prompt: str, state: PipelineState, **kwargs
   ) -> AsyncIterator[str]:
       """Yield LLM tokens as they arrive. No caching, no token accumulation during stream."""
       async for chunk in self._executor.execute_stream(role, system_prompt, user_prompt, state, **kwargs):
           if isinstance(chunk, DegradedLLMResponse):
               raise RuntimeError(chunk.error)
           yield chunk
   ```

2. **Enable streaming for generation-heavy phases** in mixins:
   - `WritingMixin._phase_writing_draft()` — stream the article draft
   - `ArticlePipelineMixin._phase_article_synthesize()` — stream the synthesized article
   - `Synthesis` phase in `ReasonerPipeline._phase_synthesis()` — stream the core solution

3. **Wire streaming into `run_stream()`** (`src/reasoner/api/streaming.py`):
   - Add a `stream_phases: list[str]` preset config field
   - When a streaming-enabled phase runs, yield `text_chunk` events *during* the phase instead of only at completion
   - Accumulate tokens after the stream ends by reconstituting the full response

**Design Patterns:** Asynchronous Generator, Adapter (mixin adapts to streaming executor)

**Testing:**
- Unit test: mock `execute_stream` to yield chunks, verify `_call_llm_stream` yields them in order
- Integration test: run writing pipeline with streaming enabled, verify SSE `text_chunk` events arrive before `phase_complete`

---

### 1.2 Streaming Token Accumulation & Cost Tracking **[PARTIAL]**

**Current State:** `execute_stream()` does not accumulate tokens or costs. Caching is explicitly disabled for streaming.

**Gap:** Streaming calls are invisible to cost tracking and cannot be cached.

**Implementation:**

1. **Post-stream accumulation** in `LLMExecutor.execute_stream()`:
   - Collect the full response into a buffer as chunks arrive
   - After the stream completes, estimate tokens via `len(buffer) // 4` (same heuristic used in cache hits)
   - Call `_accumulate_tokens()` with estimated counts
   - Store the full response in cache (optional, behind a flag)

2. **Provider-native token reporting:**
   - Some providers (OpenAI, Anthropic) report usage in the final stream chunk
   - Extract this from the provider's `stream_complete()` and use actuals instead of estimates

**Testing:** Verify that streaming calls appear in `state.detailed_token_usage` after completion.

---

## Phase 2: Quality-Driven Model Cascading

### 2.1 Fast Quality Gate for Cascading Responses **[NEW]**

**Current State:** Cascading is *failure-driven only* — if model A errors/times out/returns empty/bad JSON, try model B (`src/reasoner/infrastructure/llm/executor.py`, lines 120–178). The first successful response is accepted with no quality evaluation.

**Gap:** A cheap model may return a syntactically valid but substantively poor response. We only discover this during the later PhaseMonitor quality check, after tokens are already spent and time elapsed.

**Implementation:**

1. **Create `src/reasoner/quality/quick_check.py`** — lightweight heuristics (no LLM call):
   ```python
   class QuickQualityCheck:
       """Fast, rule-based quality gate for cascading decisions."""

       @staticmethod
       def check_json_role(role: str, response: str) -> tuple[bool, str]:
           """Return (passed, reason)."""
           if role not in ("fusion", "classification", "decomposition", "scoring", "meta_evaluator"):
               return True, "not a JSON role"
           try:
               data = json.loads(response)
               if not isinstance(data, dict):
                   return False, "JSON is not an object"
               # Role-specific key presence
               required_keys = {
                   "classification": ["task_type"],
                   "decomposition": ["sub_problems"],
                   "scoring": ["scores"],
                   "fusion": ["task_type", "sub_problems"],
               }
               for key in required_keys.get(role, []):
                   if key not in data:
                       return False, f"missing required key: {key}"
               return True, "valid JSON with required keys"
           except json.JSONDecodeError as exc:
               return False, f"invalid JSON: {exc}"

       @staticmethod
       def check_content_quality(role: str, response: str) -> tuple[bool, str]:
           """Check for empty, too-short, or repetitive responses."""
           stripped = response.strip()
           if not stripped:
               return False, "empty response"
           # Minimum length thresholds per role
           min_lengths = {
               "synthesis": 200,
               "perspective": 100,
               "article_synthesize": 500,
           }
           min_len = min_lengths.get(role, 20)
           if len(stripped) < min_len:
               return False, f"response too short ({len(stripped)} < {min_len})"
           # Repetition check: if >70% of lines are identical, likely looped
           lines = stripped.splitlines()
           if len(lines) > 5:
               unique_lines = set(lines)
               if len(unique_lines) / len(lines) < 0.3:
                   return False, "excessive repetition detected"
           return True, "content quality OK"
   ```

2. **Integrate into `LLMExecutor.execute()` cascading loop** (after line 148, before `logger.info(...)`):
   ```python
   from reasoner.quality.quick_check import QuickQualityCheck
   json_ok, json_reason = QuickQualityCheck.check_json_role(role, raw)
   content_ok, content_reason = QuickQualityCheck.check_content_quality(role, raw)
   if not (json_ok and content_ok):
       logger.warning(f"[CASCADING] Model '{model_id}' response failed quick quality check: {json_reason or content_reason}")
       raise RuntimeError(f"Quality check failed: {json_reason or content_reason}")
   ```

3. **Add `cascading_quality_check: bool` to `PipelinePreset`** — default `True` for premium presets, `False` for budget (to save the extra latency).

**Design Patterns:** Strategy Pattern (pluggable quality checks), Fail-Fast

**Testing:**
- Unit tests for `QuickQualityCheck` with valid/invalid JSON, short responses, repetitive text
- Mock `LLMExecutor.execute()` with a cheap model returning bad JSON → verify it cascades to the next model

---

### 2.2 Parallel Model Racing (Latency Optimization) **[NEW]**

**Current State:** Cascading models are tried *sequentially*. If the cheap model is slow, we wait for its timeout before trying the expensive one.

**Gap:** For latency-sensitive requests, we could race multiple models and take the first quality response.

**Implementation:**

1. **Add `race_mode: bool` to cascading config** in `PipelinePreset`:
   ```python
   cascading_routing: dict[str, list[str]]  # existing
   cascading_race_mode: dict[str, bool] = {}  # NEW: which roles should race
   ```

2. **Implement `_execute_race()` in `LLMExecutor`**:
   ```python
   async def _execute_race(
       self, role: str, system_prompt: str, user_prompt: str, state: PipelineState, model_ids: list[str], **kwargs
   ) -> tuple[str, dict]:
       """Race multiple models; return the first quality response."""
       from reasoner.quality.quick_check import QuickQualityCheck

       async def _try_model(model_id: str) -> tuple[str, dict] | None:
           try:
               temp_router = ProviderRouter(primary=build_provider(model_id), verbose=False)
               raw, meta = await temp_router.call(role="primary", system_prompt=system_prompt, user_prompt=user_prompt, **kwargs)
               if isinstance(raw, DegradedLLMResponse):
                   return None
               json_ok, _ = QuickQualityCheck.check_json_role(role, raw)
               content_ok, _ = QuickQualityCheck.check_content_quality(role, raw)
               if json_ok and content_ok:
                   return raw, meta
           except Exception:
               pass
           return None

       # Launch all models concurrently; take first success
       tasks = [asyncio.create_task(_try_model(mid)) for mid in model_ids]
       for coro in asyncio.as_completed(tasks):
           result = await coro
           if result:
               # Cancel remaining tasks
               for t in tasks:
                   if not t.done():
                       t.cancel()
               return result
       raise RuntimeError(f"All race models failed for role={role}")
   ```

**Trade-off:** Increases token cost (multiple models called) but reduces latency. Only enable for critical user-facing phases (e.g., `synthesis`, `direct_answer`).

**Testing:** Mock two models where the slower one returns first valid response; verify racing takes the faster one.

---

## Phase 3: Prompt Compression & Context Optimization

### 3.1 Wire `ContextCompressor` into the Pipeline **[PARTIAL]**

**Current State:**
- `ContextCompressor` exists in `src/reasoner/neuro/compression.py` with `NONE/MINIMAL/AGGRESSIVE` levels
- `TOKEN_OPTIMIZATION` flags exist in `src/reasoner/pipeline.py` (lines 80–86) but are largely unused
- Truncation limits are applied in prompt builders (`TRUNCATION.PROBLEM=500`, `TRUNCATION.DEEP_READ=8000`)

**Gap:** `ContextCompressor` is not integrated into `_call_llm_cached()` or phase prompts. Code context (the primary use case) is not compressed.

**Implementation:**

1. **Add prompt compression hook to `LLMExecutor.execute()`** (before the LLM call, after cache miss):
   ```python
   from reasoner.neuro.compression import ContextCompressor, CompressionLevel

   # Determine compression level from preset or token pressure
   compression_level = CompressionLevel.NONE
   if TOKEN_OPTIMIZATION["context_compression"]:
       estimated_input = len(system_prompt) + len(user_prompt)
       budget = PHASE_TOKEN_BUDGETS.get(role, DEFAULT_MAX_TOKENS)
       if estimated_input > budget * 3:  # Input is 3× the output budget
           compression_level = CompressionLevel.AGGRESSIVE
       elif estimated_input > budget * 1.5:
           compression_level = CompressionLevel.MINIMAL

   if compression_level != CompressionLevel.NONE:
       compressor = ContextCompressor(level=compression_level)
       # Compress code blocks within the prompt
       user_prompt = self._compress_prompt_code_blocks(user_prompt, compressor)
   ```

2. **Implement `_compress_prompt_code_blocks()`** — extracts fenced code blocks, compresses them based on language, reinserts:
   ```python
   import re
   from reasoner.neuro.compression import smart_compress

   _CODE_FENCE_RE = re.compile(r"```(\w+)?\n(.*?)\n```", re.DOTALL)

   def _compress_prompt_code_blocks(self, prompt: str, compressor: ContextCompressor) -> str:
       def _replace_block(match: re.Match) -> str:
           lang = match.group(1) or ""
           code = match.group(2)
           compressed = smart_compress(code, ext=lang, level=compressor.level.value)
           return f"```{lang}\n{compressed}\n```"
       return _CODE_FENCE_RE.sub(_replace_block, prompt)
   ```

3. **Enable `neuro_compression` flag** for coding and article pipelines where code context is common.

**Testing:**
- Unit test: prompt with Python code block → verify comments/whitespace removed in `MINIMAL` mode
- Unit test: prompt with no code blocks → unchanged
- Measure token savings: compare `len(prompt_before)` vs `len(prompt_after)`

---

### 3.2 Semantic Cache for Near-Miss Prompts **[PARTIAL]**

**Current State:** `TokenAwareCache` (`src/reasoner/token_cache.py`) uses exact SHA-256 matching. Semantic similarity matching is stubbed (line 172: "Future: compute cosine similarity").

**Gap:** Slightly rephrased problems or prompts with identical intent miss the cache.

**Implementation:**

1. **Add lightweight semantic matching** using a local embedding model or heuristic:
   - Option A (fast, no new deps): Use problem-level Jaccard similarity of word sets. If `jaccard(problem_a, problem_b) > 0.85`, treat as same problem group.
   - Option B (accurate): Integrate `sentence-transformers` or use OpenAI embedding API for problem embeddings. Cache embeddings alongside entries.

2. **Implement `TokenAwareCache.get_semantic()`**:
   ```python
   async def get_semantic(
       self, problem: str, phase: str, model_id: str, prompt: str, threshold: float = 0.85
   ) -> str | None:
       """Check for semantically similar cached entries."""
       # Fast path: exact match
       exact = await self.get(problem, phase, model_id, prompt)
       if exact:
           return exact

       # Semantic path: find entries with similar problem hash
       problem_hash = self._compute_problem_hash(problem)
       prompt_hash = self._compute_prompt_hash(prompt)

       async with self._lock:
           candidates = [
               e for e in self._entries.values()
               if e.phase == phase and e.model_id == model_id and e.problem_hash == problem_hash
           ]
           for entry in candidates:
               # Jaccard similarity on prompt words
               words_a = set(prompt.split())
               words_b = set(entry.prompt_hash)  # We'd need to store raw prompt, not just hash
               intersection = len(words_a & words_b)
               union = len(words_a | words_b)
               if union > 0 and intersection / union >= threshold:
                   entry.access_count += 1
                   entry.last_accessed = time.monotonic()
                   self._stats.hits += 1
                   return entry.response
       return None
   ```

3. **Store raw prompt (or a fingerprint) in cache entries** to enable semantic comparison.

**Trade-off:** Option A adds minimal latency; Option B adds a dependency or API call. Start with Option A.

**Testing:**
- Cache a response for "Explain quantum computing"
- Query with "Explain quantum computing simply" → should return cached response if Jaccard > 0.85

---

## Phase 4: Inter-Phase Parallelism

### 4.1 Dependency-Aware Phase Execution **[PARTIAL]**

**Current State:**
- Intra-phase parallelism is extensive: perspectives, jury generators, critique pools all use `asyncio.gather()` within their mixins
- Inter-phase execution is strictly sequential: Classification → Decomposition → Context Vetting → Deep Read → Method Phases → Synthesis
- `PipelineFlow` (`src/reasoner/application/flows/pipeline_flow.py`) stores flat phase lists with no dependency graph

**Gap:** Some phases are independent and could run in parallel. For example:
- `Context Vetting` and `Decomposition` both depend only on Classification → could run in parallel
- `Deep Read` depends on Context Vetting, but not on Decomposition
- In the writing pipeline: `Retrieve Sources` and `Decompose Topic` are independent

**Implementation:**

1. **Add dependency metadata to `PhaseStep`**:
   ```python
   @dataclass(frozen=True)
   class PhaseStep:
       num: int | float
       name: str
       fn: PhaseFn
       serializer: Callable[[PipelineState], dict]
       critical: bool = False
       depends_on: list[str] = field(default_factory=list)  # NEW: phase names this step depends on
   ```

2. **Annotate independent phases** in `build_default_flow_registry()`:
   ```python
   # Classification has no dependencies
   PhaseStep(0, "Classification", pipeline._phase_0_classify, _ser_0)

   # These two only depend on Classification — can run in parallel
   PhaseStep(1, "Decomposition", pipeline._phase_1_decompose, _ser_1, depends_on=["Classification"])
   PhaseStep(1.25, "Context Vetting", _run_context_vetting, _ser_context_vetting, depends_on=["Classification"])

   # Deep Read depends on Context Vetting
   PhaseStep(1.5, "Deep Read", pipeline._phase_deep_read, _ser_1_5, depends_on=["Context Vetting"])
   ```

3. **Implement topological execution in `run_stream()`** (replace the sequential `for num, name, fn, serializer in phases` loop):
   ```python
   async def _execute_phases_dag(phases: list[PhaseStep], state: PipelineState):
       """Execute phases respecting dependencies. Independent phases run in parallel."""
       completed: set[str] = set()
       pending = list(phases)

       while pending:
           # Find all phases whose dependencies are satisfied
           ready = [
               p for p in pending
               if all(dep in completed for dep in p.depends_on)
           ]
           if not ready:
               raise RuntimeError(f"Circular dependency detected among: {[p.name for p in pending]}")

           # Remove ready phases from pending
           for p in ready:
               pending.remove(p)

           # Execute ready phases in parallel
           async def _run_step(step: PhaseStep):
               await _run_phase_with_keepalive(step.fn, state, timeout_seconds=get_phase_timeout(step.name))
               return step.name

           results = await asyncio.gather(*[_run_step(s) for s in ready], return_exceptions=True)
           for name, result in zip([s.name for s in ready], results):
               if isinstance(result, Exception):
                   raise result
               completed.add(name)
   ```

**Caveat:** This is a significant structural change. The current `run_stream()` loop interleaves SSE emission, quality checks, retry logic, and phase execution. Parallel execution requires:
- Each parallel group shares a single `phase_start` event
- Serializers run after all phases in a group complete
- Quality checks run per-phase within the group

**Recommendation:** Start with a limited scope — parallelize only `Decomposition` + `Context Vetting` in the non-writing flow. Validate stability before expanding.

**Testing:**
- Integration test: run multi-perspective pipeline, verify Decomposition and Context Vetting complete in parallel (total time < sum of individual times)
- Verify Deep Read only starts after Context Vetting completes

---

## Phase 5: Adaptive Temperature & Sampling

### 5.1 Retry-Aware Temperature Escalation **[NEW]**

**Current State:** Temperatures are statically configured per role in `src/reasoner/core/temperatures.py`. `PhaseConfig` has a fixed `temperature: float = 1.0`. No runtime adaptation.

**Gap:** On retry, the same temperature is reused. For creative phases, a slightly higher temperature on retry may help escape local optima. For structured phases, a lower temperature on retry may improve consistency.

**Implementation:**

1. **Add `temperature_strategy` to `PhaseConfig`** (`src/reasoner/core/protocol.py`):
   ```python
   from enum import Enum

   class TemperatureStrategy(Enum):
       FIXED = "fixed"           # Always use configured temperature
       ESCALATE = "escalate"     # Increase by 0.1 per retry (creative phases)
       DEESCALATE = "deescalate" # Decrease by 0.05 per retry (structured phases)
       SWEEP = "sweep"           # Try 0.1, 0.5, 0.9 across retries

   @dataclass(frozen=True)
   class PhaseConfig:
       max_tokens: int = DEFAULT_MAX_TOKENS
       temperature: float = 1.0
       temperature_strategy: TemperatureStrategy = TemperatureStrategy.FIXED
       timeout_seconds: float | None = None
       role: str = "primary"
   ```

2. **Apply strategy in `LLMExecutor.execute()`** (temperature resolution block, lines 68–77):
   ```python
   if "temperature" not in kwargs:
       lookup = phase_key or role
       cfg = None
       if lookup in self.phase_configs:
           cfg = self.phase_configs[lookup]
       else:
           for c in self.phase_configs.values():
               if c.role == role:
                   cfg = c
                   break

       if cfg:
           base_temp = cfg.temperature
           strategy = getattr(cfg, "temperature_strategy", TemperatureStrategy.FIXED)
           attempt = kwargs.get("_retry_attempt", 0)

           if strategy == TemperatureStrategy.ESCALATE:
               kwargs["temperature"] = min(base_temp + 0.1 * attempt, 1.0)
           elif strategy == TemperatureStrategy.DEESCALATE:
               kwargs["temperature"] = max(base_temp - 0.05 * attempt, 0.0)
           elif strategy == TemperatureStrategy.SWEEP:
               sweep_values = [0.1, 0.5, 0.9]
               kwargs["temperature"] = sweep_values[min(attempt, len(sweep_values) - 1)]
           else:
               kwargs["temperature"] = base_temp
   ```

3. **Configure strategies in `_PHASE_CONFIGS`**:
   ```python
   "perspective": PhaseConfig(
       role="primary",
       temperature=PHASE_TEMPERATURES["perspective"],
       temperature_strategy=TemperatureStrategy.ESCALATE,
   ),
   "classification": PhaseConfig(
       role="classification",
       temperature=PHASE_TEMPERATURES["classification"],
       temperature_strategy=TemperatureStrategy.DEESCALATE,
   ),
   ```

**Testing:**
- Unit test: `PhaseConfig.with_overrides(temperature_strategy=...)` works correctly
- Mock `LLMExecutor.execute()` with retry attempt=1 → verify temperature is adjusted

---

### 5.2 Per-Model Temperature Calibration **[EXISTING / REFINEMENT]**

**Current State:** `OpenAICompatibleProvider` already maintains a `_TEMPERATURE_SUPPORTED_MODELS` whitelist (`src/reasoner/infrastructure/llm/providers/openai_compat.py`). Models not on the list silently drop the temperature parameter.

**Gap:** Some models support temperature but with different effective ranges (e.g., Claude's temperature behaves differently from GPT's at the same value). No calibration layer exists.

**Implementation (optional, lower priority):**

1. **Add `temperature_calibration` map to `registry.py`**:
   ```python
   _TEMPERATURE_CALIBRATION: dict[str, float] = {
       "claude-sonnet": 1.0,      # Default — well-calibrated
       "gpt-4o": 0.9,             # Slightly more deterministic at same nominal value
       "gemini-flash": 1.1,       # Slightly more random at same nominal value
   }
   ```

2. **Apply calibration in `ProviderRouter.call()`** before passing to provider:
   ```python
   calibration = _TEMPERATURE_CALIBRATION.get(provider.model, 1.0)
   effective_temperature = min(max(temperature * calibration, 0.0), 2.0)
   ```

**Note:** This requires empirical measurement. Mark as experimental.

---

## Phase 6: Fine-Tuned Model Integration

### 6.1 Fine-Tuned Endpoint Provider **[NEW]**

**Current State:** All non-local models route through OpenRouter. No custom fine-tuned endpoints.

**Gap:** For highly constrained, repetitive tasks (classification, JSON extraction, query generation), a fine-tuned model can be 10× cheaper and 5× faster than a generalist model.

**Implementation:**

1. **Create `FineTunedProvider` in `src/reasoner/infrastructure/llm/providers/finetuned.py`**:
   ```python
   class FineTunedProvider(OpenAICompatibleProvider):
       """Provider for fine-tuned models hosted on OpenAI, Together, or custom endpoints."""

       def __init__(self, model: str, base_url: str, api_key: str | None = None):
           super().__init__(model=model, api_key=api_key or os.getenv("OPENAI_API_KEY"))
           self._base_url = base_url
           self._client = openai.AsyncOpenAI(base_url=base_url, api_key=api_key)
   ```

2. **Register fine-tuned models in `registry.py`**:
   ```python
   _FINE_TUNED_MODELS: dict[str, dict] = {
       "ft-classifier-v1": {
           "provider": "finetuned",
           "base_url": "https://api.openai.com/v1",
           "model": "ft:gpt-4o-mini:reasoner:classifier:abc123",
       },
   }
   ```

3. **Add `fine_tuned_roles` to `PipelinePreset`**:
   ```python
   @dataclass
   class PipelinePreset:
       # ... existing fields ...
       fine_tuned_roles: dict[str, str] = field(default_factory=dict)
       # Maps role -> fine-tuned model ID for that role
   ```

4. **Update `ProviderRouter.get()`** to prefer fine-tuned models when configured:
   ```python
   def get(self, role: str) -> BaseLLMProvider:
       # Check fine-tuned override first
       if hasattr(self, '_fine_tuned_table') and role in self._fine_tuned_table:
           return self._fine_tuned_table[role]
       # Fall through to normal routing
       return self.routing_table.get(role) or self.primary
   ```

**Prerequisite:** Requires actual fine-tuned models and training data. This is a *framework* addition that enables future fine-tuning work.

**Testing:**
- Unit test: `build_provider("ft-classifier-v1")` returns `FineTunedProvider`
- Mock the fine-tuned provider's `complete()` and verify it's called when the role is routed to it

---

## Phase 7: Monitoring & Observability

### 7.1 Cache Hit Rate Metrics **[PARTIAL]**

**Current State:** `TokenAwareCache.get_stats()` returns hit/miss counts. No Prometheus metrics or dashboard integration.

**Implementation:**

1. **Add cache metrics to `src/reasoner/api/metrics.py`**:
   ```python
   from prometheus_client import Counter, Gauge, Histogram

   CACHE_HITS = Counter("reasoner_cache_hits_total", "Token cache hits", ["phase", "model"])
   CACHE_MISSES = Counter("reasoner_cache_misses_total", "Token cache misses", ["phase", "model"])
   CACHE_HIT_RATE = Gauge("reasoner_cache_hit_rate", "Overall cache hit rate")
   TOKEN_SAVINGS_USD = Counter("reasoner_token_savings_usd", "Estimated cost savings from cache")
   ```

2. **Emit metrics in `LLMExecutor.execute()`** after cache lookup (lines 85–110):
   ```python
   if cached_response:
       CACHE_HITS.labels(phase=role, model=model_id_for_cache).inc()
       TOKEN_SAVINGS_USD.inc(estimated_cost)
   else:
       CACHE_MISSES.labels(phase=role, model=model_id_for_cache).inc()
   ```

---

### 7.2 Phase Latency Histograms **[NEW]**

**Implementation:**

1. **Add latency metrics:**
   ```python
   PHASE_DURATION = Histogram(
       "reasoner_phase_duration_seconds",
       "Phase execution time",
       ["phase", "method", "preset"],
       buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0],
   )
   ```

2. **Record in `run_stream()` after each phase completes** (line 843):
   ```python
   PHASE_DURATION.labels(phase=name, method=method, preset=effective_preset_name).observe(duration)
   ```

---

## Appendix: Implementation Priority Matrix

| Priority | Optimization | Effort | Impact | Risk | Status |
|----------|-------------|--------|--------|------|--------|
| P0 | 2.1 Fast Quality Gate for Cascading | Low | High | Low | NEW |
| P0 | 3.1 Wire ContextCompressor | Low | Medium | Low | PARTIAL |
| P1 | 1.1 Phase-Level Streaming | Medium | High | Medium | PARTIAL |
| P1 | 5.1 Retry-Aware Temperature | Low | Medium | Low | NEW |
| P1 | 7.1 Cache Metrics | Low | Low | Low | PARTIAL |
| P2 | 2.2 Parallel Model Racing | Medium | High | Medium | NEW |
| P2 | 3.2 Semantic Cache | Medium | Medium | Low | PARTIAL |
| P2 | 4.1 Inter-Phase Parallelism | High | High | High | PARTIAL |
| P3 | 6.1 Fine-Tuned Provider | Medium | High | Low | NEW |
| P3 | 5.2 Temperature Calibration | Low | Low | Low | NEW |
| P3 | 7.2 Phase Latency Histograms | Low | Low | Low | NEW |

**Recommended execution order:** P0 → P1 → P2 (limited scope: only Decomposition+Context Vetting parallelism) → P3.

---

## Appendix: Design Pattern Reference

| Pattern | Used In |
|---------|---------|
| **Strategy** | `QuickQualityCheck` (2.1), `TemperatureStrategy` (5.1), `CompressionLevel` (3.1) |
| **Adapter** | `LLMExecutor` wrapping `ProviderRouter`, `_call_llm_stream` adapting mixins to streaming |
| **Decorator** | Prompt compression hook in `execute()`, quality gate in cascading loop |
| **Chain of Responsibility** | Fallback chain in `ProviderRouter.call()`, cascading in `LLMExecutor.execute()` |
| **Facade** | `ReasonerPipeline` hiding complexity of `LLMExecutor`, `ProviderRouter`, caching |
| **Observer** | Metrics emission, event persistence in `run_stream()` |
| **Circuit Breaker** | Already implemented in `_call_with_circuit()` |
| **Fail-Fast** | `QuickQualityCheck` rejecting poor responses before token accumulation |
