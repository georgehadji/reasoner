---
name: reasoner-model-routing
description: Reference for Reasoner's model routing system — how to add models to the whitelist, cross-lab diversity rules, ProviderRouter, and fallback chains. Essential before touching preset configs or adding new LLM providers.
trigger: /reasoner-model-routing
---

# Reasoner Model Routing Reference

## Architecture overview

```
Preset config (routing dict)
        ↓
ProviderRouter (infrastructure/llm/router.py)
        ↓
_REGISTRY lookup → build_provider()
        ↓
_MODEL_WHITELIST (infrastructure/llm/registry.py)  →  OpenRouter or direct adapter
        ↓
OpenAICompatibleProvider / OpenRouterProvider
```

## The model whitelist

**File:** `src/reasoner/infrastructure/llm/registry.py`

Every model alias used in any preset must appear in `_MODEL_WHITELIST`. The whitelist maps short aliases to OpenRouter model IDs:

```python
_MODEL_WHITELIST: dict[str, dict[str, Any]] = {
    "deepseek-v3":  {"model": "deepseek/deepseek-v3.2"},
    "gemini-flash": {"model": "google/gemini-2.5-flash"},
    "sonar-pro":    {"model": "perplexity/sonar-pro",
                     "extra_body": {"web_search_options": {...}}},
    # Ollama (local) gets a base_url override:
    "ollama-llama3": {"model": "llama3", "base_url": DEFAULT_OLLAMA_URL},
}
```

### Adding a new model

1. Find the OpenRouter model ID at `openrouter.ai/models`.
2. Add an entry to `_MODEL_WHITELIST` in the appropriate lab section.
3. If the model needs non-default parameters (temperature override, extra_body for web search, different base_url for Ollama/NVIDIA), include them in the dict.
4. Update at least one preset to use the alias.

```python
# Example: adding a new Qwen model
"qwen4-turbo": {"model": "qwen/qwen4-turbo"},
```

## Lab taxonomy (cross-lab diversity rule)

These are the labs recognised for diversity counting:

| Lab | Example aliases |
|-----|----------------|
| Anthropic | `claude-opus`, `claude-sonnet`, `claude-haiku` |
| OpenAI | `gpt-5`, `gpt-4o`, `o3`, `o3-mini` |
| Google | `gemini-pro`, `gemini-flash`, `gemini-flash-lite`, `gemma-*` |
| xAI | `grok-4`, `grok-3`, `grok-3-mini` |
| Perplexity | `sonar-pro`, `sonar`, `sonar-reasoning-pro`, `sonar-deep-research` |
| Mistral | `mistral-large-3`, `mistral-medium`, `mistral-small`, `codestral`, `devstral`, `ministral-*` |
| DeepSeek | `deepseek-v3`, `deepseek-r1`, `deepseek-v4-*` |
| Qwen (Alibaba) | `qwen3-*`, `qwen3.5-*`, `qwen3.6-*`, `qwen3.7-*` |
| Kimi (Moonshot) | `kimi-*`, `moonshot-*` |
| GLM (Zhipu) | `glm-5.1`, `glm-4-air`, `glm-4-flash` |
| MiniMax | `minimax-text-01`, `abab-*` |
| NVIDIA | Models via `NVIDIA_BASE_URL` |
| Ollama | Local models via `DEFAULT_OLLAMA_URL` |

### Diversity rules (enforced in CI `pr-architecture.yml`)

- **Budget presets:** Phase 2 perspective roles (`constructive`, `destructive`, `systemic`, `minimalist`) must span ≥ 3 distinct labs.
- **Premium presets:** Phase 2 must span ≥ 4 distinct labs.
- **Scorer independence:** The `scoring` role model must come from a different lab than whichever lab provides the most Phase 2 perspective slots.
- **Synthesis independence:** Strongly preferred (not hard-enforced) to use a lab distinct from the Phase 2 majority.

### Why this matters

Cross-lab diversity prevents echo chambers: models from the same training ecosystem tend to agree on the same failure modes. Keeping labs separated in Phase 2 is the primary quality lever in budget presets.

## ProviderRouter

**File:** `src/reasoner/infrastructure/llm/router.py`

`ProviderRouter` is the runtime object passed to each pipeline phase. It resolves a `routing_key` (e.g. `"constructive"`) to an `LLMProvider` instance at call time, following the fallback chain:

```
primary model → fallback model → circuit-breaker state → error
```

### Fallback chain design rules

1. Keep fallback models in the same lab family when possible (avoids quality drops).
2. Free-tier fallbacks (e.g. `deepseek-v4-flash:free`) are acceptable for Budget presets.
3. Never set a fallback that's slower than the primary (defeats the purpose).
4. The `primary_id` field in the preset is used as the human-readable identifier for cost tracking — pick the most representative model.

### Building a router in tests

```python
from reasoner.infrastructure.llm.router import ProviderRouter

router = ProviderRouter.from_preset(preset)   # from a PipelinePreset
# or
router = ProviderRouter.from_model_ids(primary_id="deepseek-v3")  # simple single-model
```

## Constants for token budgets

**File:** `src/reasoner/core/constants.py`

Each phase has a token budget constant. Use these when writing new phase prompt modules:

```python
from reasoner.core.constants import (
    PHASE_2_TOKEN_BUDGET,    # Generation / perspectives
    PHASE_3_TOKEN_BUDGET,    # Critique / scoring
    PHASE_5_TOKEN_BUDGET,    # Synthesis
    HYPERGATE_MAX_TOKENS_TIEBREAK,
)
```

Do not hardcode token values inline — always reference a constant.

## Adding a direct provider adapter (non-OpenRouter)

If a model is not on OpenRouter (e.g. a private endpoint):

1. Add a provider class in `src/reasoner/infrastructure/llm/providers/`.
2. Implement the `LLMProvider` protocol from `src/reasoner/infrastructure/llm/ports.py`.
3. Register in `build_provider()` in `registry.py` with a `base_url` key.
4. Add a constant for the base URL in `src/reasoner/core/constants.py`.

```python
# constants.py
MY_PROVIDER_BASE_URL = os.getenv("MY_PROVIDER_URL", "https://api.myprovider.com/v1")

# registry.py
"my-model": {"model": "my-model-id", "base_url": MY_PROVIDER_BASE_URL},
```
