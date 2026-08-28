from __future__ import annotations

from reasoner.domain.preset_core import PipelinePreset

# ======================================================================================
#  NOTE: When adding a new preset, run `python scripts/validate_presets.py`
#
#  CROSS-BLOC DIVERSITY (Buyl et al., npj AI 2026): the creator's geopolitical bloc
#  is the dominant axis of an LLM's ideological bias, so "cross-lab" at the company
#  level is not enough — two Chinese labs share a bloc. Invariants enforced by the
#  validator and tests/unit/test_preset_bloc_diversity.py:
#    A. synthesis bloc ≠ scoring bloc  (the final voice and its pruning critic must
#       span two blocs).
#    B. the perspective/debate generator roles span ≥2 blocs, ≤2 of any single bloc.
#  Bloc tags in comments: 🇺🇸 US · 🇨🇳 CN · 🇫🇷/🇪🇺 EU.
# ======================================================================================

_REGISTRY: dict[str, dict] = {
    # ----------------------------------------------------------------------------------
    # Foundational presets - do not remove or rename without updating UI + core logic
    # ----------------------------------------------------------------------------------
    "multi-perspective-budget": {
        "method": "multi-perspective",
        "primary_id": "grok-4.3",
        "routing": {
            "perspective_cot": "mimo-v2.5",           # Xiaomi 🇨🇳 — $0.14/$0.28, cheapest 1M ctx omnimodal
            "perspective_analysis": "qwen3.6-flash",   # was qwen3-turbo (DEAD) → stronger reasoning
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
            # ── Per-perspective echo-chamber-resistant diversity (4 labs, 3 blocs: 2🇨🇳 + 1🇺🇸 + 1🇫🇷) ──
            "constructive":  "deepseek-v3",           # 🇨🇳 DeepSeek — v3 alias now routes to v4-flash (API deprecated v3.2)
            "destructive":   "hermes-4-70b",      # 🇺🇸 Nous Research — critic-specialized ($0.13/$0.40) (was ring-2.6-1t 🇨🇳, cross-bloc echo resistance)
            "systemic":      "qwen3-30b-a3b",  # 🇨🇳 Qwen — $0.130/$0.520 per M, 131K ctx (was hy3; one model per phase)
            "minimalist":    "ministral-8b",     # 🇫🇷 Mistral — $0.075/$0.20
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "hy3",              # 🇨🇳 Tencent — anti-hallucination scoring, configurable CoT, $0.20/$0.80 (was gpt-4o-mini)
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "balanced"],
    },
    "multi-perspective-ultra-budget": {
        "method": "multi-perspective",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "perspective_cot": "mimo-v2-flash",  # 🇨🇳 Xiaomi — $0.140/$0.280 per M, 1050K ctx (was qwen3.5-flash; one model per phase)
            "perspective_analysis": "qwen3.6-flash",   # was qwen3.5-9b → stronger reasoning, 1M ctx
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
            # ── Per-perspective cross-bloc diversity (2🇨🇳 + 1🇺🇸 + 1🇫🇷, ultra-cheap) ──
            "constructive":  "stepfun-3.7-flash",    # 🇨🇳 StepFun — $0.20/$1.15
            "destructive":   "ling-3.0-flash-free",  # 🇨🇳 inclusionAI — $0.021/$0.063 (was ling-2.6-flash-free; OpenRouter delisted the 2.6 line)
            "systemic":      "gpt-oss-20b",          # 🇺🇸 OpenAI open-weight — $0.029/$0.14 (was qwen3.6-flash, added US bloc)
            "minimalist":    "ministral-8b",         # 🇫🇷 Mistral — $0.075/$0.20
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "creative", "fast"],
    },
    "multi-perspective-premium": {
        "method": "multi-perspective",
        "primary_id": "gpt-5",  # 🇺🇸 OpenAI — $1.250/$10.000 per M, 400K ctx (was gemini-pro; one model per phase)
        "routing": {
            "perspective_cot": "gemini-pro-real",  # 🇺🇸 Google — $2.000/$12.000 per M, 1048K ctx (was claude-sonnet; one model per phase)
            "perspective_analysis": "gpt-5.6-terra",  # 🇺🇸 OpenAI — $2.000/$12.000 per M, 1050K ctx (was claude-sonnet; one model per phase)
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
            # ── Per-perspective cross-bloc diversity (1🇺🇸 + 2🇨🇳 + 1🇪🇺) ──
            "constructive":  "claude-sonnet",    # 🇺🇸 Anthropic — $3/$15 per M
            "destructive":   "deepseek-v4-pro",  # 🇨🇳 DeepSeek — $0.435/$0.87 per M
            "systemic":      "qwen3.7-max",      # 🇨🇳 Qwen/Alibaba — $1.25/$3.75 per M
            "minimalist":    "mistral-large-3",  # 🇪🇺 Mistral — distinct EU bloc (was glm-5.2 🇨🇳)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "qwen3-max-real",  # 🇨🇳 Qwen — $0.780/$3.900 per M, 262K ctx (was deepseek-v4-pro; one model per phase)
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "balanced", "multilingual"],
    },
    "debate-budget": {
        "method": "debate",
        "primary_id": "hermes-4-405b",  # 🇺🇸 Nous Research — $1.000/$3.000 per M, 131K ctx (was grok-4.3; one model per phase)
        "routing": {
            # ── Cross-bloc adversarial diversity (🇨🇳 vs 🇺🇸, 🇺🇸 judge) ──
            "constructive": "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
            "destructive":  "gpt-oss-120b",     # 🇺🇸 OpenAI open-weight — adversarial critique (was ring 🇨🇳, cross-bloc debate)
            "systemic":     "grok-4.3",     # 🇺🇸 xAI — judging (was Google, swapped to Grok for budget v3.6)
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "gemini-flash-lite",  # 🇨🇳 Qwen — $0.065/$0.260 per M, 1000K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "argumentative", "robust"],
    },
    "debate-premium": {
        "method": "debate",
        "primary_id": "gpt-5",  # 🇺🇸 OpenAI — $1.250/$10.000 per M, 400K ctx (was gemini-pro; one model per phase)
        "routing": {
            # ── Cross-bloc adversarial diversity (🇺🇸 vs 🇨🇳, 🇺🇸 judge) ──
            "constructive": "claude-sonnet",     # 🇺🇸 Anthropic — strongest argumentation
            "destructive":  "deepseek-v4-pro",   # 🇨🇳 DeepSeek — adversarial reasoning
            "systemic":     "gemini-pro-real",   # 🇺🇸 Google (real) — judging; "gemini-pro" alias now routes to Anthropic, would duplicate constructive
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "qwen3-max-real",  # 🇨🇳 Qwen — $0.780/$3.900 per M, 262K ctx (was deepseek-v4-pro; one model per phase)
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "argumentative", "robust"],
    },
    "jury-budget": {
        "method": "jury",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "governance", "decision-making"],
    },
    "jury-premium": {
        "method": "jury",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "governance", "decision-making"],
    },
    "research-budget": {
        "method": "research",
        "primary_id": "claude-haiku",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "deep_read":      "sonar-deep-research",  # 🇺🇸 Perplexity — $2.000/$8.000 per M, 128K ctx (was sonar; one model per phase)
        "fusion":         "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "research", "web-search"],
    },
    "research-premium": {
        "method": "research",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",      # 🇨🇳 DeepSeek — cross-bloc from 🇺🇸 sonar scoring (web-grounded fact-check stays US)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "sonar-reasoning-pro", # Perplexity 🇺🇸 — reasoning + high-context search, $3/$15 per M
        "fusion":         "qwen3-max-real",  # 🇨🇳 Qwen — $0.780/$3.900 per M, 262K ctx (was deepseek-v4-pro; one model per phase)
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "sonar-deep-research", # Perplexity 🇺🇸 — explicit deep research mode, web-grounded scoring
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "research", "web-search"],
    },
    # ----------------------------------------------------------------------------------
    # Specialized method presets
    # ----------------------------------------------------------------------------------
    "scientific-budget": {
        "method": "scientific",
        "primary_id": "claude-haiku",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.5, cross-lab falsification) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "qwen3.6-flash",           # Qwen 🇨🇳 — cross-lab falsification (≠ Anthropic primary)
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "scientific", "structured"],
    },
    "scientific-premium": {
        "method": "scientific",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "scientific", "structured"],
    },
    "socratic-budget": {
        "method": "socratic",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "educational", "inquisitive"],
    },
    "socratic-premium": {
        "method": "socratic",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "educational", "inquisitive"],
    },
    "pre-mortem-budget": {
        "method": "pre_mortem",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "risk-assessment", "strategic"],
    },
    "pre-mortem-premium": {
        "method": "pre_mortem",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "risk-assessment", "strategic"],
    },
    "bayesian-budget": {
        "method": "bayesian",
        "primary_id": "claude-haiku",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "analytical", "probabilistic"],
    },
    "bayesian-premium": {
        "method": "bayesian",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "analytical", "probabilistic"],
    },
    "dialectical-budget": {
        "method": "dialectical",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "argumentative", "philosophical"],
    },
    "dialectical-premium": {
        "method": "dialectical",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "argumentative", "philosophical"],
    },
    "analogical-budget": {
        "method": "analogical",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "creative", "reasoning"],
    },
    "analogical-premium": {
        "method": "analogical",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "creative", "reasoning"],
    },
    "delphi-budget": {
        "method": "delphi",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "collaborative", "forecasting"],
    },
    "delphi-premium": {
        "method": "delphi",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "collaborative", "forecasting"],
    },
    "cove-budget": {
        "method": "cove",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "cove_answer":    "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "cove_revise":    "mimo-v2-flash",  # 🇨🇳 Xiaomi — $0.140/$0.280 per M, 1050K ctx (was deepseek-v4-flash; one model per phase)
        "cove_verify":    "seed-2.0-mini",  # 🇨🇳 ByteDance — $0.100/$0.400 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "fusion":         "hy3",  # 🇨🇳 Tencent — $0.132/$0.528 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "verification", "fact-checking"],
    },
    "cove-premium": {
        "method": "cove",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "cove_answer":    "deepseek-v4-pro",
        "cove_revise":    "deepseek-v4-flash",
        "cove_verify":    "qwen3-max-real",  # 🇨🇳 Qwen — $0.780/$3.900 per M, 262K ctx (was deepseek-v4-pro; one model per phase)
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "qwen3-max-thinking",  # 🇨🇳 Qwen — $0.780/$3.900 per M, 262K ctx (was deepseek-v4-pro; one model per phase)
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "verification", "fact-checking"],
    },
    "sot-budget": {
        "method": "sot",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "structured-thinking", "outlining"],
    },
    "sot-premium": {
        "method": "sot",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "structured-thinking", "outlining"],
    },
    "tot-budget": {
        "method": "tot",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "hy3",  # 🇨🇳 Tencent — $0.132/$0.528 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "tot_backtrack":  "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "tot_decompose":  "mimo-v2-flash",  # 🇨🇳 Xiaomi — $0.140/$0.280 per M, 1050K ctx (was deepseek-v4-flash; one model per phase)
        "tot_evaluate":   "seed-2.0-mini",  # 🇨🇳 ByteDance — $0.100/$0.400 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "problem-solving", "exploration"],
    },
    "tot-premium": {
        "method": "tot",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "tot_backtrack":  "deepseek-v4-flash",
        "tot_decompose":  "gpt-5",  # 🇺🇸 OpenAI — $1.250/$10.000 per M, 400K ctx (was claude-sonnet; one model per phase)
        "tot_evaluate":   "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "problem-solving", "exploration"],
    },
    "pot-budget": {
        "method": "pot",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "programming", "code-generation"],
    },
    "pot-premium": {
        "method": "pot",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "programming", "code-generation"],
    },
    "self-discover-budget": {
        "method": "self_discover",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "hy3",  # 🇨🇳 Tencent — $0.132/$0.528 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "sd_adapt":       "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "sd_implement":   "mimo-v2-flash",  # 🇨🇳 Xiaomi — $0.140/$0.280 per M, 1050K ctx (was deepseek-v4-flash; one model per phase)
        "sd_select":      "seed-2.0-mini",  # 🇨🇳 ByteDance — $0.100/$0.400 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "reasoning", "self-improvement"],
    },
    "self-discover-premium": {
        "method": "self_discover",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "qwen3.6-27b",  # 🇨🇳 Qwen — $0.600/$3.600 per M, 262K ctx (was deepseek-v4-pro; one model per phase)
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "sd_adapt":       "deepseek-v4-pro",
        "sd_implement":   "qwen3-max-real",  # 🇨🇳 Qwen — $0.780/$3.900 per M, 262K ctx (was deepseek-v4-pro; one model per phase)
        "sd_select":      "qwen3-max-thinking",  # 🇨🇳 Qwen — $0.780/$3.900 per M, 262K ctx (was deepseek-v4-pro; one model per phase)
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "reasoning", "self-improvement"],
    },
    "subagent-budget": {
        "method": "subagent",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":                     "hy3",  # 🇨🇳 Tencent — $0.132/$0.528 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator":             "minimax-m3",  # 🇨🇳 MiniMax — $0.300/$1.200 per M, 1048K ctx (was qwen3.7-plus; one model per phase)
        "scoring":                    "deepseek-v4-flash",  # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing":             "glm-5.3-flash",
        "subagent_critique_bias":     "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "subagent_critique_counter":  "qwen3.7-flash",  # 🇨🇳 Qwen — $0.030/$0.130 per M, 1000K ctx (was deepseek-v4-flash; one model per phase)
        "subagent_critique_evidence": "mimo-v2-flash",  # 🇨🇳 Xiaomi — $0.140/$0.280 per M, 1050K ctx (was deepseek-v4-flash; one model per phase)
        "subagent_critique_logic":    "seed-2.0-mini",  # 🇨🇳 ByteDance — $0.100/$0.400 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "subagent_decomposition":     "qwen3-30b-a3b",  # 🇨🇳 Qwen — $0.130/$0.520 per M, 131K ctx (was deepseek-v4-flash; one model per phase)
        "verifier":                   "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "multi-agent", "delegation"],
    },
    "subagent-premium": {
        "method": "subagent",
        "primary_id": "gpt-5",  # 🇺🇸 OpenAI — $1.250/$10.000 per M, 400K ctx (was gemini-pro; one model per phase)
        "routing": {
            "synthesis": "gemini-3.7-flash",  # 🇺🇸 Google — $0.375/$1.875 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":                  "gemini-2.5-flash",  # 🇺🇸 Google — $0.300/$2.500 per M, 1048K ctx; honours temperature (phase target 0.2) (was claude-sonnet: fixed-temp, silently ran at 1.0)
        "fusion":                     "qwen3.6-max-preview",  # 🇨🇳 Qwen — $1.027/$6.162 per M, 262K ctx (was deepseek-v4-pro; one model per phase)
        "meta_evaluator":             "qwen3.7-max",  # 🇨🇳 Qwen — cross-bloc from 🇺🇸 synthesis
        "scoring":                    "glm-5.2",  # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing":             "gemini-pro-real",  # 🇺🇸 Google — $2.000/$12.000 per M, 1048K ctx (was claude-sonnet; one model per phase)
        "subagent_critique_bias":     "deepseek-v4-pro",
        "subagent_critique_counter":  "qwen3-max-real",  # 🇨🇳 Qwen — $0.780/$3.900 per M, 262K ctx (was deepseek-v4-pro; one model per phase)
        "subagent_critique_evidence": "qwen3.6-27b",  # 🇨🇳 Qwen — $0.600/$3.600 per M, 262K ctx (was deepseek-v4-pro; one model per phase)
        "subagent_critique_logic":    "glm-5.3",  # 🇨🇳 Zhipu — $1.400/$4.400 per M, 1048K ctx (was deepseek-v4-pro; one model per phase)
        "subagent_decomposition":     "gpt-5.6-terra",  # 🇺🇸 OpenAI — $2.000/$12.000 per M, 1050K ctx (was claude-sonnet; one model per phase)
        "verifier":                   "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc from 🇺🇸 synthesis
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "multi-agent", "delegation"],
    },
    "writing-budget": {
        "method": "writing",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Article-flow roles (budget, v3.5) ──
        "primary":           "arcee-trinity-large-thinking",  # 🇺🇸 Arcee — $0.220/$0.850 per M, 262K ctx (was sonar; one model per phase)
        "writing_factcheck": "sonar",              # Perplexity 🇺🇸 — live web verification
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":            "qwen3.7-flash",  # 🇨🇳 Qwen — $0.030/$0.130 per M, 1000K ctx (was deepseek-v4-flash; one model per phase)
        "writing_assemble":  "deepseek-v4-flash",
        "writing_outline":   "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "post_synthesis_verify": "sonar-deep-research",  # 🇺🇸 Perplexity — $2.000/$8.000 per M, 128K ctx (was sonar; one model per phase)
        },
        "tags": ["budget", "writing", "content-creation"],
    },
    "writing-premium": {
        "method": "writing",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gemini-3.7-flash",  # 🇺🇸 Google — $0.375/$1.875 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Article-flow roles (premium, v3.5) ──
        "primary":           "arcee-trinity-large-thinking",  # 🇺🇸 Arcee — $0.220/$0.850 per M, 262K ctx (was sonar-pro; one model per phase)
        "writing_factcheck": "sonar-pro",          # Perplexity 🇺🇸 — live web verification
        # ── Reasoning model assignments (premium, v3.4) ──
        "fusion":            "deepseek-v4-pro",
        "writing_assemble":  "gpt-5",  # 🇺🇸 OpenAI — $1.250/$10.000 per M, 400K ctx (was claude-sonnet; one model per phase)
        "writing_outline":   "gemini-pro-real",  # 🇺🇸 Google — $2.000/$12.000 per M, 1048K ctx (was claude-sonnet; one model per phase)
        "post_synthesis_verify": "sonar-pro-search",  # 🇺🇸 Perplexity — $3.000/$15.000 per M, 200K ctx (was sonar-pro; one model per phase)
        },
        "tags": ["premium", "writing", "content-creation"],
    },
    "article-budget": {
        "method": "article",
        # primary_id is both the catch-all for unrouted roles AND the target
        # filter_routing() downgrades a role to when its key is missing, so it
        # must (a) build without a provider-specific key and (b) sit on a
        # different lab from the routed roles it may replace.
        #
        # deepseek-v4-flash satisfies both. It is NOT gated on DEEPSEEK_API_KEY:
        # the registry entry carries no explicit env, so the _MODEL_WHITELIST ->
        # _REGISTRY build setdefaults it to OPENROUTER_API_KEY and it resolves
        # through OpenRouter, while build_provider() still prefers a direct
        # DeepSeek key when one is present. (An earlier edit here swapped this
        # to gemini-flash-lite to dodge a DEEPSEEK_API_KEY requirement that the
        # registry fix had already removed, on the false premise that some
        # entry has env=None — none does; every non-local entry is
        # OPENROUTER_API_KEY.) That swap also broke cross-lab diversity:
        # "gemini-flash-lite" is an alias for qwen/qwen3.5-flash-02-23, the same
        # lab as this preset's qwen3.7-plus synthesis, so a degraded environment
        # collapsed the whole preset onto one lab — the opposite of the
        # "fail to a cross-lab equivalent" rule in CLAUDE.md §5.
        "primary_id": "deepseek-v4-flash",
        "routing": {
            "synthesis": "qwen3.7-plus",         # 🇨🇳 Qwen — 1M ctx for full article, cross-bloc (was gpt-4o-mini)
        # ── Article-flow roles (budget, v3.5) ──
        "primary":           "arcee-trinity-large-thinking",  # 🇺🇸 Arcee — $0.220/$0.850 per M, 262K ctx (was sonar; one model per phase)
        "writing_draft":     "claude-sonnet",       # 🇺🇸 Anthropic — best long-form prose, 1M ctx (was deepseek-v4-flash)
        "writing_factcheck": "sonar",              # Perplexity 🇺🇸 — live web verification against current sources
        "writing_assemble":  "gpt-4o-mini",       # 🇺🇸 OpenAI — same bloc as draft, proven reliable copy edit (was deepseek-v4-flash)
        # ── Article editorial roles (budget, v3.6) ──
        "article_sot_skeleton": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx (was gpt-4o-mini; one model per phase)
        "article_critic":       "hy3",       # 🇨🇳 Tencent — 295B MoE, configurable high-CoT for deep critique, $0.20/$0.80 (was hermes-4-70b)
        "article_revise":       "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "article_humanize":     "gpt-5",  # 🇺🇸 OpenAI — $1.250/$10.000 per M, 400K ctx (was claude-sonnet; one model per phase)
        "article_verifier":     "qwen3-30b-a3b",  # 🇨🇳 Qwen — $0.130/$0.520 per M, 131K ctx (was hy3; one model per phase)
        # ── Reasoning model assignments (budget, v3.5) ──
        "fusion":           "gemini-flash-lite",  # 🇨🇳 Qwen — $0.065/$0.260 per M, 1000K ctx (was deepseek-v4-flash; one model per phase)
        "post_synthesis_verify": "sonar-deep-research",  # 🇺🇸 Perplexity — $2.000/$8.000 per M, 128K ctx (was sonar; one model per phase)
        },
        # Cross-bloc fallback per role (v3.9, researched against the 2026-08-28
        # catalogue refresh) — every article role above previously fell back
        # straight to primary_id (deepseek-v4-flash) with no role-specific
        # reasoning if its provider failed. writing_factcheck and
        # post_synthesis_verify are the one deliberate exception: Perplexity is
        # the only live-web-search vendor in this registry, so their fallback
        # steps to a different Sonar tier rather than a non-search model that
        # would silently drop the citation-grounding these phases exist for.
        "fallback_routing": {
            "primary":               "qwen3.7-flash",         # 🇨🇳 Qwen — $0.03/$0.13 per M, 1M ctx, cross-bloc from Arcee
            "writing_draft":         "deepseek-v4-pro",       # 🇨🇳 DeepSeek — $0.87/$1.74 per M, 1M ctx, cross-bloc from Claude
            "writing_factcheck":     "sonar-pro",             # 🇺🇸 Perplexity — same-vendor step-up (see note above)
            "writing_assemble":      "seed-2.0-mini",         # 🇨🇳 ByteDance — $0.10/$0.40 per M, cross-bloc from OpenAI
            "article_sot_skeleton":  "glm-5.3-flash",         # 🇨🇳 Zhipu — $0.075/$0.25 per M, 1.31M ctx, cross-bloc from Meta
            "article_critic":        "gemini-2.5-flash",      # 🇺🇸 Google — $0.30/$2.50 per M, cross-bloc from Tencent
            "article_revise":        "gemini-flash-lite-real",# 🇺🇸 Google — $0.25/$1.50 per M, 1M ctx, cross-bloc from Qwen
            "article_humanize":      "glm-5.2",               # 🇨🇳 Zhipu — $0.476/$1.496 per M, cross-bloc from OpenAI
            "article_verifier":      "gemini-2.5-flash-lite", # 🇺🇸 Google — 3.3% HHEM hallucination rate, cross-bloc from Qwen
            "fusion":                "llama-4-scout",         # 🇺🇸 Meta — $0.10/$0.30 per M, 10M ctx, cross-bloc from Qwen
            "post_synthesis_verify": "sonar-reasoning-pro",   # 🇺🇸 Perplexity — same-vendor step-up (see note above)
            "synthesis":             "gemini-3.7-flash",      # 🇺🇸 Google — $0.375/$1.875 per M, cross-bloc from Qwen
        },
        "tags": ["budget", "writing", "article"],
    },
    "article-premium": {
        "method": "article",
        "primary_id": "claude-sonnet",
        "routing": {
            "synthesis": "qwen3.7-max",           # 🇨🇳 Qwen — 1M ctx, cross-bloc final voice, 88% cheaper output (was gpt-5.5)
        # ── Article-flow roles (premium, v3.5) ──
        "primary":           "arcee-trinity-large-thinking",  # 🇺🇸 Arcee — $0.220/$0.850 per M, 262K ctx (was sonar-pro; one model per phase)
        "writing_factcheck": "sonar-pro",          # Perplexity 🇺🇸 — live web verification, cross-bloc from CN scoring
        # ── Article editorial roles (premium, v3.6) ──
        "writing_draft":       "gpt-5",  # 🇺🇸 OpenAI — $1.250/$10.000 per M, 400K ctx (was claude-sonnet; one model per phase)
        "writing_outline":     "gemini-pro-real",  # 🇺🇸 Google — $2.000/$12.000 per M, 1048K ctx (was claude-sonnet; one model per phase)
        "article_sot_skeleton": "gpt-5.6-terra",  # 🇺🇸 OpenAI — $2.000/$12.000 per M, 1050K ctx (was claude-sonnet; one model per phase)
        "article_critic":      "grok-4.6",           # 🇺🇸 xAI — AA Intel 60.9 vs 37.6 for 4.3, frontier adversarial critique
        "article_revise":      "deepseek-v4-pro",    # 🇨🇳 DeepSeek — cross-bloc dev edit, 1.6T MoE, 97% cheaper output (was gpt-5.5)
        "article_humanize":    "gpt-5.6-terra-pro",  # 🇺🇸 OpenAI — $2.000/$12.000 per M, 1050K ctx (was claude-sonnet; one model per phase)
        "article_verifier":    "glm-5.3",  # 🇨🇳 Zhipu — $1.400/$4.400 per M, 1048K ctx (was qwen3.7-max; one model per phase)
        # ── Reasoning model assignments (premium, v3.5) ──
        "fusion":            "qwen3-max-real",  # 🇨🇳 Qwen — $0.780/$3.900 per M, 262K ctx (was deepseek-v4-pro; one model per phase)
        "writing_assemble":  "gpt-4o-mini",         # 🇺🇸 OpenAI — proven reliable copy edit (was gpt-5-mini, empty response)
        "post_synthesis_verify": "sonar-pro-search",  # 🇺🇸 Perplexity — $3.000/$15.000 per M, 200K ctx (was sonar-pro; one model per phase)
        },
        # Cross-bloc fallback per role (v3.9) — see article-budget's
        # fallback_routing comment for the writing_factcheck /
        # post_synthesis_verify same-vendor-step-up rationale, which applies
        # here too.
        "fallback_routing": {
            "primary":               "glm-5.3",           # 🇨🇳 Zhipu — $1.40/$4.40 per M, cross-bloc from Arcee
            "writing_draft":         "qwen3.7-max",       # 🇨🇳 Qwen — $1.475/$4.425 per M, 1M ctx, cross-bloc from GPT-5
            "writing_outline":       "qwen3.7-max",       # 🇨🇳 Qwen — cross-bloc from real Gemini Pro
            "article_sot_skeleton":  "glm-5.3",           # 🇨🇳 Zhipu — cross-bloc from GPT-5.6 Terra
            "article_critic":        "deepseek-v4-pro",   # 🇨🇳 DeepSeek — 1.6T MoE, cross-bloc from Grok
            "article_revise":        "claude-sonnet",     # 🇺🇸 Anthropic — this preset's own primary_id, cross-bloc from DeepSeek
            "article_humanize":      "qwen3-max-real",    # 🇨🇳 Qwen — $0.78/$3.90 per M, cross-bloc from GPT-5.6 Terra Pro
            "article_verifier":      "gemini-2.5-flash",  # 🇺🇸 Google — low-hallucination profile, cross-bloc from Zhipu
            "fusion":                "gemini-3.7-flash",  # 🇺🇸 Google — $0.375/$1.875 per M, cross-bloc from Qwen
            "writing_assemble":      "qwen3.7-plus",      # 🇨🇳 Qwen — "best VFM" per its own registry comment, cross-bloc from OpenAI
            "synthesis":             "gemini-pro-real",   # 🇺🇸 Google — real Gemini Pro, cross-bloc from Qwen
            "writing_factcheck":     "sonar-pro-search",  # 🇺🇸 Perplexity — same-vendor step-up (see note above)
            "post_synthesis_verify": "sonar-reasoning-pro", # 🇺🇸 Perplexity — same-vendor step-up (see note above)
        },
        "tags": ["premium", "writing", "article"],
    },
    "coding-budget": {
        "method": "coding",
        # qwen3-coder-flash is a dedicated coding model: reliable content,
        # fast (~11s/call, well within the 120s coding-phase budget), and far
        # stronger at code than a general-purpose flash model.
        # NOTE: avoid kimi-k2.x "code" here — reasoning models that emit output in separate channel
        # models that emit output in a separate channel, leaving `content` empty.
        # deepseek-v4-flash preferred over older V3 (timed out at 120s).
        "primary_id": "qwen3-coder-flash",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "coding_assemble": "laguna-xs-2.1",    # 🇺🇸 Poolside ($0.06/$0.12) — dedicated coding agent (was deepseek-v4-flash)
        "coding_review":   "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "coding_spec":     "qwen3.6-35b-a3b",  # 🇨🇳 Qwen — $0.140/$1.000 per M, 262K ctx (was qwen3-coder-flash; one model per phase)
        "coding_tests":    "gemini-flash-lite",  # 🇨🇳 Qwen — $0.065/$0.260 per M, 1000K ctx (was deepseek-v4-flash; one model per phase)
        "fusion":          "qwen3.7-flash",  # 🇨🇳 Qwen — $0.030/$0.130 per M, 1000K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator":  "minimax-m3",  # 🇨🇳 MiniMax — $0.300/$1.200 per M, 1048K ctx (was qwen3.7-plus; one model per phase)
        "scoring":         "deepseek-v4-flash",  # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing":  "glm-5.3-flash",
        "verifier":        "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        # Single-model fallback for the lighter coding roles (spec/tests/assemble)
        # that route through primary. codestral-2508 is fast (~3s), code-specialized,
        # and cross-lab (Mistral vs Qwen).
        "fallback_routing": {
            "primary": "codestral-2508",
        },
        # Multi-model fallback chains (tried in order, with a quality gate that skips
        # empty/degraded/low-quality responses before moving to the next model):
        #   - coding_generate: Qwen → Poolside → Mistral → DeepSeek (cross-lab, coding-optimized)
        #   - coding_review:   cross-lab critique (DeepSeek → Mistral → OpenAI)
        # deepseek-v4-flash leads both chains: reliable content (verified 2/2, no empty
        # trap), cheapest model here ($0.09/$0.18/M), 1M context, cross-lab from the Qwen
        # generator. gpt-5.1-codex-mini is demoted to a last-resort review slot — it is
        # codex-class but intermittently returns empty content on larger prompts (observed
        # live), so the quality gate handles it only as a final fallback, never as a primary.
        "cascading_routing": {
            "coding_generate": ["qwen3-coder-flash", "kat-coder-pro-v2.5", "laguna-xs-2.1", "kat-coder-air-v2.5", "codestral-2508", "grok-build-0.1", "deepseek-v4-flash"],
            "coding_review": ["deepseek-v4-flash", "kat-coder-pro-v2.5", "mimo-v2.5-pro", "codestral-2508", "gpt-5.1-codex-mini"],
        },
        "tags": ["budget", "coding", "software-development"],
    },
    "coding-premium": {
        "method": "coding",
        "primary_id": "gpt-5",  # 🇺🇸 OpenAI — $1.250/$10.000 per M, 400K ctx (was claude-sonnet; one model per phase)
        "routing": {
            "synthesis": "gemini-3.7-flash",  # 🇺🇸 Google — $0.375/$1.875 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "coding_assemble": "deepseek-v4-flash",
        "coding_review":   "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "coding_spec":     "gpt-5.1-codex",  # 🇺🇸 OpenAI — $1.250/$10.000 per M, 400K ctx (was claude-sonnet; one model per phase)
        "coding_tests":    "gemini-flash-lite",  # 🇨🇳 Qwen — $0.065/$0.260 per M, 1000K ctx (was deepseek-v4-flash; one model per phase)
        "deep_read":       "gemini-2.5-flash",  # 🇺🇸 Google — $0.300/$2.500 per M, 1048K ctx; honours temperature (phase target 0.2) (was claude-sonnet: fixed-temp, silently ran at 1.0)
        "fusion":          "deepseek-v4-pro",
        "meta_evaluator":  "qwen3.6-27b",  # 🇨🇳 Qwen — $0.600/$3.600 per M, 262K ctx (was glm-5.2; one model per phase)
        "scoring":         "qwen3.8-max",         # 🇨🇳 Qwen — AA Intel 58.1, SWE-bench Pro 67.7; kept distinct from glm-5.2 meta/verifier
        "stress_testing":  "gemini-pro-real",  # 🇺🇸 Google — $2.000/$12.000 per M, 1048K ctx (was claude-sonnet; one model per phase)
        "verifier":        "glm-5.2",           # 🇨🇳 Zhipu — cross-bloc verification, $0.476/$1.496 live (comment said $0.95/$3.00)
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "coding", "software-development"],
    },
    "cross-language-budget": {
        "method": "cross-language",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        # Not implied by any model entry: translation goes through DeepL, not
        # an LLM provider, so the preflight cannot derive this one.
        "required_env_vars": ["DEEPL_API_KEY"],
        "tags": ["budget", "translation", "multilingual"],
    },
    "cross-language-premium": {
        "method": "cross-language",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "glm-5.2",              # 🇨🇳 Zhipu — cross-bloc final voice, $0.476/$1.496 live (comment said $0.95/$3.00)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "gemini-pro-real",     # 🇺🇸 Google — multilingual cross-bloc critic of 🇨🇳 synthesis (was qwen 🇨🇳)
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "qwen3.6-27b",  # 🇨🇳 Qwen — $0.600/$3.600 per M, 262K ctx (was glm-5.2; one model per phase)
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "required_env_vars": ["DEEPL_API_KEY"],
        "tags": ["premium", "translation", "multilingual"],
    },
    # nvidia-nemotron-test removed 2026-08-21. It was a 3-role experimental
    # probe for Nemotron routing; the model it existed to exercise
    # (nvidia-nemotron-super) stays in the registry and is reachable from any
    # preset, so nothing is lost by dropping the preset itself.
    "brainstorming-budget": {
        "method": "brainstorming",
        "primary_id": "claude-haiku",
        "routing": {
            "brainstorm_cluster": "google/gemma-2-9b-it",
            "brainstorm_develop": "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "gemini-flash-lite",  # 🇨🇳 Qwen — $0.065/$0.260 per M, 1000K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "fallback_routing": {
            "primary": "claude-haiku",
        },
        "tags": ["budget", "creative"],
    },
    "brainstorming-premium": {
        "method": "brainstorming",
        "primary_id": "claude-sonnet",
        "routing": {
            "brainstorm_cluster": "gpt-5",  # 🇺🇸 OpenAI — $1.250/$10.000 per M, 400K ctx (was claude-sonnet; one model per phase)
            "brainstorm_develop": "gemini-pro-real",  # 🇺🇸 Google — $2.000/$12.000 per M, 1048K ctx (was claude-sonnet; one model per phase)
            "synthesis": "inkling-small",  # 🇺🇸 Thinking Machines — $0.450/$1.200 per M, 524K ctx; honours temperature (phase target 0.5) (was gpt-5.6-luna: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "creative"],
    },
    "image-gen-budget": {
        "method": "image-gen",
        "primary_id": "grok-4.3",
        "routing": {
            "image_generate": "gemini-3.1-flash-lite-image",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "qwen3.5-9b",  # 🇨🇳 Qwen — $0.100/$0.150 per M, 262K ctx (was deepseek-v4-flash; one model per phase)
        "meta_evaluator": "qwen3.7-flash",           # Qwen 🇨🇳 — $0.03/$0.13 (-54% vs 3.5-flash), newer gen, 1M ctx, vision
        "scoring":        "deepseek-v4-flash",
        "stress_testing": "glm-5.3-flash",
        "verifier":       "gemini-2.5-flash-lite",   # Google 🇺🇸 — 3.3% HHEM hallucination (3rd best measured), $0.10/$0.40
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        # Every fallback is a different VENDOR, not just a different model, so a
        # provider outage cannot take both the primary and its backup. Each also
        # resolves to a different served model than the role it backs — a
        # fallback sharing the served model is not a fallback.
        # None of these are fixed-temperature models: fusion/meta_evaluator/
        # scoring/stress_testing/verifier all run below 0.7, and a model that
        # ignores temperature would silently sample at 1.0 there.
        # No image_generate entry here: this preset's actual image call
        # (api/routes/images.py -> generate_images()) never reads this dict —
        # it is resolved entirely through IMAGE_GEN_FALLBACKS in
        # core/constants_limits.py (5 cross-vendor models for budget, 7 for
        # premium), or by hypergate's auto model selector. A prior version of
        # this comment claimed both were consulted; that was wrong, and an
        # image_generate key here would be dead data implying a fallback path
        # that does not exist.
        "fallback_routing": {
            "fusion":          "seed-2.0-mini",         # 🇨🇳 ByteDance — $0.10/$0.40, 262K ctx
            "meta_evaluator":  "mistral-small-2603",    # 🇫🇷 Mistral — EU bloc, accepts temperature
            "scoring":         "hy3",                   # 🇨🇳 Tencent — anti-hallucination scoring
            "stress_testing":  "stepfun-3.7-flash",     # 🇨🇳 StepFun — cheap adversarial pass
            "verifier":        "gpt-oss-120b",          # 🇺🇸 OpenAI open-weight — unlike the hosted gpt-5.x tiers this one DOES accept temperature
            "post_synthesis_verify": "sonar-reasoning-pro",  # 🇺🇸 Perplexity — search family preserved
        },
        "tags": ["image-generation", "creative", "budget"],
    },
    "image-gen-premium": {
        "method": "image-gen",
        "primary_id": "gemini-pro",
        "routing": {
            "image_generate": "gemini-pro-image",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "glm-5.2",             # 🇨🇳 Zhipu — AA Intel 52.6 vs ~32, cheaper both sides
        "stress_testing": "grok-4.6",             # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "grok-4.3",           # xAI 🇺🇸 — record 78% non-hallucination (AA Omniscience), 1M ctx, same price
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        # Same rules as image-gen-budget: different vendor from the role it
        # backs, distinct served model, and no fixed-temperature model in a
        # sub-0.7 phase (deep_read 0.2, fusion 0.2, scoring 0.3, verifier 0.2,
        # stress_testing 0.5) — which rules out the gpt-5.x tiers, claude-opus,
        # claude-sonnet and claude-fable-5 for all of them. No image_generate
        # entry: see image-gen-budget's fallback_routing comment — that role's
        # fallback lives entirely in core/constants_limits.py's
        # IMAGE_GEN_FALLBACKS, not in this dict.
        "fallback_routing": {
            "deep_read":       "claude-haiku",          # 🇺🇸 Anthropic — accepts temperature, unlike sonnet/opus/fable
            "fusion":          "qwen3-max-real",        # 🇨🇳 Qwen — cross-vendor from DeepSeek
            "meta_evaluator":  "mistral-medium-3-5",    # 🇫🇷 Mistral — EU bloc
            "scoring":         "kimi-k2-6",             # 🇨🇳 Moonshot — cross-vendor from Zhipu, keeps scoring CN vs 🇺🇸 synthesis. Not deepseek-v4-pro: that is this preset's fusion model, so falling back to it would run one model in two phases.
            "stress_testing":  "gemini-pro-real",       # 🇺🇸 Google (real) — "gemini-pro" would alias to Anthropic
            "verifier":        "gemini-flash-lite-real",# 🇺🇸 Google (real) — cross-vendor from xAI
            "post_synthesis_verify": "sonar-deep-research",  # 🇺🇸 Perplexity — search family preserved
        },
        "tags": ["image-generation", "creative", "premium"],
    },
    "iterative-critique-budget": {
        "method": "iterative-critique",
        "primary_id": "grok-4.3",
        "routing": {
            "synthesis": "llama-4-maverick",  # 🇺🇸 Meta — $0.200/$0.800 per M, 1048K ctx; honours temperature (phase target 0.5) (was claude-sonnet: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (budget, v3.6, 7-lab diversity) ──
        "fusion":         "deepseek-v4-flash",     # DeepSeek 🇨🇳 — fast, cheap analytical integration
        "meta_evaluator": "mistral-small-2603",    # Mistral 🇫🇷 — meta-level debate structure critique
        "scoring":        "qwen3.6-flash",         # Qwen 🇨🇳 — structured numerical evaluation
        "stress_testing": "glm-5.3-flash",           # inclusionAI (Ant Group) 🇨🇳 — AIME 95.83, GPQA-D 88.27, PinchBench 87.60 agent mode
        "verifier":       "gemini-flash-lite-real", # Google 🇺🇸 — Gemini 3.1 Flash Lite, structured fact-checking
        "post_synthesis_verify": "sonar",  # added v3.5
        },
        "tags": ["budget", "iterative", "critique"],
    },
    "iterative-critique-premium": {
        "method": "iterative-critique",
        "primary_id": "gpt-5",  # 🇺🇸 OpenAI — $1.250/$10.000 per M, 400K ctx (was claude-sonnet; one model per phase)
        "routing": {
            "synthesis": "grok-4.3",  # 🇺🇸 xAI — $1.250/$2.500 per M, 1000K ctx; honours temperature (phase target 0.5) (was claude-sonnet: fixed-temp, silently ran at 1.0)
        # ── Reasoning model assignments (premium, v3.5, 8-lab diversity) ──
        "deep_read":      "gemini-3.7-flash",    # Google 🇺🇸 — AA Intel 56.0 vs 47.7, 1M ctx, $0.375/$1.875 (5.3x cheaper)
        "fusion":         "mistral-large-3",     # Mistral 🇫🇷 — large-context integration across lab boundaries
        "meta_evaluator": "kimi-k2-6",           # Moonshot 🇨🇳 — best value creative, reasoning-focused meta-critique
        "scoring":        "glm-5.2",             # Zhipu 🇨🇳 — AA Intel 52.6 vs ~32, $0.476/$1.496, cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.6",            # xAI 🇺🇸 — AA Intel 60.9 vs 37.6 for 4.3, $2/$6, 500K ctx
        "verifier":       "deepseek-v4-pro",     # DeepSeek 🇨🇳 — strong structured verification
        "post_synthesis_verify": "sonar-pro",  # added v3.5
        },
        "tags": ["premium", "iterative", "critique"],
    },
}

# Public alias for backward compatibility
PRESETS = _REGISTRY


def get_preset(preset_id: str) -> PipelinePreset:
    """Return a copy of the preset."""
    if preset_id not in _REGISTRY:
        raise ValueError(f"Unknown preset '{preset_id}'")
    # Return a copy to prevent mutation of the registry
    config = _REGISTRY[preset_id]
    return PipelinePreset(**config, id=preset_id)

# Cached after first load — presets are immutable at runtime (v3.4)
_preset_cache: list[PipelinePreset] | None = None


def list_presets() -> list[PipelinePreset]:
    """Return all presets (cached after first call)."""
    global _preset_cache
    if _preset_cache is None:
        _preset_cache = [get_preset(pid) for pid in sorted(_REGISTRY)]
    return _preset_cache


def invalidate_preset_cache() -> None:
    """Invalidate the preset cache. Call after modifying _REGISTRY at runtime."""
    global _preset_cache
    _preset_cache = None
