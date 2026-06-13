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
            "synthesis": "fireworks/firefunction-v2",
        },
        "tags": ["budget", "balanced"],
    },
    "multi-perspective-ultra-budget": {
        "method": "multi-perspective",
        "primary_id": "gemini-flash-lite",
        "routing": {
            "perspective_cot": "qwen3.5-9b",
            "perspective_analysis": "qwen3.5-9b",
            "synthesis": "fireworks/firefunction-v2",
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
        # NOTE: kimi-k2.x "code" reasoning models emit output in a separate
        # reasoning channel, leaving `content` empty → empty responses. deepseek-v3
        # returns content reliably but is too slow for the 120s coding-phase budget.
        # gemini-flash is fast, reliable, and code-capable — the right budget primary.
        "primary_id": "gemini-flash",
        "routing": {
            "synthesis": "fireworks/firefunction-v2",
        },
        # Cross-lab fallback so an empty/failed primary degrades gracefully
        # rather than crashing the pipeline (coding_generate/coding_tests have
        # no per-role fallback otherwise).
        "fallback_routing": {
            "primary": "deepseek-v3",
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
