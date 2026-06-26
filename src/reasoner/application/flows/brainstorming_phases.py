"""Brainstorming phase logic."""

from __future__ import annotations

import logging
from typing import Any

from reasoner.domain.core_types import (
    FinalSolution,
    MetaCognitiveAudit,
)
from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json
from reasoner.phases.brainstorming import (
    VS_CLUSTER_SYSTEM,
    VS_DEVELOP_SYSTEM,
    VS_GENERATION_SYSTEM,
    VS_SYNTHESIS_SYSTEM,
    vs_cluster_prompt,
    vs_develop_prompt,
    vs_generation_prompt,
    vs_synthesis_prompt,
)
from reasoner.application.flows.base import WorkflowServices

logger = logging.getLogger(__name__)
_LOG_TAG = "BRAINSTORM"

async def run_brainstorm_generate_phase(state: PipelineState, services: WorkflowServices) -> None:
    cfg: dict = state.brainstorming_state.setdefault("config", {})
    rounds: int = cfg.get("rounds", 3)
    k: int = cfg.get("k", 5)
    threshold: float = cfg.get("threshold", 0.10)
    n_tail: int = cfg.get("n_tail", 2)
    use_cot: bool = cfg.get("use_cot", False)

    all_ideas: list[dict] = []
    for rnd in range(1, rounds + 1):
        services.log(_LOG_TAG, f"VS round {rnd}/{rounds} (k={k}, threshold={threshold})…", state)
        prompt = vs_generation_prompt(
            state, rnd, k, threshold, n_tail,
            previous_ideas=all_ideas,
            use_cot=use_cot,
        )
        raw, _ = await services.call_llm(
            role="brainstorm_generate",
            system_prompt=VS_GENERATION_SYSTEM.format(threshold=threshold),
            user_prompt=prompt,
            state=state,
        )
        try:
            data = extract_json(raw)
            ideas: list[dict] = data.get("ideas", [])
            all_ideas.extend(ideas)
            services.log(_LOG_TAG, f"Round {rnd}: +{len(ideas)} ideas (total {len(all_ideas)})", state)
        except Exception as exc:
            services.log(_LOG_TAG, f"Round {rnd} parse error: {exc}", state)
            state.errors.append(f"VS round {rnd}: {exc}")

    state.brainstorming_state["raw_ideas"] = all_ideas
    state.brainstorming_state["raw_idea_count"] = len(all_ideas)

async def run_brainstorm_cluster_phase(state: PipelineState, services: WorkflowServices) -> None:
    raw_ideas: list[dict] = state.brainstorming_state.get("raw_ideas", [])
    if not raw_ideas:
        services.log(_LOG_TAG, "No raw ideas to cluster — skipping.", state)
        state.errors.append("Brainstorming: VS generation produced no raw ideas; clustering skipped.")
        return

    services.log(_LOG_TAG, f"Clustering {len(raw_ideas)} raw ideas…", state)
    raw, _ = await services.call_llm(
        role="brainstorm_cluster",
        system_prompt=VS_CLUSTER_SYSTEM,
        user_prompt=vs_cluster_prompt(state, raw_ideas),
        state=state,
    )
    try:
        data = extract_json(raw)
        clusters: list[dict] = data.get("clusters", [])
        state.brainstorming_state["clusters"] = clusters
        state.brainstorming_state["deduplicated_count"] = data.get("deduplicated_count", 0)
        top_ideas: list[dict] = [
            idea
            for cluster in clusters
            if isinstance(cluster, dict)
            for idea in (cluster.get("ideas") or [])
            if isinstance(idea, dict) and idea.get("keep", True)
        ]
        state.brainstorming_state["top_ideas"] = top_ideas
        services.log(
            _LOG_TAG,
            f"Clustered into {len(clusters)} themes; {len(top_ideas)} ideas kept.",
            state,
        )
    except Exception as exc:
        services.log(_LOG_TAG, f"Cluster parse error: {exc}", state)
        state.errors.append(f"VS cluster: {exc}")

