from __future__ import annotations

import json

from reasoner.core.constants import DEFAULT_SEARCH_RESULTS, JSON_ONLY_FOOTER, TRUNCATION
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import (
    HUMANIZATION_RULES,
    _followup_context,
    _wrap_external_content,
    _wrap_user_input,
    get_language_instruction,
)

DISAMBIGUATION_SYSTEM = "You are an analytical assistant. Detect whether a problem is ambiguous and could be interpreted in multiple ways. Output ONLY valid JSON."

def disambiguation_prompt(problem: str, task_type: str | None) -> str:
    task_hint = f"Task type: {task_type}. " if task_type else ""
    return (
        f'Analyze whether the following problem is ambiguous or could be interpreted in multiple ways. '
        f'{task_hint}If ambiguous, explain why and provide a clearer rewritten version. If clear, state that it is unambiguous.\n\n'
        f'Problem: {_wrap_user_input(problem)}\n\n'
        f'Output JSON: {{"was_ambiguous": true/false, "rewritten_query": "<clearest version>", "reasoning": "<why>"}}'
    )

PROMPT_ENHANCEMENT_SYSTEM = """You are an analytical assistant. Your ONLY job is to rewrite the user's problem to make it clearer, more specific, and easier for an AI reasoning system to solve.

CRITICAL RULES:
1. Preserve the EXACT original intent, tone, language, and question type. Do NOT flip positive questions into negative ones.
2. The rewritten problem MUST be a direct rephrasing of the original — do NOT change the subject, scope, or factual claims.
3. Do NOT add any extra sentences, instructions, opinions, or requirements that were not in the original problem.
4. Output ONLY valid JSON with the exact shape: {"enhanced_problem": "<rewritten>", "improvements": ["<what was improved>"]}
5. If the problem is already clear and specific, return it nearly unchanged."""

def prompt_enhancement_prompt(problem: str, language: str) -> str:
    lang_instruction = get_language_instruction(language)
    return f'{lang_instruction}\n\nOriginal Problem:\n{_wrap_user_input(problem)}\n\nRewrite this problem to be clearer, more specific, and easier for a multi-step AI reasoning pipeline to solve. Preserve the original language and intent.\n\nOutput JSON: {{"enhanced_problem": "<rewritten problem>", "improvements": ["<what was improved>"]}}'

CLASSIFICATION_SYSTEM = "Classify task type. JSON only."
def classification_prompt(problem: str, language: str, state: PipelineState | None = None) -> str:
    lang_instruction = get_language_instruction(language)
    followup = _followup_context(state) if state else ""
    return (
        f'{lang_instruction}\n{followup}\nProblem:\n{_wrap_user_input(problem)}\n\n'
        f'Choose exactly ONE task type from: analytical, strategic, creative, technical, predictive, hybrid. '
        f'JSON: {{"task_type": "analytical", "rationale": "<why>", "language": "{language}"}}'
    )

DECOMPOSITION_SYSTEM = "Decompose problem into sub-problems. JSON only."
def decomposition_prompt(state: PipelineState) -> str:
    is_jury = "jury" in (state.preset_name or "")
    jury_instr = " Add jury_guidelines." if is_jury else ""
    web_context = f"\nWeb: {state.web_discovery_results[:TRUNCATION.KEY_INSIGHTS]}" if state.web_discovery_results else ""
    followup = _followup_context(state)

    return f'''{get_language_instruction(state)}

{followup}
Problem: {_wrap_user_input(state.problem)}{web_context}
Decompose.{jury_instr}

JSON: {{"causal_chain": [{{"step": 1, "action": "<action>", "produces": ["<output>"]}}], "assumptions": [{{"text": "<assumption>", "label": "VERIFIED|HYPOTHESIS|UNKNOWN", "rationale": "<why this label>", "source_hint": "<source name or URL if VERIFIED>"}}], "failure_modes": ["<failure>"], "critical_sources": [{{"url": "<URL>", "reason": "<why it matters>"}}]}}

Rules: Max 5 steps. Surface assumptions with rationale. VERIFIED assumptions MUST cite a source_hint. If web results exist, list 1-2 critical_sources. Be specific.'''

FUSION_SYSTEM = """You are an analytical assistant. Your job is to classify the task type, detect the language, and decompose the problem into a causal chain. Output ONLY valid JSON."""

