"""
PipelineState and sub-containers extracted from models.py.

Contains: MethodState, CostTrackingState, ConversationState,
          PipelineCore, PipelineMeta, PipelineRemainder, PipelineState
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass, field, asdict, fields as dc_fields, MISSING as _DC_MISSING
from enum import Enum
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from reasoner.domain.core_types import (
    SolutionCandidate, CritiqueScore, ReviewHypothesis, StressTestResult,
    MetaCognitiveAudit, GenerationCandidate, CriticScore,
    VerificationResult, MetaEvaluation, Decomposition, FinalSolution,
)
from reasoner.domain.models import TaskType, ClaimLabel, PerspectiveType, PerspectiveRegistry


class PipelineField:
    """Descriptor that delegates attribute access to a sub-object on PipelineState.

    Replaces ~200 lines of boilerplate property getter/setter pairs.
    Usage on PipelineState::

        problem = PipelineField("core")
        language = PipelineField("core")
        started_at = PipelineField("meta")
        phase_tokens = PipelineField("meta")

    Each declaration replaces a 6-line property pair with a single line.
    """

    def __init__(self, target: str) -> None:
        self._target = target

    def __set_name__(self, owner: object, name: str) -> None:
        self._name = name

    def __get__(self, obj: object | None, objtype: object = None) -> Any:
        if obj is None:
            return self
        target = getattr(obj, self._target)
        return getattr(target, self._name)

    def __set__(self, obj: object, value: Any) -> None:
        target = getattr(obj, self._target)
        setattr(target, self._name, value)
        if hasattr(obj, '_ensure_fields_initialized'):
            obj._ensure_fields_initialized()


if TYPE_CHECKING:
    from reasoner.core.protocol import PhaseResult

@dataclass
class MethodState:
    """Generic container for method-specific phase data.

    Replace 19 named PipelineState fields (jury_guidelines, debate_rounds,
    scientific_state, ...) with a single dict indexed by method name.
    """
    data: dict[str, Any] = field(default_factory=dict)

    def get(self, method: str) -> dict[str, Any]:
        v = self.data.get(method)
        return v if isinstance(v, dict) else {}

    def set(self, method: str, state: dict[str, Any]) -> None:
        self.data[method] = state


@dataclass
class CostTrackingState:
    """Grouped cost and token tracking for the pipeline.

    Aggregates fields that were previously flat in PipelineState
    into a single sub-object for cleaner serialization.
    """
    total_cost_usd: float = 0.0
    phase_costs: dict[str, float] = field(default_factory=dict)
    detailed_token_usage: dict[str, dict[str, int]] = field(default_factory=dict)
    phase_costs_by_key: dict[str, float] = field(default_factory=dict)
    _phase_models_by_key: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class ConversationState:
    """Grouped multi-turn follow-up context."""
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    conversation_id: str = ""
    turn_number: int = 1
    previous_synthesis: str = ""
    agent_model: str | None = None


@dataclass
class PipelineCore:
    """Fields that every phase reads during execution."""
    problem: str = ""
    enhanced_problem: str = ""  # Auto-rewritten prompt for clarity and context
    task_type: TaskType | None = None
    task_type_rationale: str = ""
    language: str = "English"  # Detected language from the problem
    complexity: str | None = None  # Estimated problem complexity (simple, medium, complex)
    decomposition: Decomposition | None = None
    candidates: list[SolutionCandidate] = field(default_factory=list)
    scores: list[CritiqueScore] = field(default_factory=list)
    # VS critique: probability-ranked failure hypotheses (premium tier only).
    review_hypotheses: list[ReviewHypothesis] = field(default_factory=list)
    top_candidates: list[SolutionCandidate] = field(default_factory=list)
    stress_results: list[StressTestResult] = field(default_factory=list)
    final_solution: FinalSolution | None = None
    errors: list[str] = field(default_factory=list)
    attachments: list[dict[str, Any]] = field(default_factory=list)
    # ORCHESTRATED method fields (populated only when preset is orchestrated)
    generation_candidates: list["GenerationCandidate"] = field(default_factory=list)
    critic_scores: list["CriticScore"] = field(default_factory=list)
    verification_results: list["VerificationResult"] = field(default_factory=list)
    meta_evaluation: "MetaEvaluation | None" = None


@dataclass
class PipelineMeta:
    """Fields that are write-only during execution, read-only after."""
    started_at: "datetime" = field(default_factory=lambda: datetime.now(timezone.utc))
    phase_logs: list[str] = field(default_factory=list)
    phase_tokens: dict[str, dict[str, int]] = field(default_factory=dict)
    phase_durations: dict[str, float] = field(default_factory=dict)
    phase_models: dict[str, str] = field(default_factory=dict)
    phase_results: list["PhaseResult"] = field(default_factory=list)
    quality_hints: dict[str, str] = field(default_factory=dict)
    quality_history: list[dict] = field(default_factory=list)
    fallback_events: list[dict] = field(default_factory=list)
    preset_name: str | None = None
    method: str | None = None
    context_quality: str = "unknown"  # "good" | "partial" | "contaminated" | "missing"


@dataclass
class PipelineRemainder:
    """Fields that don't fit cleanly into core or meta."""
    neuro_context: list[dict[str, Any]] = field(default_factory=list)
    reflexion_memory: list[str] = field(default_factory=list)
    web_discovery_results: list[dict[str, Any]] = field(default_factory=list)
    vetted_context: list[dict[str, Any]] = field(default_factory=list)
    synthesis_subagent_outputs: list[dict[str, Any]] = field(default_factory=list)
    critique_subagent_outputs: list[dict[str, Any]] = field(default_factory=list)
    decomposition_subagent_outputs: list[dict[str, Any]] = field(default_factory=list)
    enhancement_subagent_outputs: list[dict[str, Any]] = field(default_factory=list)
    search_subagent_outputs: list[dict[str, Any]] = field(default_factory=list)
    pending_events: list[dict[str, Any]] = field(default_factory=list)
    _followup_cache: str | None = field(default=None, repr=False)


