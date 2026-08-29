"""Default role requirement vectors for ACR (ACR Phase 3).

Defines what capability weights each pipeline role needs.
These are the default values used by the UtilityScorer when no
custom requirements are provided.

Coverage: every role in ``domain.preset_core._KNOWN_ROUTING_ROLES`` resolves to
a real requirement — either a hand-tuned entry below, or its family default.
New roles inherit a family by prefix, so adding one does not silently fall
through to a generic vector. ``tests/unit/test_acr_coverage.py`` enforces this.
"""

from __future__ import annotations

from dataclasses import dataclass

from reasoner.domain.task_requirements import TaskConstraints, TaskRequirement

# ── Shared constraint sets ────────────────────────────────────────────────────

_SAMPLED = TaskConstraints(requires_temperature=True)
"""Roles whose value comes from *sampling* diversity (Phase 2 perspectives run
at T=1.0). A fixed-temperature model cannot do the job, so exclude it."""

_ANY = TaskConstraints(requires_temperature=False)
"""Temperature control is optional. Most roles: a fixed-temperature model is
perfectly usable, and demanding control would bar claude-sonnet and
gpt-5.6-luna — the two most-routed models in the registry — from every role."""

_LONG = TaskConstraints(min_context_tokens=32_000, requires_temperature=False)
"""Roles that integrate the whole run (synthesis and assembly)."""

# ── Role Requirements ─────────────────────────────────────────────────────────

# Each entry maps a role name → TaskRequirement with capability weights
# and hard constraints.
#
# Capability dimensions:
#   reasoning       — multi-step logical inference, puzzle solving
#   creativity      — novel idea generation, divergent thinking
#   critical_thinking — argument analysis, fallacy detection
#   writing         — prose composition, clarity, style
#   coding          — code generation and review
#   consistency     — same output for same input, low variance
#   long_context    — handling large token windows, needle-in-haystack
#   json_output     — structured output compliance
#   knowledge       — factual recall, domain expertise

