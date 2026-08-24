# Context: Llm

## Directory: `src/reasoner/infrastructure/llm`

## Description
Language model provider clients, extraction parsers, and constraint checkers.

## Files
- **`__init__.py`**: LLM Adapters (legacy direct-provider adapters removed — all routing goes through OpenRouter)
- **`base.py`**: Don't retry non-retryable errors
- **`caching.py`**: Minimum cacheable prefix is 1024 tokens on the models we route to that honour
- **`capability_registry.py`**: ── Manual override layer ──
- **`exceptions.py`**: Infrastructure Exceptions
- **`executor.py`**: New imports for event emission
- **`image_generation.py`**: Code or resource asset facilitating system functionality.
- **`image_model_catalogue.py`**: ── Price normalisation ───────────────────────────────────────────────
- **`ports.py`**: Infrastructure - LLM Provider Ports (Hexagonal Architecture)
- **`pricing_resolver.py`**: Alias-aware pricing lookup.
- **`registry.py`**: Whitelist of supported models.  Everything except Ollama routes through OpenRouter.
- **`router.py`**: Multi-provider fallback (v3.4/P3.4) — retry OpenRouter failures via direct API keys
- **`spend_tracker.py`**: In-process monthly LLM spend tracker.
- **`utils.py`**: Low-level LLM utilities: platform patches, JSON heuristics, response formatting.

## Subfolders
- **`constraints`**: Validators enforcing format rules, token budgets, or prompt structural boundaries on model outputs.
- **`extraction`**: JSON repair and structured content parser implementations for cleaning non-standard LLM completions.
- **`providers`**: Concrete API wrapper clients for individual providers (Anthropic, OpenAI, Mistral, Perplexity, etc.).
