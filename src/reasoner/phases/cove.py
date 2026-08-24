from __future__ import annotations

import json

from reasoner.core.constants import JSON_ONLY_FOOTER
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import (
    _wrap_external_content,
    _wrap_user_input,
    get_language_instruction,
)

COVE_DRAFT_SYSTEM = (
    "You are a knowledgeable analyst. Draft a comprehensive initial answer to the problem. "
    "Break your answer into explicit, verifiable claims. " + JSON_ONLY_FOOTER
)

def cove_draft_prompt(state: PipelineState) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Draft an initial answer. Break it into explicit claims that can be independently verified. '
        f'For each claim, assign a confidence score (0.0-1.0).\n\n'
        f'Output JSON: {{"draft_answer": "<full answer text>", '
        f'"claims": [{{"claim": "<claim text>", "confidence": 0.8}}]}}'
    )

COVE_VERIFY_SYSTEM = (
    "You are a skeptical fact-checker. Given a draft answer with claims, generate specific, "
    "independent verification questions for EACH claim. Do not trust the original answer. " + JSON_ONLY_FOOTER
)

def cove_verify_prompt(state: PipelineState) -> str:
    draft = state.cove_state.get("draft_answer", "")
    claims = state.cove_state.get("claims", [])
    claims_json = json.dumps(claims, indent=2) if claims else "[]"
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Original Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Draft Answer:\n{_wrap_external_content(draft)}\n\n'
        f'Claims to verify:\n{claims_json}\n\n'
        f'For EACH claim above, generate 1-2 specific verification questions that would '
        f'independently test whether the claim is true. The questions must be answerable '
        f'without referring to the draft answer.\n\n'
        f'Output JSON: {{"verification_questions": [{{'
        f'"question": "<verification question>", '
        f'"target_claim": "<claim being tested>", '
        f'"expected_evidence_type": "<fact|statistic|authority|logic>"'
        f'}}]}}'
    )

COVE_ANSWER_SYSTEM = (
    "You are an independent researcher. Answer the verification questions based on your own "
    "knowledge. Do not refer to the draft answer. Be explicit about whether evidence supports "
    "or contradicts each claim. " + JSON_ONLY_FOOTER
)

def cove_answer_prompt(state: PipelineState) -> str:
    questions = state.cove_state.get("verification_questions", [])
    questions_json = json.dumps(questions, indent=2) if questions else "[]"
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Original Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Answer these verification questions INDEPENDENTLY, using your own knowledge. '
        f'Do not refer to any draft answer. For each question, explicitly state whether '
        f'the evidence supports, contradicts, or is insufficient to evaluate the target claim.\n\n'
        f'Questions:\n{questions_json}\n\n'
        f'Output JSON: {{"answers": [{{'
        f'"question": "<question text>", '
        f'"answer": "<your independent answer>", '
        f'"verdict": "<supports|contradicts|insufficient>", '
        f'"confidence": 0.8, '
        f'"reasoning": "<why>"'
        f'}}]}}'
    )
def cove_answer_prompt_single(question: dict) -> str:
    """Factored variant (CoVE paper Sec 3.3). One question per call, no baseline draft."""
    return (
        f'Question: {question.get("question", "")}\n\n'
        f'Answer this question accurately using your own knowledge. '
        f'Do NOT refer to any previous draft or response.\n\n'
        f'Output JSON: {{'
        f'"answer": "<your answer>", '
        f'"confidence": 0.8, '
        f'"reasoning": "<why>"'
        f'}}'
    )

# Factor+Revise Cross-Check (CoVE paper, Sec 3.4)
COVE_CROSSCHECK_SYSTEM = (
    "You are an inconsistency detector. Compare verification answers against "
    "original claims and report mismatches. " + JSON_ONLY_FOOTER
)

def cove_crosscheck_prompt(state: PipelineState) -> str:
    """Generate a cross-check prompt to detect inconsistencies between
    independent verification answers and the original draft claims."""
    draft = state.cove_state.get("draft_answer", "")
    answers = state.cove_state.get("verification_answers", [])
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Original Draft:\n{_wrap_external_content(draft)}\n\n'
        f'Verification Results:\n{json.dumps(answers, indent=2)}\n\n'
        f'For EACH verification result, determine if the answer contradicts '
        f'the original draft claim. Report any inconsistencies found.\n\n'
        f'Output JSON: {{"inconsistencies": [{{'
        f'"claim": "<original claim>", '
        f'"verification_answer": "<what was found>", '
        f'"is_contradiction": true, '
        f'"resolution": "<suggested fix>"'
        f'}}]}}'
    )

# Few-Shot Demonstrations (CoVE paper, Sec 3.4)
COVE_FEW_SHOT = (
    "Example 1:\n"
    "Draft: The Mexican-American War was from 1846 to 1848.\n"
    "Verification Q: When did the Mexican-American war start?\n"
    "Verified Answer: 1846. Therefore the draft is consistent.\n"
    "Result: Consistent. No change needed.\n\n"
    "Example 2:\n"
    "Draft: Hillary Clinton was born in NY, New York.\n"
    "Verification Q: Where was Hillary Clinton born?\n"
    "Verified Answer: Chicago, Illinois. Therefore the draft is WRONG.\n"
    "Result: INCONSISTENCY detected. Draft must be corrected.\n"
)


COVE_REVISE_SYSTEM = (
    "You are a careful editor. Given a draft answer and independent verification results, "
    "revise the entire answer to correct errors. When cross-check inconsistencies are present, you MUST correct them. Add caveats where evidence is uncertain. " + JSON_ONLY_FOOTER
)

def cove_revise_prompt(state: PipelineState) -> str:
    draft = state.cove_state.get("draft_answer", "")
    answers = state.cove_state.get("verification_answers", [])
    answers_json = json.dumps(answers, indent=2) if answers else "[]"
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Original Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Draft Answer:\n{_wrap_external_content(draft)}\n\n'
        f'Independent Verification Results:\n{_wrap_external_content(answers_json)}\n\n'
        f'Revise the draft answer based on the verification results. '
        f'Correct any contradicted claims, add caveats for insufficient evidence, '
        f'and strengthen supported claims. Document what changed and why.\n\n'
        f'Output JSON: {{"revised_answer": "<revised full answer>", '
        f'"changes_made": ["<change description>"], '
        f'"remaining_uncertainties": ["<uncertainty>"], '
        f'"upgraded_claims": ["<claim that was strengthened>"], '
        f'"retracted_claims": ["<claim that was removed or corrected>"]}}'
    )
