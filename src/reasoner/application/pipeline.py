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

        # ── Optional: Prompt Enhancement ──
        if self.enhance_prompt:
            await self._phase_enhance_prompt(state)

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
                "source_language": source_lang,
                "translated_problem": translated,
                "direction": "in",
            }
        except Exception as e:
            self._log("CROSS-LANG", f"Translate-in failed ({e}); pivot aborted — reasoning in {source_lang}.", state)

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
        except Exception as e:
            self._log("CROSS-LANG", f"Translate-out failed ({e}); output stays in English.", state)