def fusion_prompt(state: PipelineState, language: str) -> str:
    lang_instruction = get_language_instruction(language)
    is_jury = "jury" in (state.preset_name or "")
    jury_instr = " Add jury_guidelines." if is_jury else ""
    web_context = f"\nWeb: {state.web_discovery_results[:TRUNCATION.KEY_INSIGHTS]}" if state.web_discovery_results else ""
    followup = _followup_context(state)

    problem = state.enhanced_problem or state.problem
    return (
        f'{lang_instruction}\n{followup}\nProblem: {_wrap_user_input(problem)}{web_context}\n\n'
        f'First, choose exactly ONE task type from: analytical, strategic, creative, technical, predictive, hybrid.\n'
        f'\n'
        f'DISAMBIGUATION (apply strictly):\n'
        f'- "creative": ONLY if the user explicitly asks for original creative work (poem, story, fiction, satire, marketing copy).\n'
        f'- "analytical": ANY request that asks for analysis, explanation, comparison, evaluation, research, or understanding of a real-world topic.\n'
        f'- If the topic involves facts, data, evidence, or research-backed claims → "analytical" (NOT creative).\n'
        f'- When in doubt between creative and analytical, choose "analytical".\n'
        f'\n'
        f'Then, decompose the problem into a causal chain (max 5 steps). {jury_instr}\n\n'
        f'Output JSON: {{\n'
        f'  "task_type": "analytical",\n'
        f'  "task_rationale": "<why this task type>",\n'
        f'  "language": "{language}",\n'
        f'  "causal_chain": [{{"step": 1, "action": "<action>", "produces": ["<output>"]}}],\n'
        f'  "assumptions": [{{"text": "<assumption>", "label": "VERIFIED|HYPOTHESIS|UNKNOWN", "rationale": "<why>", "source_hint": "<source name or URL if VERIFIED>"}}],\n'
        f'  "failure_modes": ["<failure>"],\n'
        f'  "critical_sources": [{{"url": "<URL>", "reason": "<why it matters>"}}]\n'
        f'}}\n\n'
        f'Rules: Max 5 steps for causal_chain. Surface assumptions with rationale. VERIFIED assumptions MUST cite a source_hint. If web results exist, list 1-2 critical_sources. Be specific.'
    )

SYNTHESIS_SYSTEM = """You are a senior analytical strategist and expert technical writer. Your goal is to produce a definitive, professional synthesis that resolves complex problems with clarity and authority.

STYLE MANDATE (PROFESSIONALISM):
1.  **Crisp & Precise:** Use direct, high-signal language. Avoid "corporate fluff," filler phrases, and generic signposting.
2.  **Visual Hierarchy:** Use clear Markdown headings (###), bolding for key terms, and bulleted lists for readability.
3.  **Logical Flow:** Start with a high-level summary, move into thematic deep-dives, and end with a concrete path forward.
4.  **Tone:** Authoritative yet epistemically honest. Acknowledge the limits of the data without sacrificing clarity.

LANGUAGE RULE (CRITICAL):
- The user has explicitly requested a specific language at the start of the prompt.
- Your ENTIRE response — both the prose inside [SOLUTION] tags AND all JSON string values — MUST be written in that requested language.
- Do NOT use English unless the user explicitly asked for English.

FORMAT RULES:
- Use this exact format: [SOLUTION]...prose with structured headings and citations...[/SOLUTION] followed by a JSON block in ```json...```
- If you cannot produce the [SOLUTION] tag, return ONLY the JSON block; the pipeline will synthesize prose for you.
- Output valid JSON inside the fence with fields: critical_insights, action_blueprint, open_questions, claim_labels, meta_audit, sources, layout_hints, evidence.

CITATION REQUIREMENTS:
- Use format: [source_title](url) after each claim from a source.
- You MUST only cite sources listed in the WEB SOURCES section above. Do not invent or reuse URLs from memory.
- Include all sources used in a "sources" array in the JSON output.

LAYOUT HINTS (JSON Field):
- Provide a `layout_hints` object with keys: `primary_theme_color` (hex), `suggested_layout` ("standard"|"academic"|"executive"), and `important_sections` (array of section headers).

ACTION BLUEPRINT RULES:
- Each item MUST be an object with keys: step, action, time_horizon, go_criteria, fallback.

CIRCUIT BREAKER:
- If sources are missing or unreliable, flag this explicitly in the abstract or a "Data Integrity" section.
- Do NOT synthesize confident answers from UNVERIFIED data.""" + HUMANIZATION_RULES

