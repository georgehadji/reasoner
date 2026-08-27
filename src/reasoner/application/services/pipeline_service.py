"""Service for creating and managing ReasonerPipeline instances."""

from __future__ import annotations

import logging
from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.pipeline import ReasonerPipeline

logger = logging.getLogger(__name__)

class PipelineService:
    """Service to create ReasonerPipeline instances."""

    def create_pipeline(
        self,
        router: ProviderRouter,
        preset_name: str | None = None,
        top_k: int = 2,
        parallel_perspectives: bool = True,
        source_type: str = "general",
        domain: str | None = None,
        enhance_prompt: bool = False,
        complexity: str | None = None,
        batch_critique_jury: bool = False,
        initial_state: PipelineState | None = None,
        augmentation_methods: list[str] | None = None,
        user_id: str | None = None,
    ) -> ReasonerPipeline:
        """Create a configured ReasonerPipeline instance."""
        return ReasonerPipeline(
            router=router,
            initial_state=initial_state,
            top_k=top_k,
            parallel_perspectives=parallel_perspectives,
            verbose=False,
            preset_name=preset_name,
            source_type=source_type,
            domain=domain,
            enhance_prompt=enhance_prompt,
            complexity=complexity,
            batch_critique_jury=batch_critique_jury,
            augmentation_methods=augmentation_methods,
            user_id=user_id,
        )

    # ── Context Serialization ────────────────────────────────────────

    @staticmethod
    def to_context_dict(
        state: PipelineState,
        phase: str = "default",
        compression: str = "balanced",
        use_neuro: bool = False,
    ) -> dict[str, Any]:
        """Serialize PipelineState into a context dict for LLM calls.

        This method lives in the service layer because it performs
        data transformation and formatting — not pure data access.
        PipelineState.to_summary() provides the raw data; this method
        applies compression, truncation, and field selection.

        Args:
            state: PipelineState to serialize.
            phase: Current phase name (determines what data to include).
            compression: Compression level - "aggressive" | "balanced" | "none".
            use_neuro: If True, use neuro-compression for text content.

        Returns:
            Context dictionary optimized for token efficiency.
        """
        from reasoner.core.constants import TRUNCATION
        from reasoner.domain.models import ClaimLabel

        summary = state.to_summary()
        context: dict[str, Any] = {
            "problem": summary["problem"],
            "task_type": summary["task_type"],
            "language": summary["language"],
            "reflexion_memory": summary["reflexion_memory"],
        }

        if summary["attachments"]:
            context["attachments"] = [
                {
                    "filename": a.get("filename", "unknown"),
                    "extracted_text": (a.get("extracted_text", "") or "")[:TRUNCATION.LARGE_CONTENT],
                }
                for a in summary["attachments"]
            ]

        if compression == "aggressive":
            context["problem"] = summary["problem"][:TRUNCATION.PROBLEM]
            if phase in ("perspective", "constructive", "destructive", "systemic", "minimalist"):
                context["decomposition_summary"] = _get_decomposition_summary(summary)
            elif phase in ("scoring", "critique"):
                context["candidates_summary"] = _get_candidates_summary(summary, max_candidates=3, max_chars=200)
            elif phase in ("stress_testing",):
                context["top_candidates_summary"] = _get_candidates_summary(summary, max_candidates=2, max_chars=150)
            return context

        def _get_attr(obj: Any, key: str, default: Any = None) -> Any:
            if obj is None:
                return default
            if hasattr(obj, key):
                return getattr(obj, key, default)
            if isinstance(obj, dict):
                return obj.get(key, default)
            return default

        def _get_value(obj: Any) -> Any:
            return obj.value if hasattr(obj, "value") else obj

        content_limit = TRUNCATION.LARGE_CONTENT if phase in ("synthesis", "stress_testing", "verification") else TRUNCATION.CONTENT

        method_states: dict[str, Any] = {
            f"{k}_state" if k not in ("debate", "jury") else (
                "debate_rounds" if k == "debate" else "jury_guidelines"
            ): v
            for k, v in summary["method_state_data"].items()
            if v and k not in ("debate", "jury")
        }
        mstate = summary["method_state_data"]
        if "jury" in mstate:
            jury = mstate["jury"]
            if jury.get("guidelines"):
                method_states["jury_guidelines"] = jury["guidelines"]
            if jury.get("weighted_ranking"):
                method_states["jury_weighted_ranking"] = jury["weighted_ranking"]
        if "debate" in mstate:
            debate = mstate["debate"]
            if debate.get("rounds"):
                method_states["debate_rounds"] = debate["rounds"]

        web_results = [
            f"{r.get('title', 'Unknown')}: {r.get('snippet', '')[:TRUNCATION.SNIPPET]}"
            for r in (summary["web_discovery_results"] or [])
        ] or None
        if web_results:
            method_states["web_discovery_results"] = web_results
        context.update(method_states)

        decomp = summary["decomposition"]
        candidates_data = summary["candidates"] or []
        top_candidates_data = summary["top_candidates"] or []
        scores_data = summary["scores"] or []
        stress_data = summary["stress_results"] or []

        context.update({
            "sub_problems": [
                {
                    "id": _get_attr(sp, "id"),
                    "description": (_get_attr(sp, "description", "")[:TRUNCATION.API_STORAGE] if use_neuro
                                    else _get_attr(sp, "description", "")),
                    "inputs": _get_attr(sp, "inputs", []),
                    "outputs": _get_attr(sp, "outputs", []),
                    "constraints": _get_attr(sp, "constraints", []),
                }
                for sp in _get_attr(decomp, "sub_problems", [])
            ],
            "assumptions": [
                {"text": (_get_attr(a, "text", "")[:TRUNCATION.ASSUMPTION] if use_neuro
                          else _get_attr(a, "text", "")),
                 "label": _get_value(_get_attr(a, "label", ClaimLabel.UNKNOWN))}
                for a in _get_attr(decomp, "assumptions", [])
            ],
            "candidates": [
                {
                    "perspective": _get_value(_get_attr(c, "perspective")),
                    "content": _get_attr(c, "content", "")[:content_limit],
                    "key_insights": (_get_attr(c, "key_insights", [])[:TRUNCATION.KEY_INSIGHTS]
                                     if use_neuro else _get_attr(c, "key_insights", [])),
                }
                for c in (
                    candidates_data if phase == "synthesis" and candidates_data
                    else top_candidates_data or candidates_data
                )
            ],
            "scores": [
                {
                    "perspective": _get_value(_get_attr(s, "perspective")),
                    "total": round(_get_attr(s, "total", 0), 2),
                    "bias_flags": _get_attr(s, "bias_flags", []),
                }
                for s in scores_data
            ],
            "stress_results": [
                {
                    "scenario": _get_value(_get_attr(sr, "scenario")),
                    "survival_rate": _get_attr(sr, "survival_rate", 0),
                    "failure_mode": (_get_attr(sr, "failure_mode", "")[:TRUNCATION.SESSION_EXCERPT]
                                     if use_neuro else _get_attr(sr, "failure_mode", "")),
                    "recovery_path": (_get_attr(sr, "recovery_path", "")[:TRUNCATION.SESSION_EXCERPT]
                                      if use_neuro else _get_attr(sr, "recovery_path", "")),
                }
                for sr in stress_data
            ],
        })

        gc_data = summary["generation_candidates"] or []
        cs_data = summary["critic_scores"] or []
        vr_data = summary["verification_results"] or []

        context.update({
            "generation_candidates": [
                {
                    "generator_id": gc.generator_id,
                    "model_used": gc.model_used,
                    "solution": gc.solution[:TRUNCATION.SOLUTION],
                    "confidence": gc.confidence,
                    "key_claims": gc.key_claims[:TRUNCATION.KEY_INSIGHTS] if use_neuro else gc.key_claims,
                    "approach_summary": gc.approach_summary[:TRUNCATION.API_STORAGE] if use_neuro else gc.approach_summary,
                }
                for gc in gc_data
            ],
            "critic_scores": [
                {
                    "critic_id": cs.critic_id,
                    "critic_model": cs.critic_model,
                    "candidate_scores": {
                        gen_id: {
                            "factuality": ds.factuality,
                            "reasoning": ds.reasoning,
                            "completeness": ds.completeness,
                            "helpfulness": ds.helpfulness,
                            "total": round(ds.total, 2),
                        }
                        for gen_id, ds in cs.candidate_scores.items()
                    },
                    "ranking": cs.ranking,
                    "dissenting_note": cs.dissenting_note[:TRUNCATION.SESSION_EXCERPT] if use_neuro else cs.dissenting_note,
                }
                for cs in cs_data
            ],
            "verification_results": [
                {
                    "claim": vr.claim[:TRUNCATION.API_STORAGE] if use_neuro else vr.claim,
                    "source_generator": vr.source_generator,
                    "verdict": vr.verdict.value,
                    "evidence": vr.evidence[:TRUNCATION.API_STORAGE] if use_neuro else vr.evidence,
                    "confidence": vr.confidence,
                }
                for vr in vr_data
            ],
        })

        return context


