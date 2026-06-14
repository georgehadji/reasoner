"""Model registry and provider factory."""

from __future__ import annotations

import os
from typing import Any

from reasoner.core.constants import (
    DEFAULT_OLLAMA_URL,
    MODEL_CLAUDE_SONNET,
    MODEL_GEMINI_FLASH,
    MODEL_GEMINI_PRO,
    MODEL_GPT4O_MINI,
    MODEL_LAGUNA_XS_FREE,
    MODEL_LAGUNA_M_FREE,
    NVIDIA_BASE_URL,
)
from reasoner.infrastructure.llm.providers.openai_compat import (
    OpenAICompatibleProvider,
    OpenRouterProvider,
)


# Whitelist of supported models.  Everything except Ollama routes through OpenRouter.
_MODEL_WHITELIST: dict[str, dict[str, Any]] = {
    # Anthropic
    "claude-opus":      {"model": "qwen/qwen3.6-plus"},
    "anthropic/claude-3-haiku": {"model": "anthropic/claude-haiku-4.5"},
    MODEL_CLAUDE_SONNET: {"model": "anthropic/claude-sonnet-4.6"},  # v3.2: still current as of Jun 2026
    "claude-haiku":     {"model": "anthropic/claude-haiku-4.5"},
    # OpenAI
    "gpt-5":            {"model": "openai/gpt-5.4"},
    "gpt-5-mini":       {"model": "openai/gpt-5.4-mini"},
    "gpt-5.3-codex":    {"model": "openai/gpt-5.3-codex"},
    "gpt-5.2-codex":    {"model": "openai/gpt-5.2-codex"},
    "gpt-5.1-codex":    {"model": "openai/gpt-5.1-codex"},
    "gpt-5.1-codex-max": {"model": "openai/gpt-5.1-codex-max"},
    "gpt-5.1-codex-mini": {"model": "openai/gpt-5.1-codex-mini"},
    "gpt-4o":           {"model": "openai/gpt-4o"},
    MODEL_GPT4O_MINI:   {"model": "openai/gpt-4o-mini"},
    "o3":               {"model": "openai/o3"},
    "o3-mini":          {"model": "openai/o3-mini"},
    # Google
    "google/gemma-2-9b-it": {"model": "google/gemma-3-12b-it"},
    MODEL_GEMINI_PRO:   {"model": "google/gemini-3.5-flash"},  # v3.2: 2.5-pro → 3.5-flash (near-Pro coding at Flash cost)
    MODEL_GEMINI_FLASH: {"model": "google/gemini-3.5-flash"},
    "gemini-flash-lite": {"model": "google/gemini-3.5-flash"},  # v3.2: step-3.7-flash → 3.5-flash (more reliable)
    "gemini-3.1-flash-lite": {"model": "google/gemini-3.1-flash-lite"},  # explicit alias if someone needs Google specifically
    "gemma-4-26b":      {"model": "google/gemma-4-26b-a4b-it"},
    "gemma-4-31b":      {"model": "google/gemma-4-31b-it"},
    # xAI
    "grok-4.20":        {"model": "x-ai/grok-4.20"},
    "grok-4.1-fast":    {"model": "x-ai/grok-4.1-fast"},
    "grok-4":           {"model": "x-ai/grok-4"},
    "grok-4.3":         {"model": "x-ai/grok-4.3"},
    "grok-3":           {"model": "x-ai/grok-3"},
    "grok-3-mini":      {"model": "x-ai/grok-3-mini"},
    # Perplexity
    "sonar-pro":        {"model": "perplexity/sonar-pro",      "extra_body": {"web_search_options": {"search_context_size": "medium"}}},
    "sonar":            {"model": "perplexity/sonar",          "extra_body": {"web_search_options": {"search_context_size": "low"}}},
    "sonar-reasoning-pro": {"model": "perplexity/sonar-reasoning-pro", "extra_body": {"web_search_options": {"search_context_size": "medium"}}},
    "sonar-deep-research": {"model": "perplexity/sonar-deep-research", "extra_body": {"reasoning_effort": "low"}},
    # Mistral
    "mistral-large-3":  {"model": "mistralai/mistral-large-2512"},
    "mistral-medium":   {"model": "mistralai/mistral-medium-3.1"},
    "mistral-small":    {"model": "mistralai/mistral-small-2603"},  # v3.3: 3.2-24b (2023-10) → 2603 (Mar 2026, +28 months)
    "mistral-small-2603": {"model": "mistralai/mistral-small-2603"},  # v3.3: explicit alias for preset pinning
    "codestral":        {"model": "mistralai/codestral-2501"},
    "codestral-2508":   {"model": "mistralai/codestral-2508"},
    "devstral":         {"model": "mistralai/devstral-2512"},
    "devstral-medium":  {"model": "mistralai/devstral-medium"},
    "devstral-small":   {"model": "mistralai/devstral-small"},
    "ministral-8b":     {"model": "mistralai/mistral-small-3.2-24b-instruct"},
    "ministral-3b":     {"model": "mistralai/mistral-small-3.2-24b-instruct"},
    # DeepSeek
    "deepseek-v3":      {"model": "deepseek/deepseek-v3.2"},
    "deepseek/deepseek-chat": {"model": "deepseek/deepseek-chat"},
    "deepseek-v3.1-nex-n1": {"model": "nex-agi/deepseek-v3.1-nex-n1"},
    "deepseek-r1":      {"model": "deepseek/deepseek-r1-0528"},
    "deepseek-r1t2-chimera": {"model": "tngtech/deepseek-r1t2-chimera"},
    "deepseek-v4-flash": {"model": "deepseek/deepseek-v4-flash"},
    "deepseek-v4-flash-free": {"model": "deepseek/deepseek-v4-flash:free"},
    "deepseek-v4-pro":  {"model": "deepseek/deepseek-v4-pro"},
    # Qwen
    "qwen3-max":           {"model": "qwen/qwen3.7-plus"},  # v3.2: upgraded to 3.7-plus ($0.40/$1.60 per M)
    "qwen3.7-max":         {"model": "qwen/qwen3.7-max"},
    "qwen3.6-plus":        {"model": "qwen/qwen3.7-plus"},  # v3.2: alias → 3.7-plus (better & cheaper)
    "qwen3-plus":          {"model": "qwen/qwen3.7-plus"},  # v3.2: ancient 3.5-02-15 → 3.7-plus
    "qwen3.5-plus":        {"model": "qwen/qwen3.7-plus"},  # v3.2: 20260420 → 3.7-plus
    "qwen3-turbo":         {"model": "qwen/qwen-turbo"},
    "qwen3-coder":         {"model": "qwen/qwen3-coder-plus"},
    "qwen3-coder-next":    {"model": "qwen/qwen3-coder-next"},
    "qwen3-coder-flash":   {"model": "qwen/qwen3-coder-flash"},
    "qwen3.5-flash":       {"model": "qwen/qwen3.5-flash-02-23"},
    "qwen3.5-9b":          {"model": "qwen/qwen3.5-9b"},
    "qwen3.5-27b":         {"model": "qwen/qwen3.5-27b"},
    "qwen3.5-35b-a3b":     {"model": "qwen/qwen3.5-35b-a3b"},
    "qwen3.5-122b-a10b":   {"model": "qwen/qwen3.5-122b-a10b"},
    "qwen3.5-397b-a17b":   {"model": "qwen/qwen3.5-397b-a17b"},
    "qwen3.6-flash":       {"model": "qwen/qwen3.6-flash"},
    "qwen3.6-35b-a3b":     {"model": "qwen/qwen3.6-35b-a3b"},
    "qwen3.6-plus-preview": {"model": "qwen/qwen3.6-plus-preview"},
    "qwen3.6-max-preview":  {"model": "qwen/qwen3.6-max-preview"},
    "qwen3.6-27b":          {"model": "qwen/qwen3.6-27b"},
    # Kimi
    "kimi-k2-5":        {"model": "moonshotai/kimi-k2.5"},
    "kimi-k2-6":        {"model": "moonshotai/kimi-k2.6"},
    "kimi-k2-7-code":   {"model": "moonshotai/kimi-k2.7-code"},
    # Laguna (Poolside)
    MODEL_LAGUNA_XS_FREE: {"model": "poolside/laguna-xs.2:free"},
    MODEL_LAGUNA_M_FREE:  {"model": "poolside/laguna-m.1:free"},
    # GLM
    "glm-5":            {"model": "z-ai/glm-5"},
    "glm-4-plus":       {"model": "z-ai/glm-4.5"},
    "glm-4-air":        {"model": "z-ai/glm-4.5-air"},
    "glm-4-airx":       {"model": "z-ai/glm-4.6"},
    "glm-4-long":       {"model": "z-ai/glm-4-32b"},
    "glm-5.1":          {"model": "z-ai/glm-5.1"},
    "glm-4.7-flash":    {"model": "z-ai/glm-4.7-flash"},
    "glm-5.1":           {"model": "z-ai/glm-5.1"},
    # Elephant
    "elephant-alpha":   {"model": "openrouter/elephant-alpha"},
    # OpenRouter
    "fireworks/firefunction-v2": {"model": "openai/gpt-4o-mini"},
    "owl-alpha":        {"model": "openrouter/owl-alpha"},
    "pareto-code":      {"model": "openrouter/pareto-code"},
    # Arcee AI
    "arcee-trinity-large-thinking": {"model": "arcee-ai/trinity-large-thinking"},
    "arcee-virtuoso-large":         {"model": "arcee-ai/virtuoso-large"},
    "arcee-maestro-reasoning":      {"model": "arcee-ai/maestro-reasoning"},
    "arcee-coder-large":            {"model": "arcee-ai/coder-large"},
    # Xiaomi
    "mimo-v2-pro":    {"model": "xiaomi/mimo-v2-pro"},
    "mimo-v2-omni":   {"model": "xiaomi/mimo-v2-omni"},
    "mimo-v2-flash":  {"model": "xiaomi/mimo-v2-flash"},
    # MiniMax
    "minimax-m2":       {"model": "minimax/minimax-01"},
    "minimax-m2.5":     {"model": "minimax/minimax-m2.5"},
    "minimax-m2.5-free": {"model": "minimax/minimax-m2.5:free"},
    "minimax-m2.7":     {"model": "minimax/minimax-m2.7"},
    "minimax-m3":        {"model": "minimax/minimax-m3"},
    "minimax-m1":       {"model": "minimax/minimax-m1"},
    # Tencent
    "hy3-preview":      {"model": "tencent/hy3-preview"},
    # ByteDance Seed
    "seed-2.0-mini":    {"model": "bytedance-seed/seed-2.0-mini"},  # v3.3: $0.10/$0.40 per M — 262K ctx, Feb 2026 born
    # Baidu
    "qianfan-ocr-fast": {"model": "baidu/qianfan-ocr-fast:free"},
    # inclusionAI (Ant Group)
    "ling-2.6-flash-free": {"model": "inclusionai/ling-2.6-flash:free"},
    "ring-2.6-1t":         {"model": "inclusionai/ring-2.6-1t"},  # v3.2: $0.075/$0.625 per M — 63B active/1T total thinking model
    # StepFun — ultra-cheap multimodal MoE
    "stepfun/step-3.7-flash":   {"model": "stepfun/step-3.7-flash"},  # v3.2: $0.20/$1.15 per M — 196B MoE, 11B active
    # Nex AGI — free MoE
    "nex-n2-pro-free":     {"model": "nex-agi/nex-n2-pro:free"},  # v3.2: FREE — 17B active/397B total MoE
    # NVIDIA Nemotron — free reasoning model
    "nemotron-3-ultra-free": {"model": "nvidia/nemotron-3-ultra-550b-a55b:free"},  # v3.2: FREE — 55B active/550B MoE
    # Meta (via OpenRouter)
    "llama-3.3-70b":      {"model": "meta-llama/llama-3.3-70b-instruct:free"},
    # NVIDIA (via OpenRouter)
    # Discriminative reranker — returns relevance scores via logprobs, not generated text.
    # Use rerank_via_nemotron() in core/rerank.py; do NOT call via router.call() for text generation.
    "nvidia-nemotron-rerank-vl":  {"model": "nvidia/llama-nemotron-rerank-vl-1b-v2:free"},
    "nvidia-nemotron-nano-8b":    {"model": "nvidia/llama-3.1-nemotron-nano-8b-v1:free"},
    # NVIDIA NIM (direct, not via OpenRouter)
    "nvidia-nemotron-super": {
        "cls": "compat",
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "base": NVIDIA_BASE_URL,
        "env": "NVIDIA_API_KEY",
    },
    # Image generation models (OpenRouter multimodal image output)
    "gemini-flash-image":            {"model": "google/gemini-2.5-flash-image", "extra_body": {"include_images": True}},
    "gemini-pro-image":              {"model": "google/gemini-3-pro-image-preview", "extra_body": {"include_images": True}},
    "gemini-3.1-flash-image-preview": {"model": "google/gemini-3.1-flash-image-preview", "extra_body": {"include_images": True}},
    "gpt-5-image":                   {"model": "openai/gpt-5-image", "extra_body": {"include_images": True}},
    "gpt-5-image-mini":              {"model": "openai/gpt-5-image-mini", "extra_body": {"include_images": True}},
    "gpt-5.4-image-2":               {"model": "openai/gpt-5.4-image-2", "extra_body": {"include_images": True}},
    # Flux 2 (Black Forest Labs)
    "flux.2-pro":                    {"model": "black-forest-labs/flux.2-pro", "extra_body": {"include_images": True}},
    "flux.2-flex":                   {"model": "black-forest-labs/flux.2-flex", "extra_body": {"include_images": True}},
    "flux.2-max":                    {"model": "black-forest-labs/flux.2-max", "extra_body": {"include_images": True}},
    "flux.2-klein-4b":               {"model": "black-forest-labs/flux.2-klein-4b", "extra_body": {"include_images": True}},
    # Seedream (ByteDance)
    "seedream-4.5":                  {"model": "bytedance-seed/seedream-4.5", "extra_body": {"include_images": True}},
    # Riverflow (Sourceful)
    "riverflow-v2-pro":              {"model": "sourceful/riverflow-v2-pro", "extra_body": {"include_images": True}},
    "riverflow-v2-fast":             {"model": "sourceful/riverflow-v2-fast", "extra_body": {"include_images": True}},
    "riverflow-v2-max-preview":      {"model": "sourceful/riverflow-v2-max-preview", "extra_body": {"include_images": True}},
    "riverflow-v2-standard-preview": {"model": "sourceful/riverflow-v2-standard-preview", "extra_body": {"include_images": True}},
    "riverflow-v2-fast-preview":     {"model": "sourceful/riverflow-v2-fast-preview", "extra_body": {"include_images": True}},
    # Grok Imagine (xAI)
    "grok-imagine":               {"model": "x-ai/grok-imagine-image-quality", "extra_body": {"include_images": True}},
    # MAI-Image (Microsoft)
    "mai-image-2.5":               {"model": "microsoft/mai-image-2.5", "extra_body": {"include_images": True}},
    # Recraft (vector illustration, icons, design)
    "recraft-v4":                    {"model": "recraft/recraft-v4", "extra_body": {"include_images": True}},
    "recraft-v4-pro":                {"model": "recraft/recraft-v4-pro", "extra_body": {"include_images": True}},
    "recraft-v4.1":                  {"model": "recraft/recraft-v4.1", "extra_body": {"include_images": True}},
    "recraft-v4.1-pro":              {"model": "recraft/recraft-v4.1-pro", "extra_body": {"include_images": True}},
    "recraft-v4.1-utility":          {"model": "recraft/recraft-v4.1-utility", "extra_body": {"include_images": True}},
    "recraft-v4.1-utility-pro":      {"model": "recraft/recraft-v4.1-utility-pro", "extra_body": {"include_images": True}},
    "recraft-v4.1-vector":           {"model": "recraft/recraft-v4.1-vector", "extra_body": {"include_images": True}},
    "recraft-v4.1-pro-vector":       {"model": "recraft/recraft-v4.1-pro-vector", "extra_body": {"include_images": True}},
    # Ollama (local)
    "ollama-llama3":    {"cls": "compat", "model": "llama3",    "base": f"{DEFAULT_OLLAMA_URL}/v1", "env": "OLLAMA_API_KEY", "is_local": True},
    "ollama-llama3.1":  {"cls": "compat", "model": "llama3.1",  "base": f"{DEFAULT_OLLAMA_URL}/v1", "env": "OLLAMA_API_KEY", "is_local": True},
    "ollama-llama3.2":  {"cls": "compat", "model": "llama3.2",  "base": f"{DEFAULT_OLLAMA_URL}/v1", "env": "OLLAMA_API_KEY", "is_local": True},
    "ollama-mistral":   {"cls": "compat", "model": "mistral",   "base": f"{DEFAULT_OLLAMA_URL}/v1", "env": "OLLAMA_API_KEY", "is_local": True},
    "ollama-codellama": {"cls": "compat", "model": "codellama", "base": f"{DEFAULT_OLLAMA_URL}/v1", "env": "OLLAMA_API_KEY", "is_local": True},
    "ollama-qwen2":     {"cls": "compat", "model": "qwen2",     "base": f"{DEFAULT_OLLAMA_URL}/v1", "env": "OLLAMA_API_KEY", "is_local": True},
    "ollama-gemma2":    {"cls": "compat", "model": "gemma2",    "base": f"{DEFAULT_OLLAMA_URL}/v1", "env": "OLLAMA_API_KEY", "is_local": True},
    "ollama-phi3":      {"cls": "compat", "model": "phi3",      "base": f"{DEFAULT_OLLAMA_URL}/v1", "env": "OLLAMA_API_KEY", "is_local": True},
}