@dataclass
class PhaseOutput:
    """A typed delta returned by a phase function, to be reduced into PipelineState safely."""
    candidates: list[SolutionCandidate] | None = None
    scores: list[CritiqueScore] | None = None
    review_hypotheses: list[ReviewHypothesis] | None = None
    top_candidates: list[SolutionCandidate] | None = None
    stress_results: list[StressTestResult] | None = None
    final_solution: FinalSolution | None = None
    errors: list[str] | None = None
    generation_candidates: list["GenerationCandidate"] | None = None
    critic_scores: list["CriticScore"] | None = None
    verification_results: list["VerificationResult"] | None = None
    meta_evaluation: "MetaEvaluation | None" = None
    # Flag to indicate short-term sequential mutation (Phase C3)
    mutated_in_place: bool = False

    def apply_to(self, state: PipelineState) -> None:
        """Sequential reducer that applies the delta to the state."""
        if self.mutated_in_place:
            return  # State was already mutated directly by the phase
        if self.candidates is not None:
            state.core.candidates.extend(self.candidates)
        if self.scores is not None:
            state.core.scores.extend(self.scores)
        if self.review_hypotheses is not None:
            state.core.review_hypotheses.extend(self.review_hypotheses)
        if self.top_candidates is not None:
            state.core.top_candidates.extend(self.top_candidates)
        if self.stress_results is not None:
            state.core.stress_results.extend(self.stress_results)
        if self.final_solution is not None:
            state.core.final_solution = self.final_solution
        if self.errors is not None:
            state.core.errors.extend(self.errors)
        if self.generation_candidates is not None:
            state.core.generation_candidates.extend(self.generation_candidates)
        if self.critic_scores is not None:
            state.core.critic_scores.extend(self.critic_scores)
        if self.verification_results is not None:
            state.core.verification_results.extend(self.verification_results)
        if self.meta_evaluation is not None:
            state.core.meta_evaluation = self.meta_evaluation

