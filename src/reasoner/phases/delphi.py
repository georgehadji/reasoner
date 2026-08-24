from __future__ import annotations

import json

from reasoner.core.constants import JSON_ONLY_FOOTER
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import _wrap_user_input, get_language_instruction

DELPHI_EXPERT_SYSTEM = (
    "You are an independent expert forecaster. Make your estimate without knowing what other experts think. "
    "Be specific and provide a numeric estimate where possible. " + JSON_ONLY_FOOTER
)

def delphi_round1_prompt(state: PipelineState, expert_num: int) -> str:
    decomp = state.decomposition or {}
    if isinstance(decomp, dict):
        sub_problems = [step.get("action", "") for step in decomp.get("causal_chain", [])]
    else:
        sub_problems = [sp.description for sp in (decomp.sub_problems if decomp else [])]
    return (
        f'{get_language_instruction(state)}\n\n'
        f'You are Expert {expert_num} of 4 independent forecasters.\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Sub-problems:\n{json.dumps(sub_problems, indent=2)}\n\n'
        f'Provide your independent estimate/forecast. If numeric, provide a specific number. '
        f'Explain your reasoning. Do NOT anchor to any consensus — you are working independently.\n\n'
        f'Output JSON: {{"estimate_value": <number or null if qualitative>, '
        f'"estimate_label": "<your estimate in words>", '
        f'"confidence": "high|medium|low", '
        f'"key_assumptions": ["<assumption>"], '
        f'"reasoning": "<why you believe this>"}}'
    )

DELPHI_AGGREGATION_SYSTEM = (
    "You are a statistical aggregator. Combine expert estimates into a summary with median, IQR, and outlier identification. "
    "Be objective. Output ONLY valid JSON."
)

def delphi_aggregation_prompt(state: PipelineState) -> str:
    estimates = state.delphi_state.get("round_1_estimates", [])
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Expert estimates (anonymous — do not reveal which expert said what in outputs):\n'
        f'{json.dumps(estimates, indent=2)}\n\n'
        f'Aggregate these estimates. Identify: the central tendency (median or modal theme), '
        f'the spread (range or IQR), and which estimate is most different from the others.\n\n'
        f'Output JSON: {{"median": null, "iqr": null, '
        f'"central_theme": "<qualitative central estimate>", '
        f'"spread": "<qualitative description of disagreement>", '
        f'"outlier_expert": "<expert_1|expert_2|expert_3|expert_4>", '
        f'"outlier_reasoning": "<why this estimate is an outlier>"}}'
    )

DELPHI_REVISION_SYSTEM = (
    "You are an expert revising your estimate after seeing anonymous aggregated results. "
    "You may revise toward consensus or defend your original position with reasoning. " + JSON_ONLY_FOOTER
)

def delphi_round2_prompt(state: PipelineState, expert_id: str) -> str:
    stats = state.delphi_state.get("aggregated_stats", {})
    original = next(
        (e for e in state.delphi_state.get("round_1_estimates", []) if e.get("expert_id") == expert_id),
        {}
    )
    return (
        f'{get_language_instruction(state)}\n\n'
        f'You are {expert_id}. You previously estimated: {original.get("estimate_label", "unknown")}\n\n'
        f'Anonymous group statistics:\n'
        f'- Median: {stats.get("median", stats.get("central_theme", "unknown"))}\n'
        f'- Spread (IQR): {stats.get("iqr", stats.get("spread", "unknown"))}\n\n'
        f'You can see the group median. '
        f'Do you revise your estimate, or do you defend your original position?\n\n'
        f'Output JSON: {{"revised_estimate": <number or null>, '
        f'"revised_label": "<your revised estimate in words>", '
        f'"position": "revised|maintained", '
        f'"rationale": "<why you revised or maintained>", '
        f'"remaining_uncertainty": "<what would change your estimate>"}}'
    )

DELPHI_CONVERGENCE_SYSTEM = (
    "You are a Delphi facilitator checking if expert estimates have converged to consensus. " + JSON_ONLY_FOOTER
)

def delphi_convergence_prompt(state: PipelineState) -> str:
    r2 = state.delphi_state.get("round_2_estimates", [])
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Round 2 estimates:\n{json.dumps(r2, indent=2)}\n\n'
        f'Have the experts converged to a consensus? '
        f'Convergence means the estimates are close enough to support a single recommendation.\n\n'
        f'Output JSON: {{"converged": "<true|false>", '
        f'"consensus_label": "<the converged estimate if converged>", '
        f'"remaining_disagreement": "<what experts still disagree on>", '
        f'"convergence_quality": "strong|moderate|weak"}}'
    )

DELPHI_DISSENT_SYSTEM = (
    "You are the outlier expert. Document your dissenting rationale explicitly and professionally. "
    "Explain what the consensus is missing. Output ONLY valid JSON."
)

def delphi_dissent_prompt(state: PipelineState) -> str:
    stats = state.delphi_state.get("aggregated_stats", {})
    consensus = state.delphi_state.get("consensus", {})
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Group consensus: {consensus.get("median", consensus.get("consensus_label", "unknown"))}\n'
        f'Your estimate differs from the group median by: {stats.get("outlier_distance", stats.get("iqr", "unknown"))} units.\n\n'
        f'As the outlier expert, document your dissenting rationale. '
        f'What does the consensus miss? What evidence supports your position?\n\n'
        f'Output JSON: {{"dissenting_estimate": "<your position>", '
        f'"what_consensus_misses": ["<missing factor>"], '
        f'"evidence_for_dissent": ["<evidence>"], '
        f'"conditions_for_revision": "<what would change your mind>", '
        f'"minority_report": "<1-2 sentence professional dissent statement>"}}'
    )
