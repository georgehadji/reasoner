"""Core preset domain logic: dataclass, validation, and helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Optional, List

# Removed ProviderRouter and _REGISTRY imports to restore domain purity.
# Validation logic will be moved to an application service.
from reasoner.domain.saas import SubscriptionTier
from reasoner.core.constants_models import MODEL_GROK_43, MODEL_KIMI_K2_6

if TYPE_CHECKING:
    from reasoner.core.protocol import PhaseConfig


# Maps a model id to the env var that model needs, injected from the infrastructure
# layer (see reasoner/presets.py). Domain code must not import the model registry
# directly — see tests/architecture/test_layer_boundaries.py.
_MODEL_ENV_RESOLVER = None


def set_model_env_resolver(fn) -> None:
    """Inject a callable mapping model_id -> env var name (or None)."""
    global _MODEL_ENV_RESOLVER  # noqa: PLW0603
    _MODEL_ENV_RESOLVER = fn


def _get_model_env_resolver():
    return _MODEL_ENV_RESOLVER


# Single source of truth for valid routing role keys.
# When adding a new perspective, add its routing_key here.
_KNOWN_ROUTING_ROLES: frozenset[str] = frozenset({
    # Phase roles
    "primary",
    "fusion",
    "classification",
    "decomposition",
    "scoring",
    "verifier",
    "meta_evaluator",
    "stress_testing",
    "synthesis",
    "context_vetting",
    "deep_read",
    "perspective_analysis",
    "perspective_cot",
    # Default perspective roles (must match PerspectiveDefinition.routing_key values)
    "constructive",
    "destructive",
    "systemic",
    "minimalist",
    "perspective",
    # Delphi expert roles (Sprint 3 — B5)
    "expert_1",
    "expert_2",
    "expert_3",
    "expert_4",
    # Prompt enhancement (opt-in pre-phase)
    "prompt_enhancement",
    # CoVe roles
    "cove_draft",
    "cove_verify",
    "cove_answer",
    "cove_revise",
    # SoT roles
    "sot_skeleton",
    "sot_solve",
    "sot_assemble",
    # ToT roles
    "tot_decompose",
    "tot_generate",
    "tot_evaluate",
    "tot_backtrack",
    # PoT roles
    "pot_generate",
    "pot_execute",
    "pot_interpret",
    # Self-Discover roles
    "sd_select",
    "sd_adapt",
    "sd_implement",
    # PhaseSubAgent roles (v2.2 — per-subagent routing with fallbacks)
    "subagent_synthesis_analysis",
    "subagent_synthesis_writer",
    "subagent_critique_logic",
    "subagent_critique_evidence",
    "subagent_critique_bias",
    "subagent_critique_counter",
    "subagent_enhancement",
    "subagent_decomposition",
    "subagent_search_query",
    "subagent_search_eval",
    # Article Pipeline roles (research-backed article generation)
    "article_decompose",
    "article_claim_extract",
    "article_cove_verify",
    "article_cove_answer",
    "article_cove_revise",
    "article_verifier",
    "article_sot_skeleton",
    "article_sot_solve",
    "article_synthesize",
    "article_pre_mortem",
    "article_critic",
    "article_assemble",
    "article_revise",
    "article_humanize",
    # Coding Pipeline roles (production code generation)
    "coding_spec",
    "coding_generate",
    "coding_review",
    "coding_tests",
    "coding_assemble",
    # Brainstorming / Verbalized Sampling roles
    "brainstorm_generate",
    "brainstorm_cluster",
    "brainstorm_develop",
    # Prism integration
    "prism_classify",
    # ArticleFlow roles (4-phase source-grounded article: retrieve, draft, verify, refine)
    "writing_draft",
    "writing_outline",
    "writing_factcheck",
    "writing_assemble",
    # Image generation roles
    "image_generate",
    # Post-synthesis verification (all presets, v3.5)
    "post_synthesis_verify",
})


def get_method_from_preset(preset: str) -> str:
    """Extract method name from preset string."""
    if "debate" in preset:
        return "debate"
    if "iterative" in preset:
        return "iterative"
    if "jury" in preset or "orchestrated" in preset:
        return "jury"
    if "research" in preset:
        return "research"
    if "scientific" in preset:
        return "scientific"
    if "socratic" in preset:
        return "socratic"
    if "pre-mortem" in preset or "premortem" in preset:
        return "pre_mortem"
    if "bayesian" in preset:
        return "bayesian"
    if "dialectical" in preset:
        return "dialectical"
    if "analogical" in preset:
        return "analogical"
    if "delphi" in preset:
        return "delphi"
    if "self-discover" in preset:
        return "self_discover"
    if "cove" in preset:
        return "cove"
    if "brainstorming" in preset:
        return "brainstorming"
    if "article" in preset:
        return "article"
    if "writing" in preset:
        return "writing"
    if "sot" in preset:
        return "sot"
    if "tot" in preset:
        return "tot"
    if "pot" in preset:
        return "pot"
    if "cross-language" in preset or "cross_language" in preset:
        return "cross_language"
    return "multi-perspective"


def get_preset_price_tier(preset_id: str) -> Literal["budget", "premium", "unknown"]:
    """Infer pricing tier from preset ID suffix."""
    if preset_id.endswith("-budget"):
        return "budget"
    if preset_id.endswith("-premium"):
        return "premium"
    return "unknown"


def get_preset_tier(preset_id: str) -> SubscriptionTier:
    """Return the minimum subscription tier required for a preset."""
    from reasoner.domain.preset_registry import PRESETS
    preset = PRESETS.get(preset_id)
    if preset is None:
        return SubscriptionTier.FREE
    # PRESETS values are raw config dicts. Honour an explicit required_tier if
    # present, else derive from the tier suffix (premium -> PRO, else FREE).
    if isinstance(preset, dict):
        explicit = preset.get("required_tier")
        if explicit is not None:
            return explicit
        return SubscriptionTier.PRO if preset_id.endswith("-premium") else SubscriptionTier.FREE
    return getattr(preset, "required_tier", SubscriptionTier.FREE)


_METHOD_TO_SLUG: dict[str, str] = {
    "debate": "debate",
    "scientific": "scientific",
    "socratic": "socratic",
    "multi_perspective": "multi-perspective",
    "iterative_critique": "iterative-critique",  # v3.1: new LLM debate method
    "research": "research",
    "jury": "jury",
    "pre_mortem": "pre-mortem",
    "bayesian": "bayesian",
    "dialectical": "dialectical",
    "analogical": "analogical",
    "delphi": "delphi",
    "cove": "cove",
    "sot": "sot",
    "tot": "tot",
    "pot": "pot",
    "self_discover": "self-discover",
    "writing": "writing",
    "brainstorming": "brainstorming",
    "article": "article",
}


def build_auto_preset(method: str, tier: str = "budget") -> str:
    """Build a preset name from method classifier output."""
    safe_tier = tier if tier in ("budget", "premium") else "budget"
    slug = _METHOD_TO_SLUG.get(method, "multi-perspective")
    candidate = f"{slug}-{safe_tier}"
    # Belt-and-suspenders: confirm it actually exists in the registry.
    # We avoid a circular import by doing a late import of is_valid_preset_name.
    from reasoner.domain.preset_registry import PRESETS
    if candidate in PRESETS:
        return candidate
    return f"multi-perspective-{safe_tier}"


# Agent model used for follow-up synthesis / classification / decomposition.
# This ensures a consistent conversational persona across all methods.
FOLLOWUP_AGENT_MODELS: dict[str, str] = {
    "budget": MODEL_KIMI_K2_6,
    "premium": MODEL_GROK_43,
}


@dataclass
class PipelinePreset:
    """A named routing configuration with metadata."""
    id: str
    method: str
    primary_id: str
    name: str = ""
    description: str = ""
    routing: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    required_env_vars: list[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    # Per-role fallback model IDs. If a role's provider fails, this model is tried next.
    # Roles absent here fall back to primary automatically (if they use a non-primary model).
    fallback_routing: dict[str, str] = field(default_factory=dict)
    required_tier: SubscriptionTier = SubscriptionTier.FREE # New field: minimum tier required to use this preset
    # Method-specific runtime config injected into state before phase execution.
    # Currently used by the brainstorming method (VS rounds, k, threshold, etc.).
    brainstorming_config: dict = field(default_factory=dict)
    # New fields for dynamic pipeline behavior based on preset
    top_k: int = field(default=2)
    parallel_perspectives: bool = field(default=True)
    enhance_prompt: bool = field(default=False)
    skip_stress_test: bool = field(default=False)
    skip_deep_read: bool = field(default=False)
    batch_critique_jury: bool = field(default=False) # New field for batching jury critique
    cascading_routing: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate routing keys at construction time."""
        if not self.name:
            self.name = self.id.replace('-', ' ').title()
        if not self.description:
            self.description = f"{self.method.title()} method preset"

        unknown_roles = set(self.routing.keys()) - _KNOWN_ROUTING_ROLES
        if unknown_roles:
            raise ValueError(
                f"Preset '{self.name}' has unknown routing keys: {sorted(unknown_roles)}. "
                f"Valid roles: {sorted(_KNOWN_ROUTING_ROLES)}"
            )

        unknown_fb_roles = set(self.fallback_routing.keys()) - _KNOWN_ROUTING_ROLES
        if unknown_fb_roles:
            raise ValueError(
                f"Preset '{self.name}' has unknown fallback routing keys: {sorted(unknown_fb_roles)}. "
                f"Valid roles: {sorted(_KNOWN_ROUTING_ROLES)}"
            )

    def resolved_env_vars(self) -> list[str]:
        """Env vars this preset actually needs to run.

        Prefers the explicit ``required_env_vars`` list, falling back to the env
        vars of every model the preset routes to. Without the fallback the list is
        empty for presets that never declared one, and ``check_keys()`` reports
        "all set" no matter which credentials are missing.
        """
        if self.required_env_vars:
            return list(self.required_env_vars)

        resolver = _get_model_env_resolver()
        if resolver is None:
            return []

        model_ids = {self.primary_id, *self.routing.values(), *self.fallback_routing.values()}
        env_vars = {resolver(mid) for mid in model_ids if mid}
        return sorted(v for v in env_vars if v)

    def check_keys(self) -> dict[str, bool]:
        """Return {env_var: is_set} for all required API keys."""
        return {k: bool(os.environ.get(k)) for k in self.resolved_env_vars()}

    def missing_keys(self) -> list[str]:
        return [k for k, present in self.check_keys().items() if not present]
