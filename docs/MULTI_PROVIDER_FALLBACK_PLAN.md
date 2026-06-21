# Multi-Provider LLM Fallback — Implementation Plan

## Status
- **Created:** 2026-06-21
- **Mode:** EXPAND (Meta-Orchestration v4.0)
- **State:** HEALTHY → EXPAND eligible (RP=1.65, GT=7.0, S=7, G=5)
- **Effort:** 1 day (MVP) / 2–3 days (Full)
- **Risk:** LOW (feature-flagged, additive, zero breaking changes)

---

## 1. Motivation

OpenRouter is the sole LLM backend for all 19 reasoning methods and 50 presets. If OpenRouter experiences an outage, rate-limiting, or model deprecation, the entire pipeline fails — no fallback exists. The `ProviderRouter` retries the same provider on failure with no alternative routing.

**Impact of a 1-hour OpenRouter outage:**
- All pipeline requests fail (SSE streaming, CLI, API)
- HyperGate preflight fails → no query classification
- All 19 reasoning methods unavailable
- Stripe billing continues but users can't use the product

---

## 2. Architecture

### 2.1 Current State

```
┌──────────────┐     ┌─────────────────┐     ┌────────────┐
│ Pipeline/    │────▶│ ProviderRouter   │────▶│ OpenRouter │
│ HyperGate    │     │ .get(role)       │     │ (sole)     │
└──────────────┘     │ .call(role, ...) │     └────────────┘
                     └─────────────────┘
```

- `ProviderRouter` holds a dict of `role → BaseLLMProvider`
- Every provider resolves to an OpenRouter model slug
- Retry logic exists but retries the SAME provider
- `LLMExecutor` has cascading routing for coding phases (multi-model chains)

### 2.2 Target State (MVP — Partial Fallback)

```
┌──────────────┐     ┌─────────────────┐     ┌────────────┐
│ Pipeline/    │────▶│ ProviderRouter   │──1──▶│ OpenRouter │
│ HyperGate    │     │ .call(role, ...) │     └────────────┘
└──────────────┘     │                  │     ┌────────────┐
                     │ _fallback_chain  │──2──▶│ Anthropic  │
                     │ [Anthropic,      │     │ (direct)   │
                     │  OpenAI, Google] │     └────────────┘
                     └─────────────────┘     ┌────────────┐
                                             │ OpenAI     │
                                             │ (direct)   │
                                             └────────────┘
```

- On provider failure (empty response, timeout, auth error), try direct API keys
- Chain: OpenRouter → Anthropic direct → OpenAI direct → Google direct
- Each fallback uses the same role's system/user prompt and parameters
- Feature flag: `MULTI_PROVIDER_FALLBACK_ENABLED` (default: false)

### 2.3 Target State (Full — Multi-Provider Router)

```
┌──────────────┐     ┌──────────────────┐     ┌────────────┐
│ Pipeline/    │────▶│ MultiProvider    │──1──▶│ OpenRouter │
│ HyperGate    │     │ Router           │     └────────────┘
└──────────────┘     │                  │     ┌────────────┐
                     │ .route(role,     │──2──▶│ Anthropic  │
                     │  strategy)       │     └────────────┘
                     │                  │     ┌────────────┐
                     │ strategies:      │──3──▶│ OpenAI     │
                     │ - cost_optimal   │     └────────────┘
                     │ - latency_first  │     ┌────────────┐
                     │ - cross_lab      │──4──▶│ Google     │
                     │ - fallback_chain │     └────────────┘
                     └──────────────────┘
```

- Provider selection strategies beyond simple fallback
- Per-role provider preferences (e.g., synthesis prefers Anthropic, scoring prefers DeepSeek)
- Health-aware routing (skip providers with recent failures)
- Deferred to iteration 2

---

## 3. Implementation Plan

### Phase 1: Foundation (MVP) — Day 1

#### 3.1.1 Settings — `src/reasoner/core/settings.py`

Add feature flag:

```python
# ── Multi-Provider Fallback ──
MULTI_PROVIDER_FALLBACK_ENABLED: bool = os.getenv(
    "MULTI_PROVIDER_FALLBACK_ENABLED", "false"
).lower() in ("1", "true", "yes")
```

**Lines:** +4 | **Risk:** None | **Test:** `assert settings.MULTI_PROVIDER_FALLBACK_ENABLED == False`

#### 3.1.2 Provider Factory — `src/reasoner/infrastructure/llm/providers/`