def synthesis_prompt(state: PipelineState) -> str:
    final_context = state.to_context_dict(phase="synthesis")
    # Preserve full candidate content when context window allows (qwen3.6-plus: 1M).
    # Fallback models will truncate server-side if prompt exceeds their context.
    if 'candidates' in final_context:
        for c in final_context['candidates']:
            c.pop('raw_scores', None)  # strip numeric internals only

    sources_info = ""
    if state.vetted_context:
        deep_sources = []
        total_chars = 0
        max_chars = TRUNCATION.LARGE_CONTENT
        for r in state.vetted_context[:DEFAULT_SEARCH_RESULTS]:
            entry = {
                "title": r.get("title", "Unknown"),
                "url": r.get("url", ""),
                "summary": r.get("summary", ""),
                "key_facts": (v if isinstance(v := r.get("key_facts"), list) else [])[:TRUNCATION.KEY_INSIGHTS],
                "relevant_quotes": (v if isinstance(v := r.get("relevant_quotes"), list) else [])[:TRUNCATION.MEMORY],
                "vetting_flags": (v if isinstance(v := r.get("vetting_flags"), list) else [])[:TRUNCATION.MEMORY],
            }
            entry_text = json.dumps(entry)
            if total_chars + len(entry_text) > max_chars:
                break
            total_chars += len(entry_text)
            deep_sources.append(entry)
        sources_info = "\nWEB SOURCES (with extracted summaries):\n" + json.dumps(deep_sources, indent=2)
    elif state.web_discovery_results:
        sources_info = "\nWEB SOURCES (for citations):\n" + json.dumps([
            {"title": r.get("title", "Unknown"), "url": r.get("url", "")}
            for r in state.web_discovery_results[:DEFAULT_SEARCH_RESULTS]
        ], indent=2)

    # Prism citations (populated by PrismResearcher)
    from reasoner.phases._shared import build_synthesis_context
    prism_context = build_synthesis_context(state)
    if prism_context:
        sources_info += "\n\n" + prism_context

    method_hint = "Synthesize the best possible solution."
    is_research = state.preset_name and "research" in state.preset_name.lower()
    if is_research:
        method_hint += (
            "\n\nRESEARCH METHOD CITATION AND REPORT DISCIPLINE:\n"
            "Because this is a dedicated Research/web-grounded synthesis, you MUST apply strict report formatting and citation discipline:\n"
            "1. REPORT STRUCTURE: Deliver an exhaustive, professional-grade research-report structure targeting comprehensive depth.\n"
            "2. INLINE CITATIONS: Every factual assertion or claim MUST be backed by a clear inline reference using the format [n] (e.g. \"According to recent studies [1]...\") referencing the gathered citation index numbers.\n"
            "3. EPISTEMIC LABELLING: If a statement is speculative or cannot be supported by any of the gathered citations, you MUST explicitly label it as [HYPOTHESIS] or [UNKNOWN] using the project's standard epistemic vocabulary. Do NOT present unverified claims with confidence.\n"
            "4. SOURCE INTEGRITY: Rely only on the provided WEB SOURCES. Never fabricate citations or URLs."
        )

    followup = _followup_context(state)
    quality_note = f"\nCONTEXT QUALITY: {state.context_quality}\n" if state.context_quality and state.context_quality != "unknown" else ""

    return f'{get_language_instruction(state)}\n{followup}\nFinal Context:\n{_wrap_external_content(json.dumps(final_context, indent=2))}\n{_wrap_external_content(sources_info)}{quality_note}\n\n{method_hint}\n\nUse this exact format: [SOLUTION]...prose with structured headings and citations...[/SOLUTION] ```json...``` with fields: critical_insights, action_blueprint, open_questions, claim_labels, meta_audit, sources, layout_hints, evidence.'

COT_DETECTION_SYSTEM = """You are a meticulous, skeptical, and ruthless analytical assistant. Your primary function is to shield the reasoning pipeline from low-quality, irrelevant, or misleading information. Review retrieved text for factual errors, unsubstantiated claims, obvious speculation, or low relevance to the user's core problem. Output ONLY valid JSON.

CRITICAL VETTING RULES:
1.  **Relevance is Paramount:** Flag ANY source that is not DIRECTLY and DEEPLY relevant to the user's specific problem. General, tangentially related, or high-level content must be flagged.
2.  **No Homepages or Directories:** Aggressively flag top-level homepages (e.g., cnn.com, google.com), indexes, or "list of links" pages. Only content-rich articles, papers, or deep pages are acceptable.
3.  **Reject "Listicles" and Summaries of Summaries:** Flag any page that is just a list of other articles or a low-effort summary of other sources. We need primary or deep secondary sources.
4.  **Scrutinize Factual Claims:** Flag any statement that is DIRECTLY contradicted by well-known facts, contains clear logical errors, or makes extraordinary claims without extraordinary evidence.
5.  **Be Skeptical of Speculation:** Flag any content that is clearly marked as opinion, speculation, or forward-looking statements without a strong evidentiary basis.
6.  **Default to "Flag":** If you are uncertain about the quality or relevance of a source, ERR ON THE SIDE OF CAUTION and flag it for removal. It is better to have fewer high-quality sources than many noisy ones.
7.  If the text is a high-quality, relevant, and factual source, return an empty list for its flags."""

