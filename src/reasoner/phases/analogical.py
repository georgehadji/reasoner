from __future__ import annotations

import json

from reasoner.core.constants import JSON_ONLY_FOOTER
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import _wrap_user_input, get_language_instruction

ANALOGICAL_ABSTRACTION_SYSTEM = (
    "You are a structural abstraction expert trained in Gentner's structure-mapping theory. "
    "Extract the deep, domain-independent structure of a problem. "
    "Focus on constraints, objectives, actors, and dynamics — not surface features. " + JSON_ONLY_FOOTER
)

def analogical_abstraction_prompt(state: PipelineState) -> str:
    decomp = state.decomposition or {}
    if isinstance(decomp, dict):
        sub_problems = [step.get("action", "") for step in decomp.get("causal_chain", [])]
    else:
        sub_problems = [sp.description for sp in (decomp.sub_problems if decomp else [])]
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Sub-problems:\n{json.dumps(sub_problems, indent=2)}\n\n'
        f'Extract the abstract structural signature of this problem, ignoring domain-specific surface features. '
        f'Identify the deep constraints, objectives, actors, and core dynamics.\n\n'
        f'Output JSON: {{"abstract_structure": "<structural description>", '
        f'"constraints": ["<constraint>"], '
        f'"objectives": ["<objective>"], '
        f'"actors": ["<actor/agent>"], '
        f'"core_dynamics": ["<dynamic/tension>"], '
        f'"structural_type": "<optimization|resource_allocation|coordination|competition|emergent|etc>"}}'
    )

ANALOGICAL_DOMAIN_SEARCH_SYSTEM = (
    "You are an expert in cross-domain pattern recognition — spanning biology, physics, engineering, "
    "economics, military history, computer science, and social systems. "
    "Given an abstract problem structure, identify domains where an isomorphic problem has already been solved. " + JSON_ONLY_FOOTER
)

def analogical_domain_search_prompt(state: PipelineState) -> str:
    a = state.analogical_state
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Abstract structure: {a.get("abstract_structure", "")}\n'
        f'Structural type: {a.get("structural_type", "")}\n'
        f'Core dynamics: {json.dumps(a.get("core_dynamics", []), indent=2)}\n\n'
        f'Search for domains (biology, physics, engineering, military, economics, computer science, history, social systems) '
        f'where an isomorphic problem — same abstract structure — has been solved. '
        f'Rank by structural relevance, not surface similarity.\n\n'
        f'Output JSON: {{"source_domains": [{{'
        f'"domain": "<field name>", '
        f'"solved_problem": "<problem solved in that domain>", '
        f'"key_mechanism": "<the mechanism that solved it>", '
        f'"historical_example": "<specific example>", '
        f'"relevance_score": "<high|medium|low>", '
        f'"structural_fit": "<why the structures match>"'
        f'}}]}}'
    )

ANALOGICAL_MAPPING_SYSTEM = (
    "You are a structure-mapping theorist. "
    "Map the source domain's solution elements onto the target problem's elements. "
    "Identify object-attribute mappings, relational mappings, and higher-order relational mappings. " + JSON_ONLY_FOOTER
)

def analogical_mapping_prompt(state: PipelineState) -> str:
    a = state.analogical_state
    domains = a.get("source_domains", [])
    best_domain = domains[0] if domains else {}
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Target problem: {_wrap_user_input(state.problem)}\n\n'
        f'Abstract structure: {a.get("abstract_structure", "")}\n'
        f'Constraints: {json.dumps(a.get("constraints", []), indent=2)}\n'
        f'Objectives: {json.dumps(a.get("objectives", []), indent=2)}\n\n'
        f'Best source domain: {json.dumps(best_domain, indent=2)}\n\n'
        f'Map each element of the source domain solution onto the target problem. '
        f'Classify each mapping as: object (entity-to-entity), relational (relation-to-relation), '
        f'or higher-order (system-level pattern). '
        f'Flag any elements that do NOT map cleanly.\n\n'
        f'Output JSON: {{"analogy_mappings": [{{'
        f'"source_element": "<element in source domain>", '
        f'"target_element": "<corresponding element in target problem>", '
        f'"mapping_type": "<object|relational|higher-order>", '
        f'"confidence": "<high|medium|low>", '
        f'"mapping_rationale": "<why these correspond>"'
        f'}}], '
        f'"unmapped_elements": ["<source element with no clean target>"], '
        f'"mapping_quality": "<strong|partial|weak>"}}'
    )

ANALOGICAL_TRANSFER_SYSTEM = (
    "You are an expert in cross-domain knowledge transfer and TRIZ-style contradiction resolution. "
    "Take an analogical mapping and produce a concrete adapted solution for the target problem. "
    "Be explicit about what transfers cleanly, what must be adapted, and where the analogy breaks. " + JSON_ONLY_FOOTER
)

def analogical_transfer_prompt(state: PipelineState) -> str:
    a = state.analogical_state
    domains = a.get("source_domains", [])
    best_domain = domains[0] if domains else {}
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Target problem: {_wrap_user_input(state.problem)}\n\n'
        f'Source domain: {best_domain.get("domain", "")} — {best_domain.get("key_mechanism", "")}\n\n'
        f'Analogy mappings:\n{json.dumps(a.get("analogy_mappings", []), indent=2)}\n\n'
        f'Unmapped elements: {json.dumps(a.get("unmapped_elements", []), indent=2)}\n\n'
        f'Now perform the transfer: adapt the source mechanism to the target problem. '
        f'Be concrete — state the actual proposed solution, not just that "it could be applied". '
        f'Then explicitly state where the analogy breaks (unmapped elements, domain constraints that do not transfer).\n\n'
        f'Output JSON: {{'
        f'"transferred_solution": "<the concrete adapted solution>", '
        f'"transfer_steps": ["<step 1>", "<step 2>"], '
        f'"adaptations_required": ["<what must change vs. source domain>"], '
        f'"broken_analogies": ["<where the analogy fails and why>"], '
        f'"confidence": "<high|medium|low>", '
        f'"caveats": ["<important caveat>"]}}'
    )