_ROLE_REQUIREMENTS: dict[str, TaskRequirement] = {
    # ── Perspective generation (Phase 2) ──
    "constructive": TaskRequirement(
        role="constructive",
        capability_weights={"reasoning": 0.7, "creativity": 0.8, "writing": 0.6},
        constraints=_SAMPLED,
    ),
    "destructive": TaskRequirement(
        role="destructive",
        capability_weights={"reasoning": 0.9, "critical_thinking": 0.9, "writing": 0.5},
        constraints=_SAMPLED,
    ),
    "systemic": TaskRequirement(
        role="systemic",
        capability_weights={"reasoning": 0.8, "long_context": 0.7, "writing": 0.5},
        constraints=_SAMPLED,
    ),
    "minimalist": TaskRequirement(
        role="minimalist",
        capability_weights={"reasoning": 0.6, "creativity": 0.3, "writing": 0.4},
        constraints=_SAMPLED,
    ),
    "empirical": TaskRequirement(
        role="empirical",
        capability_weights={"reasoning": 0.9, "knowledge": 0.8, "writing": 0.5},
        constraints=_SAMPLED,
    ),
    "financial": TaskRequirement(
        role="financial",
        capability_weights={"reasoning": 0.85, "knowledge": 0.8, "writing": 0.5},
        constraints=_SAMPLED,
    ),
    "environmental": TaskRequirement(
        role="environmental",
        capability_weights={"reasoning": 0.75, "knowledge": 0.8, "writing": 0.6},
        constraints=_SAMPLED,
    ),
    "ethical": TaskRequirement(
        role="ethical",
        capability_weights={"reasoning": 0.8, "critical_thinking": 0.9, "writing": 0.7},
        constraints=_SAMPLED,
    ),
    "technical": TaskRequirement(
        role="technical",
        capability_weights={"reasoning": 0.9, "coding": 0.7, "writing": 0.4},
        constraints=_SAMPLED,
    ),
    "practical": TaskRequirement(
        role="practical",
        capability_weights={"reasoning": 0.7, "knowledge": 0.6, "writing": 0.5},
        constraints=_SAMPLED,
    ),
    # ── Debate phases ──
    "opening": TaskRequirement(
        role="opening",
        capability_weights={"reasoning": 0.8, "writing": 0.8, "creativity": 0.6},
        constraints=_SAMPLED,
    ),
    "rebuttal": TaskRequirement(
        role="rebuttal",
        capability_weights={"reasoning": 0.9, "critical_thinking": 0.9, "writing": 0.6},
        constraints=_SAMPLED,
    ),
    "judge": TaskRequirement(
        role="judge",
        capability_weights={"reasoning": 0.9, "consistency": 0.9, "writing": 0.7},
        constraints=_ANY,
    ),
    # ── Jury phases ──
    "generator": TaskRequirement(
        role="generator",
        capability_weights={"reasoning": 0.7, "creativity": 0.8, "writing": 0.6},
        constraints=_SAMPLED,
    ),
    "critic": TaskRequirement(
        role="critic",
        capability_weights={"reasoning": 0.9, "critical_thinking": 0.9, "writing": 0.5},
        constraints=_ANY,
    ),
    "verifier": TaskRequirement(
        role="verifier",
        capability_weights={"reasoning": 0.9, "consistency": 0.9, "json_output": 0.7},
        constraints=_ANY,
    ),
    # ── Scoring (Phase 3) ──
    "scoring": TaskRequirement(
        role="scoring",
        capability_weights={"reasoning": 0.9, "consistency": 0.9, "json_output": 0.8},
        constraints=_ANY,
    ),
    # ── Stress testing (Phase 4) ──
    "stress_test_optimal": TaskRequirement(
        role="stress_test_optimal",
        capability_weights={"reasoning": 0.8, "creativity": 0.6, "writing": 0.5},
        constraints=_ANY,
    ),
    "stress_test_constraint": TaskRequirement(
        role="stress_test_constraint",
        capability_weights={"reasoning": 0.9, "critical_thinking": 0.8, "writing": 0.4},
        constraints=_ANY,
    ),
    "stress_test_adversarial": TaskRequirement(
        role="stress_test_adversarial",
        capability_weights={"reasoning": 0.9, "critical_thinking": 0.9, "creativity": 0.5},
        constraints=_ANY,
    ),
    # ── Synthesis (Phase 5) ──
    "synthesis": TaskRequirement(
        role="synthesis",
        capability_weights={"reasoning": 0.9, "writing": 0.9, "long_context": 0.7},
        constraints=_LONG,
    ),
    # ── Classification (Phase 0) ──
    "classification": TaskRequirement(
        role="classification",
        capability_weights={"reasoning": 0.6, "consistency": 0.7, "json_output": 0.8},
        constraints=_ANY,
    ),
    # ── Decomposition (Phase 1) ──
    "decomposition": TaskRequirement(
        role="decomposition",
        capability_weights={"reasoning": 0.85, "long_context": 0.6, "writing": 0.5},
        constraints=_ANY,
    ),
    # ── Enhancement sub-agents ──
    "context_enrichment": TaskRequirement(
        role="context_enrichment",
        capability_weights={"reasoning": 0.7, "knowledge": 0.8, "writing": 0.6},
        constraints=_ANY,
    ),
    "ambiguity_detection": TaskRequirement(
        role="ambiguity_detection",
        capability_weights={"reasoning": 0.8, "critical_thinking": 0.8, "json_output": 0.6},
        constraints=_ANY,
    ),
    "scope_narrowing": TaskRequirement(
        role="scope_narrowing",
        capability_weights={"reasoning": 0.8, "writing": 0.5, "consistency": 0.6},
        constraints=_ANY,
    ),
    # ── Research ──
    "research_query": TaskRequirement(
        role="research_query",
        capability_weights={"reasoning": 0.6, "knowledge": 0.5, "json_output": 0.7},
        constraints=_ANY,
    ),
    "research_synthesis": TaskRequirement(
        role="research_synthesis",
        capability_weights={"reasoning": 0.8, "writing": 0.8, "long_context": 0.7},
        constraints=_LONG,
    ),
}

# ── Role families ─────────────────────────────────────────────────────────────
# Every routing role that has no hand-tuned entry above belongs to exactly one
# family. Families exist so a new role — or a new method's worth of roles —
# inherits a defensible vector instead of the generic catch-all.


@dataclass(frozen=True)
class _Family:
    """A capability vector plus constraints shared by a group of roles."""

    weights: dict[str, float]
    constraints: TaskConstraints


