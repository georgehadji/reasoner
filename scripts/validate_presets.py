#!/usr/bin/env python3
"""Validate all presets in the registry.

Checks:
  1. All routing role names are in _KNOWN_ROUTING_ROLES
  2. All model aliases (primary_id, routing values, fallback_routing values,
     cascading_routing chains) exist in the model registry
  3. All preset methods are valid
  4. Cross-lab diversity: no same-lab violations in multi-perspective/debate

Usage:
  python scripts/validate_presets.py          # validate all presets
  python scripts/validate_presets.py --quiet  # only print errors
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from reasoner.domain.preset_registry import list_presets, _REGISTRY as PRESETS
from reasoner.domain.preset_core import _KNOWN_ROUTING_ROLES
from reasoner.infrastructure.llm.registry import _REGISTRY as MODELS

# ── Lab taxonomy for cross-lab diversity check ──
_LABS: dict[str, str] = {
    "deepseek": "DeepSeek", "claude": "Anthropic", "gpt-": "OpenAI",
    "o3": "OpenAI", "gemini": "Google", "gemma": "Google",
    "grok": "xAI", "qwen": "Qwen", "glm": "Zhipu", "kimi": "Moonshot",
    "stepfun": "StepFun", "ring-": "inclusionAI", "ling-": "inclusionAI",
    "mistral": "Mistral", "ministral": "Mistral", "codestral": "Mistral",
    "devstral": "Mistral", "minimax": "MiniMax", "nvidia": "NVIDIA",
    "nemotron": "NVIDIA", "sonar": "Perplexity", "llama": "Meta",
    "mimo": "Xiaomi", "seed-": "ByteDance", "hy3": "Tencent",
    "qianfan": "Baidu", "nex-": "NexAGI", "arcee": "Arcee",
    "tngtech": "TNG", "flux.": "BFL", "riverflow": "Sourceful",
    "recraft": "Recraft", "mai-": "Microsoft",
}

def get_lab(model: str) -> str:
    for prefix, lab in _LABS.items():
        if model.startswith(prefix):
            return lab
    return "UNKNOWN"


def main() -> int:
    quiet = "--quiet" in sys.argv
    errors: list[str] = []

    presets = list_presets()
    if not quiet:
        print(f"Validating {len(presets)} presets...")

    valid_methods = {
        "multi-perspective", "debate", "jury", "research", "scientific",
        "socratic", "pre-mortem", "bayesian", "dialectical", "analogical",
        "delphi", "cove", "sot", "tot", "pot", "self-discover",
        "writing", "article", "coding", "brainstorming", "subagent",
        "cross-language", "iterative-critique", "image-gen",
    }

    for preset in presets:
        name = preset.id

        # Check method
        if preset.method not in valid_methods:
            errors.append(f"{name}: unknown method '{preset.method}'")

        # Check primary_id
        if preset.primary_id not in MODELS:
            errors.append(f"{name}: primary_id='{preset.primary_id}' not in model registry")

        # Check routing values (keys already validated by __post_init__)
        for role, model_id in preset.routing.items():
            if model_id not in MODELS:
                errors.append(f"{name}: routing['{role}']='{model_id}' not in model registry")

        # Check fallback_routing
        for role, model_id in preset.fallback_routing.items():
            if model_id not in MODELS:
                errors.append(f"{name}: fallback_routing['{role}']='{model_id}' not in model registry")

        # Check cascading_routing chains
        for role, chain in preset.cascading_routing.items():
            for model_id in chain:
                if model_id not in MODELS:
                    errors.append(f"{name}: cascading_routing['{role}']='{model_id}' not in model registry")

        # Cross-lab diversity for multi-perspective
        # Skip experimental presets (intentionally single-lab)
        if "test" in name or "experimental" in name:
            continue
        if preset.method == "multi-perspective":
            perspectives = {"constructive", "destructive", "systemic", "minimalist"}
            labs_used: dict[str, list[str]] = {}
            for p in perspectives:
                model = preset.routing.get(p) or preset.primary_id
                lab = get_lab(model)
                labs_used.setdefault(lab, []).append(p)
            for lab, roles in labs_used.items():
                if len(roles) >= 2 and lab != "UNKNOWN":
                    errors.append(
                        f"{name}: same-lab violation — {lab} used for {', '.join(roles)}"
                    )

        # Cross-lab diversity for debate
        if preset.method == "debate":
            debate_roles = {"constructive", "destructive", "systemic"}
            labs_used = {}
            for r in debate_roles:
                model = preset.routing.get(r) or preset.primary_id
                lab = get_lab(model)
                labs_used.setdefault(lab, []).append(r)
            for lab, roles in labs_used.items():
                if len(roles) >= 3 and lab != "UNKNOWN":
                    errors.append(
                        f"{name}: all debate roles use same lab — {lab}"
                    )

    if errors:
        print(f"\n❌ {len(errors)} VALIDATION ERRORS:")
        for e in errors:
            print(f"  • {e}")
        return 1
    else:
        if not quiet:
            print(f"✅ All {len(presets)} presets valid")
        return 0


if __name__ == "__main__":
    sys.exit(main())
