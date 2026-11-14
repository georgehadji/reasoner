# ═════════════════════════════════════════════════════════════════════
# MODEL ALIASES
# ═════════════════════════════════════════════════════════════════════
# Only aliases something imports. The full catalogue lives in
# infrastructure/llm/registry.py::_MODEL_WHITELIST.

# Anthropic
MODEL_CLAUDE_SONNET: str = "claude-sonnet"
MODEL_CLAUDE_HAIKU: str = "claude-haiku"
# MODEL_GEMINI_PRO removed: its value "gemini-pro" was a registry alias for
# anthropic/claude-sonnet-5, i.e. an exact duplicate of MODEL_CLAUDE_SONNET
# above. Use MODEL_CLAUDE_SONNET.

# xAI — Grok series (grok-4.1-fast, grok-4, grok-3, grok-3-mini removed — EOL)
# Was MODEL_GEMINI_FLASH, whose value v3.6 swapped to xAI without renaming the
# symbol. Every consumer below (captioning, OCR, decomposition, image-gen
# enhancement, the gate default) has been calling Grok while reading "Gemini".
MODEL_GROK_43: str = "grok-4.3"

# OpenAI
MODEL_GPT4O_MINI: str = "gpt-4o-mini"

# Qwen (temperature-supporting, non-OpenAI)
MODEL_QWEN35_FLASH: str = "qwen3.5-flash"
MODEL_QWEN35_9B: str = "qwen3.5-9b"
# MODEL_GEMINI_FLASH_LITE removed: its value "gemini-flash-lite" was a registry
# alias for qwen/qwen3.5-flash-02-23, i.e. an exact duplicate of
# MODEL_QWEN35_FLASH. Use MODEL_QWEN35_FLASH.

# Mistral
MODEL_MISTRAL_SMALL: str = "mistral-small"

# Kimi (MoonshotAI)
MODEL_KIMI_K2_6: str = "kimi-k2-6"

# Baidu
MODEL_QIANFAN_OCR_FAST: str = "qianfan-ocr-fast"

# ── Image generation ──
MODEL_GEMINI_FLASH_IMAGE: str = "gemini-flash-image"
MODEL_GEMINI_PRO_IMAGE: str = "gemini-pro-image"
MODEL_GEMINI_31_FLASH_IMAGE_PREVIEW: str = "gemini-3.1-flash-image-preview"
MODEL_GEMINI_31_FLASH_LITE_IMAGE: str = "gemini-3.1-flash-lite-image"
MODEL_GPT5_IMAGE: str = "gpt-5-image"
MODEL_GPT5_IMAGE_MINI: str = "gpt-5-image-mini"
MODEL_RECRAFT_V41: str = "recraft-v4.1"
MODEL_RECRAFT_V41_PRO: str = "recraft-v4.1-pro"
MODEL_MAI_IMAGE_25: str = "mai-image-2.5"
MODEL_MAI_IMAGE_25_PRO: str = "mai-image-2.5-pro"
MODEL_SEEDREAM_45: str = "seedream-4.5"
MODEL_GROK_IMAGINE_IMAGE_2: str = "grok-imagine-image-2"
MODEL_FLUX_2_KLEIN_4B: str = "flux.2-klein-4b"
MODEL_RIVERFLOW_V25_FAST: str = "riverflow-v2.5-fast"
