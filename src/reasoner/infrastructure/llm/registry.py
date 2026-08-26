"""Model registry and provider factory."""

from __future__ import annotations

import os
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from reasoner.infrastructure.llm.base import BaseLLMProvider

from reasoner.core.constants import (
    DEFAULT_OLLAMA_URL,
    MODEL_CLAUDE_SONNET,
    MODEL_GEMINI_31_FLASH_LITE_IMAGE,
    MODEL_GEMINI_PRO,
    MODEL_GPT4O_MINI,
    MODEL_LAGUNA_M_FREE,
    MODEL_LAGUNA_XS_21,
    MODEL_LAGUNA_XS_FREE,
    NVIDIA_BASE_URL,
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
    # ── Auto-updating (always latest) ──
    "claude-opus-latest":   {"model": "~anthropic/claude-opus-latest"},    # always -> latest Opus ($5/$25, 1M ctx today)
    "claude-sonnet-latest": {"model": "~anthropic/claude-sonnet-latest"},  # always -> latest Sonnet ($2/$10, 1M ctx today)
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
    "gpt-5.6-luna":     {"model": "openai/gpt-5.6-luna"},        # fast/cheap — $0.20/$1.20 per M, 1.05M ctx, AA Intel 51.2 — default synthesis voice
    # -pro siblings are priced identically to the base tiers on OpenRouter, so they
    # are a free capability upgrade wherever the base tier is already being used.
    "gpt-5.6-sol-pro":   {"model": "openai/gpt-5.6-sol-pro"},    # $5/$30 per M, 1.05M ctx
    "gpt-5.6-terra-pro": {"model": "openai/gpt-5.6-terra-pro"},  # $1/$6 per M, 1.05M ctx
    "gpt-5.6-luna-pro":  {"model": "openai/gpt-5.6-luna-pro"},   # $0.20/$1.20 per M, 1.05M ctx
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
    # No MODEL_GEMINI_FLASH entry here: v3.6 swapped that alias's *value* to
    # "grok-4.3" without renaming it, so an entry keyed on the constant was a
    # duplicate of the literal "grok-4.3" key in the xAI block below. The later
    # key won, this one's google/gemini-3.5-flash value was silently discarded,
    # and the dict quietly had one fewer model than it appeared to. The xAI
    # block is the single definition; a real Google flash lives under
    # gemini-3.6-flash / gemini-2.5-flash.
    "gemini-flash-lite": {"model": "qwen/qwen3.5-flash-02-23"},     # budget primary — $0.065/$0.26, fast & reliable
    # ── Real Google models (not aliased to other labs) ──
    "gemini-pro-real":         {"model": "google/gemini-3.1-pro-preview"},     # true Google Pro — $2/$12 per M, 1M ctx
    "gemini-flash-lite-real":  {"model": "google/gemini-3.1-flash-lite"},      # true Google Flash Lite — $0.25/$1.50, 1M ctx
    "gemini-2.5-flash-lite":   {"model": "google/gemini-2.5-flash-lite"},      # cheapest Google — $0.10/$0.40, 1M ctx
    "gemini-2.5-flash":        {"model": "google/gemini-2.5-flash"},           # $0.30/$2.50 per M, 1M ctx
    "gemini-3.7-flash":        {"model": "google/gemini-3.7-flash"},           # newest Google flash — $0.375/$1.875 per M, 1M ctx (half the price of 3.6-flash)
    "gemini-3.6-flash":        {"model": "google/gemini-3.6-flash"},           # $0.75/$3.75 per M, 1M ctx (repriced down from $1.50/$7.50)
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
    "grok-4.6":               {"model": "x-ai/grok-4.6"},               # newest Grok — 500K ctx, $2/$6 per M (same price as 4.5, strict upgrade)
    "grok-4.5":               {"model": "x-ai/grok-4.5"},               # 500K ctx, $2/$6 per M, frontier reasoning, structured outputs (updated Jul 2026)
    # grok-4.20 / grok-4.20-multi-agent removed 2026-08-20 (still live upstream,
    # deliberately not routable here). The 18 verifier slots they held now use
    # grok-4.3 — same $1.25/$2.50, 1M ctx instead of 2M. Do not re-add from the
    # catalogue snapshot: openrouter_models.json still lists them because it
    # mirrors upstream, and that is not a signal to reinstate the alias.
    "grok-4.3":               {"model": "x-ai/grok-4.3"},               # 1M ctx, $1.25/$2.50, τ²-Bench 97.7%, configurable reasoning effort
    "grok-build-0.1":         {"model": "x-ai/grok-build-0.1"},         # fast agentic coding, 256K ctx, $1.00/$2.00
    "grok-latest":            {"model": "~x-ai/grok-latest"},           # always -> latest Grok ($2/$6, 500K ctx today)
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
    "mistral-large-3":    {"model": "mistralai/mistral-large-2512"},  # $0.50/$1.50 per M, 262K ctx — cheapest EU-bloc frontier anchor
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
    # V4 family: 1M ctx, MoE.  Prices below are the OpenRouter list prices (the
    # fallback lane when DEEPSEEK_API_KEY is unset); DeepSeek's own API is cheaper.
    #   Pro:   1.6T total / 49B active — $0.66/$1.98 per M per the bundled catalogue
    #          (2026-08-16). Earlier comments said $0.435/$0.87 and the Aug catalogue doc
    #          said $1.168/$2.336 — this model's list price has moved repeatedly, so
    #          re-check the snapshot before costing the 23 preset slots that use it.
    #   Flash: 284B total / 13B active — $0.0615/$0.1229 per M — PRIMARY budget choice
    # No "cls"/"base"/"env" override on any of these four: leaving them plain
    # ("model" [+ "extra_body"] only) lets the _MODEL_WHITELIST -> _REGISTRY
    # build below setdefault them to cls="openrouter" / env="OPENROUTER_API_KEY",
    # exactly like every other non-local entry -- OpenRouter is "the fallback
    # lane when DEEPSEEK_API_KEY is unset" per the price comment above, and
    # build_provider()'s "DeepSeek direct routing" branch already hardcodes its
    # own https://api.deepseek.com/v1 base_url and its own DEEPSEEK_API_KEY
    # lookup, so it needs neither field from here. A prior "cls": "compat" +
    # explicit "base"/"env": "DEEPSEEK_API_KEY" on these entries pinned every
    # one of them to direct-DeepSeek-only, so build_provider() raised whenever
    # only OPENROUTER_API_KEY was configured (the common case in CI/dev) —
    # e.g. PresetService.filter_routing() had to downgrade these roles to
    # primary_id to route around it. Restoring the plain shape restores the
    # documented fallback instead of routing around its absence.
    "deepseek-v4-pro": {
        "model": "deepseek/deepseek-v4-pro",
        "extra_body": {"reasoning": {"effort": "high"}},
    },
    "deepseek-v4-flash": {
        # The 0731 dated pin was retired upstream: api.deepseek.com now accepts
        # only deepseek-v4-pro / deepseek-v4-flash and 400s on any dated suffix.
        "model": "deepseek/deepseek-v4-flash",        # $0.0615/$0.1229, 1M ctx
        "extra_body": {"reasoning": {"effort": "high"}},
    },
    "deepseek-v4-flash-0424": {
        "model": "deepseek/deepseek-v4-flash",        # legacy pin, kept for reproducibility — $0.14/$0.28, 1M ctx
        "extra_body": {"reasoning": {"effort": "high"}},
    },
    # Re-pointed to v4-flash: v3.2 deprecated, DeepSeek API no longer accepts it.
    "deepseek-v3": {
        "model": "deepseek/deepseek-v4-flash",        # was v3.2 ($0.12/$0.50) — re-pointed Jun 2026
    },
    # ═══════════════════════════════════════════════════════════════
    # Qwen (Alibaba) — 3.5 -> 3.8 series
    # ═══════════════════════════════════════════════════════════════
    # ── 3.8 (latest) ──
    "qwen3.8-max":         {"model": "qwen/qwen3.8-max"},        # newest flagship
    # ── 3.7 (Jun 2026) ──
    "qwen3.7-max":         {"model": "qwen/qwen3.7-max"},        # flagship agent — $1.475/$4.425 per M, 1M ctx
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
    "kimi-k3":          {"model": "moonshotai/kimi-k3"},           # 1M ctx, advanced agentic reasoning — $3/$15 per M, priciest CN model on OpenRouter
    "kimi-k2-thinking":  {"model": "moonshotai/kimi-k2-thinking"},    # Nov 2025, older than k2.5+ but the only dedicated reasoning-mode Kimi — $0.60/$2.50 per M, 262K ctx
    # ═══════════════════════════════════════════════════════════════
    # Meta LLaMA
    # ═══════════════════════════════════════════════════════════════
    "llama-4-scout":    {"model": "meta-llama/llama-4-scout"},     # $0.10/$0.30 per M, 10M ctx — best long-context VFM
    "llama-4-maverick": {"model": "meta-llama/llama-4-maverick"},  # $0.15/$0.60 per M, 1M ctx
    "muse-spark-1.1":   {"model": "meta/muse-spark-1.1"},          # small multimodal/general model
    "muse-spark-1.2-contributor": {"model": "meta/muse-spark-1.2-contributor"},  # $0.10/$0.20 per M, 1M ctx — discounted "contributor" tier; Meta may train on prompts/completions sent to it
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
    # Price verified against the live OpenRouter model page 2026-08-17: $0.476/$1.496.
    # The bundled catalogue snapshot says $1.19/$3.74 and docs/openrouter-catalogue-2026-08.md
    # says $0.308/$0.968 — three different figures. Re-run scripts/update_openrouter_catalogue.py
    # before trusting PRICING_DB for this model.
    "glm-5.2":          {"model": "z-ai/glm-5.2"},                # $0.476/$1.496 per M, 1M ctx — AA Intel 52.6, cheapest frontier-class CN model
    # NB: z-ai/glm-5.2:batch is *more* expensive ($0.70/$2.20) and caps at 512K ctx.
    # Do not add it as a "cheaper batch tier" — for this model the batch lane is a trap.
    "glm-5.3":          {"model": "z-ai/glm-5.3"},                # $1.40/$4.40 per M, 1M ctx — newest Zhipu gen, ~3x the price of 5.2 (verify against the catalogue before moving budget presets onto it)
    "glm-5.3-flash":    {"model": "z-ai/glm-5.3-flash"},          # $0.075/$0.25 per M, 1.31M ctx — took over stress_testing from the dead ring-2.6-1t (same bloc, same input price, cheaper output)
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
    "hy3":               {"model": "tencent/hy3"},               # 295B MoE (21B active, 192 experts, top-8), 262K ctx, $0.132/$0.528 per M, configurable reasoning effort (none/low/high CoT), anti-hallucination — answers grounded, flags missing evidence
    "hy3-preview":      {"model": "tencent/hy3-preview"},
    # ── Hunyuan-MT v2: translation specialists, NOT general reasoning models ──
    # 8K context (vs 262K for hy3) rules them out of every pipeline phase that
    # carries accumulated state — decomposition, synthesis, stress-testing. The
    # ACR capability registry derives max_context from the catalogue, so its
    # min_context_tokens role requirements exclude these automatically; the
    # constraint is recorded here so nobody hand-pins them into a long-context
    # role and only discovers the truncation at runtime.
    "hy-mt2-30b":       {"model": "tencent/hy-mt2-30b-a3b"},     # 30B/3B MoE MT — $0.074/$0.295 per M, 8K ctx
    "hy-mt2-1.8b":      {"model": "tencent/hy-mt2-1.8b"},        # 1.8B dense MT — $0.044/$0.177 per M, 8K ctx, cheapest translation lane
    # ═══════════════════════════════════════════════════════════════
    # ByteDance Seed
    # ═══════════════════════════════════════════════════════════════
    "seed-2.0-mini":    {"model": "bytedance-seed/seed-2.0-mini"},  # $0.10/$0.40 per M, 262K ctx
    "seed-2.0-lite":    {"model": "bytedance-seed/seed-2.0-lite"},  # $0.25/$2.00 per M, 262K ctx — mid tier, same gen
    # ═══════════════════════════════════════════════════════════════
    # inclusionAI (Ant Group)
    # ═══════════════════════════════════════════════════════════════
    "ling-3.0-flash-free": {"model": "inclusionai/ling-3.0-flash"},  # v3.8: :free tier died (as predicted) -> paid, $0.021/$0.063 per M, 262K ctx
    # The whole inclusionAI 2.6 line was delisted by 2026-08-26: ring-2.6-1t and
    # ling-2.6-1t 404 ("no longer available as a free model") and ling-2.6-flash
    # left the OpenRouter catalogue entirely. Not a billing issue — other paid
    # models bill fine on the same key. Reroutes: stress_testing -> glm-5.3-flash
    # (same CN bloc, $0.075/$0.25 vs the dead $0.075/$0.625); ultra-budget
    # destructive -> ling-3.0-flash-free (same vendor, still live, cheaper).
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
    # Sakana AI
    # ═══════════════════════════════════════════════════════════════
    "sakana-fugu-ultra": {"model": "sakana/fugu-ultra"},           # 1M ctx multimodal reasoning
    "sakana-namazu":     {"model": "sakana/sakana-namazu"},         # Japanese earthquake/disaster warning & robust analysis
    # ═══════════════════════════════════════════════════════════════
    # KwaiPilot (Kuaishou — coding specialists)
    # ═══════════════════════════════════════════════════════════════
    "kat-coder-air-v2.5": {"model": "kwaipilot/kat-coder-air-v2.5"}, # $0.15/$0.60 per M, lightweight fast coder
    "kat-coder-pro-v2":   {"model": "kwaipilot/kat-coder-pro-v2"},   # $0.30/$1.20 per M, professional-grade coder
    "kat-coder-pro-v2.5": {"model": "kwaipilot/kat-coder-pro-v2.5"}, # $0.74/$2.96 per M, flagship reasoning & coding
    # ═══════════════════════════════════════════════════════════════
    # Cohere
    # ═══════════════════════════════════════════════════════════════
    "cohere-command-a":            {"model": "cohere/command-a"},                # Cohere agentic model
    "cohere-command-r-08-2024":      {"model": "cohere/command-r-08-2024"},        # enterprise command-r
    "cohere-command-r-plus-08-2024": {"model": "cohere/command-r-plus-08-2024"},   # heavy enterprise command-r-plus
    "cohere-command-r7b":          {"model": "cohere/command-r7b-12-2024"},      # fast compact r7b
    "cohere-north-mini-code-free": {"model": "cohere/north-mini-code:free"},     # FREE coding assistant
    # ═══════════════════════════════════════════════════════════════
    # Image generation models (OpenRouter multimodal image output)
    # ═══════════════════════════════════════════════════════════════
    # ⚠ The "Removed: ... provider gone from OpenRouter" comments that used to live
    # here were WRONG. flux.*, riverflow, recraft, seedream, grok-imagine and
    # mai-image-2.5 were never delisted — GET /api/v1/models returns the *text*
    # lane only, and pure image generators are invisible without
    # ?output_modalities=image. All of them are live (45 image models as of
    # 2026-08). Verify against the image lane before deleting anything here;
    # scripts/update_openrouter_catalogue.py now fetches both.
    #
    # ── Hybrid chat+image (token-priced, work through OpenRouterProvider) ──
    "gemini-flash-image":             {"model": "google/gemini-2.5-flash-image",      "extra_body": {"include_images": True}},
    # v3.8: -preview pins promoted to the GA ids, which OpenRouter now serves at the
    # same price with a larger context (65K -> 131K) than the preview endpoints.
    "gemini-pro-image":               {"model": "google/gemini-3-pro-image",          "extra_body": {"include_images": True}},  # $2/$12 per M, 131K ctx
    "gemini-3.1-flash-image-preview": {"model": "google/gemini-3.1-flash-image",      "extra_body": {"include_images": True}},  # $0.50/$3 per M, 131K ctx
    MODEL_GEMINI_31_FLASH_LITE_IMAGE: {"model": "google/gemini-3.1-flash-lite-image", "extra_body": {"include_images": True}},
    "gpt-5-image":                    {"model": "openai/gpt-5-image",       "extra_body": {"include_images": True}},
    "gpt-5-image-mini":               {"model": "openai/gpt-5-image-mini",  "extra_body": {"include_images": True}},
    "gpt-5.4-image-2":                {"model": "openai/gpt-5.4-image-2",   "extra_body": {"include_images": True}},
    # ── Pure image generators (priced per image, not per token) ──
    # These have no prompt/completion pricing at all; cost is `image` /
    # `image_output`. Do not reason about their cost from the per-M columns above.
    "qwen-image-3":                   {"model": "qwen/qwen-image-3",        "extra_body": {"include_images": True}},  # $0.003/image, 65K ctx
    "qwen-image-3-pro":               {"model": "qwen/qwen-image-3-pro",    "extra_body": {"include_images": True}},  # $0.003/image, higher per-token image rate
    "seedream-5-pro":                 {"model": "bytedance-seed/seedream-5-0-pro",  "extra_body": {"include_images": True}},  # 🇨🇳 ByteDance — $0.003/image
    "seedream-5-lite":                {"model": "bytedance-seed/seedream-5-0-lite", "extra_body": {"include_images": True}},  # 🇨🇳 ByteDance — cheapest Seedream tier
    "seedream-4.5":                   {"model": "bytedance-seed/seedream-4.5",      "extra_body": {"include_images": True}},  # 🇨🇳 ByteDance — IMAGE_GEN_FALLBACKS budget pin
    "grok-imagine-image-2":           {"model": "x-ai/grok-imagine-image-2.0",      "extra_body": {"include_images": True}},  # 🇺🇸 xAI — $0.01/image, priciest per image
    "grok-imagine":                   {"model": "x-ai/grok-imagine-image-quality",  "extra_body": {"include_images": True}},  # 🇺🇸 xAI — quality tier, IMAGE_GEN_PRESETS budget pin
    "riverflow-v2-fast-preview":      {"model": "sourceful/riverflow-v2-fast",      "extra_body": {"include_images": True}},  # 🇺🇸 Sourceful — preview pin promoted to GA id
    "flux.2-pro":                     {"model": "black-forest-labs/flux.2-pro",     "extra_body": {"include_images": True}},  # 🇩🇪 Black Forest Labs — IMAGE_GEN_FALLBACKS budget pin
    "recraft-v4.1-utility":           {"model": "recraft/recraft-v4.1-utility",     "extra_body": {"include_images": True}},  # 🇺🇸 Recraft — IMAGE_GEN_FALLBACKS budget pin
    "krea-2-large":                   {"model": "krea/krea-2-large",         "extra_body": {"include_images": True}},  # 🇺🇸 Krea — highest-fidelity Krea tier
    "krea-2-medium":                  {"model": "krea/krea-2-medium",        "extra_body": {"include_images": True}},  # 🇺🇸 Krea — half the image-token rate of large
    "krea-2-medium-turbo":            {"model": "krea/krea-2-medium-turbo",  "extra_body": {"include_images": True}},  # 🇺🇸 Krea — cheapest of the three, latency-optimised
    # ── Remaining 2026-08 catalogue image models (previously undeclared) ──
    "gpt-image-1":                    {"model": "openai/gpt-image-1",              "extra_body": {"include_images": True}},
    "gpt-image-1-mini":               {"model": "openai/gpt-image-1-mini",         "extra_body": {"include_images": True}},
    "gpt-image-2":                    {"model": "openai/gpt-image-2",              "extra_body": {"include_images": True}},
    "mai-image-2.5":                  {"model": "microsoft/mai-image-2.5",         "extra_body": {"include_images": True}},  # 🇺🇸 Microsoft
    "mai-image-2.5-pro":              {"model": "microsoft/mai-image-2.5-pro",     "extra_body": {"include_images": True}},  # 🇺🇸 Microsoft
    "gemini-3-pro-image-preview":     {"model": "google/gemini-3-pro-image-preview",     "extra_body": {"include_images": True}},  # legacy preview id, GA is gemini-pro-image
    "flux.2-flex":                    {"model": "black-forest-labs/flux.2-flex",   "extra_body": {"include_images": True}},  # 🇩🇪 Black Forest Labs
    "flux.2-max":                     {"model": "black-forest-labs/flux.2-max",    "extra_body": {"include_images": True}},  # 🇩🇪 Black Forest Labs
    "flux.2-klein-4b":                {"model": "black-forest-labs/flux.2-klein-4b", "extra_body": {"include_images": True}},  # 🇩🇪 Black Forest Labs
    "recraft-v3":                     {"model": "recraft/recraft-v3",              "extra_body": {"include_images": True}},  # 🇺🇸 Recraft
    "recraft-v4":                     {"model": "recraft/recraft-v4",              "extra_body": {"include_images": True}},  # 🇺🇸 Recraft
    "recraft-v4-pro":                 {"model": "recraft/recraft-v4-pro",          "extra_body": {"include_images": True}},  # 🇺🇸 Recraft
    "recraft-v4-vector":              {"model": "recraft/recraft-v4-vector",       "extra_body": {"include_images": True}},  # 🇺🇸 Recraft — SVG output
    "recraft-v4-pro-vector":          {"model": "recraft/recraft-v4-pro-vector",   "extra_body": {"include_images": True}},  # 🇺🇸 Recraft — SVG output
    "recraft-v4.1":                   {"model": "recraft/recraft-v4.1",            "extra_body": {"include_images": True}},  # 🇺🇸 Recraft
    "recraft-v4.1-pro":               {"model": "recraft/recraft-v4.1-pro",        "extra_body": {"include_images": True}},  # 🇺🇸 Recraft
    "recraft-v4.1-vector":            {"model": "recraft/recraft-v4.1-vector",     "extra_body": {"include_images": True}},  # 🇺🇸 Recraft — SVG output
    "recraft-v4.1-pro-vector":        {"model": "recraft/recraft-v4.1-pro-vector", "extra_body": {"include_images": True}},  # 🇺🇸 Recraft — SVG output
    "recraft-v4.1-utility-pro":       {"model": "recraft/recraft-v4.1-utility-pro", "extra_body": {"include_images": True}},  # 🇺🇸 Recraft
    "recraft-v4-styles":              {"model": "recraft/recraft-v4-styles",            "extra_body": {"include_images": True}},  # 🇺🇸 Recraft — from $0.035, 65K ctx
    "recraft-v4-styles-pro":          {"model": "recraft/recraft-v4-styles-pro",        "extra_body": {"include_images": True}},  # 🇺🇸 Recraft — from $0.10, 65K ctx
    "recraft-v4-styles-vector":       {"model": "recraft/recraft-v4-styles-vector",     "extra_body": {"include_images": True}},  # 🇺🇸 Recraft — SVG output, from $0.05, 65K ctx
    "recraft-v4-styles-pro-vector":   {"model": "recraft/recraft-v4-styles-pro-vector", "extra_body": {"include_images": True}},  # 🇺🇸 Recraft — SVG output, from $0.12, 65K ctx
    "riverflow-v2-pro":               {"model": "sourceful/riverflow-v2-pro",      "extra_body": {"include_images": True}},  # 🇺🇸 Sourceful
    "riverflow-v2.5-fast":            {"model": "sourceful/riverflow-v2.5-fast",   "extra_body": {"include_images": True}},  # 🇺🇸 Sourceful
    "riverflow-v2.5-pro":             {"model": "sourceful/riverflow-v2.5-pro",    "extra_body": {"include_images": True}},  # 🇺🇸 Sourceful
    # google/gemini-3.1-flash-image-preview NOT declared separately — its alias
    # slot ("gemini-3.1-flash-image-preview") already points at the promoted GA
    # id (google/gemini-3.1-flash-image) above; adding it here would collide.
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
_REGISTRY_MUTABLE: dict[str, dict[str, Any]] = {}
for _mid, _cfg in _MODEL_WHITELIST.items():
    _entry: dict[str, Any] = dict(_cfg)
    if not _entry.get("is_local"):
        _entry.setdefault("cls", "openrouter")
        _entry.setdefault("env", "OPENROUTER_API_KEY")
    _REGISTRY_MUTABLE[_mid] = _entry

# Frozen after init — built once at import time, read from ~15+ call sites
# concurrently (see ARCH-AUDIT-V2 Phase 3 fan-in finding). MappingProxyType
# makes accidental post-init mutation a TypeError instead of a silent data race.
_REGISTRY: MappingProxyType[str, dict[str, Any]] = MappingProxyType(_REGISTRY_MUTABLE)


def build_provider(model_id: str, api_key: str | None = None) -> BaseLLMProvider:
    """Build a provider instance from a model ID string."""

    if model_id not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(
            f"""Unknown model ID: {model_id!r}
Available models:
  {available}"""
        )
    cfg = _REGISTRY[model_id]

    # xAI direct routing logic
    is_xai = _prefers_direct_key(model_id) == "XAI_API_KEY"
    using_xai_direct = False

    key = api_key
    if is_xai and not key:
        xai_key = os.environ.get("XAI_API_KEY", "")
        if xai_key:
            key = xai_key
            using_xai_direct = True

    # DeepSeek direct routing logic (try DEEPSEEK_API_KEY first, fall back to OpenRouter)
    is_deepseek = _prefers_direct_key(model_id) == "DEEPSEEK_API_KEY"
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
    "krea": "US", "black-forest-labs": "US", "sourceful": "US", "recraft": "US", "microsoft": "US",
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


# Vendors whose own API this deployment will use in preference to OpenRouter
# when the corresponding key happens to be set. These are NOT recorded as an
# entry's "env": that field is the key a role is *gated* on, and
# PresetService.filter_routing() downgrades any role whose "env" is unset — so
# declaring DEEPSEEK_API_KEY there would rewrite every DeepSeek role away
# whenever only OPENROUTER_API_KEY is configured, which is the common case and
# was a real outage. The direct key is strictly an optional upgrade.
_DIRECT_KEY_VENDORS: dict[str, str] = {
    "x-ai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


def _prefers_direct_key(model_id: str) -> str | None:
    """Env var of the vendor-direct key ``build_provider`` prefers, if any."""
    if model_id.startswith("grok-"):
        return "XAI_API_KEY"
    if model_id.startswith("deepseek-"):
        return "DEEPSEEK_API_KEY"
    return _DIRECT_KEY_VENDORS.get(_vendor_of(model_id))


def direct_key_envs() -> dict[str, list[str]]:
    """Optional vendor-direct key env vars, mapped to the models that use them.

    ``build_provider`` silently prefers these over the OpenRouter lane, so they
    are live credentials that can be stale or revoked — but because they are
    deliberately absent from every entry's ``env`` (see ``_DIRECT_KEY_VENDORS``),
    anything enumerating providers by that field alone cannot see them. The key
    status/validation endpoints use this so an operator's preflight actually
    covers the keys their traffic will use, instead of reporting all-green while
    every DeepSeek call 401s.
    """
    out: dict[str, list[str]] = {}
    for model_id in _REGISTRY:
        env = _prefers_direct_key(model_id)
        if env:
            out.setdefault(env, []).append(model_id)
    return out


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


def honours_tuned_temperature(model_id: str) -> bool:
    """True when routing this model to a phase actually applies that phase's temperature.

    A model fails this on either of two independent grounds, and both matter:

      * the provider refuses to send ``temperature`` at all
        (``OpenAICompatibleProvider._FIXED_TEMPERATURE_MARKERS``), or
      * the OpenRouter catalogue reports no ``temperature`` in the model's
        ``supported_parameters``.

    The two disagree today -- the denylist is hand-maintained from Jun 2026
    capability data and has drifted from the catalogue in both directions -- so
    this deliberately fails closed on the union rather than trusting either
    alone. An unknown model (absent from the catalogue, e.g. an ollama or
    ``~*-latest`` alias) is assumed to honour temperature, matching the
    provider's own allowlist-by-default stance.

    Why this matters: a model that ignores temperature does not error, it
    silently samples at its fixed default (1.0). Routed to a phase tuned for
    0.2, it is 5x more random than the phase asked for, and nothing surfaces it.
    """
    from reasoner.domain.pricing import MODEL_CATALOGUE
    from reasoner.infrastructure.llm.providers.openai_compat import (
        OpenAICompatibleProvider,
    )

    served = resolved_model_of(model_id).lower()
    if served.startswith(("gpt-", "o1", "o3", "o4")):
        return False
    if any(m in served for m in OpenAICompatibleProvider._FIXED_TEMPERATURE_MARKERS):
        return False

    entry = MODEL_CATALOGUE.get(resolved_model_of(model_id))
    if not entry:
        return True
    return "temperature" in set(entry.get("supported_parameters") or ())


class RegistryAdapter:
    """Infrastructure adapter implementing :class:`ModelRegistryPort`.

    Pure interface extraction — same behavior as calling ``build_provider`` /
    ``_REGISTRY`` directly, but presented behind the port so application and
    domain layers never import this module.
    """

    def get_provider(self, model_id: str, api_key: str | None = None):
        """Build a provider instance from a model ID (allowlist-enforced)."""
        return build_provider(model_id, api_key=api_key)

    def contains(self, model_id: str) -> bool:
        """Return True if *model_id* is a known registry entry."""
        return model_id in _REGISTRY

    def entry(self, model_id: str) -> dict[str, Any] | None:
        """Return the registry config entry for *model_id*, or None."""
        return _REGISTRY.get(model_id)
