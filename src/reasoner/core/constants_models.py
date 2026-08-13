# ═════════════════════════════════════════════════════════════════════
# MODEL ALIASES
# ═════════════════════════════════════════════════════════════════════

MODEL_CLAUDE_SONNET: str = "claude-sonnet"
MODEL_CLAUDE_HAIKU: str = "claude-haiku"
MODEL_GEMINI_FLASH: str = "grok-4.3"  # Swapped to xAI for budget tier (v3.6)
MODEL_GEMINI_PRO: str = "gemini-pro"
MODEL_GPT4O_MINI: str = "gpt-4o-mini"
MODEL_GEMINI_FLASH_IMAGE: str = "gemini-flash-image"
MODEL_GEMINI_PRO_IMAGE: str = "gemini-pro-image"
MODEL_GEMINI_31_FLASH_IMAGE_PREVIEW: str = "gemini-3.1-flash-image-preview"
MODEL_GEMINI_31_FLASH_LITE_IMAGE: str = "gemini-3.1-flash-lite-image"
MODEL_GPT5_IMAGE: str = "gpt-5-image"
MODEL_GPT5_IMAGE_MINI: str = "gpt-5-image-mini"
MODEL_GPT54_IMAGE_2: str = "gpt-5.4-image-2"
# Qwen (Alibaba)
MODEL_QWEN_IMAGE_3: str = "qwen-image-3"
MODEL_QWEN_IMAGE_3_PRO: str = "qwen-image-3-pro"
MODEL_FLUX_2_PRO: str = "flux.2-pro"
MODEL_FLUX_2_FLEX: str = "flux.2-flex"
# Recraft (vector illustration, icons, design)
MODEL_RECRAFT_V4: str = "recraft-v4"
MODEL_RECRAFT_V4_PRO: str = "recraft-v4-pro"
MODEL_RECRAFT_V41: str = "recraft-v4.1"
MODEL_RECRAFT_V41_PRO: str = "recraft-v4.1-pro"
MODEL_RECRAFT_V41_UTILITY: str = "recraft-v4.1-utility"
MODEL_RECRAFT_V41_UTILITY_PRO: str = "recraft-v4.1-utility-pro"
# Grok (xAI)
MODEL_GROK_IMAGINE: str = "grok-imagine"
# Microsoft
MODEL_MAI_IMAGE_25: str = "mai-image-2.5"

# Qwen (temperature-supporting, non-OpenAI)
MODEL_QWEN35_FLASH: str = "qwen3.5-flash"
MODEL_QWEN35_9B: str = "qwen3.5-9b"
MODEL_QWEN36_PLUS: str = "qwen3.6-plus"

# MiniMax (temperature-supporting, non-OpenAI, cross-lab diversity)
MODEL_MINIMAX_M3: str = "minimax-m3"
MODEL_MINIMAX_M27: str = "minimax-m2.7"
MODEL_MINIMAX_M25: str = "minimax-m2.5"
MODEL_MINIMAX_M21: str = "minimax-m2.1"
MODEL_MINIMAX_M2: str = "minimax-m2"
MODEL_MINIMAX_M1: str = "minimax-m1"
# minimax-m2.5-free removed — dead endpoint

# Poolside (temperature-supporting, non-OpenAI, cross-lab diversity)
MODEL_LAGUNA_XS_FREE: str = "laguna-xs-free"
MODEL_LAGUNA_M_FREE: str = "laguna-m-free"
MODEL_LAGUNA_XS_21: str = "laguna-xs-2.1"

# Xiaomi — MiMo series (v2.5, Apr 2026)
MODEL_MIMO_V25_PRO: str = "mimo-v2.5-pro"
MODEL_MIMO_V25: str = "mimo-v2.5"
# Legacy aliases
MODEL_MIMO_V2_PRO: str = "mimo-v2-pro"
MODEL_MIMO_V2_FLASH: str = "mimo-v2-flash"

# DeepSeek (reasoning-effort modes)
# Verified low-latency models: gemini-pro / gemini-flash-lite
MODEL_GEMINI_FLASH_LITE: str = "gemini-flash-lite"
MODEL_MISTRAL_SMALL: str = "mistral-small"

