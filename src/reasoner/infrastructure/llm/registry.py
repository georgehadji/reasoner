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
    MODEL_LAGUNA_XS_21,
    NVIDIA_BASE_URL,
    MODEL_GEMINI_31_FLASH_LITE_IMAGE,
)
from reasoner.infrastructure.llm.providers.openai_compat import (
    OpenAICompatibleProvider,
    OpenRouterProvider,
)


# Whitelist of supported models.  Everything except Ollama routes through OpenRouter.
_MODEL_WHITELIST: dict[str, dict[str, Any]] = {
    # ═══════════════════════════════════════════════════════════════
    # Anthropic
    # ═══════════════════════════════════════════════════════════════
    "claude-fable-5":    {"model": "anthropic/claude-fable-5"},      # ultra-premium creative/synthesis — $10/$50 per M, 1M ctx
    "claude-opus":       {"model": "anthropic/claude-opus-5"},       # v3.7: was opus-4.8 -> opus-5, same $5/$25 per M, 1M ctx, strict upgrade
    "claude-opus-4.8":   {"model": "anthropic/claude-opus-4.8"},     # legacy pin, kept for reproducibility — $5/$25 per M, 1M ctx
    MODEL_CLAUDE_SONNET: {"model": "anthropic/claude-sonnet-5"},     # v3.6: current as of Jun 2026 — $2/$10 per M, 1M ctx
    "claude-haiku":      {"model": "anthropic/claude-haiku-4.5"},    # $1/$5 per M, 200K ctx
    # ═══════════════════════════════════════════════════════════════
    # OpenAI — GPT series
    # ═══════════════════════════════════════════════════════════════
    # ── Current (5.5, Apr 2026) ──
    "gpt-5.5":          {"model": "openai/gpt-5.5"},             # frontier — $5/$30 per M, AI^2 Intel 54.8, 1M ctx
    "gpt-5.5-pro":      {"model": "openai/gpt-5.5-pro"},         # max reasoning — $30/$180 per M, 1M ctx
    # ── GPT-5 base (Mar 2026) — DISTINCT from 5.5 ──
    "gpt-5":            {"model": "openai/gpt-5"},               # $1.25/$10 per M, 400K ctx
    "gpt-5-pro":        {"model": "openai/gpt-5-pro"},           # $15/$120 per M, 400K ctx
    "gpt-5-mini":       {"model": "openai/gpt-5-mini"},          # $0.25/$2 per M, 400K ctx
    "gpt-5-nano":       {"model": "openai/gpt-5-nano"},          # $0.05/$0.40 per M — cheapest OpenAI, ideal Phase 0
    # ── 5.6 (Jul 2026) — tri-tier Sol/Terra/Luna naming, newest OpenAI gen ──
    "gpt-5.6-sol":      {"model": "openai/gpt-5.6-sol"},         # flagship — $5/$30 per M, 1.05M ctx
    "gpt-5.6-terra":    {"model": "openai/gpt-5.6-terra"},       # balanced mid-tier — $1/$6 per M, 1.05M ctx
    "gpt-5.6-luna":     {"model": "openai/gpt-5.6-luna"},        # fast/cheap — $0.10/$0.60 per M, 1.05M ctx
    # ── Previous (5.4, Mar 2026) ──
    "gpt-5.4":          {"model": "openai/gpt-5.4"},             # $2.50/$15 per M, AI^2 Intel 51.4
    "gpt-5.4-pro":      {"model": "openai/gpt-5.4-pro"},         # max reasoning — $30/$180 per M, 1.05M ctx
    "gpt-5.4-mini":     {"model": "openai/gpt-5.4-mini"},        # $0.75/$4.50 per M
    "gpt-5.4-nano":     {"model": "openai/gpt-5.4-nano"},        # $0.20/$1.25 per M
    # ── Open Source (via OpenRouter) ──
    "gpt-oss-120b":     {"model": "openai/gpt-oss-120b"},        # $0.039/$0.18 per M, 131K ctx — ultra-cheap open-weight
    "gpt-oss-20b":      {"model": "openai/gpt-oss-20b"},         # $0.029/$0.14 per M, 131K ctx — cheapest text on OR
    # ── Auto-updating (always latest) ──
    "gpt-latest":       {"model": "~openai/gpt-latest"},         # always -> latest GPT family
    "gpt-mini-latest":  {"model": "~openai/gpt-mini-latest"},    # always -> latest GPT Mini family
    # ── Codex (coding-optimized) ──
    "gpt-5.3-codex":    {"model": "openai/gpt-5.3-codex"},
    "gpt-5.2-codex":    {"model": "openai/gpt-5.2-codex"},
    "gpt-5.1-codex":    {"model": "openai/gpt-5.1-codex"},
    "gpt-5.1-codex-max": {"model": "openai/gpt-5.1-codex-max"},
    "gpt-5.1-codex-mini": {"model": "openai/gpt-5.1-codex-mini"},
    # ── Legacy / Budget ──
    MODEL_GPT4O_MINI:   {"model": "openai/gpt-4o-mini"},         # budget synthesis — proven, cheap, reliable
    # o-series reasoning — no temperature support; can't use for low-temp phases
    "o3":               {"model": "openai/o3"},                  # $2/$8 per M, 200K ctx
    "o3-pro":           {"model": "openai/o3-pro"},               # max reasoning — $20/$80 per M, 200K ctx
    "o3-mini":          {"model": "openai/o3-mini"},
    "o3-mini-high":     {"model": "openai/o3-mini-high"},        # $1.10/$4.40 per M — high-effort variant
    "o4-mini":          {"model": "openai/o4-mini"},             # $1.10/$4.40 per M — cheaper than o3, same reasoning class
    "o4-mini-high":     {"model": "openai/o4-mini-high"},        # $1.10/$4.40 per M — high-effort variant
    # ═══════════════════════════════════════════════════════════════
    # Google — Gemini series
    # ═══════════════════════════════════════════════════════════════
    # gemini-pro -> claude-sonnet (premium primary, not Google — changed v3.4)
    # gemini-flash-lite -> qwen3.5-flash (budget primary, not Google — changed v3.4)
    MODEL_GEMINI_PRO:   {"model": "anthropic/claude-sonnet-5"},     # premium primary (Anthropic, not Google)
    MODEL_GEMINI_FLASH: {"model": "google/gemini-3.5-flash"},       # budget primary — $1.50/$9 per M, AI^2 Intel 50.2, 1M ctx
    "gemini-flash-lite": {"model": "qwen/qwen3.5-flash-02-23"},     # budget primary — $0.065/$0.26, fast & reliable
    # ── Real Google models (not aliased to other labs) ──
    "gemini-pro-real":         {"model": "google/gemini-3.1-pro-preview"},     # true Google Pro — $2/$12 per M, 1M ctx
    "gemini-flash-lite-real":  {"model": "google/gemini-3.1-flash-lite"},      # true Google Flash Lite — $0.25/$1.50, 1M ctx
    "gemini-2.5-flash-lite":   {"model": "google/gemini-2.5-flash-lite"},      # cheapest Google — $0.10/$0.40, 1M ctx
    "gemini-2.5-flash":        {"model": "google/gemini-2.5-flash"},           # $0.30/$2.50 per M, 1M ctx
    "gemini-3.7-flash":        {"model": "google/gemini-3.7-flash"},           # newest Google Flash
    "gemini-3.7-flash-batch":  {"model": "google/gemini-3.7-flash:batch"},      # batch tier of 3.7-flash — cheaper, higher latency; not for interactive phases
    "gemini-3.6-flash":        {"model": "google/gemini-3.6-flash"},           # newer than budget primary — $1.50/$7.50 per M, 1M ctx
    "gemini-3.5-flash-lite":   {"model": "google/gemini-3.5-flash-lite"},      # $0.30/$2.50 per M, 1M ctx
    # ── Auto-updating (always latest) ──
    "gemini-pro-latest":       {"model": "~google/gemini-pro-latest"},         # always -> latest Gemini Pro
    "gemini-flash-latest":     {"model": "~google/gemini-flash-latest"},       # always -> latest Gemini Flash
    # ── Legacy ──
    "gemini-3.1-flash-lite":   {"model": "google/gemini-3.1-flash-lite"},      # -> gemini-flash-lite-real
    "google/gemma-2-9b-it":    {"model": "google/gemma-3-12b-it"},
    "gemma-4-26b":             {"model": "google/gemma-4-26b-a4b-it"},
    "gemma-4-31b":             {"model": "google/gemma-4-31b-it"},
    # ═══════════════════════════════════════════════════════════════
    # xAI — Grok series
    # ═══════════════════════════════════════════════════════════════
    "grok-4.5":               {"model": "x-ai/grok-4.5"},               # 500K ctx, $2/$6 per M, frontier reasoning, structured outputs (updated Jul 2026)
    "grok-4.3":               {"model": "x-ai/grok-4.3"},               # 1M ctx, $1.25/$2.50, τ²-Bench 97.7%, configurable reasoning effort
    "grok-build-0.1":         {"model": "x-ai/grok-build-0.1"},         # fast agentic coding, 256K ctx, $1.00/$2.00
    # ═══════════════════════════════════════════════════════════════
    # Perplexity
    # ═══════════════════════════════════════════════════════════════
    "sonar-pro":          {"model": "perplexity/sonar-pro",        "extra_body": {"web_search_options": {"search_context_size": "high"}, "search_domain_filter": ["-reddit.com","-facebook.com","-pinterest.com","-quora.com"], "search_recency_filter": "year", "return_sources": True}},
    "sonar-pro-search":   {"model": "perplexity/sonar-pro-search",  "extra_body": {"web_search_options": {"search_context_size": "high"}, "search_domain_filter": ["-reddit.com","-facebook.com","-pinterest.com","-quora.com"], "search_recency_filter": "year", "return_sources": True}},
    "sonar":              {"model": "perplexity/sonar",              "extra_body": {"web_search_options": {"search_context_size": "low"}, "search_domain_filter": ["-reddit.com","-facebook.com","-pinterest.com","-quora.com"], "search_recency_filter": "year", "return_sources": True}},
    "sonar-reasoning-pro":  {"model": "perplexity/sonar-reasoning-pro",  "extra_body": {"web_search_options": {"search_context_size": "high"}, "search_domain_filter": ["-reddit.com","-facebook.com","-pinterest.com","-quora.com"], "search_recency_filter": "month", "return_sources": True, "return_images": True, "return_related_questions": True}},
    "sonar-deep-research":  {"model": "perplexity/sonar-deep-research",  "extra_body": {"reasoning_effort": "high", "search_domain_filter": ["-reddit.com","-facebook.com","-pinterest.com","-quora.com"], "search_recency_filter": "month", "return_sources": True, "return_images": True, "return_related_questions": True}},
    # ═══════════════════════════════════════════════════════════════
    # Mistral
    # ═══════════════════════════════════════════════════════════════
    "mistral-large-3":    {"model": "mistralai/mistral-large-2512"},
    "mistral-medium":     {"model": "mistralai/mistral-medium-3.1"},
    "mistral-medium-3-5": {"model": "mistralai/mistral-medium-3-5"},    # $1.50/$7.50 per M, 262K ctx — newer mid tier
    "mistral-small":      {"model": "mistralai/mistral-small-2603"},    # v3.3: $0.15/$0.60 per M, 262K ctx
    "mistral-small-2603": {"model": "mistralai/mistral-small-2603"},    # explicit alias for preset pinning
    "codestral":          {"model": "mistralai/codestral-2508"},        # v3.5: was 2501 (dead) -> 2508
    "codestral-2508":     {"model": "mistralai/codestral-2508"},
    "ministral-8b":       {"model": "mistralai/mistral-small-3.2-24b-instruct"},
    "ministral-3b":       {"model": "mistralai/ministral-3b-2512"},   # $0.10/$0.10 flat, 131K ctx — real Ministral tier
    "ministral-14b":      {"model": "mistralai/ministral-14b-2512"},  # $0.20/$0.20 flat, 262K ctx — real Ministral tier
    # devstral, devstral-medium, devstral-small removed — no longer on OpenRouter
    # ═══════════════════════════════════════════════════════════════
    # DeepSeek — V3.2 + V4 family
    # ═══════════════════════════════════════════════════════════════
    # V4 family: 1M ctx, MoE
    #   Pro:   1.6T total / 49B active — $0.435/$0.87  per M
    #   Flash: 284B total / 13B active — $0.09/$0.18   per M — PRIMARY budget choice
    "deepseek-v4-pro": {
        "cls": "compat",
        "model": "deepseek/deepseek-v4-pro",
        "base": "https://api.deepseek.com/v1",
        "env": "DEEPSEEK_API_KEY",
        "extra_body": {"reasoning": {"effort": "high"}},
    },
    "deepseek-v4-flash": {
        "cls": "compat",
        "model": "deepseek/deepseek-v4-flash-0731",   # was undated pin -> 0731 re-post-trained revision, same $0.14/$0.28, 1M ctx
        "base": "https://api.deepseek.com/v1",
        "env": "DEEPSEEK_API_KEY",
        "extra_body": {"reasoning": {"effort": "high"}},
    },
    "deepseek-v4-flash-0424": {
        "cls": "compat",
        "model": "deepseek/deepseek-v4-flash",        # legacy pin, kept for reproducibility — $0.14/$0.28, 1M ctx
        "base": "https://api.deepseek.com/v1",
        "env": "DEEPSEEK_API_KEY",
        "extra_body": {"reasoning": {"effort": "high"}},
    },
    # Re-pointed to v4-flash: v3.2 deprecated, DeepSeek API no longer accepts it.
    "deepseek-v3": {
        "cls": "compat",
        "model": "deepseek/deepseek-v4-flash",        # was v3.2 ($0.12/$0.50) — re-pointed Jun 2026
        "base": "https://api.deepseek.com/v1",
        "env": "DEEPSEEK_API_KEY",
    },
    # ═══════════════════════════════════════════════════════════════
    # Qwen (Alibaba) — 3.5 -> 3.8 series
    # ═══════════════════════════════════════════════════════════════
    # ── 3.8 (latest) ──
    "qwen3.8-max":         {"model": "qwen/qwen3.8-max"},        # newest flagship
    # ── 3.7 (Jun 2026) ──
    "qwen3.7-max":         {"model": "qwen/qwen3.7-max"},        # flagship agent — $1.25/$3.75 per M, 1M ctx
    "qwen3.7-plus":        {"model": "qwen/qwen3.7-plus"},       # best VFM — $0.32/$1.28 per M, 1M ctx
    "qwen3.7-flash":       {"model": "qwen/qwen3.7-flash"},      # cheapest Qwen — $0.03/$0.13 per M, 1M ctx, vision
    # ── 3.7 value aliases (intentionally route to 3.7-plus for cost) ──
    "qwen3-max":           {"model": "qwen/qwen3.7-plus"},       # "max" alias -> 3.7-plus ($0.32/$1.28)
    "qwen3-max-real":      {"model": "qwen/qwen3-max"},          # literal qwen3-max — $0.78/$3.90 per M, 262K ctx (older arch, costlier than the alias above)
    "qwen3.6-plus":        {"model": "qwen/qwen3.7-plus"},       # alias -> 3.7-plus (cheaper AND stronger than real 3.6-plus)
    "qwen3-plus":          {"model": "qwen/qwen3.7-plus"},       # generic "plus" -> best plus
    "qwen3.5-plus":        {"model": "qwen/qwen3.7-plus"},       # 3.5-plus legacy -> 3.7-plus
    # ── 3.6 (mid 2026) ──
    "qwen3.6-plus-real":   {"model": "qwen/qwen3.6-plus"},       # real 3.6-plus — $0.325/$1.95 per M, 1M ctx
    "qwen3.6-flash":       {"model": "qwen/qwen3.6-flash"},      # $0.1875/$1.125 per M, 1M ctx
    "qwen3.6-35b-a3b":     {"model": "qwen/qwen3.6-35b-a3b"},    # $0.14/$1.00 per M, 262K ctx, open-weight
    "qwen3.6-27b":         {"model": "qwen/qwen3.6-27b"},        # $0.2885/$3.17 per M, 262K ctx, dense
    "qwen3.6-max-preview": {"model": "qwen/qwen3.6-max-preview"}, # $1.04/$6.24 per M, 262K ctx, ~1T MoE preview
    # ── 3.5 (early-mid 2026) ──
    "qwen3.5-flash":       {"model": "qwen/qwen3.5-flash-02-23"}, # cheapest Qwen — $0.065/$0.26 per M, 1M ctx
    "qwen3.5-9b":          {"model": "qwen/qwen3.5-9b"},          # $0.10/$0.15 per M, 262K ctx
    "qwen3.5-27b":         {"model": "qwen/qwen3.5-27b"},         # $0.195/$1.56 per M, 262K ctx, dense
    "qwen3.5-35b-a3b":     {"model": "qwen/qwen3.5-35b-a3b"},     # $0.14/$1.00 per M, 262K ctx, MoE
    "qwen3.5-122b-a10b":   {"model": "qwen/qwen3.5-122b-a10b"},   # $0.26/$2.08 per M, 262K ctx, MoE
    "qwen3.5-397b-a17b":   {"model": "qwen/qwen3.5-397b-a17b"},   # $0.385/$2.45 per M, 256K ctx, MoE
    # ── Qwen3 large open-weight ──
    "qwen3-235b-a22b":     {"model": "qwen/qwen3-235b-a22b"},      # $0.455/$1.82 per M, 131K ctx, large MoE
    "qwen3-30b-a3b":       {"model": "qwen/qwen3-30b-a3b"},        # $0.12/$0.50 per M, 131K ctx, compact MoE
    # ── Qwen3 Max Thinking — dedicated reasoning (Jan 2026) ──
    "qwen3-max-thinking":  {"model": "qwen/qwen3-max-thinking"},   # $0.78/$3.90 per M, 262K ctx — deep multi-step reasoning
    # ── Turbo (dead — replaced with 3.5-flash) ──
    "qwen3-turbo":         {"model": "qwen/qwen3.5-flash-02-23"},  # was qwen/qwen-turbo (DEAD) -> qwen3.5-flash
    # ── Coder series ──
    "qwen3-coder":            {"model": "qwen/qwen3-coder-plus"},        # proprietary — $0.65/$3.25 per M, 1M ctx
    "qwen3-coder-flash":      {"model": "qwen/qwen3-coder-flash"},       # $0.195/$0.975 per M, 1M ctx
    "qwen3-coder-next":       {"model": "qwen/qwen3-coder-next"},        # open-weight — $0.11/$0.80 per M, 262K ctx
    "qwen3-coder-30b-a3b":    {"model": "qwen/qwen3-coder-30b-a3b-instruct"}, # cheapest coder — $0.07/$0.27 per M, 160K ctx
    # ═══════════════════════════════════════════════════════════════
    # Kimi (Moonshot AI)
    # ═══════════════════════════════════════════════════════════════
    "kimi-k2":          {"model": "moonshotai/kimi-k2"},           # $0.57/$2.30 per M, 131K ctx
    "kimi-k2-5":        {"model": "moonshotai/kimi-k2.5"},
    "kimi-k2-6":        {"model": "moonshotai/kimi-k2.6"},
    "kimi-k2-7-code":   {"model": "moonshotai/kimi-k2.7-code"},
    "kimi-k3":          {"model": "moonshotai/kimi-k3"},           # 1M ctx, advanced agentic reasoning
    "kimi-k2-thinking":  {"model": "moonshotai/kimi-k2-thinking"},    # Nov 2025, older than k2.5+ but the only dedicated reasoning-mode Kimi — $0.60/$2.50 per M, 262K ctx
    # ═══════════════════════════════════════════════════════════════
    # Meta LLaMA
    # ═══════════════════════════════════════════════════════════════
    "llama-4-scout":    {"model": "meta-llama/llama-4-scout"},     # $0.10/$0.30 per M, 10M ctx — best long-context VFM
    "llama-4-maverick": {"model": "meta-llama/llama-4-maverick"},  # $0.15/$0.60 per M, 1M ctx
    "muse-spark-1.1":   {"model": "meta/muse-spark-1.1"},          # small multimodal/general model
    "llama-3.3-70b":    {"model": "meta-llama/llama-3.3-70b-instruct"},  # $0.13/$0.40 per M, 131K ctx — workhorse open-weight
    # ═══════════════════════════════════════════════════════════════
    # Laguna (Poolside)
    # ═══════════════════════════════════════════════════════════════
    MODEL_LAGUNA_XS_FREE: {"model": "poolside/laguna-xs-2.1:free"},  # was laguna-xs.2:free (dead) -> vendor rebumped to xs-2.1:free
    MODEL_LAGUNA_M_FREE:  {"model": "poolside/laguna-s-2.1:free"},   # was laguna-m.1:free (dead) -> M tier discontinued, vendor replaced with S tier free
    MODEL_LAGUNA_XS_21:   {"model": "poolside/laguna-xs-2.1"},  # $0.06/$0.12 per M, 262K ctx — Poolside coding agent (Jul '26)
    "laguna-s-2.1":       {"model": "poolside/laguna-s-2.1"},   # $0.09/$0.18 per M, 1M ctx — new S tier, between XS and M
    # ═══════════════════════════════════════════════════════════════
    # GLM (Zhipu AI / z-ai)
    # ═══════════════════════════════════════════════════════════════
    "glm-5.2":          {"model": "z-ai/glm-5.2"},                # $0.95/$3.00 per M, 1M ctx
    # ═══════════════════════════════════════════════════════════════
    # OpenRouter native
    # ═══════════════════════════════════════════════════════════════
    # elephant-alpha removed — no longer on OpenRouter
    # owl-alpha removed — openrouter/owl-alpha dead, no replacement on OpenRouter
    "pareto-code":      {"model": "openrouter/pareto-code"},
    # ═══════════════════════════════════════════════════════════════
    # Arcee AI
    # ═══════════════════════════════════════════════════════════════
    # arcee-maestro-reasoning removed — no longer on OpenRouter
    "arcee-trinity-large-thinking": {"model": "arcee-ai/trinity-large-thinking"},
    "arcee-virtuoso-large":         {"model": "arcee-ai/virtuoso-large"},
    # arcee-coder-large removed — arcee-ai/coder-large dead, no replacement on OpenRouter
    # ═══════════════════════════════════════════════════════════════
    # Xiaomi — MiMo series (v2.5, Apr 2026)
    # ═══════════════════════════════════════════════════════════════
    "mimo-v2.5-pro":  {"model": "xiaomi/mimo-v2.5-pro"},   # flagship agent — $0.435/$0.87 per M, 1M ctx
    "mimo-v2.5":      {"model": "xiaomi/mimo-v2.5"},       # omnimodal value — $0.14/$0.28 per M, 1M ctx
    # Legacy aliases (presets may reference these)
    "mimo-v2-pro":    {"model": "xiaomi/mimo-v2.5-pro"},
    "mimo-v2-flash":  {"model": "xiaomi/mimo-v2.5"},
    # ═══════════════════════════════════════════════════════════════
    # MiniMax — M-series
    # ═══════════════════════════════════════════════════════════════
    "minimax-m3":        {"model": "minimax/minimax-m3"},        # latest, 1M ctx, multimodal, $0.30/$1.20 per M
    "minimax-m2.7":      {"model": "minimax/minimax-m2.7"},      # agentic, reasoning mandatory, $0.25/$1.00
    "minimax-m2.5":      {"model": "minimax/minimax-m2.5"},      # coding expert, reasoning mandatory, $0.15/$0.90
    "minimax-m2.1":      {"model": "minimax/minimax-m2.1"},      # lightweight coding, 10B active, $0.29/$0.95
    "minimax-m2":        {"model": "minimax/minimax-m2"},        # 230B/10B MoE, $0.255/$1.00
    "minimax-m1":        {"model": "minimax/minimax-m1"},        # 1M ctx, lightning attention, $0.40/$2.20
    "minimax-01-legacy": {"model": "minimax/minimax-01"},        # old 456B MiniMax-01 (Jan 2025) — preserved for reference
    # ═══════════════════════════════════════════════════════════════
    # Thinking Machines Lab
    # ═══════════════════════════════════════════════════════════════
    "inkling-small":    {"model": "thinkingmachines/inkling-small"},  # 276B/12B MoE multimodal — $0.50/$1.20 per M, 512K ctx
    # ═══════════════════════════════════════════════════════════════
    # Tencent
    # ═══════════════════════════════════════════════════════════════
    "hy3":               {"model": "tencent/hy3"},               # 295B MoE (21B active, 192 experts, top-8), 262K ctx, $0.20/$0.80 per M, configurable reasoning effort (none/low/high CoT), anti-hallucination — answers grounded, flags missing evidence
    "hy3-preview":      {"model": "tencent/hy3-preview"},
    # ═══════════════════════════════════════════════════════════════
    # ByteDance Seed
    # ═══════════════════════════════════════════════════════════════
    "seed-2.0-mini":    {"model": "bytedance-seed/seed-2.0-mini"},  # $0.10/$0.40 per M, 262K ctx
    "seed-2.0-lite":    {"model": "bytedance-seed/seed-2.0-lite"},  # $0.25/$2.00 per M, 262K ctx — mid tier, same gen
    # ═══════════════════════════════════════════════════════════════
    # inclusionAI (Ant Group)
    # ═══════════════════════════════════════════════════════════════
    "ling-2.6-flash-free": {"model": "inclusionai/ling-2.6-flash"},  # v3.5: :free tier dead -> paid non-free model
    "ling-3.0-flash-free": {"model": "inclusionai/ling-3.0-flash:free"},  # FREE — newest gen; :free tiers on this vendor have died before, watch for drift
    "ring-2.6-1t":         {"model": "inclusionai/ring-2.6-1t"},     # $0.075/$0.625 per M, 63B active/1T total, thinking model
    "ling-2.6-1t":         {"model": "inclusionai/ling-2.6-1t"},     # $0.075/$0.625 per M, general-purpose counterpart to ring-2.6-1t (non-reasoning)
    # ═══════════════════════════════════════════════════════════════
    # StepFun — ultra-cheap multimodal MoE
    # ═══════════════════════════════════════════════════════════════
    "stepfun/step-3.7-flash":   {"model": "stepfun/step-3.7-flash"},  # $0.20/$1.15 per M — 196B MoE, 11B active
    "stepfun-3.7-flash":        {"model": "stepfun/step-3.7-flash"},  # hyphenated alias (presets use this form)
    # ═══════════════════════════════════════════════════════════════
    # Nex AGI — MoE
    # ═══════════════════════════════════════════════════════════════
    "nex-n2-pro-free":   {"model": "nex-agi/nex-n2-pro"},           # v3.5: :free tier dead -> paid, $0.25/$1.00 per M
    # ═══════════════════════════════════════════════════════════════
    # Nous Research — Hermes series
    # ═══════════════════════════════════════════════════════════════
    "hermes-4-405b":     {"model": "nousresearch/hermes-4-405b"},   # $1.00/$3.00 per M, 131K ctx — powerful critic
    "hermes-4-70b":      {"model": "nousresearch/hermes-4-70b"},    # $0.13/$0.40 per M, 131K ctx
    # ═══════════════════════════════════════════════════════════════
    # Thinking Machines
    # ═══════════════════════════════════════════════════════════════
    "inkling":          {"model": "thinkingmachines/inkling"},      # $1/$4.05 per M, 1M ctx, 41B active/975B MoE
    # ═══════════════════════════════════════════════════════════════
    # Morph — coding specialists
    # ═══════════════════════════════════════════════════════════════
    "morph-v3-large":    {"model": "morph/morph-v3-large"},         # $0.90/$1.90 per M, 262K ctx
    "morph-v3-fast":     {"model": "morph/morph-v3-fast"},          # $0.80/$1.20 per M, 81K ctx
    # ═══════════════════════════════════════════════════════════════
    # NVIDIA Nemotron (via OpenRouter)
    # ═══════════════════════════════════════════════════════════════
    # nvidia-nemotron-nano-8b removed — no longer on OpenRouter
    # nvidia/llama-nemotron-rerank-vl-1b-v2:free removed — dead endpoint
    "nemotron-3-ultra-free":      {"model": "nvidia/nemotron-3-ultra-550b-a55b:free"},    # FREE — 550B/55B MoE, 1M ctx, frontier reasoning
    "nemotron-3-super-free":      {"model": "nvidia/nemotron-3-super-120b-a12b:free"},    # FREE — 120B/12B MoE, 1M ctx
    "nemotron-nano-omni-free":    {"model": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"}, # FREE — 30B/3B, multimodal reasoning
    "nemotron-nano-30b-free":     {"model": "nvidia/nemotron-3-nano-30b-a3b:free"},       # FREE — 30B/3B MoE
    "nemotron-nano-30b":          {"model": "nvidia/nemotron-3-nano-30b-a3b"},            # paid fallback for the :free tier above — $0.05/$0.20 per M
    "nemotron-3-ultra":           {"model": "nvidia/nemotron-3-ultra-550b-a55b"},         # paid fallback for nemotron-3-ultra-free — $0.60/$3.60 per M, 512K ctx
    "nemotron-nano-9b-v2-free":   {"model": "nvidia/nemotron-nano-9b-v2:free"},           # FREE — 9B, unified reasoning
    # llama-nemotron-super-49b removed — dead pin, redundant with nemotron-3-super pins above
    # NVIDIA NIM (direct, not via OpenRouter)
    "nvidia-nemotron-super": {
        "cls": "compat",
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "base": NVIDIA_BASE_URL,
        "env": "NVIDIA_API_KEY",
    },
    # ═══════════════════════════════════════════════════════════════
    # Image generation models (OpenRouter multimodal image output)
    # ═══════════════════════════════════════════════════════════════
    # Removed: black-forest-labs/flux.* (all 4 models) — provider gone from OpenRouter
    # Removed: sourceful/riverflow-v2-* (all 5 models) — provider gone from OpenRouter
    # Removed: bytedance-seed/seedream-4.5 — not on OpenRouter
    # Removed: x-ai/grok-imagine-image-quality — not on OpenRouter
    # Removed: microsoft/mai-image-2.5 — not on OpenRouter
    # Removed: recraft/recraft-v4* (all 8 models) — provider gone from OpenRouter
    "gemini-flash-image":             {"model": "google/gemini-2.5-flash-image",      "extra_body": {"include_images": True}},
    "gemini-pro-image":               {"model": "google/gemini-3-pro-image-preview",  "extra_body": {"include_images": True}},
    "gemini-3.1-flash-image-preview": {"model": "google/gemini-3.1-flash-image-preview", "extra_body": {"include_images": True}},
    MODEL_GEMINI_31_FLASH_LITE_IMAGE: {"model": "google/gemini-3.1-flash-lite-image", "extra_body": {"include_images": True}},
    "gpt-5-image":                    {"model": "openai/gpt-5-image",       "extra_body": {"include_images": True}},
    "gpt-5-image-mini":               {"model": "openai/gpt-5-image-mini",  "extra_body": {"include_images": True}},
    "gpt-5.4-image-2":                {"model": "openai/gpt-5.4-image-2",   "extra_body": {"include_images": True}},
    "qwen-image-3":                   {"model": "qwen/qwen-image-3",        "extra_body": {"include_images": True}},
    "qwen-image-3-pro":               {"model": "qwen/qwen-image-3-pro",    "extra_body": {"include_images": True}},
    # ═══════════════════════════════════════════════════════════════
    # Ollama (local)
    # ═══════════════════════════════════════════════════════════════
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
    
    # xAI direct routing logic
    is_xai = model_id.startswith("grok-") or _vendor_of(model_id) == "x-ai"
    using_xai_direct = False
    
    key = api_key
    if is_xai and not key:
        xai_key = os.environ.get("XAI_API_KEY", "")
        if xai_key:
            key = xai_key
            using_xai_direct = True

    # DeepSeek direct routing logic (try DEEPSEEK_API_KEY first, fall back to OpenRouter)
    is_deepseek = model_id.startswith("deepseek-") or _vendor_of(model_id) == "deepseek"
    using_deepseek_direct = False

    if is_deepseek and not key and not using_xai_direct:
        ds_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if ds_key:
            key = ds_key
            using_deepseek_direct = True
            
    if not key:
        key = os.environ.get(cfg["env"], "")

    if not key and not cfg.get("is_local"):
        raise ValueError(
            f"API key for '{model_id}' is not set. "
            f"Set the {cfg['env']} environment variable."
        )

    if using_xai_direct:
        direct_model = cfg["model"].lstrip("~").replace("x-ai/", "")
        return OpenAICompatibleProvider(
            model=direct_model,
            api_key=key,
            base_url="https://api.x.ai/v1",
            extra_body=cfg.get("extra_body"),
        )

    if using_deepseek_direct:
        direct_model = cfg["model"].lstrip("~").replace("deepseek/", "")
        return OpenAICompatibleProvider(
            model=direct_model,
            api_key=key,
            base_url="https://api.deepseek.com/v1",
            extra_body=cfg.get("extra_body"),
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


# ══════════════════════════════════════════════════════════════════════════
# Geopolitical training bloc
# ══════════════════════════════════════════════════════════════════════════
# Buyl et al. (npj AI 2026, "LLMs reflect the ideology of their creators") show
# the creator's geopolitical bloc is the dominant axis of an LLM's ideological
# bias. "Cross-lab diversity" at the *company* level (e.g. DeepSeek vs Qwen) does
# NOT buy ideological diversity when both labs sit in the same bloc. We therefore
# map every vendor to a bloc and enforce cross-*bloc* spread in the consequential
# pipeline roles (generation, synthesis, scoring) so no single bloc owns the
# result. The paper also identifies Russian and Arabic blocs; no frontier model
# from those blocs is currently routable via OpenRouter, so achievable diversity
# here spans US, CN, and EU.
_VENDOR_BLOC: dict[str, str] = {
    # United States / Western
    "anthropic": "US", "openai": "US", "google": "US", "x-ai": "US",
    "perplexity": "US", "meta-llama": "US", "meta": "US", "poolside": "US", "arcee-ai": "US",
    "nvidia": "US", "nousresearch": "US", "thinkingmachines": "US", "morph": "US",
    # China
    "deepseek": "CN", "qwen": "CN", "moonshotai": "CN", "z-ai": "CN",
    "xiaomi": "CN", "tencent": "CN", "bytedance-seed": "CN", "inclusionai": "CN",
    "stepfun": "CN", "minimax": "CN", "baidu": "CN",
    # European Union
    "mistralai": "EU",
}


def _vendor_of(model_id: str) -> str:
    """Resolve a whitelist model ID to its underlying OpenRouter vendor prefix.

    Resolution goes through the registry's actual ``model`` string, never the
    alias, because several aliases route cross-vendor (e.g. ``gemini-pro`` →
    Anthropic, ``gemini-flash-lite`` → Qwen).
    """
    cfg = _REGISTRY.get(model_id) or _MODEL_WHITELIST.get(model_id) or {}
    model = str(cfg.get("model", model_id)).lstrip("~")
    return model.split("/", 1)[0] if "/" in model else model


def bloc_of(model_id: str) -> str:
    """Return the geopolitical training bloc for a model ID.

    One of ``"US"``, ``"CN"``, ``"EU"``, or ``"OTHER"`` (unknown/stealth vendors).
    """
    return _VENDOR_BLOC.get(_vendor_of(model_id), "OTHER")


def resolved_model_of(model_id: str) -> str:
    """Resolve a whitelist model ID to the exact underlying model string.

    Unlike ``_vendor_of`` (vendor prefix only), this returns the full
    ``vendor/model`` string so callers can detect two differently-named
    aliases silently pointing at the identical served model (e.g.
    ``gemini-pro`` and ``claude-sonnet`` both resolving to
    ``anthropic/claude-sonnet-5``).
    """
    cfg = _REGISTRY.get(model_id) or _MODEL_WHITELIST.get(model_id) or {}
    return str(cfg.get("model", model_id)).lstrip("~")
