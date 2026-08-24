"""Synthesis phase logic."""

from __future__ import annotations

import logging
import re

import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices
from reasoner.core.constants import (
    DEFAULT_MAX_TOKENS,
    get_token_budget,
)
from reasoner.domain.core_types import (
    FinalSolution,
    MetaCognitiveAudit,
)
from reasoner.domain.pipeline_state import PipelineState
from reasoner.models import (
    ClaimLabel,
)
from reasoner.parsing import (
    ParseError,
    extract_json,
    extract_solution_prose,
    parse_evidence_bundles,
    strip_json_fences,
)
from reasoner.sanitization import clean_llm_artifacts_with_report

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

    core_solution, core_solution_report = clean_llm_artifacts_with_report(core_solution)

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

    # Parse evidence bundles
    raw_evidence = json_data.get("evidence", {})
    evidence_bundles = parse_evidence_bundles(raw_evidence)

    # Apply promotion rules: model-sourced VERIFIED is capped at HYPOTHESIS
    # This import is lazy to avoid circular dependency at module level
    try:
        from reasoner.application.services.evidence_service import apply_promotion_rules
        evidence_bundles = apply_promotion_rules(evidence_bundles)
    except Exception:
        pass

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

    # Egress Layer A scrub on the remaining user-facing prose fields --
    # core_solution was already scrubbed above via clean_llm_artifacts_with_report.
    def _scrub_strings(items: list) -> tuple[list[str], int]:
        cleaned: list[str] = []
        changed = 0
        for item in items:
            text, report = clean_llm_artifacts_with_report(str(item))
            cleaned.append(text)
            if report is not None:
                changed += report.suspicious_total
        return cleaned, changed

    def _scrub_blueprint_steps(items: list[dict]) -> tuple[list[dict], int]:
        changed = 0
        cleaned: list[dict] = []
        for step in items:
            new_step = dict(step)
            for key in ("step", "action", "time_horizon", "go_criteria", "fallback"):
                if key in new_step and new_step[key]:
                    text, report = clean_llm_artifacts_with_report(str(new_step[key]))
                    new_step[key] = text
                    if report is not None:
                        changed += report.suspicious_total
            cleaned.append(new_step)
        return cleaned, changed

    critical_insights, insights_changed = _scrub_strings(json_data.get("critical_insights", []))
    open_questions, questions_changed = _scrub_strings(json_data.get("open_questions", []))
    clean_bp, blueprint_changed = _scrub_blueprint_steps(clean_bp)

    state.meta.provenance_report = {
        "core_solution": core_solution_report.to_dict() if core_solution_report else None,
        "critical_insights_removed": insights_changed,
        "action_blueprint_removed": blueprint_changed,
        "open_questions_removed": questions_changed,
    }

    state.final_solution = FinalSolution(
        core_solution=core_solution,
        critical_insights=critical_insights,
        action_blueprint=clean_bp,
        open_questions=open_questions,
        claim_labels=clean_labels,
        meta_audit=MetaCognitiveAudit(
            most_dangerous_assumption=meta_audit_data.get("most_dangerous_assumption", ""),
            dominant_bias=meta_audit_data.get("dominant_bias", ""),
            remaining_uncertainty=meta_audit_data.get("remaining_uncertainty", ""),
            assumption_failure_impact=meta_audit_data.get("assumption_failure_impact", ""),
            non_obvious_insight=meta_audit_data.get("non_obvious_insight", "")
        ),
        sources=_coerce_sources(json_data.get("sources", [])),
        layout_hints=json_data.get("layout_hints", {}),
        evidence=evidence_bundles,
    )