async def run_brainstorm_develop_phase(state: PipelineState, services: WorkflowServices) -> None:
    top_ideas: list[dict] = state.brainstorming_state.get("top_ideas", [])
    max_develop: int = state.brainstorming_state.get("config", {}).get("max_develop", 3)
    ideas_to_develop = top_ideas[:max_develop]

    if not ideas_to_develop:
        services.log(_LOG_TAG, "No top ideas to develop — skipping.", state)
        state.errors.append("Brainstorming: no ideas survived clustering; development skipped.")
        return

    services.log(_LOG_TAG, f"Developing top {len(ideas_to_develop)} ideas…", state)
    raw, _ = await services.call_llm(
        role="brainstorm_develop",
        system_prompt=VS_DEVELOP_SYSTEM,
        user_prompt=vs_develop_prompt(state, ideas_to_develop),
        state=state,
    )
    try:
        data = extract_json(raw)
        developments: list[dict] = data.get("developments", [])
        state.brainstorming_state["developments"] = developments
        services.log(_LOG_TAG, f"Developed {len(developments)} ideas.", state)
    except Exception as exc:
        services.log(_LOG_TAG, f"Develop parse error: {exc}", state)
        state.errors.append(f"VS develop: {exc}")

async def run_brainstorm_synthesis_phase(state: PipelineState, services: WorkflowServices) -> None:
    developments: list[dict] = state.brainstorming_state.get("developments", [])
    clusters: list[dict] = state.brainstorming_state.get("clusters", [])

    if not developments:
        top_ideas: list[dict] = state.brainstorming_state.get("top_ideas", [])
        if top_ideas:
            services.log(
                _LOG_TAG,
                "No developments found — synthesizing from top_ideas directly.",
                state,
            )
            developments = top_ideas
        else:
            services.log(_LOG_TAG, "No ideas to synthesize — skipping.", state)
            state.errors.append("Brainstorming synthesis: no developments or top_ideas available.")
            return

    services.log(_LOG_TAG, f"Synthesizing {len(developments)} developed ideas…", state)
    raw, _ = await services.call_llm(
        role="synthesis",
        system_prompt=VS_SYNTHESIS_SYSTEM,
        user_prompt=vs_synthesis_prompt(state, developments, clusters),
        state=state,
    )

    try:
        data = extract_json(raw)
        raw_bp = data.get("action_blueprint", [])
        action_blueprint: list[dict] = []
        for step in raw_bp if isinstance(raw_bp, list) else []:
            if isinstance(step, dict):
                action_blueprint.append(step)
            elif step is not None and str(step).strip():
                action_blueprint.append({"action": str(step).strip()})

        meta_audit = MetaCognitiveAudit(
            most_dangerous_assumption=data.get("most_dangerous_assumption", ""),
            dominant_bias=data.get("dominant_bias", ""),
            remaining_uncertainty=data.get("remaining_uncertainty", ""),
            assumption_failure_impact="",
            non_obvious_insight="",
        )

        state.final_solution = FinalSolution(
            core_solution=data.get("core_solution", ""),
            critical_insights=data.get("critical_insights", []),
            action_blueprint=action_blueprint,
            open_questions=data.get("open_questions", []),
            claim_labels={},
            meta_audit=meta_audit,
            sources=[],
        )
        services.log(_LOG_TAG, "Brainstorming synthesis complete.", state)
    except Exception as exc:
        services.log(_LOG_TAG, f"Synthesis parse error: {exc}", state)
        state.errors.append(f"VS synthesis: {exc}")
        if raw and raw.strip():
            state.final_solution = FinalSolution(
                core_solution=raw.strip(),
                critical_insights=[],
                action_blueprint=[],
                open_questions=[],
                claim_labels={},
                meta_audit=MetaCognitiveAudit(
                    most_dangerous_assumption="",
                    dominant_bias="",
                    remaining_uncertainty="",
                    assumption_failure_impact="",
                    non_obvious_insight="",
                ),
                sources=[],
            )