_FAMILIES: dict[str, _Family] = {
    # Divergent generation — sampling diversity is the product.
    "generate": _Family(
        {"reasoning": 0.7, "creativity": 0.8, "writing": 0.6},
        _SAMPLED,
    ),
    # Independent judgement: score, critique, adversarially probe.
    "critique": _Family(
        {"reasoning": 0.9, "critical_thinking": 0.9, "consistency": 0.7},
        _ANY,
    ),
    # Last line of defence before user-facing output. Repeatability dominates.
    "verify": _Family(
        {"reasoning": 0.9, "consistency": 0.9, "json_output": 0.7},
        _ANY,
    ),
    # Integrate many prior phases into one artefact.
    "assemble": _Family(
        {"reasoning": 0.85, "writing": 0.9, "long_context": 0.8},
        _LONG,
    ),
    # Turn a problem into structure: outlines, skeletons, specs, sub-problems.
    "structure": _Family(
        {"reasoning": 0.85, "long_context": 0.6, "json_output": 0.6},
        _ANY,
    ),
    # Prose quality is the deliverable. Not _SAMPLED: a single draft is written
    # once and revised, so temperature control is not the mechanism — and
    # demanding it would bar the strongest writing models in the fleet.
    "write": _Family(
        {"writing": 0.9, "creativity": 0.7, "reasoning": 0.5},
        _ANY,
    ),
    # Code generation, execution reasoning, and review.
    "code": _Family(
        {"coding": 0.9, "reasoning": 0.8, "consistency": 0.6},
        _ANY,
    ),
    # Cheap, deterministic routing and extraction. Overthinking is waste.
    "route": _Family(
        {"consistency": 0.8, "json_output": 0.8, "reasoning": 0.5},
        _ANY,
    ),
    # Grounded retrieval and reading over long inputs.
    "research": _Family(
        {"knowledge": 0.8, "long_context": 0.8, "reasoning": 0.6},
        _ANY,
    ),
    # General-purpose catch-all provider for unspecified roles.
    "general": _Family(
        {"reasoning": 0.8, "writing": 0.7, "consistency": 0.6},
        _ANY,
    ),
}

_ROLE_FAMILY: dict[str, str] = {
    # Generation
    "perspective": "generate",
    "perspective_cot": "generate",
    "perspective_analysis": "generate",
    "brainstorm_generate": "generate",
    "brainstorm_develop": "generate",
    "expert_1": "generate",
    "expert_2": "generate",
    "expert_3": "generate",
    "expert_4": "generate",
    "tot_generate": "generate",
    # Chain-of-Verification answers a fixed set of verification questions and
    # drafts once — factual work, not divergent sampling.
    "cove_draft": "general",
    "cove_answer": "general",
    "article_cove_answer": "general",
    # Critique
    "meta_evaluator": "critique",
    "stress_testing": "critique",
    "article_critic": "critique",
    "article_pre_mortem": "critique",
    "coding_review": "critique",
    "tot_evaluate": "critique",
    "subagent_critique_bias": "critique",
    "subagent_critique_counter": "critique",
    "subagent_critique_evidence": "critique",
    "subagent_critique_logic": "critique",
    # Verification
    "post_synthesis_verify": "verify",
    "cove_verify": "verify",
    "article_cove_verify": "verify",
    "article_verifier": "verify",
    "writing_factcheck": "verify",
    "context_vetting": "verify",
    "coding_tests": "verify",
    # Assembly / synthesis
    "article_synthesize": "assemble",
    "article_assemble": "assemble",
    "sot_assemble": "assemble",
    "coding_assemble": "assemble",
    "writing_assemble": "assemble",
    "subagent_synthesis_writer": "assemble",
    "subagent_synthesis_analysis": "assemble",
    "article_revise": "assemble",
    "article_cove_revise": "assemble",
    "cove_revise": "assemble",
    # Structure
    "subagent_decomposition": "structure",
    "article_decompose": "structure",
    "tot_decompose": "structure",
    "tot_backtrack": "structure",
    "sot_skeleton": "structure",
    "article_sot_skeleton": "structure",
    "coding_spec": "structure",
    "sd_select": "structure",
    "sd_adapt": "structure",
    "brainstorm_cluster": "structure",
    "writing_outline": "structure",
    "pot_generate": "structure",
    # Prose
    "writing_draft": "write",
    "article_humanize": "write",
    # Code
    "coding_generate": "code",
    "sot_solve": "code",
    "article_sot_solve": "code",
    "sd_implement": "code",
    "pot_execute": "code",
    "pot_interpret": "code",
    # Routing / extraction
    "prism_classify": "route",
    "fusion": "route",
    "article_claim_extract": "route",
    "prompt_enhancement": "route",
    "subagent_enhancement": "route",
    "subagent_search_query": "route",
    # Research
    "deep_read": "research",
    "subagent_search_eval": "research",
    # Catch-all provider
    "primary": "general",
}

