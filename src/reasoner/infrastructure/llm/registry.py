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
    "claude-opus":      {"model": "anthropic/claude-opus-4.8"},
    MODEL_CLAUDE_SONNET: {"model": "anthropic/claude-sonnet-4.6"},  # v3.2: still current as of Jun 2026
    "claude-haiku":     {"model": "anthropic/claude-haiku-4.5"},
    # ═══════════════════════════════════════════════════════════════
    # OpenAI — GPT series
    # ═══════════════════════════════════════════════════════════════
    # ── Current (5.5, Apr 2026) ──
    "gpt-5.5":          {"model": "openai/gpt-5.5"},             # frontier — $5/$30 per M, AI² Intel 54.8, 1M ctx
    "gpt-5.5-pro":      {"model": "openai/gpt-5.5-pro"},         # max reasoning — $30/$180 per M, 1M ctx
    "gpt-5":            {"model": "openai/gpt-5.5"},             # alias → 5.5 (current frontier)
    # ── Previous (5.4, Mar 2026) ──
    "gpt-5.4":          {"model": "openai/gpt-5.4"},             # $2.50/$15 per M, AI² Intel 51.4
    "gpt-5-mini":       {"model": "openai/gpt-5.4-mini"},        # $0.75/$4.50 per M, AI² Intel 40
    "gpt-5.4-mini":     {"model": "openai/gpt-5.4-mini"},        # explicit alias
    "gpt-5.4-nano":     {"model": "openai/gpt-5.4-nano"},        # cheapest OpenAI — $0.20/$1.25 per M, AI² Intel 38.2
    # ── Auto-updating (always latest) ──
    "gpt-latest":       {"model": "~openai/gpt-latest"},         # always → latest GPT family
    "gpt-mini-latest":  {"model": "~openai/gpt-mini-latest"},    # always → latest GPT Mini family
    # ── Codex (coding-optimized) ──
    "gpt-5.3-codex":    {"model": "openai/gpt-5.3-codex"},
    "gpt-5.2-codex":    {"model": "openai/gpt-5.2-codex"},
    "gpt-5.1-codex":    {"model": "openai/gpt-5.1-codex"},
    "gpt-5.1-codex-max": {"model": "openai/gpt-5.1-codex-max"},
    "gpt-5.1-codex-mini": {"model": "openai/gpt-5.1-codex-mini"},
    # ── Legacy / Budget ──
    # gpt-4o removed — 2 generations behind (5.4 → 5.5)
    MODEL_GPT4O_MINI:   {"model": "openai/gpt-4o-mini"},         # budget synthesis — proven, cheap, reliable
    # o3/o3-mini — no temperature support; can't use for low-temp phases
    "o3":               {"model": "openai/o3"},
    "o3-mini":          {"model": "openai/o3-mini"},
    # ═══════════════════════════════════════════════════════════════
    # Google — Gemini series
    # ═══════════════════════════════════════════════════════════════
    # gemini-pro → claude-sonnet (premium primary, not Google — changed v3.4)
    # gemini-flash-lite → qwen3.5-flash (budget primary, not Google — changed v3.4)
    MODEL_GEMINI_PRO:   {"model": "anthropic/claude-sonnet-4.6"},  # premium primary (Anthropic, not Google)
    MODEL_GEMINI_FLASH: {"model": "google/gemini-3.5-flash"},      # budget primary — $1.50/$9 per M, AI² Intel 50.2, 1M ctx
    "gemini-flash-lite": {"model": "qwen/qwen3.5-flash-02-23"},    # budget primary — $0.065/$0.26, fast & reliable
    # ── Real Google models (not aliased to other labs) ──
    "gemini-pro-real":         {"model": "google/gemini-3.1-pro-preview"},      # true Google Pro — $2/$12 per M, AI² Intel 46.5, reasoning mandatory
    "gemini-flash-lite-real":  {"model": "google/gemini-3.1-flash-lite"},       # true Google Flash Lite — $0.25/$1.50, 1M ctx
    "gemini-2.5-flash-lite":   {"model": "google/gemini-2.5-flash-lite"},       # cheapest Google — $0.10/$0.40, 1M ctx
    # ── Auto-updating (always latest) ──
    "gemini-pro-latest":       {"model": "~google/gemini-pro-latest"},          # always → latest Gemini Pro
    "gemini-flash-latest":     {"model": "~google/gemini-flash-latest"},        # always → latest Gemini Flash
    # ── Legacy ──
    "gemini-3.1-flash-lite":   {"model": "google/gemini-3.1-flash-lite"},       # → gemini-flash-lite-real
    "google/gemma-2-9b-it":    {"model": "google/gemma-3-12b-it"},
    "gemma-4-26b":             {"model": "google/gemma-4-26b-a4b-it"},
    "gemma-4-31b":             {"model": "google/gemma-4-31b-it"},
    # xAI — Grok series
    # grok-4.1-fast, grok-4, grok-3, grok-3-mini removed — no longer on OpenRouter
    "grok-4.20":              {"model": "x-ai/grok-4.20"},              # reasoning, 2M ctx, $1.25/$2.50 per M
    "grok-4.20-multi-agent":  {"model": "x-ai/grok-4.20-multi-agent"},  # multi-agent variant, 2M ctx, reasoning mandatory
    "grok-4.3":               {"model": "x-ai/grok-4.3"},               # general reasoning, 1M ctx, $1.25/$2.50
    "grok-build-0.1":         {"model": "x-ai/grok-build-0.1"},         # fast agentic coding, 256K ctx, $1.00/$2.00
    # Perplexity
    "sonar-pro":        {"model": "perplexity/sonar-pro",      "extra_body": {"web_search_options": {"search_context_size": "high"}}},
    "sonar":            {"model": "perplexity/sonar",          "extra_body": {"web_search_options": {"search_context_size": "low"}}},
    "sonar-reasoning-pro": {"model": "perplexity/sonar-reasoning-pro", "extra_body": {"web_search_options": {"search_context_size": "high"}}},
    "sonar-deep-research": {"model": "perplexity/sonar-deep-research", "extra_body": {"reasoning_effort": "high"}},
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
    # ministral-3b removed — no known OpenRouter model; use ministral-8b or stepfun-3.7-flash
    # ═══════════════════════════════════════════════════════════════
    # DeepSeek — ordering: V4 (latest) → V3.2 → V3.1 → R1 → legacy
    # ═══════════════════════════════════════════════════════════════
    # V4 family: 1M ctx, MoE, reasoning_effort high/xhigh
    #   Pro:  1.6T total / 49B active — $0.435/$0.87  per M
    #   Flash: 284B total / 13B active — $0.09/$0.18   per M
    "deepseek-v4-pro":  {"model": "deepseek/deepseek-v4-pro",
                         "extra_body": {"reasoning": {"effort": "high"}}},
    "deepseek-v4-flash": {"model": "deepseek/deepseek-v4-flash",
                          "extra_body": {"reasoning": {"effort": "high"}}},
    # deepseek-v4-flash-free removed — OpenRouter endpoints returned empty (dead model)
    # V3.2: 131K ctx, GPT-5 class reasoning, MoE — $0.2288/$0.3432 per M
    # reasoning is optional (default disabled); enable per-call via extra_body if needed
    "deepseek-v3.2":    {"model": "deepseek/deepseek-v3.2"},
    "deepseek-v3":      {"model": "deepseek/deepseek-v3.2"},  # alias → V3.2 (latest V3)
    # V3-0324: 164K ctx, Mar 2025 update — $0.20/$0.77 per M
    # Better AND cheaper than original V3 ($0.2002/$0.8001)
    "deepseek-v3-0324": {"model": "deepseek/deepseek-chat-v3-0324"},
    # Legacy alias — upgraded from original V3 to V3-0324 (strictly dominates old model)
    "deepseek/deepseek-chat": {"model": "deepseek/deepseek-chat-v3-0324"},
    # V3.1: 164K ctx, HYBRID reasoning — supports both thinking + non-thinking modes
    # via prompt templates. $0.21/$0.79 per M. 671B total / 37B active.
    "deepseek-v3.1":    {"model": "deepseek/deepseek-chat-v3.1"},
    # V3.1 Terminus: newer V3.1 update with language consistency + agent fixes
    "deepseek-v3.1-terminus": {"model": "deepseek/deepseek-v3.1-terminus"},
    # deepseek-v3.1-nex-n1 removed — 8K context window is unusable for pipeline phases
    # R1-0528: 164K ctx, 671B/37B active, reasoning MANDATORY — $0.50/$2.15 per M
    "deepseek-r1":      {"model": "deepseek/deepseek-r1-0528"},
    # Original R1 (Jan 2025) — fallback for R1-0528. reasoning MANDATORY. $0.70/$2.50 per M
    "deepseek-r1-original": {"model": "deepseek/deepseek-r1"},
    # R1T2 Chimera (TNG Tech): tri-parent merge (R1-0528 + R1 + V3-0324). 20% faster than R1.
    "deepseek-r1t2-chimera": {"model": "tngtech/deepseek-r1t2-chimera"},
    # ═══════════════════════════════════════════════════════════════
    # Qwen (Alibaba) — 3.5 → 3.7 series
    # ═══════════════════════════════════════════════════════════════
    # ── 3.7 (latest, Jun 2026) ──
    "qwen3.7-max":         {"model": "qwen/qwen3.7-max"},       # flagship agent — $1.25/$3.75 per M, 1M ctx
    "qwen3.7-plus":        {"model": "qwen/qwen3.7-plus"},      # best VFM — $0.32/$1.28 per M, 1M ctx
    # ── 3.7 value aliases (intentionally route to 3.7-plus for cost) ──
    "qwen3-max":           {"model": "qwen/qwen3.7-plus"},      # "max" alias → 3.7-plus (budget-friendly, $0.32/$1.28)
    "qwen3.6-plus":        {"model": "qwen/qwen3.7-plus"},      # alias → 3.7-plus (cheaper AND stronger than real 3.6-plus)
    "qwen3-plus":          {"model": "qwen/qwen3.7-plus"},      # generic "plus" → best plus
    "qwen3.5-plus":        {"model": "qwen/qwen3.7-plus"},      # 3.5-plus legacy → 3.7-plus
    # ── 3.6 (mid 2026) ──
    "qwen3.6-plus-real":   {"model": "qwen/qwen3.6-plus"},      # real 3.6-plus — $0.325/$1.95 per M, 1M ctx
    "qwen3.6-flash":       {"model": "qwen/qwen3.6-flash"},     # $0.1875/$1.125 per M, 1M ctx
    "qwen3.6-35b-a3b":     {"model": "qwen/qwen3.6-35b-a3b"},   # $0.14/$1.00 per M, 262K ctx, open-weight
    "qwen3.6-27b":         {"model": "qwen/qwen3.6-27b"},       # $0.2885/$3.17 per M, 262K ctx, dense
    "qwen3.6-max-preview": {"model": "qwen/qwen3.6-max-preview"}, # $1.04/$6.24 per M, 262K ctx, ~1T MoE preview
    # qwen3.6-plus-preview removed — dead model (API returns empty)
    # ── 3.5 (early-mid 2026) ──
    "qwen3.5-flash":       {"model": "qwen/qwen3.5-flash-02-23"}, # cheapest Qwen — $0.065/$0.26 per M, 1M ctx
    "qwen3.5-9b":          {"model": "qwen/qwen3.5-9b"},          # $0.10/$0.15 per M, 262K ctx
    "qwen3.5-27b":         {"model": "qwen/qwen3.5-27b"},         # $0.195/$1.56 per M, 262K ctx, dense
    "qwen3.5-35b-a3b":     {"model": "qwen/qwen3.5-35b-a3b"},     # $0.14/$1.00 per M, 262K ctx, MoE
    "qwen3.5-122b-a10b":   {"model": "qwen/qwen3.5-122b-a10b"},   # $0.26/$2.08 per M, 262K ctx, MoE
    "qwen3.5-397b-a17b":   {"model": "qwen/qwen3.5-397b-a17b"},   # $0.385/$2.45 per M, 256K ctx, MoE
    # ── Qwen3 Max Thinking — dedicated reasoning (Jan 2026) ──
    "qwen3-max-thinking":  {"model": "qwen/qwen3-max-thinking"},  # $0.78/$3.90 per M, 262K ctx — deep multi-step reasoning
    # ── Turbo (dead — replaced with 3.5-flash) ──
    # qwen/qwen-turbo removed from OpenRouter; qwen3-turbo alias now routes to cheapest 1M Qwen
    "qwen3-turbo":         {"model": "qwen/qwen3.5-flash-02-23"}, # was qwen/qwen-turbo (DEAD) → qwen3.5-flash ($0.065/$0.26)
    # ── Coder series ──
    "qwen3-coder":            {"model": "qwen/qwen3-coder-plus"},        # proprietary — $0.65/$3.25 per M, 1M ctx
    "qwen3-coder-flash":      {"model": "qwen/qwen3-coder-flash"},       # $0.195/$0.975 per M, 1M ctx
    "qwen3-coder-next":       {"model": "qwen/qwen3-coder-next"},        # open-weight — $0.11/$0.80 per M, 262K ctx
    "qwen3-coder-30b-a3b":    {"model": "qwen/qwen3-coder-30b-a3b-instruct"}, # cheapest coder — $0.07/$0.27 per M, 160K ctx
    # qwen3-coder:free (480B A35B, FREE) — available but not registered (rate limits likely)
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

    "owl-alpha":        {"model": "openrouter/owl-alpha"},
    "pareto-code":      {"model": "openrouter/pareto-code"},
    # Arcee AI
    "arcee-trinity-large-thinking": {"model": "arcee-ai/trinity-large-thinking"},
    "arcee-virtuoso-large":         {"model": "arcee-ai/virtuoso-large"},
    "arcee-maestro-reasoning":      {"model": "arcee-ai/maestro-reasoning"},
    "arcee-coder-large":            {"model": "arcee-ai/coder-large"},
    # Xiaomi — MiMo series (v2.5, Apr 2026)
    # mimo-v2-pro/omni/flash replaced with v2.5 equivalents
    "mimo-v2.5-pro":  {"model": "xiaomi/mimo-v2.5-pro"},   # flagship agent — $0.435/$0.87 per M, 1M ctx, AI² Intel 42.2
    "mimo-v2.5":      {"model": "xiaomi/mimo-v2.5"},       # omnimodal value — $0.14/$0.28 per M, 1M ctx
    # Legacy aliases (presets may reference these)
    "mimo-v2-pro":    {"model": "xiaomi/mimo-v2.5-pro"},   # alias → v2.5 Pro
    "mimo-v2-flash":  {"model": "xiaomi/mimo-v2.5"},       # alias → v2.5 (value tier)
    # MiniMax — M-series
    "minimax-m3":        {"model": "minimax/minimax-m3"},        # latest, 1M ctx, multimodal, $0.30/$1.20 per M, AI² Intel 44.4
    "minimax-m2.7":      {"model": "minimax/minimax-m2.7"},      # agentic, reasoning mandatory, $0.25/$1.00, AI² Intel 38.1
    "minimax-m2.5":      {"model": "minimax/minimax-m2.5"},      # coding expert, reasoning mandatory, $0.15/$0.90
    "minimax-m2.1":      {"model": "minimax/minimax-m2.1"},      # lightweight coding, 10B active, $0.29/$0.95
    # minimax-m2.5-free removed — dead endpoint
    "minimax-m2":        {"model": "minimax/minimax-m2"},        # FIXED: was minimax-01 — now real M2, 230B/10B MoE, $0.255/$1.00
    "minimax-m1":        {"model": "minimax/minimax-m1"},        # 1M ctx, lightning attention, $0.40/$2.20
    "minimax-01-legacy": {"model": "minimax/minimax-01"},        # old 456B MiniMax-01 (Jan 2025) — preserved for reference"
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
    "stepfun-3.7-flash":        {"model": "stepfun/step-3.7-flash"},  # hyphenated alias (presets use this form)
    # Nex AGI — free MoE
    "nex-n2-pro-free":     {"model": "nex-agi/nex-n2-pro:free"},  # v3.2: FREE — 17B active/397B total MoE
    # ── NVIDIA Nemotron (via OpenRouter) ──
    # nvidia-nemotron-nano-8b removed — no longer on OpenRouter
    "nemotron-3-ultra-free":      {"model": "nvidia/nemotron-3-ultra-550b-a55b:free"},    # FREE — 550B/55B MoE, 1M ctx, frontier reasoning
    "nemotron-3-super-free":      {"model": "nvidia/nemotron-3-super-120b-a12b:free"},    # FREE — 120B/12B MoE, 1M ctx
    "nemotron-nano-omni-free":    {"model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"}, # FREE — 30B/3B, multimodal reasoning
    "nemotron-nano-30b-free":     {"model": "nvidia/nemotron-3-nano-30b-a3b:free"},       # FREE — 30B/3B MoE
    "nemotron-nano-9b-v2-free":   {"model": "nvidia/nemotron-nano-9b-v2:free"},           # FREE — 9B, unified reasoning
    # Discriminative reranker — returns relevance scores via logprobs, not generated text.
    # Use rerank_via_nemotron() in core/rerank.py; do NOT call via router.call() for text generation.
    "nvidia-nemotron-rerank-vl":  {"model": "nvidia/llama-nemotron-rerank-vl-1b-v2:free"},
    "llama-nemotron-super-49b":   {"model": "nvidia/llama-3.3-nemotron-super-49b-v1.5"},  # $0.40/$0.40 per M, 131K ctx, Llama-based agentic
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