# Build _REGISTRY from whitelist so every non-local model routes through OpenRouter.
_REGISTRY: dict[str, dict[str, Any]] = {}
for _mid, _cfg in _MODEL_WHITELIST.items():
    _entry: dict[str, Any] = dict(_cfg)
    if not _entry.get("is_local"):
        _entry.setdefault("cls", "openrouter")
        _entry.setdefault("env", "OPENROUTER_API_KEY")
    _REGISTRY[_mid] = _entry


def build_provider(model_id: str, api_key: str | None = None) -> "BaseLLMProvider":
    """Build a provider instance from a model ID string."""
    from reasoner.infrastructure.llm.base import BaseLLMProvider

    if model_id not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(
            f"""Unknown model ID: {model_id!r}
Available models:
  {available}"""
        )
    cfg = _REGISTRY[model_id]
    key = api_key or os.environ.get(cfg["env"], "")
    if not key and not cfg.get("is_local"):
        raise ValueError(
            f"API key for '{model_id}' is not set. "
            f"Set the {cfg['env']} environment variable."
        )

    match cfg["cls"]:
        case "openrouter":
            return OpenRouterProvider(
                model=cfg["model"],
                api_key=key,
                extra_body=cfg.get("extra_body"),
            )
        case "compat":
            # Handle Ollama base URL from environment
            base_url = cfg.get("base")
            if cfg.get("is_local") and os.environ.get("OLLAMA_BASE_URL"):
                base_url = os.environ.get("OLLAMA_BASE_URL")
            # For Ollama, api_key is optional (can be any dummy value)
            ollama_key = key if key else "ollama"
            return OpenAICompatibleProvider(
                model=cfg["model"],
                api_key=ollama_key,
                base_url=base_url,
                extra_body=cfg.get("extra_body"),
            )
        case _:
            raise ValueError(f"Unknown cls: {cfg['cls']!r}")


def list_models() -> dict[str, list[str]]:
    """Return all model IDs grouped by ecosystem."""
    groups: dict[str, list[str]] = {"openrouter": [], "ollama": [], "direct": []}
    for mid in sorted(_REGISTRY):
        cfg = _REGISTRY[mid]
        if cfg.get("is_local"):
            groups["ollama"].append(mid)
        elif cfg.get("cls") == "openrouter":
            groups["openrouter"].append(mid)
        else:
            groups["direct"].append(mid)
    return groups