@dataclass
class PipelineState:
    """Complete pipeline state — passed between phases."""
    core: PipelineCore = field(default_factory=PipelineCore)
    method_state: MethodState = field(default_factory=MethodState)
    meta: PipelineMeta = field(default_factory=PipelineMeta)
    remainder: PipelineRemainder = field(default_factory=PipelineRemainder)
    cost_state: CostTrackingState = field(default_factory=CostTrackingState)
    conversation_state: ConversationState = field(default_factory=ConversationState)

    def __init__(self, **kwargs: Any) -> None:
        """Backward-compatible init: accepts both old flat kwargs and new nested kwargs."""
        _CORE_FIELDS = {
            'problem', 'enhanced_problem', 'task_type', 'task_type_rationale',
            'language', 'complexity', 'decomposition', 'candidates', 'scores',
            'review_hypotheses', 'top_candidates', 'stress_results',
            'final_solution', 'errors',
            'attachments', 'generation_candidates', 'critic_scores',
            'verification_results', 'meta_evaluation',
        }
        _META_FIELDS = {
            'started_at', 'phase_logs', 'phase_tokens', 'phase_durations',
            'phase_models', 'phase_results', 'quality_hints', 'quality_history',
            'preset_name', 'method', 'context_quality',
            'fallback_events',
        }
        _REMAINDER_FIELDS = {
            'neuro_context', 'reflexion_memory', 'web_discovery_results',
            'vetted_context', 'synthesis_subagent_outputs',
            'critique_subagent_outputs', 'decomposition_subagent_outputs',
            'enhancement_subagent_outputs', 'search_subagent_outputs',
            'pending_events', '_followup_cache',
        }

        core_kwargs: dict[str, Any] = {}
        meta_kwargs: dict[str, Any] = {}
        remainder_kwargs: dict[str, Any] = {}
        direct_kwargs: dict[str, Any] = {}

        for key, value in kwargs.items():
            if key in _CORE_FIELDS:
                core_kwargs[key] = value
            elif key in _META_FIELDS:
                meta_kwargs[key] = value
            elif key in _REMAINDER_FIELDS:
                remainder_kwargs[key] = value
            else:
                direct_kwargs[key] = value

        # Build sub-objects: explicit containers take precedence
        core = direct_kwargs.pop('core', None)
        if core is None:
            core = PipelineCore(**core_kwargs) if core_kwargs else PipelineCore()
        elif core_kwargs:
            # Merge flat kwargs into existing container
            for k, v in core_kwargs.items():
                setattr(core, k, v)

        meta = direct_kwargs.pop('meta', None)
        if meta is None:
            meta = PipelineMeta(**meta_kwargs) if meta_kwargs else PipelineMeta()
        elif meta_kwargs:
            for k, v in meta_kwargs.items():
                setattr(meta, k, v)

        remainder = direct_kwargs.pop('remainder', None)
        if remainder is None:
            remainder = PipelineRemainder(**remainder_kwargs) if remainder_kwargs else PipelineRemainder()
        elif remainder_kwargs:
            for k, v in remainder_kwargs.items():
                setattr(remainder, k, v)

        method_state = direct_kwargs.pop('method_state', MethodState())
        cost_state = direct_kwargs.pop('cost_state', CostTrackingState())
        conversation_state = direct_kwargs.pop('conversation_state', ConversationState())

        # Assign fields directly to avoid dataclass __init__ recursion
        object.__setattr__(self, 'core', core)
        object.__setattr__(self, 'method_state', method_state)
        object.__setattr__(self, 'meta', meta)
        object.__setattr__(self, 'remainder', remainder)
        object.__setattr__(self, 'cost_state', cost_state)
        object.__setattr__(self, 'conversation_state', conversation_state)

        # v3.1: Set any remaining direct kwargs (dataclass fields added after original impl)
        for k, v in direct_kwargs.items():
            object.__setattr__(self, k, v)

        # Run post-init migration logic
        self.__post_init__()

        # v3.1: Initialize dataclass fields with defaults that weren't explicitly set
        self._ensure_fields_initialized()
        object.__setattr__(self, '_initialized', True)

    def _ensure_fields_initialized(self) -> None:
        """Initialize missing dataclass fields for backward-compatible --resume loading.

        Called only when _initialized is not yet set, meaning this is a partially
        deserialized state. After the first call completes, sets _initialized=True
        so subsequent calls are a no-op.
        """
        if getattr(self, '_initialized', False):
            return
        for f in dc_fields(self):
            if not hasattr(self, f.name):
                if f.default_factory is not _DC_MISSING:
                    object.__setattr__(self, f.name, f.default_factory())
                elif f.default is not _DC_MISSING:
                    object.__setattr__(self, f.name, f.default)
        object.__setattr__(self, '_initialized', True)

    # ─────────────────────────────────────────────────────────────────────
    # Backward-compatible property aliases for core fields
    # ─────────────────────────────────────────────────────────────────────
    problem = PipelineField("core")
    enhanced_problem = PipelineField("core")
    task_type = PipelineField("core")
    task_type_rationale = PipelineField("core")
    language = PipelineField("core")
    complexity = PipelineField("core")
    decomposition = PipelineField("core")
    candidates = PipelineField("core")
    scores = PipelineField("core")
    review_hypotheses = PipelineField("core")
    top_candidates = PipelineField("core")
    stress_results = PipelineField("core")
    final_solution = PipelineField("core")
    errors = PipelineField("core")
    attachments = PipelineField("core")
    generation_candidates = PipelineField("core")
    critic_scores = PipelineField("core")
    verification_results = PipelineField("core")
    meta_evaluation = PipelineField("core")

    # ─────────────────────────────────────────────────────────────────────
    # Backward-compatible property aliases for meta fields
    # ─────────────────────────────────────────────────────────────────────
    started_at = PipelineField("meta")
    phase_logs = PipelineField("meta")
    phase_tokens = PipelineField("meta")
    phase_durations = PipelineField("meta")
    phase_models = PipelineField("meta")
    phase_results = PipelineField("meta")
    quality_hints = PipelineField("meta")
    quality_history = PipelineField("meta")
    preset_name = PipelineField("meta")
    method = PipelineField("meta")
    context_quality = PipelineField("meta")

    # ─────────────────────────────────────────────────────────────────────
    # Backward-compatible property aliases for remainder fields
    # ─────────────────────────────────────────────────────────────────────
    neuro_context = PipelineField("remainder")
    reflexion_memory = PipelineField("remainder")
    web_discovery_results = PipelineField("remainder")
    vetted_context = PipelineField("remainder")
    synthesis_subagent_outputs = PipelineField("remainder")
    critique_subagent_outputs = PipelineField("remainder")
    decomposition_subagent_outputs = PipelineField("remainder")
    enhancement_subagent_outputs = PipelineField("remainder")
    search_subagent_outputs = PipelineField("remainder")
    pending_events = PipelineField("remainder")
    _followup_cache = PipelineField("remainder")

    @property
    def synthesis(self) -> dict[str, Any] | None:
        """Compatibility layer for old handler code expecting a dict."""
        if self.core.final_solution:
            return {
                "core_solution": self.core.final_solution.core_solution,
                "critical_insights": self.core.final_solution.critical_insights,
            }
        return None

    # ─────────────────────────────────────────────────────────────────────
    # Method State (replaces 19 named fields with a single dict container)
    # ─────────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────
    # Backward-compatible property aliases for method state fields
    # ─────────────────────────────────────────────────────────────────────
        self._ensure_fields_initialized()
    @property
    def jury_guidelines(self) -> list[str]:
        return self.method_state.data.setdefault("jury", {}).setdefault("guidelines", [])

    @jury_guidelines.setter
    def jury_guidelines(self, value: list[str]) -> None:
        self.method_state.data.setdefault("jury", {})["guidelines"] = value

        self._ensure_fields_initialized()
    @property
    def debate_rounds(self) -> list[dict[str, Any]]:
        return self.method_state.data.setdefault("debate", {}).setdefault("rounds", [])

    @debate_rounds.setter
    def debate_rounds(self, value: list[dict[str, Any]]) -> None:
        self.method_state.data.setdefault("debate", {})["rounds"] = value

        self._ensure_fields_initialized()
    @property
    def scientific_state(self) -> dict[str, Any]:
        return self.method_state.data.setdefault("scientific", {})

    @scientific_state.setter
    def scientific_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["scientific"] = value

        self._ensure_fields_initialized()
    @property
    def socratic_state(self) -> dict[str, Any]:
        return self.method_state.data.setdefault("socratic", {})

    @socratic_state.setter
    def socratic_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["socratic"] = value

        self._ensure_fields_initialized()
    @property
    def jury_weighted_ranking(self) -> list[str]:
        return self.method_state.data.setdefault("jury", {}).setdefault("weighted_ranking", [])

    @jury_weighted_ranking.setter
    def jury_weighted_ranking(self, value: list[str]) -> None:
        self.method_state.data.setdefault("jury", {})["weighted_ranking"] = value

        self._ensure_fields_initialized()
    @property
    def pre_mortem_state(self) -> dict[str, Any]:
        val = self.method_state.data.setdefault("pre_mortem", {})
        # Defensive: if corrupted to non-dict (e.g. from old serialization), reset
        if not isinstance(val, dict):
            val = {}
            self.method_state.data["pre_mortem"] = val
        return val

    @pre_mortem_state.setter
    def pre_mortem_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["pre_mortem"] = value

        self._ensure_fields_initialized()
    @property
    def bayesian_state(self) -> dict[str, Any]:
        return self.method_state.data.setdefault("bayesian", {})

    @bayesian_state.setter
    def bayesian_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["bayesian"] = value

        self._ensure_fields_initialized()
    @property
    def dialectical_state(self) -> dict[str, Any]:
        return self.method_state.data.setdefault("dialectical", {})

    @dialectical_state.setter
    def dialectical_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["dialectical"] = value

        self._ensure_fields_initialized()
    @property
    def analogical_state(self) -> dict[str, Any]:
        return self.method_state.data.setdefault("analogical", {})

    @analogical_state.setter
    def analogical_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["analogical"] = value

        self._ensure_fields_initialized()
    @property
    def delphi_state(self) -> dict[str, Any]:
        return self.method_state.data.setdefault("delphi", {})

    @delphi_state.setter
    def delphi_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["delphi"] = value

        self._ensure_fields_initialized()
    @property
    def cove_state(self) -> dict[str, Any]:
        return self.method_state.data.setdefault("cove", {})

    @cove_state.setter
    def cove_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["cove"] = value

        self._ensure_fields_initialized()
    @property
    def sot_state(self) -> dict[str, Any]:
        return self.method_state.data.setdefault("sot", {})

    @sot_state.setter
    def sot_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["sot"] = value

        self._ensure_fields_initialized()
    @property
    def tot_state(self) -> dict[str, Any]:
        return self.method_state.data.setdefault("tot", {})

    @tot_state.setter
    def tot_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["tot"] = value

        self._ensure_fields_initialized()
    @property
    def pot_state(self) -> dict[str, Any]:
        return self.method_state.data.setdefault("pot", {})

    @pot_state.setter
    def pot_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["pot"] = value

        self._ensure_fields_initialized()
    @property
    def self_discover_state(self) -> dict[str, Any]:
        return self.method_state.data.setdefault("self_discover", {})

    @self_discover_state.setter
    def self_discover_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["self_discover"] = value

        self._ensure_fields_initialized()
    @property
    def writing_state(self) -> dict[str, Any]:
        return self.method_state.data.setdefault("writing", {})

    @writing_state.setter
    def writing_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["writing"] = value

        self._ensure_fields_initialized()
    @property
    def coding_state(self) -> dict[str, Any]:
        return self.method_state.data.setdefault("coding", {})

    @coding_state.setter
    def coding_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["coding"] = value

        self._ensure_fields_initialized()
    @property
    def brainstorming_state(self) -> dict[str, Any]:
        return self.method_state.data.setdefault("brainstorming", {})

    @brainstorming_state.setter
    def brainstorming_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["brainstorming"] = value

        self._ensure_fields_initialized()
    @property
    def cross_language_state(self) -> dict[str, Any]:
        return self.method_state.data.setdefault("cross_language", {})

    @cross_language_state.setter
    def cross_language_state(self, value: dict[str, Any]) -> None:
        self.method_state.data["cross_language"] = value

    def __post_init__(self) -> None:
        """Backward-compat migration for --resume with old-format state files.
        Also sets up property-backed alias attributes for the grouped fields."""
        if not isinstance(self.core, PipelineCore):
            if isinstance(self.core, dict):
                self.core = PipelineCore(**self.core)
            else:
                self.core = PipelineCore()
        if not isinstance(self.meta, PipelineMeta):
            if isinstance(self.meta, dict):
                self.meta = PipelineMeta(**self.meta)
            else:
                self.meta = PipelineMeta()
        if not isinstance(self.remainder, PipelineRemainder):
            if isinstance(self.remainder, dict):
                self.remainder = PipelineRemainder(**self.remainder)
            else:
                self.remainder = PipelineRemainder()
        if not isinstance(self.method_state, MethodState):
            if isinstance(self.method_state, dict):
                self.method_state = MethodState(**self.method_state)
            else:
                self.method_state = MethodState()
        if not isinstance(self.cost_state, CostTrackingState):
            if isinstance(self.cost_state, dict):
                self.cost_state = CostTrackingState(**self.cost_state)
            else:
                self.cost_state = CostTrackingState()
        if not isinstance(self.conversation_state, ConversationState):
            if isinstance(self.conversation_state, dict):
                self.conversation_state = ConversationState(**self.conversation_state)
            else:
                self.conversation_state = ConversationState()

        self._ensure_fields_initialized()
    total_cost_usd = PipelineField("cost_state")
    phase_costs = PipelineField("cost_state")
    detailed_token_usage = PipelineField("cost_state")
    conversation_history = PipelineField("conversation_state")
    conversation_id = PipelineField("conversation_state")
    turn_number = PipelineField("conversation_state")
    previous_synthesis = PipelineField("conversation_state")
    agent_model = PipelineField("conversation_state")

    # Adversarial debate (iterative critique method)
    adversarial_rounds: list = field(default_factory=list)
    adversarial_converged: bool = False
    adversarial_convergence_round: int = 0
    adversarial_convergence_reason: str = ""

    def add_error(self, message: str) -> None:
        """Atomic append to error list."""
        if message and message not in self.errors:
            self.errors.append(str(message))

    def add_log(self, phase: str, message: str) -> None:
        """Atomic log entry."""
        entry = f"[{phase}] {message}"
        self.phase_logs.append(entry)

    def set_duration(self, phase: str, seconds: float) -> None:
        """Safe update of phase durations."""
        self.phase_durations[phase] = seconds

    def log(self, phase: str, message: str) -> None:
        self.add_log(phase, message)

    def to_summary(self) -> dict[str, Any]:
        """Return raw data summary — minimal, no I/O, no compression logic.

        Used by PipelineService.to_context_dict() for full serialization.
        This method lives on the domain object because it describes the data;
        the heavy formatting lives in the service layer.
        """
        return {
            "problem": self.problem,
            "task_type": (self.task_type.value if hasattr(self.task_type, 'value') else self.task_type) if self.task_type else None,
            "language": self.language,
            "reflexion_memory": self.reflexion_memory,
            "decomposition": self.decomposition,
            "candidates": self.candidates,
            "top_candidates": self.top_candidates,
            "scores": self.scores,
            "stress_results": self.stress_results,
            "generation_candidates": self.generation_candidates,
            "critic_scores": self.critic_scores,
            "verification_results": self.verification_results,
            "attachments": self.attachments,
            "web_discovery_results": self.web_discovery_results,
            "method_state_data": dict(self.method_state.data) if hasattr(self.method_state, 'data') else {},
        }

    def to_context_dict(self, phase: str = "default", compression: str = "balanced", use_neuro: bool = False) -> dict[str, Any]:
        # COMPAT: Delegated to PipelineService — this method is deprecated.
        from reasoner.application.services.pipeline_service import PipelineService
        return PipelineService.to_context_dict(self, phase=phase, compression=compression, use_neuro=use_neuro)
