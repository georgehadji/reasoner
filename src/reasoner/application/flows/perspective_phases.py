"""Perspective and critique phases logic."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from reasoner.core.constants import TRUNCATION, get_token_budget, DEFAULT_MAX_TOKENS
from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.core_types import (
    SolutionCandidate,
    StressTestResult,
    ScenarioType,
)
from reasoner.models import (
    PerspectiveRegistry,
    PerspectiveType,
)
from reasoner.parsing import ParseError, extract_json, _parse_critique_scores
import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices
from reasoner.application.services.recovery_service import RecoveryService

logger = logging.getLogger(__name__)

async def run_perspectives_phase(
    state: PipelineState, 
    services: WorkflowServices,
    parallel: bool = True,
    perspectives: list[Any] = None
) -> None:
    services.log("PHASE-2", "Running multi-perspective analysis...", state)
    
    if perspectives is None:
        from reasoner.core import DEFAULT_PERSPECTIVES
        perspectives = list(DEFAULT_PERSPECTIVES)

    # Warn when all perspective roles resolve to the same model (diversity collapse).
    _perspective_roles = {"constructive", "destructive", "systemic", "minimalist"}
    _active_models = {
        getattr(services.router.routing_table.get(r, services.router.primary), "model", "")
        for r in _perspective_roles
    }
    if len(_active_models) < 2:
        state.pending_events.append({
            "type": "phase_warning",
            "message": "All perspectives using the same model — cross-lab diversity unavailable. Add API keys for Anthropic, OpenAI, or Google to improve result quality.",
        })

    _PERSPECTIVE_HALLUCINATION_KEYWORDS = {"greek text", "greek characters", "parsing errors", "encoding issues", "unicode problems"}

    def _is_perspective_hallucinated(candidate: SolutionCandidate) -> bool:
        if state.language != "English":
            return False
        text = f"{candidate.content} {' '.join(candidate.key_insights)}".lower()
        return any(kw in text for kw in _PERSPECTIVE_HALLUCINATION_KEYWORDS)

    async def _get_perspective(p_name: str):
        from reasoner.pipeline import TOKEN_OPTIMIZATION
        p_enum = PerspectiveRegistry.coerce(p_name)
        base_system = phases.PERSPECTIVE_SYSTEMS.get(p_name, "")
        lang_instruction = phases.get_language_instruction(state)
        system_prompt = f"{lang_instruction}\n\n{base_system}"
        user_prompt = phases.perspective_prompt(state, p_name)
        
        raw, _ = await services.call_llm(
            role=p_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            state=state,
            max_tokens=get_token_budget(p_name) if TOKEN_OPTIMIZATION["dynamic_budgets"] else DEFAULT_MAX_TOKENS
        )
        data = extract_json(raw)
        core_analysis = data.get("core_analysis") or ""
        if not isinstance(core_analysis, str):
            import json
            core_analysis = json.dumps(core_analysis, ensure_ascii=False) if isinstance(core_analysis, (dict, list)) else str(core_analysis)
        
        if not core_analysis and isinstance(data, dict) and len(data) > 1:
            import json
            core_analysis = json.dumps(data, ensure_ascii=False)
            key_insights = []
            services.log("PHASE-2", f"Perspective '{p_name}' returned non-standard schema; using full JSON as content.", state)
        else:
            key_insights = data.get("key_insights") or []
            if not isinstance(key_insights, list):
                key_insights = [str(key_insights)] if key_insights else []
        
        return SolutionCandidate(
            perspective=p_enum,
            content=core_analysis,
            key_insights=key_insights,
            model_used="",
        )

    def _perspective_name(p) -> str:
        return p.name if hasattr(p, 'name') else str(p)

    if parallel:
        tasks = [_get_perspective(_perspective_name(p)) for p in perspectives]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            p_name = _perspective_name(perspectives[i])
            if isinstance(r, Exception):
                msg = f"Perspective '{p_name}' failed: {r}"
                services.log("PHASE-2", msg, state)
                state.errors.append(msg)
            else:
                if _is_perspective_hallucinated(r):
                    services.log("PHASE-2", f"Filtering hallucinated perspective '{p_name}'; regenerating once.", state)
                    try:
                        replacement = await _get_perspective(p_name)
                        state.candidates.append(replacement)
                    except Exception as exc:
                        services.log("PHASE-2", f"Regeneration failed for '{p_name}': {exc}", state)
                else:
                    state.candidates.append(r)
    else:
        for p in perspectives:
            p_name = _perspective_name(p)
            try:
                candidate = await _get_perspective(p_name)
                if _is_perspective_hallucinated(candidate):
                    services.log("PHASE-2", f"Filtering hallucinated perspective '{p_name}'; regenerating once.", state)
                    candidate = await _get_perspective(p_name)
                state.candidates.append(candidate)
            except Exception as e:
                msg = f"Perspective '{p_name}' failed: {e}"
                services.log("PHASE-2", msg, state)
                state.errors.append(msg)

async def run_critique_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("PHASE-3", "Running adversarial critique and scoring...", state)
    if not state.candidates:
        services.log("PHASE-3", "No candidates to critique. Skipping.", state)
        return

    raw, _ = await services.call_llm(
        role="scoring",
        system_prompt=phases.CRITIQUE_SYSTEM,
        user_prompt=phases.critique_prompt(state),
        state=state,
    )
    try:
        data = extract_json(raw)
        scores = _parse_critique_scores(data.get("scores", []))
        state.scores = scores
        
        # Recovery path check
        for score in state.scores:
            if score.confidence_vs_accuracy_penalty > 5.0: # Threshold for triggering recovery
                candidate_to_check = next((c for c in state.candidates if c.perspective == score.perspective), None)
                if candidate_to_check:
                    services.log("PHASE-3", f"High penalty for candidate {score.perspective}. Triggering recovery path.", state)
                    await RecoveryService.run_recovery_path(state, services, candidate_to_check)

        # Rank candidates by score
        score_map = {s.perspective: s.total for s in scores}
        state.candidates.sort(key=lambda c: score_map.get(c.perspective, 0.0), reverse=True)
        state.top_candidates = state.candidates[:2]
        services.log("PHASE-3", f"Top candidates selected: {[c.perspective.value for c in state.top_candidates]}", state)
    except Exception as e:
        services.log("PHASE-3", f"Scoring failed: {e}", state)
        state.errors.append(f"Scoring failed: {e}")
        state.top_candidates = state.candidates[:2]

async def run_stress_test_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("PHASE-4", "Running scenario-based stress testing...", state)
    if not state.top_candidates:
        services.log("PHASE-4", "No top candidates to stress test. Skipping.", state)
        return

    raw, _ = await services.call_llm(
        role="stress_testing",
        system_prompt=phases.STRESS_SYSTEM,
        user_prompt=phases.stress_test_prompt(state),
        state=state,
    )
    try:
        data = extract_json(raw)
        state.stress_results = [
            StressTestResult(
                scenario=ScenarioType.coerce(st.get("scenario", "optimal")),
                survival_rate=float(st.get("survival_rate") or 0.0),
                failure_mode=st.get("failure_mode", ""),
                recovery_path=st.get("recovery_path", ""),
            )
            for st in data.get("stress_tests", [])
        ]
    except Exception as e:
        services.log("PHASE-4", f"Stress test failed: {e}", state)
        state.errors.append(f"Stress test failed: {e}")
