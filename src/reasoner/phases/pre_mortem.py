from __future__ import annotations

import json

from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import _wrap_user_input, get_language_instruction

PRE_MORTEM_FAILURE_SYSTEM = "You are an analytical assistant. Assume failure has already occurred and reconstruct why. Be specific and unflinching. Output ONLY valid JSON."

def pre_mortem_failure_prompt(state: PipelineState) -> str:
    web_context = ""
    if state.web_discovery_results:
        web_snippets = [
            f"  - {r.get('title', '')}: {r.get('snippet', '')[:300]}"
            for r in state.web_discovery_results[:5]
            if r.get('title') or r.get('snippet')
        ]
        if web_snippets:
            web_context = "\n\nRelevant real-world case studies of similar failures:\n" + "\n".join(web_snippets) + "\n"

    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'{web_context}'
        f'It is exactly 1 year later. The solution to this problem catastrophically failed. '
        f'Write the post-mortem as if it already happened. Be vivid, specific, and brutally honest. '
        f'Draw on the real-world case studies provided above for concrete details.\n\n'
        f'Output JSON: {{"scenario": "<failure scenario name>", '
        f'"what_happened": "<narrative of the failure>", '
        f'"immediate_triggers": ["<trigger>"], '
        f'"affected_stakeholders": ["<stakeholder>"], '
        f'"severity": "catastrophic|severe|moderate"}}'
    )

PRE_MORTEM_BACKTRACK_SYSTEM = "You are an analytical assistant. Given a failure, identify the single most critical decision that led to it. Output ONLY valid JSON."

def pre_mortem_backtrack_prompt(state: PipelineState) -> str:
    failure = state.pre_mortem_state.get("failure_narrative", {})
    if not isinstance(failure, dict):
        failure = {"what_happened": str(failure)}
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Original Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Post-Mortem:\n{json.dumps(failure, indent=2)}\n\n'
        f'Trace back to the single initial decision that was the pivot point. '
        f'What seemingly reasonable choice, made early, set this failure in motion?\n\n'
        f'Output JSON: {{"pivot_decision": "<the decision>", '
        f'"decision_point": "<when it was made>", '
        f'"why_it_seemed_reasonable": "<the reason>", '
        f'"cascade": ["<cascade step>"]}}'
    )

PRE_MORTEM_SIGNALS_SYSTEM = "You are an analytical assistant. Identify observable signals that would have predicted failure before it happened. Output ONLY valid JSON."

def pre_mortem_signals_prompt(state: PipelineState) -> str:
    root_cause = state.pre_mortem_state.get("root_cause", {})
    if not isinstance(root_cause, dict):
        root_cause = {"pivot_decision": str(root_cause)}
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Root Cause:\n{json.dumps(root_cause, indent=2)}\n\n'
        f'What observable signals appeared in the first 30 days after implementation '
        f'that, in hindsight, were early warnings of the coming failure?\n\n'
        f'Output JSON: {{"early_signals": ['
        f'{{"signal": "<observable event>", "day": 1, "how_to_detect": "<measurement>", "action_threshold": "<when to act>"}}], '
        f'"monitoring_cadence": "<frequency>"}}'
    )

PRE_MORTEM_REDESIGN_SYSTEM = "You are an analytical assistant. Redesign the original solution hardened against the identified failure modes. Output ONLY valid JSON."

def pre_mortem_redesign_prompt(state: PipelineState) -> str:
    pm = state.pre_mortem_state
    failure_narrative = pm.get("failure_narrative", {})
    if not isinstance(failure_narrative, dict):
        failure_narrative = {}
    root_cause = pm.get("root_cause", {})
    if not isinstance(root_cause, dict):
        root_cause = {}
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Failure: {json.dumps(failure_narrative.get("what_happened", ""), indent=0)}\n'
        f'Root Cause: {json.dumps(root_cause.get("pivot_decision", ""), indent=0)}\n'
        f'Early Signals: {json.dumps([s.get("signal") if isinstance(s, dict) else s for s in pm.get("early_signals", [])], indent=0)}\n\n'
        f'Redesign the solution to be robust against these failure modes. '
        f'Add specific safeguards, checkpoints, and rollback mechanisms.\n\n'
        f'Output JSON: {{"hardened_solution": "<redesigned approach>", '
        f'"safeguards": ["<specific safeguard>"], '
        f'"checkpoints": [{{"milestone": "<m>", "go_nogo_criterion": "<criterion>"}}], '
        f'"rollback_plan": "<what to do if failing>"}}'
    )
