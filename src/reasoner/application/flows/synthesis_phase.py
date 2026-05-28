"""Synthesis phase logic."""

from __future__ import annotations

import logging
import re
from typing import Any

from reasoner.core.constants import ARTICLE_MIN_SOURCE_COUNT, ARTICLE_MIN_CLAIM_SUPPORT_RATIO, get_token_budget, DEFAULT_MAX_TOKENS, TRUNCATION
from reasoner.models import PipelineState, FinalSolution, MetaCognitiveAudit, ClaimLabel, TaskType
from reasoner.parsing import extract_solution_prose, extract_json, strip_json_fences, ParseError
from reasoner.sanitization import clean_llm_artifacts
import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices

logger = logging.getLogger(__name__)

async def run_synthesis_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("SYNTHESIS", "Synthesizing final solution...", state)

    # Simplified synthesis logic extracted from pipeline.py
    from reasoner.pipeline import TOKEN_OPTIMIZATION, USE_PHASE_SUBAGENTS
    
    # ── Subagent path (opt-in via env) ────────────────────────────
    if USE_PHASE_SUBAGENTS["synthesis"]:
        from reasoner.subagents.synthesis.hyper_agent import SynthesisHyperAgent
        agent = SynthesisHyperAgent()
        try:
            state.final_solution = await agent.execute(state, services.router)
            services.log("SYNTHESIS", "SynthesisHyperAgent complete.", state)
            return
        except Exception as exc:
            services.log("SYNTHESIS", f"SynthesisHyperAgent failed ({exc}), falling back to legacy.", state)

    # ── Legacy monolithic path ─────────────────────────────────────
    system_prompt = phases.SYNTHESIS_SYSTEM
    raw, _ = await services.call_llm(
        role="synthesis",
        system_prompt=system_prompt,
        user_prompt=phases.synthesis_prompt(state),
        state=state,
        max_tokens=get_token_budget("synthesis") if TOKEN_OPTIMIZATION["dynamic_budgets"] else DEFAULT_MAX_TOKENS
    )
    
    try:
        json_data = extract_json(raw) or {}
    except ParseError as exc:
        services.log("SYNTHESIS", f"Failed to parse JSON from synthesis: {exc}", state)
        json_data = {}

    def _reconstruct_prose(data: dict) -> str:
        parts = []
        insights = data.get("critical_insights", [])
        if insights:
            parts.append("Critical Insights:\n" + "\n".join(f"- {i}" for i in insights))
        bp = data.get("action_blueprint", [])
        if bp:
            parts.append("Action Blueprint:\n" + "\n".join(
                f"- {b.get('step', '')}: {b.get('action', '')}" for b in bp if isinstance(b, dict)
            ))
        oq = data.get("open_questions", [])
        if oq:
            parts.append("Open Questions:\n" + "\n".join(f"- {q}" for q in oq))
        return "\n\n".join(parts)

    core_solution = extract_solution_prose(raw)
    if not core_solution:
        core_solution = json_data.get("core_solution", "")
    if not core_solution:
        core_solution = _reconstruct_prose(json_data)
    if not core_solution:
        core_solution = strip_json_fences(raw)

    core_solution = clean_llm_artifacts(core_solution)

    # Citation integrity validator
    allowed_urls = {r.get("url", "").rstrip("/") for r in (state.vetted_context or [])}
    allowed_urls.update(r.get("url", "").rstrip("/") for r in (state.web_discovery_results or []))
    found_urls = set(re.findall(r"https?://[^\s\)\]]+", core_solution))
    for url in found_urls:
        base = url.rstrip("/")
        if base and base not in allowed_urls:
            services.log("SYNTHESIS", f"Citation integrity warning: {url} not found in current context", state)

    # Safely handle claim labels
    raw_labels = json_data.get("claim_labels", {})
    if not isinstance(raw_labels, dict): raw_labels = {}
    clean_labels = {}
    for k, v in raw_labels.items():
        try:
            if v in [e.value for e in ClaimLabel]:
                clean_labels[k] = ClaimLabel(v)
            else:
                clean_labels[k] = ClaimLabel.UNKNOWN
        except Exception:
            clean_labels[k] = ClaimLabel.UNKNOWN

    # Safely handle meta audit
    meta_audit_data = json_data.get("meta_audit", {})
    if not isinstance(meta_audit_data, dict): meta_audit_data = {}

    # Safely coerce sources
    def _coerce_sources(items):
        out = []
        for item in items:
            if isinstance(item, dict) and "title" in item:
                out.append({"title": str(item.get("title", "")), "url": str(item.get("url", ""))})
            elif isinstance(item, str):
                m = re.search(r"\[([^\]]+)\]\(([^)]+)\)", item)
                if m:
                    out.append({"title": m.group(1).strip(), "url": m.group(2).strip()})
                else:
                    out.append({"title": item.strip(), "url": ""})
        return out

    # Sanitize action blueprint
    raw_bp = json_data.get("action_blueprint", [])
    clean_bp = []
    for step in (raw_bp if isinstance(raw_bp, list) else []):
        if isinstance(step, dict):
            if not any(k in step for k in ("step", "action", "time_horizon", "go_criteria", "fallback")):
                continue
            if not str(step.get("step", "") or "").strip() and not str(step.get("action", "") or "").strip():
                continue
            clean_bp.append(step)
        elif step is not None and str(step).strip():
            clean_bp.append({"step": "", "action": str(step).strip(), "time_horizon": "", "go_criteria": "", "fallback": ""})

    state.final_solution = FinalSolution(
        core_solution=core_solution,
        critical_insights=json_data.get("critical_insights", []),
        action_blueprint=clean_bp,
        open_questions=json_data.get("open_questions", []),
        claim_labels=clean_labels,
        meta_audit=MetaCognitiveAudit(
            most_dangerous_assumption=meta_audit_data.get("most_dangerous_assumption", ""),
            dominant_bias=meta_audit_data.get("dominant_bias", ""),
            remaining_uncertainty=meta_audit_data.get("remaining_uncertainty", ""),
            assumption_failure_impact=meta_audit_data.get("assumption_failure_impact", ""),
            non_obvious_insight=meta_audit_data.get("non_obvious_insight", "")
        ),
        sources=_coerce_sources(json_data.get("sources", [])),
        layout_hints=json_data.get("layout_hints", {})
    )