# v3.2 — new ultra-VFM models
MODEL_STEPFUN_37_FLASH: str = "stepfun-3.7-flash"
MODEL_RING_26_1T: str = "ring-2.6-1t"
MODEL_NEX_N2_PRO_FREE: str = "nex-n2-pro-free"
MODEL_NEMOTRON_3_ULTRA_FREE: str = "nemotron-3-ultra-free"

# ── Google Gemini (real models, not aliased) ──
MODEL_GEMINI_PRO_REAL: str = "gemini-pro-real"
MODEL_GEMINI_FLASH_LITE_REAL: str = "gemini-flash-lite-real"
MODEL_GEMINI_25_FLASH_LITE: str = "gemini-2.5-flash-lite"
MODEL_GEMINI_PRO_LATEST: str = "gemini-pro-latest"
MODEL_GEMINI_FLASH_LATEST: str = "gemini-flash-latest"
MODEL_NEMOTRON_3_SUPER_FREE: str = "nemotron-3-super-free"
MODEL_NEMOTRON_NANO_OMNI_FREE: str = "nemotron-nano-omni-free"
MODEL_NEMOTRON_NANO_30B_FREE: str = "nemotron-nano-30b-free"
MODEL_NEMOTRON_NANO_9B_V2_FREE: str = "nemotron-nano-9b-v2-free"
MODEL_LLAMA_NEMOTRON_SUPER_49B: str = "llama-nemotron-super-49b"

# ── Additional model aliases used across the codebase ──
# (added for SSOT — previously hardcoded as raw strings in multiple files)

# Anthropic
MODEL_CLAUDE_OPUS: str = "claude-opus"

# OpenAI — GPT series
MODEL_GPT5: str = "gpt-5"              # → gpt-5.5 (current frontier)
MODEL_GPT55: str = "gpt-5.5"           # AI² Intel 54.8, $5/$30 per M
MODEL_GPT55_PRO: str = "gpt-5.5-pro"   # max reasoning, $30/$180 per M
MODEL_GPT5_MINI: str = "gpt-5-mini"
MODEL_GPT54_NANO: str = "gpt-5.4-nano" # cheapest OpenAI, $0.20/$1.25 per M
MODEL_GPT_LATEST: str = "gpt-latest"    # auto-updating → always latest
MODEL_GPT_MINI_LATEST: str = "gpt-mini-latest"
MODEL_O3: str = "o3"

# Google
MODEL_GEMMA_4_26B: str = "gemma-4-26b"
MODEL_GEMMA_4_31B: str = "gemma-4-31b"
MODEL_GEMMA_2_9B_IT: str = "google/gemma-2-9b-it"

# xAI — Grok series (grok-4.1-fast, grok-4, grok-3, grok-3-mini removed — EOL)
MODEL_GROK_43: str = "grok-4.3"
MODEL_GROK_BUILD_01: str = "grok-build-0.1"

# Mistral
MODEL_MISTRAL_LARGE_3: str = "mistral-large-3"
MODEL_MISTRAL_MEDIUM: str = "mistral-medium"
MODEL_MISTRAL_SMALL_2603: str = "mistral-small-2603"
MODEL_CODESTRAL: str = "codestral"
MODEL_CODESTRAL_2508: str = "codestral-2508"
MODEL_DEVSTRAL: str = "devstral"
MODEL_DEVSTRAL_MEDIUM: str = "devstral-medium"
MODEL_DEVSTRAL_SMALL: str = "devstral-small"
MODEL_MINISTRAL_8B: str = "ministral-8b"

# DeepSeek
MODEL_DEEPSEEK_V4_FLASH: str = "deepseek-v4-flash"
MODEL_DEEPSEEK_V4_PRO: str = "deepseek-v4-pro"