import json
from collections import deque
from dataclasses import asdict
from dataclasses import fields as dc_fields
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from reasoner.core.constants import TRUNCATION
from reasoner.domain.core_types import (
    Assumption,
    CriticDimensionScore,
    CriticScore,
    CritiqueScore,
    Decomposition,
    FinalSolution,
    GenerationCandidate,
    MetaCognitiveAudit,
    MetaEvaluation,
    ReviewHypothesis,
    ScenarioType,
    SolutionCandidate,
    StressTestResult,
    SubProblem,
    VerificationResult,
)
from reasoner.domain.models import ClaimLabel, PerspectiveRegistry, TaskType


class PipelineSerializationService:
    @staticmethod
    def to_dict(state: PipelineState) -> dict[str, Any]:
        """Serialize complete state to dictionary (for persistence)."""
        def serialize(obj: Any) -> Any:
            if isinstance(obj, Enum):
                return obj.value
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, deque):
                return list(obj)
            if isinstance(obj, list):
                return [serialize(item) for item in obj]
            if isinstance(obj, dict):
                return {k: serialize(v) for k, v in obj.items()}
            if hasattr(obj, '__dataclass_fields__'):
                return {k: serialize(v) for k, v in asdict(obj).items()}
            return obj

        return serialize(asdict(state))

    @staticmethod
    def save(state: PipelineState, path: str | Path) -> None:
        """
        Save state to JSON file.
        
        Args:
            path: File path to save to
            
        Raises:
            PermissionError: If write permission is denied
            OSError: If disk is full or path is invalid
            TypeError: If state contains non-serializable data
        """
        import logging
        logger = logging.getLogger(__name__)

        path = Path(path)
        if ".." in path.parts:
            raise ValueError("Invalid path: directory traversal not allowed")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(PipelineSerializationService.to_dict(state), f, indent=2, ensure_ascii=False)
            logger.info(f"PipelineState saved to {path}")
        except PermissionError as e:
            logger.error(f"Permission denied saving PipelineState to {path}: {e}")
            raise
        except OSError as e:
            logger.error(f"OS error saving PipelineState to {path}: {e}")
            raise
        except TypeError as e:
            logger.error(f"Cannot serialize PipelineState: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error saving PipelineState to {path}: {e}")
            raise

    @staticmethod
    def load(path: str | Path) -> PipelineState:
        """
        Load state from JSON file.
        
        Args:
            path: File path to load from
            
        Returns:
            Reconstructed PipelineState instance
            
        Raises:
            FileNotFoundError: If the file does not exist
            PermissionError: If read permission is denied
            json.JSONDecodeError: If the file contains invalid JSON
            ValueError: If the file is corrupted or incomplete
        """
        import logging
        logger = logging.getLogger(__name__)

        path = Path(path)
        if ".." in path.parts:
            raise ValueError("Invalid path: directory traversal not allowed")
        try:
            if not path.exists():
                raise FileNotFoundError(f"PipelineState file not found: {path}")

            with open(path, encoding='utf-8') as f:
                data = json.load(f)

            state = PipelineSerializationService._from_dict(data)
            logger.info(f"PipelineState loaded from {path}")
            return state
        except FileNotFoundError:
            raise
        except PermissionError as e:
            logger.error(f"Permission denied loading PipelineState from {path}: {e}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in PipelineState file {path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error loading PipelineState from {path}: {e}")
            raise ValueError(f"Failed to load PipelineState: {e}") from e

    @staticmethod
    def _from_dict(data: dict[str, Any]) -> PipelineState:
        """Deserialize dictionary to PipelineState with proper type reconstruction."""
        # ── Phase A: Migrate old flat-format to new nested structure FIRST ──
        # This ensures all downstream reconstruction works on the new layout.

        # Migrate old-format flat method state fields into method_state
        _METHOD_KEYS = [
            'jury_guidelines', 'debate_rounds', 'scientific_state',
            'socratic_state', 'jury_weighted_ranking', 'pre_mortem_state',
            'bayesian_state', 'dialectical_state', 'analogical_state',
            'delphi_state', 'cove_state', 'sot_state', 'tot_state', 'pot_state',
            'self_discover_state', 'writing_state', 'coding_state',
            'brainstorming_state', 'cross_language_state',
        ]
        if 'method_state' not in data:
            raw: dict[str, Any] = {}
            for key in _METHOD_KEYS:
                val = data.pop(key, None)
                if val is not None and val != [] and val != {}:
                    if key == 'debate_rounds':
                        raw.setdefault('debate', {})['rounds'] = val
                    elif key == 'jury_guidelines':
                        raw.setdefault('jury', {})['guidelines'] = val
                    elif key == 'jury_weighted_ranking':
                        raw.setdefault('jury', {})['weighted_ranking'] = val
                    else:
                        method_name = key.replace('_state', '')
                        raw[method_name] = val
            if raw:
                data['method_state'] = {'data': raw}

        # Migrate old-format flat cost fields into cost_state
        if 'cost_state' not in data:
            cost_fields = {}
            for key in ('total_cost_usd', 'phase_costs', 'detailed_token_usage',
                        'phase_costs_by_key', '_phase_models_by_key'):
                if key in data:
                    cost_fields[key] = data.pop(key)
            if cost_fields:
                data['cost_state'] = cost_fields

        # Migrate old-format flat conversation fields into conversation_state
        if 'conversation_state' not in data:
            conv_fields = {}
            for key in ('conversation_history', 'conversation_id', 'turn_number',
                        'previous_synthesis', 'agent_model'):
                if key in data:
                    conv_fields[key] = data.pop(key)
            if conv_fields:
                data['conversation_state'] = conv_fields

        # Migrate old-format flat fields into core/meta/remainder sub-objects
        if 'core' not in data:
            core_fields = {}
            for key in ('problem', 'enhanced_problem', 'task_type', 'task_type_rationale',
                        'language', 'complexity', 'decomposition', 'candidates', 'scores',
                        'review_hypotheses', 'top_candidates', 'stress_results',
                        'final_solution', 'errors',
                        'attachments', 'generation_candidates', 'critic_scores',
                        'verification_results', 'meta_evaluation'):
                if key in data:
                    core_fields[key] = data.pop(key)
            if core_fields:
                data['core'] = core_fields

        if 'meta' not in data:
            meta_fields = {}
            for key in ('started_at', 'phase_logs', 'phase_tokens', 'phase_durations',
                        'phase_models', 'phase_results', 'quality_hints', 'quality_history',
                        'preset_name', 'method', 'context_quality'):
                if key in data:
                    meta_fields[key] = data.pop(key)
            if meta_fields:
                data['meta'] = meta_fields

        if 'remainder' not in data:
            remainder_fields = {}
            for key in ('neuro_context', 'reflexion_memory', 'web_discovery_results',
                        'vetted_context', 'synthesis_subagent_outputs',
                        'critique_subagent_outputs', 'decomposition_subagent_outputs',
                        'enhancement_subagent_outputs', 'search_subagent_outputs',
                        'pending_events', '_followup_cache'):
                if key in data:
                    remainder_fields[key] = data.pop(key)
            if remainder_fields:
                data['remainder'] = remainder_fields

        # ── Phase B: Reconstruct nested types in the new layout ──
        core = data.get('core', {})
        meta = data.get('meta', {})

        # Convert string enums back to Enum types
        if core.get('task_type'):
            try:
                core['task_type'] = TaskType(core['task_type'])
            except ValueError:
                core['task_type'] = None
        if meta.get('started_at'):
            dt = datetime.fromisoformat(meta['started_at'])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            meta['started_at'] = dt

        # Reconstruct decomposition inside core
        # The LLM returns extra keys (causal_chain, critical_sources, …) that are
        # not in the Decomposition dataclass.  Strip unknown keys before unpacking
        # so that a saved state with any LLM-generated decomposition can be resumed.
        # CRITICAL: Use defensive .get() for ALL nested dataclasses to handle
        # truncated or corrupted state files gracefully.
        if core.get('decomposition'):
            dec = core['decomposition']
            # SubProblem reconstruction with error handling and type coercion
            _sub_problems = []
            for sp in dec.get('sub_problems', []):
                try:
                    # Coerce list fields to lists in case LLM returned wrong type
                    _inputs = sp.get('inputs', [])
                    if not isinstance(_inputs, list):
                        _inputs = [str(_inputs)] if _inputs else []
                    _outputs = sp.get('outputs', [])
                    if not isinstance(_outputs, list):
                        _outputs = [str(_outputs)] if _outputs else []
                    _constraints = sp.get('constraints', [])
                    if not isinstance(_constraints, list):
                        _constraints = [str(_constraints)] if _constraints else []

                    _sub_problems.append(SubProblem(
                        id=str(sp.get('id', '')),
                        description=str(sp.get('description', '')),
                        inputs=_inputs,
                        outputs=_outputs,
                        constraints=_constraints,
                    ))
                except (TypeError, ValueError, KeyError):
                    pass  # skip malformed sub_problem entry
            dec['sub_problems'] = _sub_problems

            # Use .get() with fallbacks: a missing 'rationale' or 'label' key in a
            # saved assumption entry must not crash the entire resume.  Direct
            # subscript access caused KeyError for any partially-written state file.
            _assumptions = []
            for a in dec.get('assumptions', []):
                try:
                    _assumptions.append(Assumption(
                        text=str(a.get('text', '')),
                        label=ClaimLabel(str(a.get('label', ClaimLabel.UNKNOWN.value))),
                        rationale=str(a.get('rationale', '')),
                        source_hint=str(a.get('source_hint', '')),
                        # W2 premise audit fields — absent on pre-W2 state files,
                        # which is why every one of these has a safe default.
                        origin=str(a.get('origin', 'analyst')),
                        load_bearing=bool(a.get('load_bearing', False)),
                        falsifier=str(a.get('falsifier', '')),
                        resolvable_by=str(a.get('resolvable_by', '')),
                    ))
                except (ValueError, KeyError):
                    pass  # skip malformed assumption entry
            dec['assumptions'] = _assumptions

            # Preserve critical_sources if present
            _cs = dec.get('critical_sources', [])
            dec['critical_sources'] = [dict(cs) for cs in _cs if isinstance(cs, dict)]

            # Strip unknown keys before constructing Decomposition
            _known = {f.name for f in dc_fields(Decomposition)}
            core['decomposition'] = Decomposition(**{k: v for k, v in dec.items() if k in _known})

        # Reconstruct candidates with PerspectiveType
        if core.get('candidates'):
            _candidates = []
            for c in core['candidates']:
                try:
                    _candidates.append(SolutionCandidate(
                        perspective=PerspectiveRegistry.coerce(c['perspective']),
                        content=c['content'],
                        key_insights=c['key_insights'],
                        model_used=c['model_used']
                    ))
                except (ValueError, KeyError):
                    pass # skip malformed candidate
            core['candidates'] = _candidates

        # Reconstruct scores with PerspectiveType
        if core.get('scores'):
            _scores = []
            for s in core['scores']:
                try:
                    _scores.append(CritiqueScore(
                        perspective=PerspectiveRegistry.coerce(s['perspective']),
                        logical_consistency=s['logical_consistency'],
                        evidence_support=s['evidence_support'],
                        failure_resilience=s['failure_resilience'],
                        feasibility=s['feasibility'],
                        bias_flags=s['bias_flags'],
                        steel_man=s['steel_man']
                    ))
                except (ValueError, KeyError):
                    pass # skip malformed score
            core['scores'] = _scores

        # Reconstruct review_hypotheses (VS critique). All-optional fields, so
        # use .get() and skip malformed entries — older state files omit this
        # block entirely and must still load.
        if core.get('review_hypotheses'):
            _hypotheses: list[ReviewHypothesis] = []
            for h in core['review_hypotheses']:
                try:
                    _hypotheses.append(ReviewHypothesis(
                        claim=h.get('claim', ''),
                        probability=float(h.get('probability') or 0.0),
                        severity=h.get('severity', 'LOW'),
                        evidence_for=h.get('evidence_for', ''),
                        evidence_against=h.get('evidence_against', ''),
                        verification=h.get('verification', ''),
                        cost_if_wrong=h.get('cost_if_wrong', ''),
                    ))
                except (ValueError, TypeError, AttributeError):
                    pass  # skip malformed hypothesis entry
            core['review_hypotheses'] = _hypotheses

        # Reconstruct top_candidates
        if core.get('top_candidates'):
            _top_candidates = []
            for c in core['top_candidates']:
                try:
                    _top_candidates.append(SolutionCandidate(
                        perspective=PerspectiveRegistry.coerce(c['perspective']),
                        content=c['content'],
                        key_insights=c['key_insights'],
                        model_used=c['model_used']
                    ))
                except (ValueError, KeyError):
                    pass # skip malformed candidate
            core['top_candidates'] = _top_candidates

        # Reconstruct stress_results with ScenarioType.
        # BUG-021: _from_dict used direct subscripts sr['scenario'] etc. — a
        # truncated or older state file missing any field crashed with KeyError.
        # Use .get() + coerce (matching the live-pipeline fix from BUG-015) and
        # skip malformed entries with a warning instead of crashing the load.
        if core.get('stress_results'):
            _stress_results: list[StressTestResult] = []
            for sr in core['stress_results']:
                try:
                    _stress_results.append(StressTestResult(
                        scenario=ScenarioType.coerce(sr.get('scenario', 'optimal')),
                        survival_rate=float(sr.get('survival_rate') or 0),
                        failure_mode=sr.get('failure_mode', ''),
                        recovery_path=sr.get('recovery_path', ''),
                    ))
                except (ValueError, TypeError):
                    pass  # skip malformed stress result entry
            core['stress_results'] = _stress_results

        # Reconstruct final_solution with ClaimLabel and MetaCognitiveAudit
        if core.get('final_solution'):
            fs = core['final_solution']
            # If it's already a FinalSolution object (unlikely here but for safety)
            if hasattr(fs, '__dataclass_fields__'):
                data['final_solution'] = fs
            else:
                # Ensure it's a dict
                fs_dict = fs if isinstance(fs, dict) else {}

                # Safely reconstruct meta_audit
                ma = fs_dict.get('meta_audit', {})
                if not isinstance(ma, dict): ma = {}
                meta_audit_obj = MetaCognitiveAudit(
                    most_dangerous_assumption=ma.get('most_dangerous_assumption', ''),
                    dominant_bias=ma.get('dominant_bias', ''),
                    remaining_uncertainty=ma.get('remaining_uncertainty', ''),
                    assumption_failure_impact=ma.get('assumption_failure_impact', ''),
                    non_obvious_insight=ma.get('non_obvious_insight', '')
                )

                # Safely reconstruct claim_labels
                raw_labels = fs_dict.get('claim_labels', {})
                if not isinstance(raw_labels, dict): raw_labels = {}
                clean_labels = {}
                for k, v in raw_labels.items():
                    try:
                        clean_labels[k] = ClaimLabel(v)
                    except ValueError:
                        clean_labels[k] = ClaimLabel.UNKNOWN

                core['final_solution'] = FinalSolution(
                    core_solution=fs_dict.get('core_solution', ''),
                    critical_insights=fs_dict.get('critical_insights', []),
                    action_blueprint=fs_dict.get('action_blueprint', []),
                    open_questions=fs_dict.get('open_questions', []),
                    claim_labels=clean_labels,
                    meta_audit=meta_audit_obj,
                    sources=fs_dict.get('sources', []),
                    generator_attribution=fs_dict.get('generator_attribution', {}),
                    critic_weighting=fs_dict.get('critic_weighting', {})
                )

        # Reconstruct generation_candidates
        if core.get('generation_candidates'):
            core['generation_candidates'] = [
                GenerationCandidate(**gc) for gc in core['generation_candidates']
            ]

        # Reconstruct critic_scores.
        # CriticDimensionScore(**v) and CriticScore(**cs) have required fields with
        # no defaults — a truncated or partially-written state file causes TypeError.
        # Build each object explicitly with .get() fallbacks and skip bad entries.
        if core.get('critic_scores'):
            new_scores = []
            for cs in core['critic_scores']:
                try:
                    safe_dim: dict[str, CriticDimensionScore] = {}
                    for k, v in cs.get('candidate_scores', {}).items():
                        try:
                            safe_dim[k] = CriticDimensionScore(
                                factuality=float(v.get('factuality') or 0),
                                reasoning=float(v.get('reasoning') or 0),
                                completeness=float(v.get('completeness') or 0),
                                helpfulness=float(v.get('helpfulness') or 0),
                                confidence_vs_accuracy_penalty=float(v.get('confidence_vs_accuracy_penalty') or 0),
                            )
                        except (TypeError, ValueError):
                            pass  # skip this dimension entry
                    new_scores.append(CriticScore(
                        critic_id=cs.get('critic_id', ''),
                        critic_model=cs.get('critic_model', ''),
                        candidate_scores=safe_dim,
                        ranking=cs.get('ranking') or [],
                        dissenting_note=cs.get('dissenting_note') or '',
                    ))
                except (TypeError, ValueError, KeyError):
                    pass  # skip malformed critic score entry
            core['critic_scores'] = new_scores

        # Reconstruct verification_results with ClaimLabel.
        # BUG-022: _from_dict used direct subscripts vr['claim'] etc. — a
        # truncated or older state file missing any field crashed with KeyError.
        # Use .get() fallbacks + try/except so malformed entries are skipped.
        if core.get('verification_results'):
            _vresults: list[VerificationResult] = []
            for vr in core['verification_results']:
                try:
                    _vresults.append(VerificationResult(
                        claim=vr.get('claim', ''),
                        source_generator=vr.get('source_generator', ''),
                        verdict=ClaimLabel(vr.get('verdict', ClaimLabel.UNKNOWN.value)),
                        evidence=vr.get('evidence', ''),
                        confidence=float(vr.get('confidence') or 0),
                    ))
                except (TypeError, ValueError, KeyError):
                    pass  # skip malformed verification result entry
            core['verification_results'] = _vresults

        # Reconstruct meta_evaluation
        if core.get('meta_evaluation'):
            core['meta_evaluation'] = MetaEvaluation(**core['meta_evaluation'])

        return PipelineState(**data)

# ── Helper Functions (shared by PipelineService.to_context_dict) ──


def _get_decomposition_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Get condensed decomposition summary for token efficiency."""
    decomp = summary.get("decomposition")
    if not decomp:
        return {}
    return {
        "causal_chain_length": len(decomp.sub_problems) if hasattr(decomp, "sub_problems") else 0,
        "key_assumptions": [
            {"text": a.text[:TRUNCATION.SESSION_EXCERPT], "label": a.label.value}
            for a in (decomp.assumptions[:TRUNCATION.KEY_INSIGHTS] if decomp.assumptions else [])
        ],
    }


def _get_candidates_summary(
    summary: dict[str, Any],
    max_candidates: int = 3,
    max_chars: int = 200,
) -> list[dict]:
    """Get condensed candidates summary for token efficiency."""
    from reasoner.core.constants import TRUNCATION
    candidates = summary.get("top_candidates") or summary.get("candidates") or []
    return [
        {
            "perspective": c.perspective.value,
            "one_liner": c.content[:max_chars],
            "key_insights": c.key_insights[:TRUNCATION.MEMORY],
        }
        for c in candidates[:max_candidates]
    ]
