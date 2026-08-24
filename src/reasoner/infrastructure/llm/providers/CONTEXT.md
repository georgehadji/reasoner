# Context: Providers

## Directory: `src/reasoner/infrastructure/llm/providers`

## Description
Concrete API wrapper clients for individual providers (Anthropic, OpenAI, Mistral, Perplexity, etc.).

## Files
- **`__init__.py`**: LLM provider implementations.
- **`direct.py`**: Direct API provider wrappers for multi-provider fallback.
- **`finetuned.py`**: Fine-Tuned Model Provider
- **`noop.py`**: No-op / Dummy LLM Provider
- **`openai_compat.py`**: Shared connection pool (httpx client) across all instances for performance

## Subfolders
*No subfolders in this directory.*
