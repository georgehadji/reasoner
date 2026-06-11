"""Jury phase logic."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.core_types import (
    GenerationCandidate,
    CriticScore,
    CriticDimensionScore,
    VerificationResult,
    MetaEvaluation,
    SolutionCandidate,
)
from reasoner.models import ClaimLabel
from reasoner.parsing import extract_json
from reasoner.core.constants import TRUNCATION
from reasoner.core.constants_limits import get_token_budget
import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices
from reasoner.application.services.recovery_service import RecoveryService

logger = logging.getLogger(__name__)

async def run_recovery_path(state: PipelineState, services: WorkflowServices, candidate_to_verify: SolutionCandidate | GenerationCandidate) -> None:
    """Executes a cross-verification path for a potentially problematic candidate."""
    candidate_id = candidate_to_verify.perspective if isinstance(candidate_to_verify, SolutionCandidate) else candidate_to_verify.generator_id
    services.log("RECOVERY", f"Initiating recovery path for candidate: {candidate_id}", state)
    
    try:
        raw_verification, _ = await services.call_llm(
            role="recovery_path",
            system_prompt=phases.CROSS_VERIFICATION_SYSTEM,
            user_prompt=phases.cross_verification_prompt(state, candidate_solution=asdict(candidate_to_verify)),
            state=state,
            max_tokens=get_token_budget("recovery_path")
        )
        verification_data = extract_json(raw_verification)
        if verification_data.get("verification_findings"):
            services.log("RECOVERY", f"Cross-verification found issues for candidate. Findings: {verification_data['verification_findings'][:TRUNCATION.MEMORY]}", state)
        else:
            services.log("RECOVERY", "Cross-verification found no issues.", state)
    except Exception as e:
        services.log("RECOVERY", f"Recovery Path failed for {candidate_id}: {e}", state)
        state.errors.append(f"Recovery Path failed for {candidate_id}: {e}")

async def run_jury_generate_phase(state: PipelineState, services: WorkflowServices, gen_roles: list[str] | None = None) -> None:
    services.log("JURY", "Generating independent solutions...", state)
    
    if not gen_roles:
        gen_roles = ["generator_1", "generator_2", "generator_3"]
            
    async def _get_generator(gen_id: str):
        raw, _ = await services.call_llm(
            role=gen_id,
            system_prompt=phases.JURY_GENERATOR_SYSTEM,
            user_prompt=phases.jury_generator_prompt(state, gen_id), 
            state=state
        )
        data = extract_json(raw)
        return GenerationCandidate(**data, model_used="")

    tasks = [_get_generator(role) for role in gen_roles]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            role = gen_roles[i]
            msg = f"Jury generator '{role}' failed: {r}"
            services.log("JURY", msg, state)
            state.errors.append(msg)
        else:
            state.generation_candidates.append(r)

async def run_jury_critique_phase(state: PipelineState, services: WorkflowServices, critic_roles: list[str] | None = None, batch_critique: bool = False) -> None:
    services.log("JURY_CRITIQUE", "Jury critiquing candidates...", state)
    
    async def _get_jury_critique(critic_id: str):
        raw, _ = await services.call_llm(
            role=critic_id,
            system_prompt=phases.JURY_CRITIC_SYSTEM,
            user_prompt=phases.jury_critic_prompt(state),
            state=state
        )
        data = extract_json(raw)
        # Instantiate nested CriticDimensionScore objects
        candidate_scores = {}
        for gen_id, dims in data.get('candidate_scores', {}).items():
            candidate_scores[gen_id] = CriticDimensionScore(
                factuality=float(dims.get('factuality') or 0),
                reasoning=float(dims.get('reasoning') or 0),
                completeness=float(dims.get('completeness') or 0),
                helpfulness=float(dims.get('helpfulness') or 0),
                confidence_vs_accuracy_penalty=float(dims.get('confidence_vs_accuracy_penalty') or 0.0)
            )
        data['candidate_scores'] = candidate_scores
        data['critic_id'] = critic_id
        return CriticScore(**data)

    if batch_critique:
        services.log("JURY_CRITIQUE", "Running batch critique (single panel critic)...", state)
        try:
            panel_score = await _get_jury_critique("panel_critic")
            state.critic_scores.append(panel_score)
        except Exception as exc:
            msg = f"Batch jury critic failed: {exc}"
            services.log("JURY_CRITIQUE", msg, state)
            state.errors.append(msg)
    else:
        if not critic_roles:
            critic_roles = ["critic_1", "critic_2", "critic_3"]
            
        tasks = [_get_jury_critique(role) for role in critic_roles]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                role = critic_roles[i]
                msg = f"Jury critic '{role}' failed: {r}"
                services.log("JURY_CRITIQUE", msg, state)
                state.errors.append(msg)
            else:
                state.critic_scores.append(r)

    # Recovery path
    for critic_score in state.critic_scores:
        for gen_id, scores in critic_score.candidate_scores.items():
            if scores.confidence_vs_accuracy_penalty > 5.0:
                candidate_to_check = next((gc for gc in state.generation_candidates if gc.generator_id == gen_id), None)
                if candidate_to_check:
                    services.log("JURY_CRITIQUE", f"High penalty for Jury candidate {gen_id}. Triggering recovery path.", state)
                    await RecoveryService.run_recovery_path(state, services, candidate_to_check)

async def run_jury_verify_and_meta_eval_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("JURY", "Verifying claims and meta-evaluating critics...", state)

    def _parse_verification_results(raw_list: list[dict]) -> list[VerificationResult]:
        out: list[VerificationResult] = []
        for v in raw_list:
            try:
                verdict_raw = v.get("verdict", "UNKNOWN")
                verdict = ClaimLabel(verdict_raw) if verdict_raw in [e.value for e in ClaimLabel] else ClaimLabel.UNKNOWN
                out.append(VerificationResult(
                    claim=str(v.get("claim", "")),
                    source_generator=str(v.get("source_generator", "")),
                    verdict=verdict,
                    evidence=str(v.get("evidence", "")),
                    confidence=float(v.get("confidence") or 0.0),
                ))
            except Exception as exc:
                logger.warning("Skipping malformed VerificationResult entry: %s", exc)
        return out

    def _parse_meta_evaluation(data: dict) -> MetaEvaluation:
        try:
            return MetaEvaluation(
                critic_reliability=data.get("critic_reliability", {}),
                bias_analysis=data.get("bias_analysis", {}),
                agreement_rate=float(data.get("agreement_rate") or 0.0),
                most_reliable_critic=str(data.get("most_reliable_critic", "")),
                least_reliable_critic=str(data.get("least_reliable_critic", "")),
                meta_insight=str(data.get("meta_insight", "")),
            )
        except Exception as exc:
            logger.warning("Malformed MetaEvaluation response: %s", exc)
            return MetaEvaluation(
                critic_reliability={},
                bias_analysis={},
                agreement_rate=0.0,
                most_reliable_critic="",
                least_reliable_critic="",
                meta_insight="",
            )

    # 1. Verification
    raw_v, _ = await services.call_llm(
        role="verifier",
        system_prompt=phases.JURY_VERIFIER_SYSTEM,
        user_prompt=phases.jury_verifier_prompt(state), 
        state=state
    )
    v_data = extract_json(raw_v)
    state.verification_results = _parse_verification_results(v_data.get("verifications", []))

    # 2. Meta Evaluation
    raw_m, _ = await services.call_llm(
        role="meta_evaluator",
        system_prompt=phases.JURY_META_EVAL_SYSTEM,
        user_prompt=phases.jury_meta_eval_prompt(state), 
        state=state
    )
    m_data = extract_json(raw_m)
    state.meta_evaluation = _parse_meta_evaluation(m_data)

async def run_jury_weighted_ranking_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("JURY", "Computing reliability-weighted ranking...", state)
    reliability: dict[str, float] = {}
    if state.meta_evaluation:
        reliability = state.meta_evaluation.critic_reliability or {}
    
    def _safe_float(v) -> float:
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, dict):
            return 0.0
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return 0.0

    generator_scores: dict[str, float] = {}
    for cs in state.critic_scores:
        weight = _safe_float(reliability.get(cs.critic_id, 1.0))
        for gen_id, dims in cs.candidate_scores.items():
            score = (_safe_float(dims.factuality) + _safe_float(dims.reasoning)
                   + _safe_float(dims.completeness) + _safe_float(dims.helpfulness))
            generator_scores[gen_id] = generator_scores.get(gen_id, 0.0) + (score * weight)
    
    state.jury_weighted_ranking = sorted(
        generator_scores.keys(),
        key=lambda gid: generator_scores[gid],
        reverse=True,
    )
    services.log("JURY", f"Weighted ranking: {state.jury_weighted_ranking}", state)
