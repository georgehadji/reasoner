"""Perspective and critique phases logic."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from reasoner.core.constants import TRUNCATION, get_token_budget, DEFAULT_MAX_TOKENS
from reasoner.infrastructure.search.discovery import get_search_client_for_method
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
from reasoner.parsing import ParseError, extract_json, _parse_critique_scores, _parse_review_hypotheses
from reasoner.domain.preset_core import get_preset_price_tier
import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices
from reasoner.application.services.recovery_service import RecoveryService

logger = logging.getLogger(__name__)

async def run_multi_perspective_research_phase(state: PipelineState, services: WorkflowServices) -> None:
    """Search for evidence to ground perspective generation."""
    services.log("PHASE-2", "Gathering evidence for multi-perspective analysis...", state)
    try:
        from reasoner.presets import get_preset_price_tier
        tier = get_preset_price_tier(state.preset_name) or "budget"
        client, _ = await get_search_client_for_method("multi_perspective", tier, source_type="general")

        raw_plan, _ = await services.call_llm(
            role="primary",
            system_prompt=phases.ARTICLE_RETRIEVAL_PLAN_SYSTEM,
            user_prompt=phases.article_retrieval_plan_prompt(state),
            state=state
        )
        plan = extract_json(raw_plan)
        queries = plan.get("queries", [])[:3]

        async def _search(q):
            try: return await client.search(q, num_results=5)
            except Exception: return []

        results = await asyncio.gather(*[_search(q) for q in queries], return_exceptions=True)
        flattened = []
        seen = set()
        for r_list in results:
            if isinstance(r_list, list):
                for r in r_list:
                    url = r.get("url", "")
                    if url not in seen:
                        seen.add(url)
                        flattened.append(r)

        state.web_discovery_results = flattened[:10]
        if flattened:
            services.log("PHASE-2", f"Found {len(flattened)} relevant sources.", state)
    except Exception as e:
        services.log("PHASE-2", f"Evidence search failed: {e}", state)


async def run_perspectives_phase(
    state: PipelineState, 
    services: WorkflowServices,
    parallel: bool = True,
    perspectives: list[Any] = None
) -> None:
    services.log("PHASE-2", "Running multi-perspective analysis...", state)
    
    if perspectives is None:
        from reasoner.core import DEFAULT_PERSPECTIVES
        perspectives = services.perspectives or list(DEFAULT_PERSPECTIVES)

    # Warn on diversity collapse: all perspectives resolve to the same model, or
    # all to a single geopolitical bloc. Cross-bloc spread (not just cross-company)
    # is what mitigates creator ideology (Buyl et al. npj AI 2026) — so we surface
    # both failure modes and recommend keys across blocs, not one ecosystem.
    _perspective_roles = {"constructive", "destructive", "systemic", "minimalist"}
    _active_models = {
        getattr(services.router.routing_table.get(r, services.router.primary), "model", "")
        for r in _perspective_roles
    }
    # Bloc inferred from the resolved vendor prefix (e.g. "anthropic/…" → US).
    _US = {"anthropic", "openai", "google", "x-ai", "perplexity", "meta-llama",
           "poolside", "arcee-ai", "nvidia", "nousresearch", "morph"}
    _CN = {"deepseek", "qwen", "moonshotai", "z-ai", "xiaomi", "tencent",
           "bytedance-seed", "inclusionai", "stepfun", "minimax", "baidu"}
    _EU = {"mistralai"}

    def _bloc(model: str) -> str:
        vendor = model.lstrip("~").split("/", 1)[0]
        if vendor in _US:
            return "US"
        if vendor in _CN:
            return "CN"
        if vendor in _EU:
            return "EU"
        return "OTHER"

    _active_blocs = {_bloc(m) for m in _active_models if m} - {"OTHER"}
    if len(_active_models) < 2:
        state.pending_events.append({
            "type": "phase_warning",
            "message": "All perspectives using the same model — diversity collapsed. Add API keys spanning blocs (e.g. Anthropic/OpenAI 🇺🇸, DeepSeek/Qwen 🇨🇳, Mistral 🇪🇺) to restore cross-bloc reasoning.",
        })
    elif len(_active_blocs) < 2:
        state.pending_events.append({
            "type": "phase_warning",
            "message": "All perspectives resolve to a single geopolitical bloc — creator-ideology bias is not mitigated. Add API keys from a different bloc (🇺🇸/🇨🇳/🇪🇺) for cross-bloc diversity.",
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

    from reasoner.domain.pipeline_state import PhaseOutput
    # mutated_in_place=True: every executor (SSE path, runner, services fallback)
    # calls the phase function and drops its return, so the delta has to be
    # written to `state` here or the candidates are lost and Phase 3 skips.
    # apply_to() no-ops on this flag, so the DAG runner cannot double-apply.
    output = PhaseOutput(candidates=[], errors=[], mutated_in_place=True)

    if parallel:
        tasks = [_get_perspective(_perspective_name(p)) for p in perspectives]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            p_name = _perspective_name(perspectives[i])
            if isinstance(r, Exception):
                msg = f"Perspective '{p_name}' failed: {r}"
                services.log("PHASE-2", msg, state)
                output.errors.append(msg)
            elif not r.content or not r.content.strip():
                msg = f"Perspective '{p_name}' returned empty content — skipping"
                services.log("PHASE-2", msg, state)
                output.errors.append(msg)
            else:
                if _is_perspective_hallucinated(r):
                    services.log("PHASE-2", f"Filtering hallucinated perspective '{p_name}'; regenerating once.", state)
                    try:
                        replacement = await _get_perspective(p_name)
                        if replacement.content and replacement.content.strip():
                            output.candidates.append(replacement)
                        else:
                            msg = f"Regeneration for '{p_name}' also empty — skipping"
                            services.log("PHASE-2", msg, state)
                            output.errors.append(msg)
                    except Exception as exc:
                        msg = f"Regeneration failed for '{p_name}': {exc}"
                        services.log("PHASE-2", msg, state)
                        output.errors.append(msg)
                else:
                    output.candidates.append(r)
    else:
        for p in perspectives:
            p_name = _perspective_name(p)
            try:
                candidate = await _get_perspective(p_name)
                if not candidate.content or not candidate.content.strip():
                    services.log("PHASE-2", f"Perspective '{p_name}' returned empty content — skipping", state)
                    output.errors.append(f"Perspective '{p_name}' returned empty content")
                    continue
                if _is_perspective_hallucinated(candidate):
                    services.log("PHASE-2", f"Filtering hallucinated perspective '{p_name}'; regenerating once.", state)
                    candidate = await _get_perspective(p_name)
                    if not candidate.content or not candidate.content.strip():
                        services.log("PHASE-2", f"Regeneration for '{p_name}' also empty — skipping", state)
                        continue
                output.candidates.append(candidate)
            except Exception as e:
                msg = f"Perspective '{p_name}' failed: {e}"
                services.log("PHASE-2", msg, state)
                output.errors.append(msg)

    state.candidates.extend(output.candidates)
    state.errors.extend(output.errors)
    return output

async def run_critique_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("PHASE-3", "Running adversarial critique and scoring...", state)
    if not state.candidates:
        services.log("PHASE-3", "No candidates to critique. Skipping.", state)
        return

    # VS critique is a premium-tier opt-in: budget runs stay byte-identical.
    preset_name = getattr(state, "preset_name", None) or getattr(state.meta, "preset_name", None) or ""
    with_hypotheses = get_preset_price_tier(preset_name) == "premium"

    raw, _ = await services.call_llm(
        role="scoring",
        system_prompt=phases.CRITIQUE_SYSTEM,
        user_prompt=phases.critique_prompt(state, with_hypotheses=with_hypotheses),
        state=state,
    )
    try:
        data = extract_json(raw)
        scores = _parse_critique_scores(data.get("scores", []))
        state.scores = scores

        if with_hypotheses:
            hypotheses = _parse_review_hypotheses(data.get("review_hypotheses", []))
            state.review_hypotheses = hypotheses
            if hypotheses:
                top = hypotheses[0]
                services.log(
                    "PHASE-3",
                    f"VS critique: {len(hypotheses)} failure hypotheses "
                    f"(top: {top.severity} p={top.probability:.2f} — {top.claim[:80]})",
                    state,
                )

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
        # Cap candidates to prevent unbounded memory growth (P4)
        if len(state.candidates) > 8:
            state.candidates = state.candidates[:8]
        state.top_candidates = state.candidates[:2]
        services.log("PHASE-3", f"Top candidates selected: {[c.perspective.value for c in state.top_candidates]}", state)
    except Exception as e:
        services.log("PHASE-3", f"Scoring failed: {e}", state)
        state.errors.append(f"Scoring failed: {e}")
        state.top_candidates = state.candidates[:2]

# Failure modes describing the model's own generation limits rather than a
# real-world risk. STRESS_SYSTEM already tells the model to avoid these, but a
# prompt is not a guarantee, and letting them through puts "the answer got cut
# off" in front of users as if it were a finding about their problem.
_SELF_REFERENTIAL_FAILURE_MARKERS = (
    "truncat",
    "length limit",
    "token limit",
    "max_tokens",
    "output was cut",
    "incomplete response",
    "malformed json",
    "parsing error",
    "off-topic response",
    "formatting issue",
)


def _is_self_referential_failure(failure_mode: str) -> bool:
    lowered = (failure_mode or "").lower()
    return any(marker in lowered for marker in _SELF_REFERENTIAL_FAILURE_MARKERS)


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
            if not _is_self_referential_failure(st.get("failure_mode", ""))
        ]
    except Exception as e:
        services.log("PHASE-4", f"Stress test failed: {e}", state)
        state.errors.append(f"Stress test failed: {e}")