def cot_detection_prompt(state: PipelineState, retrieved_text: str) -> str:
    return f'{get_language_instruction(state)}\n\nProblem: {_wrap_user_input(state.problem)}\n\nReview the following retrieved text. Identify ONLY statements that are clearly factually incorrect, unsubstantiated, or overly speculative. Do NOT flag minor simplifications or educational summaries. If no clear issues are found, return an empty list.\n\nRetrieved Text:\n{retrieved_text}\n\nOutput JSON: {{"flags": [{{"statement": "<problematic statement>", "reasoning": "<why it\'s problematic>"}}]}}'


def cot_detection_batch_prompt(state: PipelineState, snippets: list[dict]) -> str:
    """Batch vetting prompt — vet multiple search snippets in a single LLM call."""
    items = "\n\n".join(
        f'--- Item {s["index"]} ---\nURL: {s.get("url", "N/A")}\nSnippet: {s["text"]}'
        for s in snippets
    )
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Review the following retrieved texts (each with an index). For EACH item, '
        f'identify ONLY statements that are clearly factually incorrect, unsubstantiated, '
        f'or overly speculative. Do NOT flag minor simplifications or educational summaries. '
        f'If no clear issues are found for an item, omit it from the flagged list.\n\n'
        f'{items}\n\n'
        f'Output JSON: {{"flagged": [{{"index": 0, "flags": [{{"statement": "<problematic statement>", "reasoning": "<why>"}}], "reasoning": "<summary>"}}]}}'
    )

ITERATIVE_CONTEXT_SYSTEM = (
    "You are an analytical research assistant. Your job is to gather high-quality, "
    "verifiable external sources for a reasoning problem. You must NOT rely on your "
    "internal knowledge — always search for external sources. Output ONLY valid JSON."
)

# Pre-planned search: generates all search rounds upfront so they can execute in parallel.
ITERATIVE_PREPLAN_SYSTEM = (
    "You are an analytical research strategist. Your job is to plan ALL search rounds "
    "upfront so they can be executed in parallel. Plan 2-3 rounds of increasingly "
    "targeted search queries. Do NOT rely on your internal knowledge — always plan "
    "to search for external sources. Output ONLY valid JSON."
)

def iterative_context_prompt(state: PipelineState, current_results: list[dict], iteration: int, max_iterations: int) -> str:
    results_str = json.dumps(current_results, indent=2) if current_results else "No results yet."
    source_count = len(current_results)
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Iteration: {iteration} of {max_iterations}\n'
        f'Sources gathered so far: {source_count}\n\n'
        f'Current Search Results:\n{results_str}\n\n'
        f'RULES:\n'
        f'1. You MUST continue searching until you have at least 3-5 relevant, '
        f'high-quality external sources, OR until maximum iterations are reached.\n'
        f'2. Do NOT declare "done" just because you have internal knowledge on the topic.\n'
        f'3. Generate up to 3 highly specific, targeted search queries.\n'
        f'4. Avoid generic queries (e.g., "AI", "technology", "video"). Be specific to the problem.\n'
        f'5. Prefer authoritative sources: academic papers, reputable news, expert analyses.\n\n'
        f'Output JSON: {{"action": "search|done", "queries": ["<query1>", "<query2>"], "reasoning": "<why you need more info or have enough>"}}'
    )


def iterative_preplan_prompt(state: PipelineState) -> str:
    """Pre-plan all search rounds upfront for parallel execution."""
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Plan 2-3 rounds of search queries to gather high-quality external sources.\n'
        f'Each round should contain up to 3 specific, targeted queries.\n'
        f'Round 1: Broad initial search to understand the landscape.\n'
        f'Round 2: Follow-up on specific aspects or gaps.\n'
        f'Round 3: Targeted search for authoritative sources or missing perspectives.\n\n'
        f'RULES:\n'
        f'1. All queries will be executed in parallel, so make them self-contained.\n'
        f'2. Avoid generic queries (e.g., "AI", "technology"). Be specific to the problem.\n'
        f'3. Prefer authoritative sources: academic papers, reputable news, expert analyses.\n'
        f'4. Do NOT rely on your internal knowledge — plan searches that will find real sources.\n\n'
        f'Output JSON: {{"iterations": [{{"queries": ["<q1>", "<q2>"], "reasoning": "<why>"}}, {{"queries": ["<q3>"], "reasoning": "<why>"}}]}}'
    )

