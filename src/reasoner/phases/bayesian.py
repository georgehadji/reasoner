from __future__ import annotations
import json
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import get_language_instruction, _wrap_user_input

BAYESIAN_PRIOR_SYSTEM = "You are an analytical assistant. Elicit prior probability distributions over competing hypotheses. Be explicit about uncertainty. Output ONLY valid JSON."

def bayesian_prior_prompt(state: PipelineState) -> str:
    decomp = state.decomposition or {}
    if isinstance(decomp, dict):
        sub_problems = [step.get("action", "") for step in decomp.get("causal_chain", [])]
    else:
        sub_problems = [sp.description for sp in (decomp.sub_problems if decomp else [])]
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Sub-problems:\n{json.dumps(sub_problems, indent=2)}\n\n'
        f'Identify 2-4 competing hypotheses that could explain or solve this problem. '
        f'Assign prior probability P(H) to each (must sum to approximately 1.0). '
        f'Explain your reasoning for each prior.\n\n'
        f'Output JSON: {{"hypotheses": [{{"id": "H1", "statement": "<hypothesis>", '
        f'"prior_probability": 0.4, "reasoning": "<why this prior>"}}]}}'
    )

BAYESIAN_LIKELIHOOD_SYSTEM = "You are an analytical assistant. For each hypothesis, assess the likelihood of key observations. Output ONLY valid JSON."

def bayesian_likelihood_prompt(state: PipelineState) -> str:
    hypotheses = state.bayesian_state.get("hypotheses_with_priors", [])
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Hypotheses:\n{json.dumps(hypotheses, indent=2)}\n\n'
        f'Identify 3-5 key observations or pieces of evidence relevant to this problem. '
        f'For each observation, assess P(E|H) and P(E|not-H) for each hypothesis.\n\n'
        f'Output JSON: {{"observations": ["<obs 1>"], "likelihoods": [{{"observation": "<obs>", '
        f'"hypothesis_id": "H1", "p_e_given_h": 0.8, "p_e_given_not_h": 0.2, '
        f'"reasoning": "<why>"}}]}}'
    )

BAYESIAN_POSTERIOR_SYSTEM = "You are an analytical assistant. Apply Bayes' theorem to compute posterior probabilities. Show your reasoning. Output ONLY valid JSON."

def bayesian_posterior_prompt(state: PipelineState) -> str:
    hypotheses = state.bayesian_state.get("hypotheses_with_priors", [])
    likelihoods = state.bayesian_state.get("evidence_likelihoods", [])
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Priors:\n{json.dumps(hypotheses, indent=2)}\n\n'
        f'Likelihoods:\n{json.dumps(likelihoods, indent=2)}\n\n'
        f'Apply Bayes rule P(H|E) ∝ P(E|H) × P(H) to compute posterior for each hypothesis '
        f'after observing all evidence. Normalize so posteriors sum to 1.0.\n\n'
        f'Output JSON: {{"posteriors": [{{"hypothesis_id": "H1", "posterior_probability": 0.75, '
        f'"explanation": "<how evidence updated belief>"}}], '
        f'"most_probable": "H1"}}'
    )

BAYESIAN_SENSITIVITY_SYSTEM = "You are an analytical assistant. Test which prior assumptions most change the posterior if they are wrong. Output ONLY valid JSON."

def bayesian_sensitivity_prompt(state: PipelineState) -> str:
    hypotheses = state.bayesian_state.get("hypotheses_with_priors", [])
    posteriors = state.bayesian_state.get("posteriors", [])
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Priors:\n{json.dumps(hypotheses, indent=2)}\n\n'
        f'Posteriors:\n{json.dumps(posteriors, indent=2)}\n\n'
        f'For each major prior assumption, assess: if this prior were very different, '
        f'how much would the posterior change? Which assumption is most critical?\n\n'
        f'Output JSON: {{"sensitivity_analysis": [{{"assumption": "<prior assumption>", '
        f'"if_wrong": "<alternative>", "posterior_shift": "small|medium|large", '
        f'"importance": "critical|high|medium"}}], '
        f'"most_sensitive_assumption": "<which assumption>"}}'
    )
