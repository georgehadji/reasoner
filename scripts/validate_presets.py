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

from reasoner.core.temperatures import PHASE_TEMPERATURES
from reasoner.domain.preset_registry import list_presets
from reasoner.infrastructure.llm.registry import (
    _REGISTRY as MODELS,
)
from reasoner.infrastructure.llm.registry import (
    bloc_of,
    honours_tuned_temperature,
    resolved_model_of,
)

# Below this, a model that silently samples at its fixed 1.0 default is far
# enough from the phase's intent to count as mis-routed. Roles at 0.7/1.0
# (perspectives, generators) are close enough that a fixed-temp model is fine.
_TEMP_TOLERANCE_FLOOR = 0.7

# Roles that inherit the "perspective" temperature rather than naming their own.
_GENERATOR_ROLES = {
    "constructive", "destructive", "systemic", "minimalist", "perspective",
    "expert_1", "expert_2", "expert_3", "expert_4",
}


def target_temperature(role: str) -> float | None:
    """Temperature a role will actually be called with, or None if untuned."""
    if role in PHASE_TEMPERATURES:
        return PHASE_TEMPERATURES[role]
    if role in _GENERATOR_ROLES or role.startswith("perspective_"):
        return PHASE_TEMPERATURES["perspective"]
    return None

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
    "hy-mt": "Tencent",
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
        "socratic", "pre_mortem", "bayesian", "dialectical", "analogical",
        "delphi", "cove", "sot", "tot", "pot", "self_discover",
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

        # ── Cross-BLOC diversity (Buyl et al. npj AI 2026) ──
        # Geopolitical bloc, not company, is the dominant ideological axis. Two
        # Chinese labs are NOT diverse. bloc_of() resolves aliases to the real
        # vendor (e.g. gemini-flash-lite → Qwen → CN).
        #
        # Invariant A: synthesis bloc ≠ scoring bloc (final voice and its pruning
        # critic must span two blocs).
        synth = preset.routing.get("synthesis")
        score = preset.routing.get("scoring")
        if synth and score:
            b_synth, b_score = bloc_of(synth), bloc_of(score)
            if b_synth != "OTHER" and b_synth == b_score:
                errors.append(
                    f"{name}: synthesis and scoring share bloc {b_synth} "
                    f"({synth} / {score}) — final voice and its critic must be cross-bloc"
                )

        # Invariant B: generator roles span ≥2 blocs, ≤2 of any single bloc.
        gen_roles: set[str] = set()
        if preset.method == "multi-perspective":
            gen_roles = {"constructive", "destructive", "systemic", "minimalist"}
        elif preset.method == "debate":
            gen_roles = {"constructive", "destructive", "systemic"}
        if gen_roles:
            blocs_used: dict[str, list[str]] = {}
            for r in gen_roles:
                model = preset.routing.get(r) or preset.primary_id
                blocs_used.setdefault(bloc_of(model), []).append(r)
            known = {b: rs for b, rs in blocs_used.items() if b != "OTHER"}
            if len(known) < 2:
                errors.append(
                    f"{name}: generator roles span <2 known blocs ({blocs_used}) "
                    f"— need cross-bloc generation"
                )
            for b, rs in known.items():
                if len(rs) > 2:
                    errors.append(
                        f"{name}: bloc {b} dominates generation ({', '.join(sorted(rs))}) "
                        f"— max 2 generator roles per bloc"
                    )

        # ── Invariant C: no model serves two phases of the same preset ──
        # Compared on the RESOLVED model string, not the alias: several aliases
        # point at the same served model (gemini-pro and claude-sonnet both ->
        # anthropic/claude-sonnet-5), so alias-level distinctness would pass
        # while the preset actually ran one model twice — the echo chamber the
        # cross-bloc invariants above exist to prevent, but cannot see.
        seen_models: dict[str, list[str]] = {}
        slots = list(preset.routing.items()) + [("primary_id", preset.primary_id)]
        for role, model_id in slots:
            if not model_id:
                continue
            seen_models.setdefault(resolved_model_of(model_id), []).append(role)
        for served, roles in seen_models.items():
            if len(roles) > 1:
                errors.append(
                    f"{name}: {served} serves {len(roles)} roles "
                    f"({', '.join(sorted(roles))}) — each model may serve at "
                    f"most one phase per preset"
                )

        # ── Invariant D: no fixed-temperature model in a low-temperature phase ──
        # Models that reject a custom temperature (OpenAI gpt-*/o-series,
        # claude-opus/sonnet/fable) do not error when routed to a tuned phase —
        # the provider just omits the parameter and the model samples at its
        # fixed 1.0 default. A synthesis role tuned to 0.5, or a fusion role
        # tuned to 0.2, silently runs twice to five times more random than
        # intended, and nothing in the response reveals it.
        for role, model_id in slots:
            if not model_id:
                continue
            target = target_temperature(role)
            if target is None or target >= _TEMP_TOLERANCE_FLOOR:
                continue
            if honours_tuned_temperature(model_id):
                continue
            errors.append(
                f"{name}: role '{role}' targets temperature {target} but "
                f"'{model_id}' ({resolved_model_of(model_id)}) ignores it and "
                f"runs at 1.0 — route a temperature-honouring model here"
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