_FAMILY_PREFIXES: tuple[tuple[str, str], ...] = (
    ("subagent_critique_", "critique"),
    ("stress_test", "critique"),
    ("brainstorm_", "generate"),
    ("coding_", "code"),
    ("pot_", "code"),
    ("sot_", "structure"),
    ("tot_", "structure"),
    ("sd_", "structure"),
    ("cove_", "verify"),
    ("article_", "write"),
    ("writing_", "write"),
    ("research_", "research"),
    ("expert_", "generate"),
)
"""Prefix → family, tried in order when a role has no explicit mapping.

Longest/most-specific prefixes come first: ``article_cove_verify`` must reach
``verify`` via its explicit entry, and an unmapped ``article_*`` role should
land on ``write`` rather than the generic default.
"""

# ── Roles ACR must not touch ──────────────────────────────────────────────────

ACR_EXCLUDED_ROLES: frozenset[str] = frozenset({
    "image_generate",
    # HyperGate sub-agent roles (W4). Their models are chosen by measurement,
    # not by catalogue score: every candidate was run against all five sub-agent
    # system prompts and kept only if the reply parsed. Utility scoring would
    # undo that -- qwen3.5-flash and qwen3.6-flash rank respectably on
    # reasoning/writing and return -1.0000000000000002e+308 and "" here, and
    # gemma-4-31b emits -1 for string fields. It would also ignore the point of
    # the split: no two of the five concurrent roles may resolve to the same
    # model, an invariant a per-role ranking cannot see. See
    # application/services/gate_service.py for the table and the measurements.
    "hypergate_subagent",
    "hypergate_language",
    "hypergate_complexity",
    "hypergate_direct",
    "hypergate_web",
    "hypergate_method",
    "hypergate_tiebreak",
})
"""Roles selected by machinery other than text-model utility scoring.

``image_generate`` is resolved by ``hypergate.sub_agents.image_model_selector``
against ``image_model_catalogue``; ranking it on reasoning/writing scores would
pick a text model for an image call.

The ``hypergate_*`` roles are resolved by
``application/services/gate_service.build_hypergate_router`` from a table of
models that were probed with the real prompts, per the project's rule that no
model may be routed on catalogue metadata alone.
"""

# ── Catch-all Fallback ──

_DEFAULT_REQUIREMENT = TaskRequirement(
    role="unknown",
    capability_weights={"reasoning": 0.5, "writing": 0.5},
    constraints=_ANY,
)


def _family_for(role: str) -> str | None:
    """Resolve a role to its family via the explicit map, then by prefix."""
    family = _ROLE_FAMILY.get(role)
    if family is not None:
        return family
    for prefix, candidate in _FAMILY_PREFIXES:
        if role.startswith(prefix):
            return candidate
    return None


def get_requirement(role: str) -> TaskRequirement:
    """Get the task requirement for a role.

    Resolution order: hand-tuned entry → family (explicit map, then prefix) →
    generic default.

    Args:
        role: The pipeline role name (e.g. ``"constructive"``, ``"scoring"``).

    Returns:
        The corresponding ``TaskRequirement``.
    """
    explicit = _ROLE_REQUIREMENTS.get(role)
    if explicit is not None:
        return explicit

    family = _family_for(role)
    if family is not None:
        spec = _FAMILIES[family]
        return TaskRequirement(
            role=role,
            capability_weights=dict(spec.weights),
            constraints=spec.constraints,
        )

    return _DEFAULT_REQUIREMENT


def has_requirement(role: str) -> bool:
    """Whether *role* resolves to a real requirement rather than the default."""
    return role in _ROLE_REQUIREMENTS or _family_for(role) is not None


def get_all_requirements() -> dict[str, TaskRequirement]:
    """Return all hand-tuned role requirements."""
    return dict(_ROLE_REQUIREMENTS)


__all__ = [
    "ACR_EXCLUDED_ROLES",
    "get_requirement",
    "get_all_requirements",
    "has_requirement",
]
