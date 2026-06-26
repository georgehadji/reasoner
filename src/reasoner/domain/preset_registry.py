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
        "primary_id": "gemini-flash",
        "routing": {
            "perspective_cot": "mimo-v2.5",           # Xiaomi 🇨🇳 — $0.14/$0.28, cheapest 1M ctx omnimodal
            "perspective_analysis": "qwen3.6-flash",   # was qwen3-turbo (DEAD) → stronger reasoning
            "synthesis": "gpt-4o-mini",                # 🇺🇸 OpenAI — cross-bloc final voice vs CN-heavy generation/scoring
            # ── Per-perspective cross-bloc diversity (2🇨🇳 + 1🇺🇸 + 1🇫🇷) ──
            "constructive":  "deepseek-v4-flash",      # 🇨🇳 DeepSeek — $0.229/$0.343
            "destructive":   "ring-2.6-1t",      # 🇨🇳 inclusionAI — $0.075/$0.625
            "systemic":      "gpt-oss-120b",     # 🇺🇸 OpenAI open-weight — $0.039/$0.18 (was qwen3-max, added US bloc)
            "minimalist":    "ministral-8b",     # 🇫🇷 Mistral — $0.075/$0.20
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "balanced"],
    },
    "multi-perspective-ultra-budget": {
        "method": "multi-perspective",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "perspective_cot": "qwen3.5-flash",       # was qwen3.5-9b → 1M ctx (vs 262K), multimodal
            "perspective_analysis": "qwen3.6-flash",   # was qwen3.5-9b → stronger reasoning, 1M ctx
            "synthesis": "gpt-4o-mini",                # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring (was stepfun 🇨🇳)
            # ── Per-perspective cross-bloc diversity (2🇨🇳 + 1🇺🇸 + 1🇫🇷, ultra-cheap) ──
            "constructive":  "stepfun-3.7-flash",    # 🇨🇳 StepFun — $0.20/$1.15
            "destructive":   "ling-2.6-flash-free",  # 🇨🇳 inclusionAI — FREE
            "systemic":      "gpt-oss-20b",          # 🇺🇸 OpenAI open-weight — $0.029/$0.14 (was qwen3.6-flash, added US bloc)
            "minimalist":    "ministral-8b",         # 🇫🇷 Mistral — $0.075/$0.20
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "creative", "fast"],
    },
    "multi-perspective-premium": {
        "method": "multi-perspective",
        "primary_id": "gemini-pro",
        "routing": {
            "perspective_cot": "claude-sonnet",
            "perspective_analysis": "claude-sonnet",
            "synthesis": "gpt-5.5",                  # 🇺🇸 OpenAI — cross-bloc final voice (counters CN-heavy generation)
            # ── Per-perspective cross-bloc diversity (1🇺🇸 + 2🇨🇳 + 1🇪🇺) ──
            "constructive":  "claude-sonnet",    # 🇺🇸 Anthropic — $3/$15 per M
            "destructive":   "deepseek-v4-pro",  # 🇨🇳 DeepSeek — $0.435/$0.87 per M
            "systemic":      "qwen3.7-max",      # 🇨🇳 Qwen/Alibaba — $1.25/$3.75 per M
            "minimalist":    "mistral-large-3",  # 🇪🇺 Mistral — distinct EU bloc (was glm-5.2 🇨🇳)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "balanced", "multilingual"],
    },
    "debate-budget": {
        "method": "debate",
        "primary_id": "gemini-flash",
        "routing": {
            # ── Cross-bloc adversarial diversity (🇨🇳 vs 🇺🇸, 🇺🇸 judge) ──
            "constructive": "deepseek-v4-flash",    # 🇨🇳 DeepSeek — constructive argumentation
            "destructive":  "gpt-oss-120b",     # 🇺🇸 OpenAI open-weight — adversarial critique (was ring 🇨🇳, cross-bloc debate)
            "systemic":     "gemini-flash",     # 🇺🇸 Google — judging (keep)
            "synthesis": "gpt-4o-mini",         # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "argumentative", "robust"],
    },
    "debate-premium": {
        "method": "debate",
        "primary_id": "gemini-pro",
        "routing": {
            # ── Cross-bloc adversarial diversity (🇺🇸 vs 🇨🇳, 🇺🇸 judge) ──
            "constructive": "claude-sonnet",     # 🇺🇸 Anthropic — strongest argumentation
            "destructive":  "deepseek-v4-pro",   # 🇨🇳 DeepSeek — adversarial reasoning
            "systemic":     "gemini-pro",        # 🇺🇸 Google — judging (keep)
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "argumentative", "robust"],
    },
    "jury-budget": {
        "method": "jury",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "governance", "decision-making"],
    },
    "jury-premium": {
        "method": "jury",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "governance", "decision-making"],
    },
    "research-budget": {
        "method": "research",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "deep_read":      "sonar",               # Perplexity 🇺🇸 — live web grounding, $1/$1 per M, 1505ms
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "research", "web-search"],
    },
    "research-premium": {
        "method": "research",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",      # 🇨🇳 DeepSeek — cross-bloc from 🇺🇸 sonar scoring (web-grounded fact-check stays US)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "sonar-pro",           # Perplexity 🇺🇸 — live web grounding, search_context_size: high, $3/$15 per M
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "sonar-pro",           # Perplexity 🇺🇸 — web-grounded fact-checked scoring, cross-bloc from 🇨🇳 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "research", "web-search"],
    },
    # ----------------------------------------------------------------------------------
    # Specialized method presets
    # ----------------------------------------------------------------------------------
    "scientific-budget": {
        "method": "scientific",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "scientific", "structured"],
    },
    "scientific-premium": {
        "method": "scientific",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "scientific", "structured"],
    },
    "socratic-budget": {
        "method": "socratic",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "educational", "inquisitive"],
    },
    "socratic-premium": {
        "method": "socratic",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "educational", "inquisitive"],
    },
    "pre-mortem-budget": {
        "method": "pre-mortem",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "risk-assessment", "strategic"],
    },
    "pre-mortem-premium": {
        "method": "pre-mortem",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "risk-assessment", "strategic"],
    },
    "bayesian-budget": {
        "method": "bayesian",
        "primary_id": "claude-haiku",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "analytical", "probabilistic"],
    },
    "bayesian-premium": {
        "method": "bayesian",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "analytical", "probabilistic"],
    },
    "dialectical-budget": {
        "method": "dialectical",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "argumentative", "philosophical"],
    },
    "dialectical-premium": {
        "method": "dialectical",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "argumentative", "philosophical"],
    },
    "analogical-budget": {
        "method": "analogical",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "creative", "reasoning"],
    },
    "analogical-premium": {
        "method": "analogical",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "creative", "reasoning"],
    },
    "delphi-budget": {
        "method": "delphi",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "collaborative", "forecasting"],
    },
    "delphi-premium": {
        "method": "delphi",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "collaborative", "forecasting"],
    },
    "cove-budget": {
        "method": "cove",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "cove_answer":    "deepseek-v4-flash",
        "cove_revise":    "deepseek-v4-flash",
        "cove_verify":    "deepseek-v4-flash",
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "verification", "fact-checking"],
    },
    "cove-premium": {
        "method": "cove",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "cove_answer":    "deepseek-v4-pro",
        "cove_revise":    "deepseek-v4-flash",
        "cove_verify":    "deepseek-v4-pro",
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "verification", "fact-checking"],
    },
    "sot-budget": {
        "method": "sot",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "structured-thinking", "outlining"],
    },
    "sot-premium": {
        "method": "sot",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "structured-thinking", "outlining"],
    },
    "tot-budget": {
        "method": "tot",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "tot_backtrack":  "deepseek-v4-flash",
        "tot_decompose":  "deepseek-v4-flash",
        "tot_evaluate":   "deepseek-v4-flash",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "problem-solving", "exploration"],
    },
    "tot-premium": {
        "method": "tot",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "tot_backtrack":  "deepseek-v4-flash",
        "tot_decompose":  "claude-sonnet",
        "tot_evaluate":   "deepseek-v4-flash",
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "problem-solving", "exploration"],
    },
    "pot-budget": {
        "method": "pot",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "programming", "code-generation"],
    },
    "pot-premium": {
        "method": "pot",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "programming", "code-generation"],
    },
    "self-discover-budget": {
        "method": "self-discover",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "sd_adapt":       "deepseek-v4-flash",
        "sd_implement":   "deepseek-v4-flash",
        "sd_select":      "deepseek-v4-flash",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "reasoning", "self-improvement"],
    },
    "self-discover-premium": {
        "method": "self-discover",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # OpenAI 🇺🇸 — AI² Intel 54.8, 1M ctx, cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "sd_adapt":       "deepseek-v4-pro",
        "sd_implement":   "deepseek-v4-pro",
        "sd_select":      "deepseek-v4-pro",
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "reasoning", "self-improvement"],
    },
    "subagent-budget": {
        "method": "subagent",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":                     "deepseek-v4-flash",
        "meta_evaluator":             "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        "scoring":                    "deepseek-v4-flash",  # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing":             "ring-2.6-1t",
        "subagent_critique_bias":     "deepseek-v4-flash",
        "subagent_critique_counter":  "deepseek-v4-flash",
        "subagent_critique_evidence": "deepseek-v4-flash",
        "subagent_critique_logic":    "deepseek-v4-flash",
        "subagent_decomposition":     "deepseek-v4-flash",
        "verifier":                   "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        },
        "tags": ["budget", "multi-agent", "delegation"],
    },
    "subagent-premium": {
        "method": "subagent",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":                  "claude-sonnet",
        "fusion":                     "deepseek-v4-pro",
        "meta_evaluator":             "qwen3.7-max",  # 🇨🇳 Qwen — cross-bloc from 🇺🇸 synthesis
        "scoring":                    "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing":             "claude-sonnet",
        "subagent_critique_bias":     "deepseek-v4-pro",
        "subagent_critique_counter":  "deepseek-v4-pro",
        "subagent_critique_evidence": "deepseek-v4-pro",
        "subagent_critique_logic":    "deepseek-v4-pro",
        "subagent_decomposition":     "claude-sonnet",
        "verifier":                   "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc from 🇺🇸 synthesis
        },
        "tags": ["premium", "multi-agent", "delegation"],
    },
    "writing-budget": {
        "method": "writing",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":            "deepseek-v4-flash",
        "meta_evaluator":    "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        "scoring":           "deepseek-v4-flash",  # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing":    "ring-2.6-1t",
        "verifier":          "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        "writing_assemble":  "deepseek-v4-flash",
        "writing_factcheck": "deepseek-v4-flash",
        "writing_outline":   "deepseek-v4-flash",
        },
        "tags": ["budget", "writing", "content-creation"],
    },
    "writing-premium": {
        "method": "writing",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":         "claude-sonnet",
        "fusion":            "deepseek-v4-pro",
        "meta_evaluator":    "qwen3.7-max",  # 🇨🇳 Qwen — cross-bloc from 🇺🇸 synthesis
        "scoring":           "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing":    "claude-sonnet",
        "verifier":          "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc from 🇺🇸 synthesis
        "writing_assemble":  "claude-sonnet",
        "writing_factcheck": "deepseek-v4-pro",
        "writing_outline":   "claude-sonnet",
        },
        "tags": ["premium", "writing", "content-creation"],
    },
    "article-budget": {
        "method": "article",
        "primary_id": "deepseek-v4-flash",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "article_critic":   "deepseek-v4-flash",
        "article_verifier": "deepseek-v4-flash",
        "fusion":           "deepseek-v4-flash",
        "meta_evaluator":   "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        "scoring":          "deepseek-v4-flash",  # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing":   "ring-2.6-1t",
        "verifier":         "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        },
        "tags": ["budget", "writing", "article"],
    },
    "article-premium": {
        "method": "article",
        "primary_id": "claude-sonnet",
        "routing": {
            "synthesis": "gpt-5.5",              # OpenAI 🇺🇸 — AI² Intel 54.8, 1M ctx, cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "article_critic":    "deepseek-v4-pro",
        "article_decompose": "claude-sonnet",
        "article_verifier":  "deepseek-v4-pro",
        "deep_read":         "claude-sonnet",
        "fusion":            "deepseek-v4-pro",
        "meta_evaluator":    "qwen3.7-max",  # 🇨🇳 Qwen — cross-bloc from 🇺🇸 synthesis
        "scoring":           "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing":    "claude-sonnet",
        "verifier":          "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc from 🇺🇸 synthesis
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
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "coding_assemble": "deepseek-v4-flash",
        "coding_review":   "deepseek-v4-flash",
        "coding_spec":     "qwen3-coder-flash",
        "coding_tests":    "deepseek-v4-flash",
        "fusion":          "deepseek-v4-flash",
        "meta_evaluator":  "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        "scoring":         "deepseek-v4-flash",  # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing":  "ring-2.6-1t",
        "verifier":        "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        },
        # Single-model fallback for the lighter coding roles (spec/tests/assemble)
        # that route through primary. codestral-2508 is fast (~3s), code-specialized,
        # and cross-lab (Mistral vs Qwen).
        "fallback_routing": {
            "primary": "codestral-2508",
        },
        # Multi-model fallback chains (tried in order, with a quality gate that skips
        # empty/degraded/low-quality responses before moving to the next model):
        #   - coding_generate: 1 primary + 2 fallbacks (Qwen → Mistral → DeepSeek)
        #   - coding_review:   cross-lab critique (DeepSeek → Mistral → OpenAI)
        # deepseek-v4-flash leads both chains: reliable content (verified 2/2, no empty
        # trap), cheapest model here ($0.09/$0.18/M), 1M context, cross-lab from the Qwen
        # generator. gpt-5.1-codex-mini is demoted to a last-resort review slot — it is
        # codex-class but intermittently returns empty content on larger prompts (observed
        # live), so the quality gate handles it only as a final fallback, never as a primary.
        "cascading_routing": {
            "coding_generate": ["qwen3-coder-flash", "codestral-2508", "grok-build-0.1", "deepseek-v4-flash"],
            "coding_review": ["deepseek-v4-flash", "mimo-v2.5-pro", "codestral-2508", "gpt-5.1-codex-mini"],
        },
        "tags": ["budget", "coding", "software-development"],
    },
    "coding-premium": {
        "method": "coding",
        "primary_id": "claude-sonnet",
        "routing": {
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "coding_assemble": "deepseek-v4-flash",
        "coding_review":   "deepseek-v4-flash",
        "coding_spec":     "claude-sonnet",
        "coding_tests":    "deepseek-v4-flash",
        "deep_read":       "claude-sonnet",
        "fusion":          "deepseek-v4-pro",
        "meta_evaluator":  "qwen3.7-max",  # 🇨🇳 Qwen — cross-bloc from 🇺🇸 synthesis
        "scoring":         "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing":  "claude-sonnet",
        "verifier":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc from 🇺🇸 synthesis
        },
        "tags": ["premium", "coding", "software-development"],
    },
    "cross-language-budget": {
        "method": "cross-language",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "translation", "multilingual"],
    },
    "cross-language-premium": {
        "method": "cross-language",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "glm-5.2",              # Zhipu 🇨🇳 — multilingual strength; cross-bloc from 🇺🇸 scoring
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "gemini-pro-real",     # 🇺🇸 Google — multilingual cross-bloc critic of 🇨🇳 synthesis (was qwen 🇨🇳)
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "glm-5.2",             # Zhipu 🇨🇳 — distinct training signal for multilingual verification
        },
        "tags": ["premium", "translation", "multilingual"],
    },
    # ----------------------------------------------------------------------------------
    # Special-purpose / Experimental presets
    # ----------------------------------------------------------------------------------
    "nvidia-nemotron-test": {
        "method": "multi-perspective",
        "primary_id": "nvidia-nemotron-super",
        "routing": {
            "perspective_cot": "nvidia-nemotron-super",
            "perspective_analysis": "nvidia-nemotron-super",
            "synthesis": "nvidia-nemotron-super",
        },
        "tags": ["experimental", "nvidia"],
    },
    "brainstorming-budget": {
        "method": "brainstorming",
        "primary_id": "claude-haiku",
        "routing": {
            "brainstorm_cluster": "google/gemma-2-9b-it",
            "brainstorm_develop": "deepseek-v4-flash",
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
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
            "brainstorm_cluster": "claude-sonnet",
            "brainstorm_develop": "claude-sonnet",
            "synthesis": "gpt-5.5",              # 🇺🇸 OpenAI — cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "creative"],
    },
    "image-gen-budget": {
        "method": "image-gen",
        "primary_id": "gemini-flash",
        "routing": {
            "image_generate": "gemini-flash-image",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["image-generation", "creative", "budget"],
    },
    "image-gen-premium": {
        "method": "image-gen",
        "primary_id": "gemini-pro",
        "routing": {
            "image_generate": "gemini-pro-image",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["image-generation", "creative", "premium"],
    },
    "iterative-critique-budget": {
        "method": "iterative-critique",
        "primary_id": "claude-haiku",
        "routing": {
            "synthesis": "gpt-4o-mini",          # 🇺🇸 OpenAI — cross-bloc final voice vs CN scoring
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v4-flash",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v4-flash",        # 🇨🇳 DeepSeek — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable
        },
        "tags": ["budget", "iterative", "critique"],
    },
    "iterative-critique-premium": {
        "method": "iterative-critique",
        "primary_id": "gpt-5",
        "routing": {
            "synthesis": "gpt-5.5",              # OpenAI 🇺🇸 — AI² Intel 54.8, 1M ctx, cross-bloc final voice
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # 🇨🇳 Qwen — cross-bloc critic of 🇺🇸 synthesis
        "stress_testing": "grok-4.3",             # xAI 🇺🇸 — τ²-Bench 97.7% adversarial, $1.25/$2.50
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
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