CROSS_VERIFICATION_SYSTEM = "You are an analytical assistant. Identify specific factual errors, unsupported claims, or logical inconsistencies in a proposed solution. Be precise and cite exact problems. Output ONLY valid JSON."

def cross_verification_prompt(state: PipelineState, candidate_solution: dict) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Original Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Candidate Solution to Verify:\n{json.dumps(candidate_solution, indent=2)}\n\n'
        f'Identify any claims made with high confidence that are factually incorrect, '
        f'logically unsound, or unsubstantiated. Be specific.\n\n'
        f'Output JSON: {{"verified": <true|false>, "verification_findings": ["<issue1>", "<issue2>"], "summary": "<one sentence>"}}'
    )

DEEP_READ_SYSTEM = "You are an analytical assistant. Extract and summarize key information from web pages. Provide a structured summary of the page content relevant to the user's problem. Output ONLY valid JSON."

SHALLOW_READ_SYSTEM = "You are an analytical assistant. Infer the content of a web page from its title and snippet. Provide a brief summary. Output ONLY valid JSON."

def deep_read_prompt(state: PipelineState, url: str, title: str, content: str) -> str:
    trimmed = content[:TRUNCATION.DEEP_READ]
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Original Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Source:\nURL: {url}\nTitle: {title}\n\n'
        f'Page Content (first {TRUNCATION.DEEP_READ} chars):\n{_wrap_external_content(trimmed)}\n\n'
        f'Extract the key information from this page that is relevant to the problem. '
        f'If the page is irrelevant, too short, or lacks substantive content, set "summary" to "INSUFFICIENT".\n\n'
        f'Output ONLY valid JSON with this exact structure:\n'
        f'{{\n'
        f'  "summary": "<comprehensive summary or INSUFFICIENT>",\n'
        f'  "key_facts": ["<fact1>", "<fact2>"],\n'
        f'  "relevant_quotes": ["<quote1>"]\n'
        f'}}'
    )

def shallow_read_prompt(state: PipelineState, url: str, title: str, snippet: str) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Original Problem: {_wrap_user_input(state.problem)}\n\n'
        f'We could not fetch the full page. Based on the title and snippet below, '
        f'provide a brief summary of what this source likely contains. '
        f'If it seems irrelevant, return "INSUFFICIENT".\n\n'
        f'URL: {url}\n'
        f'Title: {title}\n'
        f'Snippet: {_wrap_external_content(snippet)}\n\n'
        f'Output ONLY valid JSON:\n'
        f'{{\n'
        f'  "summary": "<brief summary or INSUFFICIENT>",\n'
        f'  "key_facts": [],\n'
        f'  "relevant_quotes": []\n'
        f'}}'
    )

POST_SYNTHESIS_VERIFY_SYSTEM = (
    "You are an independent fact-checker. Given a synthesized answer, generate verification "
    "questions and evaluate the answer's claims without referring to the original synthesis model. "
    + JSON_ONLY_FOOTER
)

POST_SYNTHESIS_VERIFY_SYSTEM_SONAR = (
    "You are an independent fact-checker with live web search capability. "
    "Given a synthesized answer, generate verification questions and independently verify "
    "each claim against current, authoritative sources. "
    "Use your web search to check every factual assertion. "
    "Mark claims as 'verified' only when you can confirm them via live search. "
    "Flag any claims that appear unsupported, contradictory, or overstated. "
    + JSON_ONLY_FOOTER
)

def post_synthesis_verify_prompt(synthesis_text: str, state: PipelineState) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Synthesized Answer to Verify:\n{_wrap_external_content(synthesis_text)}\n\n'
        f'Generate 3-5 verification questions for the key claims in this answer. '
        f'Then evaluate each claim independently based on your own knowledge. '
        f'Flag any claims that appear unsupported, contradictory, or overstated.\n\n'
        f'Output JSON: {{"verification_questions": ["<question>"], '
        f'"evaluation": [{{'
        f'"claim": "<claim>", '
        f'"verdict": "<verified|hypothesis|incorrect|uncertain>", '
        f'"confidence": 0.8, '
        f'"notes": "<evaluation notes>"'
        f'}}], '
        f'"recommendations": ["<suggested improvement>"]}}'
    )
