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

from reasoner.core.model_policy import WESTERN_TAG
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


# Role groups that must span blocs (Invariant B), per method. Each group is
# the set of roles one phase runs side by side as independent voices.
_PERSPECTIVES = frozenset({"constructive", "destructive", "systemic", "minimalist"})
_BLOC_GROUPS: dict[str, tuple[frozenset[str], ...]] = {
    "multi-perspective": (_PERSPECTIVES,),
    "cross-language": (_PERSPECTIVES,),
    "subagent": (_PERSPECTIVES,),
    "debate": (frozenset({"constructive", "destructive", "systemic"}),),
    "socratic": (frozenset({"constructive", "destructive"}),),
    "dialectical": (frozenset({"constructive", "destructive"}),),
    "bayesian": (frozenset({"constructive", "destructive"}),),
    # tests/unit/test_delphi_expert_routing.py: the panel spans blocs, and
    # experts are the ACR "generate" family, which needs temperature control.
    "delphi": (frozenset({"expert_1", "expert_2", "expert_3", "expert_4"}),),
    "jury": (
        frozenset({"generator_1", "generator_2", "generator_3"}),
        frozenset({"critic_1", "critic_2", "critic_3"}),
    ),
}


# Article's two editorial pairs must be cross-bloc (tests/unit/
# test_preset_bloc_diversity.py::test_article_critique_roles_are_cross_bloc,
# which names these same known violations).
_KNOWN_ARTICLE_VIOLATIONS = frozenset({
    ("article-premium", "draft_vs_critic"),
    ("article-western-premium", "draft_vs_critic"),
})


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


_VALID_METHODS = {
    "multi-perspective", "debate", "jury", "research", "scientific",
    "socratic", "pre_mortem", "bayesian", "dialectical", "analogical",
    "delphi", "cove", "sot", "tot", "pot", "self_discover",
    "writing", "article", "coding", "brainstorming", "subagent",
    "cross-language", "iterative-critique", "image-gen",
}


def check_preset(preset) -> list[str]:
    """Every rule violation for one PipelinePreset; empty when valid."""
    errors: list[str] = []
    valid_methods = _VALID_METHODS
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
            errors.append(
                f"{name}: fallback_routing['{role}']='{model_id}' not in model registry"
            )

    # Check cascading_routing chains
    for role, chain in preset.cascading_routing.items():
        for model_id in chain:
            if model_id not in MODELS:
                errors.append(
                    f"{name}: cascading_routing['{role}']='{model_id}' not in model registry"
                )

    # Cross-lab diversity for multi-perspective
    # Skip experimental presets (intentionally single-lab)
    if "test" in name or "experimental" in name:
        return errors
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
    # Checked per group: the jury critics are a second panel, judged apart
    # from the generators they score (FLOW-2).
    for gen_roles in _BLOC_GROUPS.get(preset.method, ()):
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
        # Western-only presets have one EU lab (Mistral), so lab diversity
        # forces a US majority in 4-voice groups: allow 3, still need >=1 EU.
        cap = 3 if WESTERN_TAG in preset.tags else 2
        for b, rs in known.items():
            if len(rs) > cap:
                errors.append(
                    f"{name}: bloc {b} dominates generation ({', '.join(sorted(rs))}) "
                    f"— max {cap} generator roles per bloc"
                )

    if preset.method == "delphi":
        for role in ("expert_1", "expert_2", "expert_3", "expert_4"):
            model = preset.routing.get(role)
            if model and not honours_tuned_temperature(model):
                errors.append(f"{name}: delphi {role}={model} ignores temperature")

    # tests/test_preset_validation.py::test_adversarial_roles_are_cross_bloc
    if preset.method == "iterative-critique":
        a = preset.routing.get("expert_1") or preset.primary_id
        b = preset.routing.get("expert_2") or preset.primary_id
        if bloc_of(a) == bloc_of(b) or resolved_model_of(a) == resolved_model_of(b):
            errors.append(f"{name}: iterative-critique experts {a}/{b} must be cross-bloc")
        if preset.routing.get("synthesis") in (a, b):
            errors.append(f"{name}: synthesis model also plays an expert")

    if preset.method == "article":
        r = preset.routing
        pairs = {
            "draft_vs_critic": (
                r.get("writing_draft") or preset.primary_id, r.get("article_critic")
            ),
            "humanize_vs_verifier": (
                r.get("article_humanize") or r.get("writing_assemble") or preset.primary_id,
                r.get("article_verifier"),
            ),
        }
        for pair, (writer, checker) in pairs.items():
            known = (name, pair) in _KNOWN_ARTICLE_VIOLATIONS
            if checker and not known and bloc_of(writer) == bloc_of(checker):
                errors.append(f"{name}: article {pair} share bloc {bloc_of(writer)}")

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
    return errors


def main() -> int:
    quiet = "--quiet" in sys.argv
    errors: list[str] = []

    presets = list_presets()
    if not quiet:
        print(f"Validating {len(presets)} presets...")

    for preset in presets:
        errors.extend(check_preset(preset))

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
