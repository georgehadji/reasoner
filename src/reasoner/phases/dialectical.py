from __future__ import annotations
import json
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import get_language_instruction, _wrap_user_input

DIALECTICAL_THESIS_SYSTEM = "You are an analytical assistant. Articulate the strongest possible affirmative position. Be rigorous and committed. Output ONLY valid JSON."

def dialectical_thesis_prompt(state: PipelineState) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Articulate the strongest possible affirmative thesis position. '
        f'Be fully committed — this is the strongest case FOR one approach, not a balanced view.\n\n'
        f'Output JSON: {{"thesis": "<strongest affirmative position>", '
        f'"key_commitments": ["<commitment 1>"], '
        f'"assumptions": ["<assumption>"]}}'
    )

DIALECTICAL_ANTITHESIS_SYSTEM = "You are an analytical assistant. Expose the internal contradictions of a thesis. Negate its commitments rigorously. Output ONLY valid JSON."

def dialectical_antithesis_prompt(state: PipelineState) -> str:
    thesis = state.dialectical_state.get("thesis", "")
    commitments = state.dialectical_state.get("key_commitments", [])
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Thesis: {thesis}\n\n'
        f'Key Commitments: {json.dumps(commitments, indent=2)}\n\n'
        f'Expose the internal contradictions of this thesis. '
        f'Negate each commitment. Show why this position is untenable.\n\n'
        f'Output JSON: {{"antithesis": "<negation of thesis>", '
        f'"contradictions_exposed": ["<contradiction in thesis>"], '
        f'"negated_commitments": [{{"commitment": "<c>", "negation": "<n>"}}]}}'
    )

DIALECTICAL_CONTRADICTIONS_SYSTEM = "You are an analytical assistant. Classify which contradictions are truly irreconcilable and which can be transcended at a higher level. Output ONLY valid JSON."

def dialectical_contradictions_prompt(state: PipelineState) -> str:
    thesis = state.dialectical_state.get("thesis", "")
    antithesis = state.dialectical_state.get("antithesis", "")
    contradictions = state.dialectical_state.get("contradictions_exposed", [])
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Thesis: {thesis}\n\nAntithesis: {antithesis}\n\n'
        f'Contradictions: {json.dumps(contradictions, indent=2)}\n\n'
        f'Classify each contradiction: irreconcilable (cannot coexist) vs '
        f'compatible (can resolve at higher conceptual level). '
        f'Identify synthesis candidates — truths from each side worth preserving.\n\n'
        f'Output JSON: {{"irreconcilable": ["<contradiction>"], '
        f'"compatible": ["<resolves at higher level>"], '
        f'"synthesis_candidates": ["<truth from thesis>", "<truth from antithesis>"]}}'
    )

DIALECTICAL_AUFHEBUNG_SYSTEM = "You are an analytical assistant. Achieve qualitative transcendence, NOT compromise. Preserve the truths of both positions at a higher level. Output ONLY valid JSON."

def dialectical_aufhebung_prompt(state: PipelineState) -> str:
    d = state.dialectical_state
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Thesis: {d.get("thesis", "")}\n'
        f'Antithesis: {d.get("antithesis", "")}\n'
        f'Compatible contradictions: {json.dumps(d.get("compatible", []), indent=2)}\n'
        f'Synthesis candidates: {json.dumps(d.get("synthesis_candidates", []), indent=2)}\n\n'
        f'Perform Aufhebung: a qualitatively higher position that transcends both. '
        f'This is NOT a compromise — it must contain genuine novelty.\n\n'
        f'Output JSON: {{"aufhebung": "<higher position>", '
        f'"preserved_from_thesis": ["<truth kept>"], '
        f'"preserved_from_antithesis": ["<truth kept>"], '
        f'"transcended": "<what was left behind>", '
        f'"new_insights": ["<genuine novelty>"]}}'
    )
