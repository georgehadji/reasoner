# Author: Georgios-Chrysovalantis Chatzivantsidis
"""
Reasoner Pipeline - Strategy-based Orchestrator
Refactored to eliminate mixin-based God Object in favor of 
composition-based WorkflowStrategy pattern.
"""

from __future__ import annotations
import asyncio
import functools
import json
import logging
import re
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")

def timed(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator that records phase duration in ``state.phase_durations``."""
    @functools.wraps(func)
    async def async_wrapper(self, *args, **kwargs):
        start = time.monotonic()
        try:
            return await func(self, *args, **kwargs)
        finally:
            elapsed = time.monotonic() - start
            state = kwargs.get("state")
            if state is None and args:
                state = args[0]
            if state is not None and hasattr(state, "phase_durations"):
                state.phase_durations[func.__name__] = elapsed
            if state is not None and hasattr(state, "log"):
                self._log("TIMING", f"{func.__name__} completed in {elapsed*1000:.1f}ms", state)
    return async_wrapper  # type: ignore[return-value]

from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.core_types import (
    SolutionCandidate,
    CritiqueScore,
    StressTestResult,
    ScenarioType,
    GenerationCandidate,
    CriticScore,
    VerificationResult,
    MetaEvaluation,
    FinalSolution,
    MetaCognitiveAudit,
)
from reasoner.models import (
    ClaimLabel,
    PerspectiveType,
    TaskType,
)
from reasoner.core.parsing import ParseError, extract_json, safe_list, safe_float, _parse_critique_scores
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.infrastructure.llm.executor import LLMExecutor
from reasoner.core import PhaseConfig, make_phase_result, DEFAULT_PERSPECTIVES
from reasoner.core.protocol import TemperatureStrategy
from reasoner.core.temperatures import PHASE_TEMPERATURES, PHASE_REASONING_EFFORT
from reasoner.core.constants import (
    PHASE_TOKEN_BUDGETS,
    get_token_budget,
    DEFAULT_MAX_TOKENS,
    TRUNCATION,
)
from reasoner.token_cache import get_token_cache 
from reasoner.sanitization import sanitize_for_prompt, clean_llm_artifacts
import reasoner.phases as phases

logger = logging.getLogger(__name__)

from reasoner.core.settings import settings

TOKEN_OPTIMIZATION = {
    "dynamic_budgets":     settings.TOKEN_DYNAMIC_BUDGETS,
    "context_compression": settings.TOKEN_CONTEXT_COMPRESSION,
    "prompt_compression":  settings.TOKEN_PROMPT_COMPRESSION,
    "neuro_compression":   settings.TOKEN_NEURO_COMPRESSION,
    "caching":             settings.TOKEN_CACHING,
}

USE_PHASE_SUBAGENTS = {
    "enhancement": settings.USE_SUBAGENT_ENHANCEMENT,
    "decomposition": settings.USE_SUBAGENT_DECOMPOSITION,
    "critique": settings.USE_SUBAGENT_CRITIQUE,
    "synthesis": settings.USE_SUBAGENT_SYNTHESIS,
    "search": settings.USE_SUBAGENT_SEARCH,
}

token_cache = get_token_cache(
    max_tokens=1_000_000,
    ttl_seconds=3600,
    cache_dir="cache/tokens",
) if TOKEN_OPTIMIZATION["caching"] else None

class ReasonerPipeline:
    """
    Refactored Reasoner Orchestrator.
    Now uses WorkflowStrategy composition instead of Mixin inheritance.
    """
    _PHASE_CONFIGS: dict[str, PhaseConfig] = {
        "classification": PhaseConfig(role="classification", temperature=PHASE_TEMPERATURES["classification"], temperature_strategy=TemperatureStrategy.DEESCALATE, reasoning_effort=PHASE_REASONING_EFFORT.get("classification")),
        "decomposition": PhaseConfig(role="decomposition", temperature=PHASE_TEMPERATURES["decomposition"], temperature_strategy=TemperatureStrategy.DEESCALATE, reasoning_effort=PHASE_REASONING_EFFORT.get("decomposition")),
        "synthesis": PhaseConfig(role="synthesis", temperature=PHASE_TEMPERATURES["synthesis"], temperature_strategy=TemperatureStrategy.DEESCALATE, reasoning_effort=PHASE_REASONING_EFFORT.get("synthesis")),
        "fusion": PhaseConfig(role="fusion", temperature=PHASE_TEMPERATURES.get("fusion", 0.1), temperature_strategy=TemperatureStrategy.DEESCALATE, reasoning_effort=PHASE_REASONING_EFFORT.get("fusion")),
    }

    def __init__(
        self,
        router: ProviderRouter,
        initial_state: PipelineState | None = None,
        top_k: int = 2,
        parallel_perspectives: bool = True,
        verbose: bool = True,
        preset_name: str | None = None,
        source_type: str = "general",
        domain: str | None = None,
        enhance_prompt: bool = False,
        complexity: str | None = None,
        batch_critique_jury: bool = False,
        phase_configs: dict[str, PhaseConfig] | None = None,
        augmentation_methods: list[str] | None = None,
        user_id: str | None = None,
    ) -> None:
        self.router = router
        self.initial_state = initial_state
        self.top_k = top_k
        self.parallel = parallel_perspectives
        self.verbose = verbose
        self.preset_name = preset_name
        self.source_type = source_type
        self.domain = domain
        self.enhance_prompt = enhance_prompt
        self.complexity = complexity
        self.batch_critique_jury = batch_critique_jury
        self.augmentation_methods = augmentation_methods
        self.user_id = user_id
        self.phase_configs = phase_configs or self._PHASE_CONFIGS
        
        from reasoner.application.flows.factory import WorkflowFactory
        self.flow_factory = WorkflowFactory()
        self.perspectives = list(DEFAULT_PERSPECTIVES)
        
        self._executor = LLMExecutor(
            router=router,
            phase_configs=self.phase_configs,
            token_cache=token_cache,
            caching_enabled=TOKEN_OPTIMIZATION["caching"],
            cascading_routing=getattr(self.router, 'cascading_routing', None),
            cascading_quality_check=True,
            prompt_compression=TOKEN_OPTIMIZATION["neuro_compression"],
        )

    def _log(self, phase: str, message: str, state: PipelineState) -> None:
        if self.verbose: logger.info(f"[{phase}] {message}")
        state.log(phase, message)

    async def _build_attachment_context(
        self,
        attachments: list[dict[str, Any]],
        query: str | None = None,
    ) -> str:
        """Build a context string from extracted attachment texts.

        When DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED is true and a query is provided,
        retrieves only the most relevant chunks via semantic search instead of
        injecting the full document text.

        Format is designed to be unambiguous to LLMs: the injected text IS the
        actual file content. We use explicit markers so the model cannot mistake
        this for metadata or instructions.
        """
        from reasoner.core.settings import settings

        # ── Semantic retrieval path (opt-in) ──
        if (
            settings.DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED
            and query
            and attachments
        ):
            try:
                from reasoner.documents.vector_store import DocumentVectorStore

                store = DocumentVectorStore()
                file_ids = [att.get("file_id", "") for att in attachments if att.get("file_id")]
                chunks = await store.retrieve(query, file_ids, top_k=5, user_id=self.user_id)
                if chunks:
                    parts: list[str] = []
                    for i, chunk_text in enumerate(chunks, 1):
                        parts.append(
                            f"=== EXCERPT {i} (most relevant passage) ===\n"
                            f"[CONTENT START]\n"
                            f"{chunk_text}\n"
                            f"[CONTENT END]"
                        )
                    return (
                        "=== ATTACHED FILES (semantic excerpts) ===\n"
                        "The user has uploaded file(s). Below are the most relevant "
                        "passages retrieved from those files based on the query.\n\n"
                        + "\n\n".join(parts)
                        + "\n=== END OF ATTACHED FILES ==="
                    )
            except Exception as exc:
                logger.warning(
                    "Semantic attachment retrieval failed, falling back to full text: %s", exc
                )

        # ── Fallback: verbatim full-text injection ──
        parts: list[str] = []
        for att in attachments:
            filename = att.get("filename", "unknown")
            extracted = att.get("extracted_text", "").strip()
            if extracted:
                parts.append(
                    f"=== FILE: {filename} ===\n"
                    f"[CONTENT START]\n"
                    f"{extracted}\n"
                    f"[CONTENT END]"
                )
        if not parts:
            return ""
        return (
            "=== ATTACHED FILES (full content provided below) ===\n"
            "The user has uploaded the following file(s). "
            "Treat the content between [CONTENT START] and [CONTENT END] "
            "as the actual file contents.\n\n"
            + "\n\n".join(parts)
            + "\n=== END OF ATTACHED FILES ==="
        )

    def _workflow_services(self) -> Any:
        """Build a WorkflowServices bound to this pipeline for phase delegation."""
        from reasoner.application.flows.services import PipelineWorkflowServices
        return PipelineWorkflowServices(self)

    # ── Backward-compatible phase delegators ──────────────────────────────
    # The mixin-cleanup refactor (c7f3104) moved phase logic to standalone
    # `(state, services)` flow functions but left production callers (api/routes/
    # context.py) and the phase behavior tests referencing the old bound methods.
    # These thin delegators restore that contract without duplicating logic.

    async def _phase_2_perspectives(self, state: PipelineState) -> None:
        from reasoner.application.flows.perspective_phases import run_perspectives_phase
        await run_perspectives_phase(state, self._workflow_services(), perspectives=self.perspectives)

    async def _phase_3_critique(self, state: PipelineState) -> None:
        from reasoner.application.flows.perspective_phases import run_critique_phase
        await run_critique_phase(state, self._workflow_services())

    async def _phase_4_stress_test(self, state: PipelineState) -> None:
        from reasoner.application.flows.perspective_phases import run_stress_test_phase
        await run_stress_test_phase(state, self._workflow_services())

    async def _phase_synthesis(self, state: PipelineState) -> None:
        from reasoner.application.flows.synthesis_phase import run_synthesis_phase
        await run_synthesis_phase(state, self._workflow_services())

    async def _phase_deep_read(self, state: PipelineState) -> None:
        from reasoner.application.flows.search_phases import run_deep_read_phase
        await run_deep_read_phase(state, self._workflow_services(), domain=self.domain)

    def _validate_evidence_coverage(self, state: PipelineState) -> None:
        from reasoner.application.flows.search_phases import validate_evidence_coverage
        validate_evidence_coverage(state, self._workflow_services())

    @staticmethod
    def _enrich_query(query: str, problem: str) -> str:
        from reasoner.application.flows.search_phases import _enrich_query
        return _enrich_query(query, problem)

    async def _phase_jury_generate(self, state: PipelineState) -> None:
        from reasoner.application.flows.jury_phases import run_jury_generate_phase
        await run_jury_generate_phase(state, self._workflow_services())

    async def _phase_jury_critique(self, state: PipelineState) -> None:
        from reasoner.application.flows.jury_phases import run_jury_critique_phase
        await run_jury_critique_phase(
            state, self._workflow_services(), batch_critique=self.batch_critique_jury
        )

    async def _phase_jury_verify_and_meta_eval(self, state: PipelineState) -> None:
        from reasoner.application.flows.jury_phases import run_jury_verify_and_meta_eval_phase
        await run_jury_verify_and_meta_eval_phase(state, self._workflow_services())

    async def _phase_jury_weighted_ranking(self, state: PipelineState) -> None:
        from reasoner.application.flows.jury_phases import run_jury_weighted_ranking_phase
        await run_jury_weighted_ranking_phase(state, self._workflow_services())

    # CoVe
    async def _phase_cove_draft(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_cove_draft_phase
        await run_cove_draft_phase(state, self._workflow_services())

    async def _phase_cove_verify(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_cove_verify_phase
        await run_cove_verify_phase(state, self._workflow_services())

    async def _phase_cove_answer(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_cove_answer_phase
        await run_cove_answer_phase(state, self._workflow_services())

    async def _phase_cove_revise(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_cove_revise_phase
        await run_cove_revise_phase(state, self._workflow_services())

    # SoT
    async def _phase_sot_skeleton(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_sot_skeleton_phase
        await run_sot_skeleton_phase(state, self._workflow_services())

    async def _phase_sot_solve(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_sot_solve_phase
        await run_sot_solve_phase(state, self._workflow_services())

    async def _phase_sot_assemble(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_sot_assemble_phase
        await run_sot_assemble_phase(state, self._workflow_services())

    # ToT
    async def _phase_tot_decompose(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_tot_decompose_phase
        await run_tot_decompose_phase(state, self._workflow_services())

    async def _phase_tot_generate(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_tot_generate_phase
        await run_tot_generate_phase(state, self._workflow_services())

    async def _phase_tot_evaluate(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_tot_evaluate_phase
        await run_tot_evaluate_phase(state, self._workflow_services())

    async def _phase_tot_backtrack(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_tot_backtrack_phase
        await run_tot_backtrack_phase(state, self._workflow_services())

    # PoT
    async def _phase_pot_generate(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_pot_generate_phase
        await run_pot_generate_phase(state, self._workflow_services())

    async def _phase_pot_execute(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_pot_execute_phase
        await run_pot_execute_phase(state, self._workflow_services())

    async def _phase_pot_interpret(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_pot_interpret_phase
        await run_pot_interpret_phase(state, self._workflow_services())

    # Self-Discover
    async def _phase_sd_select(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_sd_select_phase
        await run_sd_select_phase(state, self._workflow_services())

    async def _phase_sd_adapt(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_sd_adapt_phase
        await run_sd_adapt_phase(state, self._workflow_services())

    async def _phase_sd_implement(self, state: PipelineState) -> None:
        from reasoner.application.flows.cognitive_phases import run_sd_implement_phase
        await run_sd_implement_phase(state, self._workflow_services())

    # Delphi
    async def _phase_delphi_round1(self, state: PipelineState) -> None:
        from reasoner.application.flows.delphi_phases import run_delphi_round1_phase
        await run_delphi_round1_phase(state, self._workflow_services())

    async def _phase_delphi_aggregation(self, state: PipelineState) -> None:
        from reasoner.application.flows.delphi_phases import run_delphi_aggregation_phase
        await run_delphi_aggregation_phase(state, self._workflow_services())

    async def _phase_delphi_round2(self, state: PipelineState) -> None:
        from reasoner.application.flows.delphi_phases import run_delphi_round2_phase
        await run_delphi_round2_phase(state, self._workflow_services())

    async def _phase_delphi_convergence(self, state: PipelineState) -> None:
        from reasoner.application.flows.delphi_phases import run_delphi_convergence_phase
        await run_delphi_convergence_phase(state, self._workflow_services())

    async def _phase_delphi_dissent(self, state: PipelineState) -> None:
        from reasoner.application.flows.delphi_phases import run_delphi_dissent_phase
        await run_delphi_dissent_phase(state, self._workflow_services())

    async def _call_llm_cached(
        self,
        role: str,
        system_prompt: str,
        user_prompt: str,
        state: PipelineState,
        phase_key: str | None = None,
        **kwargs: Any,
    ) -> tuple[str, dict[str, Any]]:
        return await self._executor.execute(
            role=role,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            state=state,
            phase_key=phase_key,
            **kwargs
        )

    def _get_method_from_preset(self) -> str:
        if not self.preset_name: return "multi_perspective"
        from reasoner.presets import get_method_from_preset
        return get_method_from_preset(self.preset_name)

    async def run(self, problem: str, method: str | None = None) -> PipelineState:
        """Execute the reasoning pipeline."""
        if not problem or not problem.strip():
            raise ValueError("Problem cannot be empty")
        start_time = time.monotonic()
        if not method:
            method = self._get_method_from_preset()
        
        from reasoner.application.event_bus.bus import get_event_bus
        from reasoner.core.events.domain_events import make_event, EventType
        bus = get_event_bus()

        state = self.initial_state or PipelineState(
            problem=problem,
            preset_name=self.preset_name,
            complexity=self.complexity or "unknown",
        )

        # ── Carry augmentation methods from preflight ──
        if self.augmentation_methods:
            state.meta.augmentation_methods = self.augmentation_methods

        # ── Publish Pipeline Started Event ──
        start_evt = make_event(
            EventType.PIPELINE_STARTED,
            aggregate_id=state.conversation_id or "unknown",
            version=1,
            problem=problem,
            preset=self.preset_name
        )
        await bus.publish(start_evt)
        
        self._log("ORCHESTRATOR", f"Routing to '{method}' method pipeline.", state)

        # ── Optional: Cross-Language Translate In ──
        from reasoner.core.settings import settings as _settings
        from reasoner.core.constants_limits import NATIVE_LANGUAGE_METHODS
        _pivot_eligible = (
            _settings.LANGUAGE_PIVOT_ENABLED
            and state.language
            and state.language != "English"
            and method not in NATIVE_LANGUAGE_METHODS
        )
        if _pivot_eligible:
            await self._phase_cross_language_translate_in(state)

        # ── B1: Sensitivity classification (regex fast path) ──────────
        if state.output_language != "English":
            from reasoner.application.services.sensitivity_service import classify_sensitivity
            _sensitive, _axis = classify_sensitivity(state.problem)
            state.language_sensitive = _sensitive
            if _sensitive:
                state.language_divergence = {"axis": _axis}
                self._log("LANG-PROBE", f"Sensitive axis detected: {_axis}", state)

        # ── Optional: Prompt Enhancement ──
        if self.enhance_prompt:
            await self._phase_enhance_prompt(state)
        else:
            state.enhanced_problem = state.problem

        # ── Mandatory: Fusion (Classification + Decomposition) ──
        await self._phase_fusion(state)

        # ── E3: Context compression after fusion, gated by flag ──
        if TOKEN_OPTIMIZATION.get("context_compression") and state.candidates:
            try:
                from reasoner.neuro.compression import smart_compress
                import dataclasses as _dc
                compressed = []
                for c in state.candidates:
                    content = getattr(c, "content", None) or (c.get("content") if isinstance(c, dict) else None)
                    if not content:
                        compressed.append(c)
                        continue
                    compressed_content = smart_compress(content, level="minimal")
                    if hasattr(c, "model_copy"):  # Pydantic v2
                        compressed.append(c.model_copy(update={"content": compressed_content}))
                    elif _dc.is_dataclass(c) and not isinstance(c, type):  # stdlib dataclass
                        compressed.append(_dc.replace(c, content=compressed_content))
                    elif isinstance(c, dict):  # plain dict
                        compressed.append({**c, "content": compressed_content})
                    else:
                        compressed.append(c)
                state.candidates = compressed
                logger.debug("E3: Compressed %d candidates after fusion", len(compressed))
            except Exception as exc:
                logger.debug("E3: Context compression skipped: %s", exc)
        else:
            logger.debug("E3: Context compression disabled or no candidates")

        # --- DYNAMIC METHOD DISPATCH ---
        if self.flow_factory.is_migrated(method):
            from reasoner.application.flows.services import PipelineWorkflowServices
            from reasoner.application.flows.runner import WorkflowRunner
            
            strategy = self.flow_factory.get_strategy(method)
            runner = WorkflowRunner(PipelineWorkflowServices(self))
            services = PipelineWorkflowServices(self, runner=runner)
            
            await runner.run(strategy, state)
        else:
            # Legacy path (should be empty now)
            self._log("ORCHESTRATOR", f"FATAL: Method '{method}' not migrated to Strategy pattern.", state)
            state.errors.append(f"Unmigrated method: {method}")

        # ── Optional: Post-Synthesis Verification ──
        await self._phase_post_synthesis_verify(state)

        # ── Optional: B2-B4 Cross-Lingual Probe ─────────────────────────
        if state.language_sensitive and state.pivot_active:
            from reasoner.application.flows.language_probe_phase import run_language_probe_phase
            from reasoner.application.flows.services import PipelineWorkflowServices
            _probe_services = PipelineWorkflowServices(self)
            await run_language_probe_phase(state, _probe_services)

        # ── Optional: Cross-Language Translate Out ──
        if state.pivot_active:
            await self._phase_cross_language_translate_out(state)

        # ── Publish Pipeline Completed Event ──
        total_tokens = sum(t.get("total", 0) for t in state.phase_tokens.values())
        done_evt = make_event(
            EventType.PIPELINE_COMPLETED,
            aggregate_id=state.conversation_id or "unknown",
            version=1,
            total_duration_seconds=time.monotonic() - start_time if 'start_time' in locals() else 0,
            total_tokens={"total": total_tokens},
            solution={"core_solution": state.final_solution.core_solution if state.final_solution else ""}
        )
        await bus.publish(done_evt)

        return state

    @timed
    async def _phase_enhance_prompt(self, state: PipelineState):
        if state.enhanced_problem:
            self._log("PROMPT-ENHANCE", "Using cached enhanced prompt.", state)
            return

        if USE_PHASE_SUBAGENTS["enhancement"]:
            from reasoner.subagents.enhancement.hyper_agent import EnhancementHyperAgent
            agent = EnhancementHyperAgent()
            try:
                enhanced = await agent.execute(state, self.router)
                if self._validate_enhancement(state.problem, enhanced):
                    state.enhanced_problem = enhanced
                    self._log("PROMPT-ENHANCE", f"Enhanced prompt: {enhanced[:TRUNCATION.API_STORAGE]}...", state)
                else:
                    state.enhanced_problem = state.problem
            except Exception as exc:
                state.enhanced_problem = state.problem
            return

        from reasoner.phases import detect_language
        lang = state.language or detect_language(state.problem)
        raw, _ = await self._call_llm_cached(
            role="prompt_enhancement",
            system_prompt=phases.PROMPT_ENHANCEMENT_SYSTEM,
            user_prompt=phases.prompt_enhancement_prompt(state.problem, lang),
            state=state,
        )
        try:
            data = extract_json(raw)
            enhanced = data.get("enhanced_problem", "").strip()
            if self._validate_enhancement(state.problem, enhanced):
                state.enhanced_problem = enhanced
            else:
                state.enhanced_problem = state.problem
        except Exception:
            state.enhanced_problem = state.problem

    def _validate_enhancement(self, original: str, enhanced: str) -> bool:
        if not enhanced or len(enhanced) < 10: return False
        if len(enhanced) > len(original) * 5: return False
        from reasoner.phases._shared import detect_language
        if detect_language(original) != detect_language(enhanced):
            return False
        return True

    @timed
    async def _phase_fusion(self, state: PipelineState):
        self._log("PHASE-FUSION", "Classifying task and decomposing problem...", state)
        from reasoner.phases._shared import detect_language
        problem = state.enhanced_problem or state.problem
        lang = detect_language(problem)

        raw, _ = await self._call_llm_cached(
            role="fusion",
            system_prompt=phases.FUSION_SYSTEM,
            user_prompt=phases.fusion_prompt(state, lang),
            state=state,
        )
        try:
            data = extract_json(raw)
        except Exception:
            self._log("PHASE-FUSION", "JSON extraction failed, using defaults", state)
            data = {}
        state.task_type = TaskType.coerce(data.get("task_type"))
        detected_lang = data.get("language") or lang
        if detected_lang == "English" and lang != "English":
            detected_lang = lang
        state.language = detected_lang
        state.decomposition = {
            "causal_chain": data.get("causal_chain", []),
            "assumptions": data.get("assumptions", []),
            "failure_modes": data.get("failure_modes", []),
            "critical_sources": data.get("critical_sources", []),
        }
        self._log("PHASE-FUSION", f"Task type: {state.task_type.value}, Language: {state.language}", state)

    @timed
    async def _phase_post_synthesis_verify(self, state: PipelineState) -> None:
        if not state.final_solution: return
        synthesis_text = state.final_solution.core_solution
        if not synthesis_text: return
        self._log("POST-SYNTHESIS", "Running cross-model verification...", state)
        try:
            raw, _ = await self._call_llm_cached(
                role="post_synthesis_verify",
                system_prompt=phases.POST_SYNTHESIS_VERIFY_SYSTEM,
                user_prompt=phases.post_synthesis_verify_prompt(synthesis_text, state), state=state)
            data = extract_json(raw)
            state.final_solution.verification_audit = {
                "verification_questions": data.get("verification_questions", []),
                "evaluation": data.get("evaluation", []),
                "recommendations": data.get("recommendations", []),
            }
        except Exception as e:
            self._log("POST-SYNTHESIS", f"Verification failed: {e}", state)

    async def _phase_cross_language_translate_in(self, state: PipelineState) -> None:
        from reasoner.infrastructure.translation import get_composite_translator
        source_lang = state.language
        if not source_lang or source_lang.lower() in ("english", "en", "unknown", ""):
            return
        original_problem = state.problem
        original_enhanced = state.enhanced_problem
        self._log("CROSS-LANG", f"Pivot: translating problem from {source_lang} to English.", state)
        # Record user's detected language before overwriting state.language.
        state.output_language = source_lang
        try:
            translator = get_composite_translator(router=self.router)
            result = await translator.translate(original_problem, target_lang="EN", source_lang=source_lang)
            if result.degraded:
                # The composite never raises -- it falls back to identity. Without
                # this branch a failed pivot looked identical to a successful one:
                # state.problem kept its source-language text, pivot_active was set,
                # and every downstream phase reasoned in the wrong language with
                # nothing in state.errors to show for it.
                raise RuntimeError(result.degraded_reason or "all translators failed")
            translated = result.text or original_problem
            state.problem = translated
            if original_enhanced and original_enhanced != original_problem:
                enh_result = await translator.translate(original_enhanced, target_lang="EN", source_lang=source_lang)
                state.enhanced_problem = enh_result.text or original_enhanced
            else:
                state.enhanced_problem = translated
            # Explicit pivot: set reasoning language to English; get_language_instruction()
            # keys on state.language so all 25 phase modules automatically reason in English.
            state.language = "English"
            state.pivot_active = True
            # Keep cross_language_state for legacy callers / resume compat.
            state.cross_language_state = {
                "original_problem": original_problem,
                "original_enhanced": original_enhanced,
                # The translator's detected code (e.g. "DE") is more precise than
                # the pipeline's own language guess (e.g. "German").
                "source_language": result.detected_source_language or source_lang,
                "translated_problem": translated,
                "direction": "in",
            }
        except Exception as e:
            self._log("CROSS-LANG", f"Translate-in failed ({e}); pivot aborted — reasoning in {source_lang}.", state)
            state.errors.append(f"translation-in error: {e}")

    async def _phase_cross_language_translate_out(self, state: PipelineState) -> None:
        from reasoner.infrastructure.translation import get_composite_translator
        from reasoner.core.constants_limits import LANG_NAME_TO_ISO
        if not state.pivot_active or not state.output_language or state.output_language == "English":
            return
        target_lang_name = state.output_language
        target_lang_iso = LANG_NAME_TO_ISO.get(target_lang_name, target_lang_name.upper()[:2])
        if not state.final_solution:
            self._log("CROSS-LANG", "No final_solution to translate out; skipping.", state)
            return
        self._log("CROSS-LANG", f"Translating output to {target_lang_name} ({target_lang_iso}).", state)
        try:
            translator = get_composite_translator(router=self.router)
            fs = state.final_solution

            async def _t(text: str) -> str:
                if not text or not text.strip():
                    return text
                res = await translator.translate(text, target_lang=target_lang_iso, source_lang="EN")
                if res.degraded:
                    # Fail the whole translate-out rather than emitting a solution
                    # half in English and half in the target language.
                    raise RuntimeError(res.degraded_reason or "all translators failed")
                return res.text or text

            fs.core_solution = await _t(fs.core_solution)
            fs.critical_insights = [await _t(s) for s in (fs.critical_insights or [])]
            fs.open_questions = [await _t(s) for s in (fs.open_questions or [])]

            translated_blueprint = []
            for step in (fs.action_blueprint or []):
                if isinstance(step, dict):
                    translated_step = dict(step)
                    for key in ("step", "action", "rationale", "expected_outcome"):
                        if key in translated_step and isinstance(translated_step[key], str):
                            translated_step[key] = await _t(translated_step[key])
                    translated_blueprint.append(translated_step)
                else:
                    translated_blueprint.append(step)
            fs.action_blueprint = translated_blueprint

            audit = fs.meta_audit
            if audit is not None:
                for attr in (
                    "most_dangerous_assumption",
                    "dominant_bias",
                    "remaining_uncertainty",
                    "assumption_failure_impact",
                    "non_obvious_insight",
                ):
                    val = getattr(audit, attr, None)
                    if isinstance(val, str):
                        setattr(audit, attr, await _t(val))

            for src in (fs.sources or []):
                if isinstance(src, dict) and "title" in src:
                    src["title"] = await _t(src["title"])

            if state.cross_language_state:
                state.cross_language_state["direction"] = "out"
                # Record the back-translated synthesis: the SSE payload and any
                # --resume of this state need to know the output was translated,
                # and "direction" alone does not say it succeeded.
                state.cross_language_state["translated_synthesis"] = fs.core_solution
        except Exception as e:
            self._log("CROSS-LANG", f"Translate-out failed ({e}); output stays in English.", state)
            state.errors.append(f"translation-out error: {e}")