Add direct-provider wrappers for Anthropic, OpenAI, Google. Each wraps the existing SDK client with the `BaseLLMProvider` interface:

```
New files:
  providers/anthropic_direct.py   (~40 lines)
  providers/openai_direct.py      (~40 lines)
  providers/google_direct.py      (~40 lines)
```

Each provider:
- Reads API key from env (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`)
- Implements `complete(system_prompt, user_prompt, max_tokens, temperature)` → str
- Raises `ProviderError` on failure (caught by fallback chain)
- Respects rate limits via simple exponential backoff (reuse existing `DEFAULT_BACKOFF_*` constants)

**Lines:** ~120 total | **Risk:** LOW (isolated modules) | **Test:** Unit test each provider with mock API responses

#### 3.1.3 Fallback Chain — `src/reasoner/infrastructure/llm/router.py`

Add `_try_fallback_providers()` method to `ProviderRouter`:

```python
# In ProviderRouter.call():
async def call(self, role, system_prompt, user_prompt, **kwargs):
    try:
        provider = self.get(role)
        return await _execute_call(provider, ...)
    except (ProviderError, EmptyResponseError, TimeoutError) as exc:
        if settings.MULTI_PROVIDER_FALLBACK_ENABLED:
            return await self._try_fallback_providers(
                role, system_prompt, user_prompt, original_error=exc, **kwargs
            )
        raise

_FALLBACK_CHAIN = ["anthropic_direct", "openai_direct", "google_direct"]

async def _try_fallback_providers(self, role, system_prompt, user_prompt,
                                   original_error, **kwargs):
    """Try direct API providers in order. Returns result or raises last error."""
    last_error = original_error
    for provider_name in _FALLBACK_CHAIN:
        try:
            provider = _build_fallback_provider(provider_name)
            logger.warning(
                "Falling back to %s for role '%s' after OpenRouter failure: %s",
                provider_name, role, original_error
            )
            return await _execute_call(provider, is_fallback=True, ...)
        except Exception as e:
            last_error = e
            logger.warning("Fallback %s failed for role '%s': %s", provider_name, role, e)
    raise last_error
```

**Lines:** ~40 added to existing file | **Risk:** LOW (only active when flag is true) | **Test:** Mock OpenRouter failure, verify fallback is called

#### 3.1.4 Environment Variables — `.env.example`

Document the new optional keys:

```bash
# Multi-provider fallback (optional — used when OpenRouter fails)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
MULTI_PROVIDER_FALLBACK_ENABLED=false
```

#### 3.1.5 Tests — `tests/test_multi_provider.py`

```python
# 1. Fallback disabled by default — OpenRouter failure propagates
# 2. Fallback enabled — OpenRouter timeout → Anthropic succeeds
# 3. Fallback enabled — all providers fail → last error raised
# 4. Fallback preserves role parameters (system_prompt, temperature, max_tokens)
# 5. Fallback logs warning on each provider switch
```

**Lines:** ~150 | **Risk:** None | **Run:** `pytest tests/test_multi_provider.py -v`

---

### Phase 2: Hardening (Day 2)

#### 3.2.1 Circuit Breaker Integration

Integrate with existing `reasoner.infrastructure.redis.circuit_breaker`:

```python
# Per-provider circuit breaker prevents hammering a failing provider
_breaker = CircuitBreaker("multi_provider_fallback", threshold=3, cooldown=60)
if not _breaker.allow_call():
    logger.warning("Circuit breaker open — skipping fallback chain")
    raise last_error
```

#### 3.2.2 Metrics

Add Prometheus counters:

```python
FALLBACK_ATTEMPTS = Counter(
    "reasoner_fallback_attempts_total",
    "Multi-provider fallback attempts",
    ["provider", "role"]
)
FALLBACK_SUCCESSES = Counter(
    "reasoner_fallback_successes_total", 
    "Multi-provider fallback successes",
    ["provider", "role"]
)
```

#### 3.2.3 Preset-Level Configuration

Allow presets to override the fallback chain:

```python
# preset_registry.py — new optional field
"multi_provider_fallback": ["anthropic_direct", "openai_direct"]
```

Per-preset fallback chains enable method-specific preferences (e.g., coding presets prefer Anthropic, research presets prefer Google with search).

---

### Phase 3: Full Multi-Provider Router (Day 3–4, deferred)

#### 3.3.1 Provider Strategies

```python
class RoutingStrategy(Enum):
    COST_OPTIMAL = "cost_optimal"       # cheapest provider first
    LATENCY_FIRST = "latency_first"     # fastest provider first  
    CROSS_LAB = "cross_lab"            # different lab from synthesis
    FALLBACK_CHAIN = "fallback_chain"  # sequential fallback (Phase 1)
    ROUND_ROBIN = "round_robin"        # distribute load
```

#### 3.3.2 Health-Aware Routing

Track per-provider latency and error rates. Skip providers with >10% error rate in last 60s.

#### 3.3.3 Lab-Aware Selection

When `CROSS_LAB` strategy is active, select a fallback provider from a different lab than the failed one:

```python
_LAB_MAP = {
    "openrouter": "openrouter",
    "anthropic_direct": "anthropic", 
    "openai_direct": "openai",
    "google_direct": "google",
}
# If OpenRouter (Anthropic model) fails → try OpenAI direct next (different lab)
```

---

## 4. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Direct API key leak via error logs | LOW | HIGH | Existing log redaction covers API keys. Add `_redact_key()` before logging provider failures |
| Rate limit exhaustion on direct APIs | MEDIUM | MEDIUM | Circuit breaker prevents hammering. Per-provider rate limit counters in Phase 2 |
| Cost increase (direct APIs more expensive than OpenRouter) | MEDIUM | LOW | Feature flag off by default. Fallback only triggers on OpenRouter failure — rare |
| Provider SDK version incompatibility | LOW | MEDIUM | Use existing SDKs already in `requirements.txt`. Pin versions |
| Increased latency (fallback chain adds retries) | HIGH | LOW | Fallback is additive to existing retry. Users already wait 30–250s for pipelines. Marginal |

---

## 5. Rollback Protocol

```
Snapshot:    git tag before multi-provider merge
Trigger:     Any of:
              - Provider auth failure in production
              - S drops below 6.5 within 7 days
              - C increases > 1.5 from baseline (6.0 → >7.5)
Rollback:    Set MULTI_PROVIDER_FALLBACK_ENABLED=false (instant)
             OR: git revert <merge-commit> (5 min)
Owner:       [team assignment needed]
```

---

## 6. Verification Plan

### Pre-Deployment

```bash
# Unit tests
pytest tests/test_multi_provider.py -v

# Integration test — mock OpenRouter failure
MULTI_PROVIDER_FALLBACK_ENABLED=true python -c "
# Run a pipeline with OpenRouter unavailable → verify fallback succeeds
"

# Preset validation unaffected
python scripts/validate_presets.py

# Import chain clean
python -c "from reasoner.infrastructure.llm.router import ProviderRouter"
```

### Post-Deployment (with flag OFF)

1. Deploy with `MULTI_PROVIDER_FALLBACK_ENABLED=false`
2. Monitor for 48h — verify no regression in error rates
3. Enable flag in staging — run 9-method budget test suite
4. Enable flag in production — monitor fallback metrics
5. After 1 week with 0 fallback-related incidents → mark feature stable

---

## 7. Metrics to Track

| Metric | Source | Alert Threshold |
|---|---|---|
| `reasoner_fallback_attempts_total` | Prometheus counter | >10/hour — OpenRouter may be degraded |
| `reasoner_fallback_successes_total` | Prometheus counter | <50% success rate — fallback chain broken |
| Pipeline error rate | SSE error events | >5% — escalate |
| Phase duration p99 | Prometheus histogram | >300s — fallback adding unacceptable latency |

---

## 8. File Manifest

```
Modified:
  src/reasoner/core/settings.py          (+4 lines — feature flag)
  src/reasoner/infrastructure/llm/router.py  (+40 lines — fallback chain)

Added:
  src/reasoner/infrastructure/llm/providers/anthropic_direct.py  (~40 lines)
  src/reasoner/infrastructure/llm/providers/openai_direct.py     (~40 lines)
  src/reasoner/infrastructure/llm/providers/google_direct.py     (~40 lines)
  tests/test_multi_provider.py                                    (~150 lines)

Phase 2 (deferred):
  src/reasoner/infrastructure/metrics.py    (+8 lines — fallback counters)

Phase 3 (deferred):
  src/reasoner/infrastructure/llm/multi_provider_router.py  (~200 lines)
```

**Total MVP lines:** ~320 | **Total MVP files:** 7 (3 new, 2 modified, 1 test, 1 env example)
