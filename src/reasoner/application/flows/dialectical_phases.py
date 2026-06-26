"""Dialectical, Scientific, Socratic, Pre-Mortem, Bayesian, and Analogical phase logic."""

from __future__ import annotations

import logging
from typing import Any

from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json, ParseError
import reasoner.phases as phases
from reasoner.application.flows.base import WorkflowServices

logger = logging.getLogger(__name__)

# --- Scientific ---

async def run_scientific_hypothesize_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("SCIENTIFIC", "Generating hypotheses...", state)
    raw, _ = await services.call_llm(
        role="primary",
        system_prompt=phases.SCIENTIFIC_HYPOTHESIS_SYSTEM,
        user_prompt=phases.scientific_hypothesis_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    state.scientific_state["hypotheses"] = data.get("hypotheses", [])

async def run_scientific_test_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("SCIENTIFIC", "Running falsification tests...", state)
    raw, _ = await services.call_llm(
        role="scoring",
        system_prompt=phases.SCIENTIFIC_TEST_SYSTEM,
        user_prompt=phases.scientific_test_prompt(state), 
        state=state
    )
    
    try:
        data = extract_json(raw)
    except ParseError:
        services.log("SCIENTIFIC", "Scientific test phase failed JSON extraction, retrying...", state)
        raw, _ = await services.call_llm(
            role="scoring",
            system_prompt="You are an analytical assistant. You MUST produce a valid JSON object ONLY. Do not include introductory text or markdown. Output JSON ONLY.",
            user_prompt=f"Previous attempt failed JSON parsing. Please re-generate the JSON for: {phases.scientific_test_prompt(state)}",
            state=state
        )
        data = extract_json(raw)

    state.scientific_state["test_results"] = data.get("test_results", [])
    
    # Bayesian posterior update
    hypotheses = state.scientific_state.get("hypotheses", [])
    test_results = state.scientific_state.get("test_results", [])
    for hyp in hypotheses:
        if not isinstance(hyp, dict):
            continue
        hyp_id = hyp.get("id", "")
        tests = [t for t in test_results if isinstance(t, dict) and t.get("hypothesis_id") == hyp_id]
        supported = sum(1 for t in tests if isinstance(t, dict) and t.get("result") == "SUPPORTED")
        hyp["posterior_probability"] = round(supported / max(len(tests), 1), 2)
    state.scientific_state["hypotheses"] = hypotheses

# --- Socratic ---

async def run_socratic_question_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("SOCRATIC", "Generating Socratic questions...", state)
    raw, _ = await services.call_llm(
        role="destructive",
        system_prompt=phases.SOCRATIC_QUESTION_SYSTEM,
        user_prompt=phases.socratic_question_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    state.socratic_state["questions"] = data.get("questions", [])

async def run_socratic_answer_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("SOCRATIC", "Attempting Dialectic answers...", state)
    raw, _ = await services.call_llm(
        role="constructive",
        system_prompt=phases.SOCRATIC_ANSWER_SYSTEM,
        user_prompt=phases.socratic_answer_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    state.socratic_state["answers"] = data.get("answers", [])

# --- Pre-Mortem ---

async def run_pre_mortem_failure_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("PRE-MORTEM", "Constructing failure narrative...", state)
    raw, _ = await services.call_llm(
        role="destructive",
        system_prompt=phases.PRE_MORTEM_FAILURE_SYSTEM,
        user_prompt=phases.pre_mortem_failure_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    if not isinstance(data, dict):
        data = {"what_happened": str(data)[:500], "immediate_triggers": [], "severity": "unknown"}
    state.pre_mortem_state["failure_narrative"] = data

async def run_pre_mortem_backtrack_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("PRE-MORTEM", "Identifying root cause pivot point...", state)
    raw, _ = await services.call_llm(
        role="scoring",
        system_prompt=phases.PRE_MORTEM_BACKTRACK_SYSTEM,
        user_prompt=phases.pre_mortem_backtrack_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    if not isinstance(data, dict):
        data = {"pivot_decision": str(data)[:300], "cascade": []}
    state.pre_mortem_state["root_cause"] = data

async def run_pre_mortem_signals_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("PRE-MORTEM", "Identifying early warning signals...", state)
    raw, _ = await services.call_llm(
        role="scoring",
        system_prompt=phases.PRE_MORTEM_SIGNALS_SYSTEM,
        user_prompt=phases.pre_mortem_signals_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    state.pre_mortem_state["early_signals"] = data.get("early_signals", [])
    state.pre_mortem_state["monitoring_cadence"] = data.get("monitoring_cadence", "")

async def run_pre_mortem_redesign_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("PRE-MORTEM", "Generating hardened redesign...", state)
    raw, _ = await services.call_llm(
        role="synthesis",
        system_prompt=phases.PRE_MORTEM_REDESIGN_SYSTEM,
        user_prompt=phases.pre_mortem_redesign_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    if not isinstance(data, dict):
        data = {"hardened_solution": str(data)[:500]}
    state.pre_mortem_state["hardened_solution"] = data.get("hardened_solution", "")
    state.pre_mortem_state["safeguards"] = data.get("safeguards", [])
    state.pre_mortem_state["checkpoints"] = data.get("checkpoints", [])
    state.pre_mortem_state["rollback_plan"] = data.get("rollback_plan", "")

# --- Bayesian ---

async def run_bayesian_priors_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("BAYESIAN", "Eliciting prior distributions...", state)
    raw, _ = await services.call_llm(
        role="constructive",
        system_prompt=phases.BAYESIAN_PRIOR_SYSTEM,
        user_prompt=phases.bayesian_prior_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    state.bayesian_state["hypotheses_with_priors"] = data.get("hypotheses", [])

async def run_bayesian_likelihood_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("BAYESIAN", "Assessing likelihoods...", state)
    raw, _ = await services.call_llm(
        role="destructive",
        system_prompt=phases.BAYESIAN_LIKELIHOOD_SYSTEM,
        user_prompt=phases.bayesian_likelihood_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    state.bayesian_state["evidence_likelihoods"] = data.get("likelihoods", [])
    state.bayesian_state["observations"] = data.get("observations", [])

async def run_bayesian_posterior_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("BAYESIAN", "Computing posteriors...", state)
    raw, _ = await services.call_llm(
        role="scoring",
        system_prompt=phases.BAYESIAN_POSTERIOR_SYSTEM,
        user_prompt=phases.bayesian_posterior_prompt(state),
        state=state
    )
    data = extract_json(raw)
    posteriors = data.get("posteriors", [])
    # Normalize
    total = sum(p.get("posterior_probability", 0.0) for p in posteriors if isinstance(p, dict))
    if total > 0 and abs(total - 1.0) > 0.01:
        for p in posteriors:
            if isinstance(p, dict) and "posterior_probability" in p:
                p["posterior_probability"] = round(p["posterior_probability"] / total, 4)
    state.bayesian_state["posteriors"] = posteriors
    state.bayesian_state["most_probable"] = data.get("most_probable", "")

async def run_bayesian_sensitivity_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("BAYESIAN", "Running sensitivity analysis...", state)
    raw, _ = await services.call_llm(
        role="synthesis",
        system_prompt=phases.BAYESIAN_SENSITIVITY_SYSTEM,
        user_prompt=phases.bayesian_sensitivity_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    state.bayesian_state["sensitivity_results"] = data.get("sensitivity_analysis", [])
    state.bayesian_state["most_sensitive_assumption"] = data.get("most_sensitive_assumption", "")

# --- Dialectical ---

async def run_dialectical_thesis_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("DIALECTICAL", "Formulating thesis...", state)
    raw, _ = await services.call_llm(
        role="constructive",
        system_prompt=phases.DIALECTICAL_THESIS_SYSTEM,
        user_prompt=phases.dialectical_thesis_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    state.dialectical_state["thesis"] = data.get("thesis", "")
    state.dialectical_state["key_commitments"] = data.get("key_commitments", [])
    state.dialectical_state["thesis_assumptions"] = data.get("assumptions", [])

async def run_dialectical_antithesis_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("DIALECTICAL", "Formulating antithesis...", state)
    raw, _ = await services.call_llm(
        role="destructive",
        system_prompt=phases.DIALECTICAL_ANTITHESIS_SYSTEM,
        user_prompt=phases.dialectical_antithesis_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    state.dialectical_state["antithesis"] = data.get("antithesis", "")
    state.dialectical_state["contradictions_exposed"] = data.get("contradictions_exposed", [])
    state.dialectical_state["negated_commitments"] = data.get("negated_commitments", [])

async def run_dialectical_contradictions_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("DIALECTICAL", "Analyzing contradictions...", state)
    raw, _ = await services.call_llm(
        role="scoring",
        system_prompt=phases.DIALECTICAL_CONTRADICTIONS_SYSTEM,
        user_prompt=phases.dialectical_contradictions_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    state.dialectical_state["irreconcilable"] = data.get("irreconcilable", [])
    state.dialectical_state["compatible"] = data.get("compatible", [])
    state.dialectical_state["synthesis_candidates"] = data.get("synthesis_candidates", [])

async def run_dialectical_aufhebung_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("DIALECTICAL", "Formulating Aufhebung...", state)
    raw, _ = await services.call_llm(
        role="synthesis",
        system_prompt=phases.DIALECTICAL_AUFHEBUNG_SYSTEM,
        user_prompt=phases.dialectical_aufhebung_prompt(state), 
        state=state
    )
    data = extract_json(raw)
    state.dialectical_state["aufhebung"] = data.get("aufhebung", "")
    state.dialectical_state["preserved_from_thesis"] = data.get("preserved_from_thesis", [])
    state.dialectical_state["preserved_from_antithesis"] = data.get("preserved_from_antithesis", [])
    state.dialectical_state["transcended"] = data.get("transcended", "")
    state.dialectical_state["new_insights"] = data.get("new_insights", [])

# --- Analogical ---

async def run_analogical_abstraction_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("ANALOGICAL", "Extracting abstract problem structure...", state)
    raw, _ = await services.call_llm(
        role="systemic",
        system_prompt=phases.ANALOGICAL_ABSTRACTION_SYSTEM,
        user_prompt=phases.analogical_abstraction_prompt(state), 
        state=state
    )
    try:
        data = extract_json(raw)
    except ParseError:
        import re as _re
        # Graceful degradation: pull the abstract_structure string directly from raw text
        m = _re.search(r'"abstract_structure"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, _re.DOTALL)
        data = {"abstract_structure": m.group(1) if m else raw[:500]}
    state.analogical_state["abstract_structure"] = data.get("abstract_structure", "") or ""
    state.analogical_state["constraints"] = data.get("constraints", [])
    state.analogical_state["objectives"] = data.get("objectives", [])
    state.analogical_state["actors"] = data.get("actors", [])
    state.analogical_state["core_dynamics"] = data.get("core_dynamics", [])
    state.analogical_state["structural_type"] = data.get("structural_type", "") or ""

async def run_analogical_domain_search_phase(state: PipelineState, services: WorkflowServices) -> None:
    services.log("ANALOGICAL", "Searching for isomorphic source domains...", state)
    raw, _ = await services.call_llm(
        role="systemic",
        system_prompt=phases.ANALOGICAL_DOMAIN_SEARCH_SYSTEM,
        user_prompt=phases.analogical_domain_search_prompt(state), 
        state=state
    )
    try:
        data = extract_json(raw)
    except ParseError:
        data = {}
    _raw_domains = data.get("source_domains", [])
    state.analogical_state["source_domains"] = _raw_domains if isinstance(_raw_domains, list) else []

async def run_analogical_mapping_phase(state: PipelineState, services: WorkflowServices) -> None:
    if not state.analogical_state.get("source_domains"):
        return
    services.log("ANALOGICAL", "Mapping source domain elements to target problem...", state)
    raw, _ = await services.call_llm(
        role="systemic",
        system_prompt=phases.ANALOGICAL_MAPPING_SYSTEM,
        user_prompt=phases.analogical_mapping_prompt(state), 
        state=state
    )
    try:
        data = extract_json(raw)
    except ParseError:
        data = {}
    _raw_mappings = data.get("analogy_mappings", [])
    state.analogical_state["analogy_mappings"] = _raw_mappings if isinstance(_raw_mappings, list) else []
    state.analogical_state["unmapped_elements"] = data.get("unmapped_elements", [])
    state.analogical_state["mapping_quality"] = data.get("mapping_quality", "") or ""

async def run_analogical_transfer_phase(state: PipelineState, services: WorkflowServices) -> None:
    if not state.analogical_state.get("source_domains"):
        return
    services.log("ANALOGICAL", "Transferring and adapting solution from source domain...", state)
    raw, _ = await services.call_llm(
        role="synthesis",
        system_prompt=phases.ANALOGICAL_TRANSFER_SYSTEM,
        user_prompt=phases.analogical_transfer_prompt(state), 
        state=state
    )
    try:
        data = extract_json(raw)
    except ParseError:
        data = {}
    if isinstance(data, str):
        data = {"transferred_solution": data}

    state.analogical_state["transferred_solution"] = data.get("transferred_solution", "") or ""
    state.analogical_state["transfer_steps"] = data.get("transfer_steps", [])
    state.analogical_state["adaptations_required"] = data.get("adaptations_required", [])
    state.analogical_state["broken_analogies"] = data.get("broken_analogies", [])
    state.analogical_state["transfer_confidence"] = data.get("confidence", "") or ""
    state.analogical_state["caveats"] = data.get("caveats", [])
