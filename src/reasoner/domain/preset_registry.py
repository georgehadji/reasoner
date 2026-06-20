from __future__ import annotations

from reasoner.domain.preset_core import PipelinePreset

# ======================================================================================
#  NOTE: When adding a new preset, run `python scripts/validate_presets.py`
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
            "synthesis": "deepseek-v4-pro",
            # ── Per-perspective cross-lab diversity (4 labs) ──
            "constructive":  "deepseek-v3",      # 🇨🇳 DeepSeek — $0.229/$0.343
            "destructive":   "ring-2.6-1t",      # 🇨🇳 inclusionAI — $0.075/$0.625
            "systemic":      "qwen3-max",        # 🇨🇳 Qwen/Alibaba — $0.40/$1.60
            "minimalist":    "ministral-8b",     # 🇫🇷 Mistral — $0.075/$0.20
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "balanced"],
    },
    "multi-perspective-ultra-budget": {
        "method": "multi-perspective",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "perspective_cot": "qwen3.5-flash",       # was qwen3.5-9b → 1M ctx (vs 262K), multimodal
            "perspective_analysis": "qwen3.6-flash",   # was qwen3.5-9b → stronger reasoning, 1M ctx
            "synthesis": "stepfun-3.7-flash",
            # ── Per-perspective cross-lab diversity (4 labs, ultra-cheap) ──
            "constructive":  "stepfun-3.7-flash",    # 🇨🇳 StepFun — $0.20/$1.15
            "destructive":   "ling-2.6-flash-free",  # 🇨🇳 inclusionAI — FREE
            "systemic":      "qwen3.6-flash",        # 🇨🇳 Qwen — cheap flash
            "minimalist":    "ministral-8b",         # 🇫🇷 Mistral — $0.075/$0.20
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "creative", "fast"],
    },
    "multi-perspective-premium": {
        "method": "multi-perspective",
        "primary_id": "gemini-pro",
        "routing": {
            "perspective_cot": "claude-sonnet",
            "perspective_analysis": "claude-sonnet",
            "synthesis": "deepseek-v4-pro",
            # ── Per-perspective cross-lab diversity (4 labs, premium) ──
            "constructive":  "claude-sonnet",    # 🇺🇸 Anthropic — $3/$15 per M
            "destructive":   "deepseek-v4-pro",  # 🇨🇳 DeepSeek — $0.435/$0.87 per M
            "systemic":      "qwen3.7-max",      # 🇨🇳 Qwen/Alibaba — $1.25/$3.75 per M
            "minimalist":    "mistral-large-3",  # 🇫🇷 Mistral — $2/$8 per M
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "balanced", "multilingual"],
    },
    "debate-budget": {
        "method": "debate",
        "primary_id": "gemini-flash",
        "routing": {
            # ── Cross-lab adversarial diversity (3 labs, budget) ──
            "constructive": "deepseek-v3.2",    # 🇨🇳 DeepSeek — constructive argumentation
            "destructive":  "ring-2.6-1t",      # 🇨🇳 inclusionAI — adversarial critique
            "systemic":     "gemini-flash",     # 🇺🇸 Google — judging (keep)
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "argumentative", "robust"],
    },
    "debate-premium": {
        "method": "debate",
        "primary_id": "gemini-pro",
        "routing": {
            # ── Cross-lab adversarial diversity (3 labs) ──
            "constructive": "claude-sonnet",     # 🇺🇸 Anthropic — strongest argumentation
            "destructive":  "deepseek-v4-pro",   # 🇨🇳 DeepSeek — adversarial reasoning
            "systemic":     "gemini-pro",        # 🇺🇸 Google — judging (keep)
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "argumentative", "robust"],
    },
    "jury-budget": {
        "method": "jury",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "governance", "decision-making"],
    },
    "jury-premium": {
        "method": "jury",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "governance", "decision-making"],
    },
    "research-budget": {
        "method": "research",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "research", "web-search"],
    },
    "research-premium": {
        "method": "research",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
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
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "scientific", "structured"],
    },
    "scientific-premium": {
        "method": "scientific",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "scientific", "structured"],
    },
    "socratic-budget": {
        "method": "socratic",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "educational", "inquisitive"],
    },
    "socratic-premium": {
        "method": "socratic",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "educational", "inquisitive"],
    },
    "pre-mortem-budget": {
        "method": "pre-mortem",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "risk-assessment", "strategic"],
    },
    "pre-mortem-premium": {
        "method": "pre-mortem",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "risk-assessment", "strategic"],
    },
    "bayesian-budget": {
        "method": "bayesian",
        "primary_id": "claude-haiku",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "analytical", "probabilistic"],
    },
    "bayesian-premium": {
        "method": "bayesian",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "analytical", "probabilistic"],
    },
    "dialectical-budget": {
        "method": "dialectical",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "argumentative", "philosophical"],
    },
    "dialectical-premium": {
        "method": "dialectical",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "argumentative", "philosophical"],
    },
    "analogical-budget": {
        "method": "analogical",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "creative", "reasoning"],
    },
    "analogical-premium": {
        "method": "analogical",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "creative", "reasoning"],
    },
    "delphi-budget": {
        "method": "delphi",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "collaborative", "forecasting"],
    },
    "delphi-premium": {
        "method": "delphi",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "collaborative", "forecasting"],
    },
    "cove-budget": {
        "method": "cove",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "cove_answer":    "deepseek-v3.2",
        "cove_revise":    "deepseek-v3.2",
        "cove_verify":    "deepseek-v3.2",
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "verification", "fact-checking"],
    },
    "cove-premium": {
        "method": "cove",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "cove_answer":    "deepseek-v4-pro",
        "cove_revise":    "deepseek-v3.2",
        "cove_verify":    "deepseek-v4-pro",
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "verification", "fact-checking"],
    },
    "sot-budget": {
        "method": "sot",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "structured-thinking", "outlining"],
    },
    "sot-premium": {
        "method": "sot",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "structured-thinking", "outlining"],
    },
    "tot-budget": {
        "method": "tot",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "tot_backtrack":  "deepseek-v3.2",
        "tot_decompose":  "deepseek-v3.2",
        "tot_evaluate":   "deepseek-v3.2",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "problem-solving", "exploration"],
    },
    "tot-premium": {
        "method": "tot",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "tot_backtrack":  "deepseek-v3.2",
        "tot_decompose":  "claude-sonnet",
        "tot_evaluate":   "deepseek-v3.2",
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "problem-solving", "exploration"],
    },
    "pot-budget": {
        "method": "pot",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "programming", "code-generation"],
    },
    "pot-premium": {
        "method": "pot",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "programming", "code-generation"],
    },
    "self-discover-budget": {
        "method": "self-discover",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "sd_adapt":       "deepseek-v3.2",
        "sd_implement":   "deepseek-v3.2",
        "sd_select":      "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "reasoning", "self-improvement"],
    },
    "self-discover-premium": {
        "method": "self-discover",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "gpt-5.5",              # OpenAI 🇺🇸 — AI² Intel 54.8, 1M ctx (was deepseek-v4-pro)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "sd_adapt":       "deepseek-v4-pro",
        "sd_implement":   "deepseek-v4-pro",
        "sd_select":      "deepseek-v4-pro",
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "reasoning", "self-improvement"],
    },
    "subagent-budget": {
        "method": "subagent",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":                     "deepseek-v3.2",
        "meta_evaluator":             "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        "scoring":                    "deepseek-v3.2",
        "stress_testing":             "ring-2.6-1t",
        "subagent_critique_bias":     "deepseek-v3.2",
        "subagent_critique_counter":  "deepseek-v3.2",
        "subagent_critique_evidence": "deepseek-v3.2",
        "subagent_critique_logic":    "deepseek-v3.2",
        "subagent_decomposition":     "deepseek-v3.2",
        "verifier":                   "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        },
        "tags": ["budget", "multi-agent", "delegation"],
    },
    "subagent-premium": {
        "method": "subagent",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":                  "claude-sonnet",
        "fusion":                     "deepseek-v4-pro",
        "meta_evaluator":             "qwen3.7-max",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "scoring":                    "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing":             "claude-sonnet",
        "subagent_critique_bias":     "deepseek-v4-pro",
        "subagent_critique_counter":  "deepseek-v4-pro",
        "subagent_critique_evidence": "deepseek-v4-pro",
        "subagent_critique_logic":    "deepseek-v4-pro",
        "subagent_decomposition":     "claude-sonnet",
        "verifier":                   "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        },
        "tags": ["premium", "multi-agent", "delegation"],
    },
    "writing-budget": {
        "method": "writing",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":            "deepseek-v3.2",
        "meta_evaluator":    "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        "scoring":           "deepseek-v3.2",
        "stress_testing":    "ring-2.6-1t",
        "verifier":          "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        "writing_assemble":  "deepseek-v3.2",
        "writing_factcheck": "deepseek-v3.2",
        "writing_outline":   "deepseek-v3.2",
        },
        "tags": ["budget", "writing", "content-creation"],
    },
    "writing-premium": {
        "method": "writing",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":         "claude-sonnet",
        "fusion":            "deepseek-v4-pro",
        "meta_evaluator":    "qwen3.7-max",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "scoring":           "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing":    "claude-sonnet",
        "verifier":          "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "writing_assemble":  "claude-sonnet",
        "writing_factcheck": "deepseek-v4-pro",
        "writing_outline":   "claude-sonnet",
        },
        "tags": ["premium", "writing", "content-creation"],
    },
    "article-budget": {
        "method": "article",
        "primary_id": "deepseek-v3",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "article_critic":   "deepseek-v3.2",
        "article_verifier": "deepseek-v3.2",
        "fusion":           "deepseek-v3.2",
        "meta_evaluator":   "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        "scoring":          "deepseek-v3.2",
        "stress_testing":   "ring-2.6-1t",
        "verifier":         "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        },
        "tags": ["budget", "writing", "article"],
    },
    "article-premium": {
        "method": "article",
        "primary_id": "claude-sonnet",
        "routing": {
            "synthesis": "gpt-5.5",              # OpenAI 🇺🇸 — AI² Intel 54.8, 1M ctx (was deepseek-v4-pro)
        # ── Reasoning model assignments (premium, v3.4) ──
        "article_critic":    "deepseek-v4-pro",
        "article_decompose": "claude-sonnet",
        "article_verifier":  "deepseek-v4-pro",
        "deep_read":         "claude-sonnet",
        "fusion":            "deepseek-v4-pro",
        "meta_evaluator":    "qwen3.7-max",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "scoring":           "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing":    "claude-sonnet",
        "verifier":          "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        },
        "tags": ["premium", "writing", "article"],
    },
    "coding-budget": {
        "method": "coding",
        # qwen3-coder-flash is a dedicated coding model: reliable content,
        # fast (~11s/call, well within the 120s coding-phase budget), and far
        # stronger at code than a general-purpose flash model.
        # NOTE: avoid kimi-k2.x "code" and glm-4.7-flash here — both are reasoning
        # models that emit output in a separate channel, leaving `content` empty.
        # deepseek-v3 is reliable but too slow (times out at 120s).
        "primary_id": "qwen3-coder-flash",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "coding_assemble": "deepseek-v4-flash",
        "coding_review":   "deepseek-v4-flash",
        "coding_spec":     "qwen3-coder-flash",
        "coding_tests":    "deepseek-v4-flash",
        "fusion":          "deepseek-v3.2",
        "meta_evaluator":  "qwen3.7-plus",  # cross-lab from DeepSeek scoring
        "scoring":         "deepseek-v3.2",
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
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "coding_assemble": "deepseek-v4-flash",
        "coding_review":   "deepseek-v4-flash",
        "coding_spec":     "claude-sonnet",
        "coding_tests":    "deepseek-v4-flash",
        "deep_read":       "claude-sonnet",
        "fusion":          "deepseek-v4-pro",
        "meta_evaluator":  "qwen3.7-max",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "scoring":         "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing":  "claude-sonnet",
        "verifier":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        },
        "tags": ["premium", "coding", "software-development"],
    },
    "cross-language-budget": {
        "method": "cross-language",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "translation", "multilingual"],
    },
    "cross-language-premium": {
        "method": "cross-language",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
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
            "brainstorm_develop": "deepseek/deepseek-chat",
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
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
            "synthesis": "deepseek-v4-pro",
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["premium", "creative"],
    },
    "image-gen-budget": {
        "method": "image-gen",
        "primary_id": "gemini-flash",
        "routing": {
            "image_generate": "riverflow-v2-fast-preview",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
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
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "verifier":       "grok-4.20",           # xAI 🇺🇸 — lowest hallucination rate, 2M ctx
        },
        "tags": ["image-generation", "creative", "premium"],
    },
    "iterative-critique-budget": {
        "method": "iterative-critique",
        "primary_id": "claude-haiku",
        "routing": {
            "synthesis": "gpt-4o-mini",
        # ── Reasoning model assignments (budget, v3.4) ──
        "fusion":         "deepseek-v3.2",
        "meta_evaluator": "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget)
        "scoring":        "deepseek-v3.2",
        "stress_testing": "ring-2.6-1t",
        "verifier":       "qwen3.5-flash",           # Qwen 🇨🇳 — fast & reliable (nemotron FREE too slow for budget) (🇨🇳 → 🇨🇳 different labs)
        },
        "tags": ["budget", "iterative", "critique"],
    },
    "iterative-critique-premium": {
        "method": "iterative-critique",
        "primary_id": "gpt-5",
        "routing": {
            "synthesis": "gpt-5.5",              # OpenAI 🇺🇸 — AI² Intel 54.8, 1M ctx (was deepseek-v4-pro)
        # ── Reasoning model assignments (premium, v3.4) ──
        "deep_read":      "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
        "fusion":         "deepseek-v4-pro",
        "meta_evaluator": "minimax-m3",          # MiniMax 🇨🇳 — AI² Intel 44.4, $0.30/$1.20 (3× cheaper than qwen3.7-max)
        "scoring":        "qwen3-max-thinking",  # cross-lab from synthesis (DeepSeek 🇨🇳 → Qwen 🇨🇳)
        "stress_testing": "gemini-pro-real",     # Google 🇺🇸 — frontier reasoning, AI² Intel 46.5
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

def list_presets() -> list[PipelinePreset]:
    """Return all presets."""
    return [get_preset(pid) for pid in sorted(_REGISTRY)]
