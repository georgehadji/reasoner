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
            "perspective_cot": "qwen3-turbo",
            "perspective_analysis": "qwen3-turbo",
            "synthesis": "deepseek-v4-pro",
            # ── Per-perspective cross-lab diversity (4 labs) ──
            "constructive":  "deepseek-v3",      # 🇨🇳 DeepSeek — $0.229/$0.343
            "destructive":   "ring-2.6-1t",      # 🇨🇳 inclusionAI — $0.075/$0.625
            "systemic":      "qwen3-max",        # 🇨🇳 Qwen/Alibaba — $0.40/$1.60
            "minimalist":    "ministral-8b",     # 🇫🇷 Mistral — $0.075/$0.20
        },
        "tags": ["budget", "balanced"],
    },
    "multi-perspective-ultra-budget": {
        "method": "multi-perspective",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "perspective_cot": "qwen3.5-9b",
            "perspective_analysis": "qwen3.5-9b",
            "synthesis": "stepfun-3.7-flash",
            # ── Per-perspective cross-lab diversity (4 labs, ultra-cheap) ──
            "constructive":  "stepfun-3.7-flash",    # 🇨🇳 StepFun — $0.20/$1.15
            "destructive":   "ling-2.6-flash-free",  # 🇨🇳 inclusionAI — FREE
            "systemic":      "qwen3.6-flash",        # 🇨🇳 Qwen — cheap flash
            "minimalist":    "ministral-8b",         # 🇫🇷 Mistral — $0.075/$0.20
        },
        "tags": ["budget", "creative", "fast"],
    },
    "multi-perspective-premium": {
        "method": "multi-perspective",
        "primary_id": "gemini-pro",
        "routing": {
            "perspective_cot": "claude-sonnet",
            "perspective_analysis": "claude-sonnet",
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "balanced", "multilingual"],
    },
    "debate-budget": {
        "method": "debate",
        "primary_id": "gemini-flash",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "argumentative", "robust"],
    },
    "debate-premium": {
        "method": "debate",
        "primary_id": "gemini-pro",
        "routing": {
            "constructive": "gemini-pro",
            "destructive": "gemini-pro",
            "systemic": "gemini-pro",
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "argumentative", "robust"],
    },
    "jury-budget": {
        "method": "jury",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "governance", "decision-making"],
    },
    "jury-premium": {
        "method": "jury",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "governance", "decision-making"],
    },
    "research-budget": {
        "method": "research",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "research", "web-search"],
    },
    "research-premium": {
        "method": "research",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
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
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "scientific", "structured"],
    },
    "scientific-premium": {
        "method": "scientific",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "scientific", "structured"],
    },
    "socratic-budget": {
        "method": "socratic",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "educational", "inquisitive"],
    },
    "socratic-premium": {
        "method": "socratic",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "educational", "inquisitive"],
    },
    "pre-mortem-budget": {
        "method": "pre-mortem",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "risk-assessment", "strategic"],
    },
    "pre-mortem-premium": {
        "method": "pre-mortem",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "risk-assessment", "strategic"],
    },
    "bayesian-budget": {
        "method": "bayesian",
        "primary_id": "anthropic/claude-3-haiku",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "analytical", "probabilistic"],
    },
    "bayesian-premium": {
        "method": "bayesian",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "analytical", "probabilistic"],
    },
    "dialectical-budget": {
        "method": "dialectical",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "argumentative", "philosophical"],
    },
    "dialectical-premium": {
        "method": "dialectical",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "argumentative", "philosophical"],
    },
    "analogical-budget": {
        "method": "analogical",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "creative", "reasoning"],
    },
    "analogical-premium": {
        "method": "analogical",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "creative", "reasoning"],
    },
    "delphi-budget": {
        "method": "delphi",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "collaborative", "forecasting"],
    },
    "delphi-premium": {
        "method": "delphi",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "collaborative", "forecasting"],
    },
    "cove-budget": {
        "method": "cove",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "verification", "fact-checking"],
    },
    "cove-premium": {
        "method": "cove",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "verification", "fact-checking"],
    },
    "sot-budget": {
        "method": "sot",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "structured-thinking", "outlining"],
    },
    "sot-premium": {
        "method": "sot",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "structured-thinking", "outlining"],
    },
    "tot-budget": {
        "method": "tot",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "problem-solving", "exploration"],
    },
    "tot-premium": {
        "method": "tot",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "problem-solving", "exploration"],
    },
    "pot-budget": {
        "method": "pot",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "programming", "code-generation"],
    },
    "pot-premium": {
        "method": "pot",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "programming", "code-generation"],
    },
    "self-discover-budget": {
        "method": "self-discover",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "reasoning", "self-improvement"],
    },
    "self-discover-premium": {
        "method": "self-discover",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "reasoning", "self-improvement"],
    },
    "subagent-budget": {
        "method": "subagent",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "multi-agent", "delegation"],
    },
    "subagent-premium": {
        "method": "subagent",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "multi-agent", "delegation"],
    },
    "writing-budget": {
        "method": "writing",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "writing", "content-creation"],
    },
    "writing-premium": {
        "method": "writing",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "writing", "content-creation"],
    },
    "article-budget": {
        "method": "article",
        "primary_id": "deepseek-v3",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "writing", "article"],
    },
    "article-premium": {
        "method": "article",
        "primary_id": "claude-sonnet",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
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
            "synthesis": "fireworks/firefunction-v2",
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
            "coding_generate": ["qwen3-coder-flash", "codestral-2508", "deepseek-v4-flash"],
            "coding_review": ["deepseek-v4-flash", "codestral-2508", "gpt-5.1-codex-mini"],
        },
        "tags": ["budget", "coding", "software-development"],
    },
    "coding-premium": {
        "method": "coding",
        "primary_id": "claude-sonnet",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "coding", "software-development"],
    },
    "cross-language-budget": {
        "method": "cross-language",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "translation", "multilingual"],
    },
    "cross-language-premium": {
        "method": "cross-language",
        "primary_id": "gemini-pro",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
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
        "primary_id": "anthropic/claude-3-haiku",
        "routing": {
            "brainstorm_cluster": "google/gemma-2-9b-it",
            "brainstorm_develop": "deepseek/deepseek-chat",
            "synthesis": "fireworks/firefunction-v2",
        },
        "fallback_routing": {
            "primary": "anthropic/claude-3-haiku",
        },
        "tags": ["budget", "creative"],
    },
    "brainstorming-premium": {
        "method": "brainstorming",
        "primary_id": "claude-sonnet",
        "routing": {
            "brainstorm_cluster": "claude-sonnet",
            "brainstorm_develop": "claude-sonnet",
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["premium", "creative"],
    },
    "image-gen-budget": {
        "method": "image-gen",
        "primary_id": "gemini-flash",
        "routing": {
            "image_generate": "riverflow-v2-fast-preview",
        },
        "tags": ["image-generation", "creative", "budget"],
    },
    "image-gen-premium": {
        "method": "image-gen",
        "primary_id": "gemini-pro",
        "routing": {
            "image_generate": "gemini-pro-image",
        },
        "tags": ["image-generation", "creative", "premium"],
    },
    "iterative-critique-budget": {
        "method": "iterative-critique",
        "primary_id": "anthropic/claude-3-haiku",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "iterative", "critique"],
    },
    "iterative-critique-premium": {
        "method": "iterative-critique",
        "primary_id": "gpt-5",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
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