# Qwen
MODEL_QWEN37_MAX: str = "qwen3.7-max"
MODEL_QWEN37_PLUS: str = "qwen3.7-plus"
MODEL_QWEN3_MAX_THINKING: str = "qwen3-max-thinking"
MODEL_QWEN36_FLASH: str = "qwen3.6-flash"
MODEL_QWEN36_35B_A3B: str = "qwen3.6-35b-a3b"
MODEL_QWEN36_27B: str = "qwen3.6-27b"
MODEL_QWEN36_MAX_PREVIEW: str = "qwen3.6-max-preview"
MODEL_QWEN35_27B: str = "qwen3.5-27b"
MODEL_QWEN35_35B_A3B: str = "qwen3.5-35b-a3b"
MODEL_QWEN35_122B_A10B: str = "qwen3.5-122b-a10b"
MODEL_QWEN35_397B_A17B: str = "qwen3.5-397b-a17b"
MODEL_QWEN3_CODER: str = "qwen3-coder"
MODEL_QWEN3_CODER_NEXT: str = "qwen3-coder-next"
MODEL_QWEN3_CODER_FLASH: str = "qwen3-coder-flash"
MODEL_QWEN3_CODER_30B_A3B: str = "qwen3-coder-30b-a3b"

# Kimi (MoonshotAI)
MODEL_KIMI_K2: str = "kimi-k2"
MODEL_KIMI_K2_5: str = "kimi-k2-5"
MODEL_KIMI_K2_6: str = "kimi-k2-6"
MODEL_KIMI_K2_7_CODE: str = "kimi-k2-7-code"
MODEL_KIMI_K3: str = "kimi-k3"

# Tencent
MODEL_HY3: str = "hy3"
MODEL_HY3_PREVIEW: str = "hy3-preview"

# GLM (Zhipu)
MODEL_GLM_5_2: str = "glm-5.2"

# Perplexity
MODEL_SONAR_PRO: str = "sonar-pro"
MODEL_SONAR_PRO_SEARCH: str = "sonar-pro-search"
MODEL_SONAR: str = "sonar"
MODEL_SONAR_REASONING_PRO: str = "sonar-reasoning-pro"
MODEL_SONAR_DEEP_RESEARCH: str = "sonar-deep-research"

# ByteDance
MODEL_SEED_20_MINI: str = "seed-2.0-mini"
MODEL_SEEDREAM_45: str = "seedream-4.5"

# Baidu
MODEL_QIANFAN_OCR_FAST: str = "qianfan-ocr-fast"

# inclusionAI
MODEL_LING_26_FLASH_FREE: str = "ling-2.6-flash-free"

# Meta
MODEL_LLAMA_33_70B: str = "llama-3.3-70b"

# Arcee AI
MODEL_ARCEE_TRINITY_LARGE_THINKING: str = "arcee-trinity-large-thinking"
MODEL_ARCEE_VIRTUOSO_LARGE: str = "arcee-virtuoso-large"
MODEL_ARCEE_MAESTRO_REASONING: str = "arcee-maestro-reasoning"
MODEL_ARCEE_CODER_LARGE: str = "arcee-coder-large"

# OpenRouter
MODEL_OWL_ALPHA: str = "owl-alpha"
MODEL_PARETO_CODE: str = "pareto-code"
MODEL_ELEPHANT_ALPHA: str = "elephant-alpha"

# xAI image
MODEL_GROK_IMAGINE_QUALITY: str = "grok-imagine"

# Black Forest Labs
MODEL_FLUX_2_MAX: str = "flux.2-max"
MODEL_FLUX_2_KLEIN_4B: str = "flux.2-klein-4b"

# Sourceful
MODEL_RIVERFLOW_V2_PRO: str = "riverflow-v2-pro"
MODEL_RIVERFLOW_V2_FAST: str = "riverflow-v2-fast"
MODEL_RIVERFLOW_V2_MAX_PREVIEW: str = "riverflow-v2-max-preview"
MODEL_RIVERFLOW_V2_STANDARD_PREVIEW: str = "riverflow-v2-standard-preview"
MODEL_RIVERFLOW_V2_FAST_PREVIEW: str = "riverflow-v2-fast-preview"

# Thinking Machines
MODEL_INKLING: str = "inkling"

