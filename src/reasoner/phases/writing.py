from __future__ import annotations

import json

from reasoner.core.constants import (
    ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION,
    ARTICLE_MIN_SOURCE_COUNT,
    JSON_ONLY_FOOTER,
)
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import (
    HUMANIZATION_RULES,
    _wrap_external_content,
    _wrap_user_input,
    get_language_instruction,
)

# ── CoVE for Claims ──────────────────────────────────────────────────────────

ARTICLE_COVE_DRAFT_SYSTEM = (
    "You are a precise fact extractor. Draft atomic claims from the provided sources. "
    "One factual statement per claim. No interpretation. Must be directly supported by text. "
    "Prefer claims backed by multiple independent sources when available. "
    + JSON_ONLY_FOOTER
)

ARTICLE_COVE_VERIFY_SYSTEM = (
    "You are a skeptical fact-checker. For EACH claim below, independently verify whether it is "
    "actually supported by the provided sources. Do NOT trust the claims — check them against the sources. "
    "Generate 1-2 specific verification questions per claim. "
    + JSON_ONLY_FOOTER
)

ARTICLE_COVE_ANSWER_SYSTEM = (
    "You are a HOSTILE reviewer whose bonus depends on REJECTING claims. "
    "Answer the verification questions based ONLY on the sources. "
    "Do not refer to the draft claims. "
    "CRITICAL SKEPTICISM RULES:\n"
    "1. If a source mentions the topic but does NOT explicitly contain the exact statement or an unambiguous paraphrase, answer INSUFFICIENT.\n"
    "2. Do NOT infer support from tangential mentions, general discussions, or related topics.\n"
    "3. Do NOT give the benefit of the doubt. When in doubt, reject.\n"
    "4. For each 'supports' answer, you MUST cite the exact sentence or passage from the source that directly confirms the claim.\n"
    "5. If the source discusses the general topic but not the specific claim, the verdict is INSUFFICIENT — never SUPPORTS.\n"
    "6. Watch for claims that slightly exaggerate, generalize, or rephrase source text — downgrade these.\n"
    + JSON_ONLY_FOOTER
)

ARTICLE_COVE_REVISE_SYSTEM = (
    "You are a careful editor. Given draft claims and independent verification results, "
    "revise the claim list. Keep only claims where verification SUPPORTS them. "
    "Downgrade weak claims. Remove contradicted claims. Add caveats where evidence is insufficient. "
    + JSON_ONLY_FOOTER
)


def article_cove_draft_prompt(state, sources_json: str) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Topic: {state.problem}\n\n'
        f'Sources:\n{sources_json}\n\n'
        f'Draft atomic claims from the sources. Rules:\n'
        f'- One factual statement per claim\n'
        f'- No interpretation or speculation\n'
        f'- Must be directly supported by source text\n'
        f'- Assign a confidence score (0.0-1.0) per claim\n\n'
        f'Output JSON: {{"claims": [{{'
        f'"id": "C1", "text": "...", "source_url": "...", "confidence": 0.85'
        f'}}]}}'
    )


def article_cove_verify_prompt(state, claims_json: str, sources_json: str) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Draft Claims:\n{claims_json}\n\n'
        f'Sources:\n{sources_json}\n\n'
        f'For EACH claim above, generate 1-2 specific verification questions that would '
        f'independently test whether the claim is true. The questions must be answerable '
        f'from the sources without referring to the claims.\n\n'
        f'Output JSON: {{"verification_questions": [{{'
        f'"question": "...", "target_claim_id": "C1", "expected_evidence_type": "fact|statistic|authority"'
        f'}}]}}'
    )


def article_cove_answer_prompt(state, questions_json: str, sources_json: str) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Sources:\n{sources_json}\n\n'
        f'Answer these verification questions INDEPENDENTLY using ONLY the sources above. '
        f'CRITICAL: Be skeptical. If a source mentions the topic but does NOT directly support the specific claim, '
        f'state "insufficient evidence" rather than "supports". '
        f'Flag any claim that generalizes beyond what the source explicitly states. '
        f'Do not refer to any draft claims. For each question, explicitly state whether '
        f'the evidence supports, contradicts, or is insufficient.\n\n'
        f'VERDICT RULES:\n'
        f'- SUPPORTS: The source contains an EXACT or unambiguous paraphrase of the claim. You must quote the supporting passage.\n'
        f'- CONTRADICTS: The source explicitly says the opposite. You must quote the contradicting passage.\n'
        f'- INSUFFICIENT: The source mentions the topic but does not directly confirm or deny the specific claim.\n'
        f'When in doubt, choose INSUFFICIENT. Do not give benefit of the doubt.\n\n'
        f'Questions:\n{questions_json}\n\n'
        f'Output JSON: {{"answers": [{{'
        f'"question": "...", "answer": "...", "verdict": "supports|contradicts|insufficient", '
        f'"confidence": 0.8, "reasoning": "...", '
        f'"supporting_quote": "exact passage from source that supports this (empty if insufficient or contradicts)"'
        f'}}]}}'
    )


def article_cove_revise_prompt(state, claims_json: str, answers_json: str) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Draft Claims:\n{claims_json}\n\n'
        f'Independent Verification Results:\n{answers_json}\n\n'
        f'Revise the claim list. Keep ONLY claims where verification explicitly SUPPORTS them with direct evidence. '
        f'Downgrade claims where verification states "insufficient evidence" to "weak" (not "verified"). '
        f'Remove contradicted claims. Add caveats for insufficient evidence. Document what changed.\n\n'
        f'Output JSON: {{"claims": [{{'
        f'"id": "C1", "text": "...", "source_url": "...", "confidence": 0.85, "status": "verified|weak|rejected"'
        f'}}], '
        f'"changes_made": ["..."], '
        f'"remaining_uncertainties": ["..."]}}'
    )


# ── Pre-Mortem for Articles ──────────────────────────────────────────────────

ARTICLE_PRE_MORTEM_SYSTEM = (
    "You are a strategic risk analyst. Imagine the article was rejected by journal reviewers. "
    "Work backwards to identify the root causes of failure. Be brutally honest. "
    "All string values must be plain text — no markdown, no formatting, no line breaks inside strings. "
    "Keep 'failure_narrative' to ONE sentence (max 30 words). "
    + JSON_ONLY_FOOTER
)


def article_pre_mortem_prompt(state, article: str, claims_json: str) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Article Draft:\n{article}\n\n'
        f'Claims:\n{claims_json}\n\n'
        f'Imagine this article was submitted to a top-tier journal and was REJECTED. '
        f'Work backwards: what went wrong?\n\n'
        f'Return ONLY this JSON object (no markdown fences, no extra text):\n'
        f'{{\n'
        f'  "failure_narrative": "<ONE sentence, max 30 words, plain text, no quotes inside>",\n'
        f'  "root_causes": ["<short phrase>", "..."],\n'
        f'  "weak_sections": ["<section name>", "..."],\n'
        f'  "challenged_claims": ["<short phrase>", "..."],\n'
        f'  "missing_counterarguments": ["<short phrase>", "..."],\n'
        f'  "overgeneralizations": ["<short phrase>", "..."],\n'
        f'  "early_warnings": ["<short phrase>", "..."]\n'
        f'}}'
    )


# ── SoT for Article Synthesis ────────────────────────────────────────────────

ARTICLE_SOT_SYSTEM = (
    "You are an expert at parallel article writing. Generate a skeleton outline with sections "
    "that can be written independently. Identify dependencies between sections. "
    + JSON_ONLY_FOOTER
)

ARTICLE_SOT_SOLVE_SYSTEM = (
    "You are a disciplined research writer. Write ONE section using ONLY verified claims. "
    "Inline markdown citations required. Do not generalize beyond sources. "
    "Every non-trivial factual paragraph must include at least one citation. "
    + JSON_ONLY_FOOTER
    + HUMANIZATION_RULES
)

ACADEMIC_SOT_SYSTEM = (
    "You are an expert academic writer. Generate a scholarly paper skeleton following academic "
    "conventions (IMRaD or thesis structure). Each section must be self-contained, citable, "
    "and written in formal academic register. Assign appropriate word targets per section. "
    + JSON_ONLY_FOOTER
)

ACADEMIC_SOT_SOLVE_SYSTEM = (
    "You are a disciplined academic writer. Write ONE section of a scholarly paper using ONLY "
    "the provided verified claims. Use formal academic tone: third-person voice, precise language, "
    "hedged claims where evidence is limited (e.g. 'suggests', 'indicates', 'appears to'). "
    "Every factual statement requires an inline citation [Source: URL]. "
    "State limitations explicitly if evidence is thin. Do not generalize beyond sources. "
    + JSON_ONLY_FOOTER
    + HUMANIZATION_RULES
)


def article_sot_skeleton_prompt(state, claims_json: str) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Topic: {state.problem}\n\n'
        f'Verified Claims:\n{claims_json}\n\n'
        f'Create an article skeleton. Break into sections that can be written in parallel. '
        f'For each section, specify:\n'
        f'1. Section heading\n'
        f'2. Which claims it uses (by claim_id)\n'
        f'3. Dependencies (which sections must be written before this one)\n'
        f'4. Estimated word count\n\n'
        f'Output JSON: {{"sections": [{{'
        f'"id": "S1", "heading": "...", "claim_ids": ["C1"], '
        f'"dependencies": [], "word_count": 200'
        f'}}]}}'
    )


def academic_sot_skeleton_prompt(state, claims_json: str) -> str:
    doc_type = state.writing_state.get("document_type", "paper")
    if doc_type == "thesis":
        sections_guide = (
            "Abstract | Introduction (research question, scope, significance) | "
            "Literature Review (existing scholarship, theoretical framework, research gap) | "
            "Methodology (research design, data sources, analytical approach) | "
            "Findings (primary results, organized thematically) | "
            "Analysis & Discussion (interpretation, implications, limitations) | "
            "Conclusion (contributions, synthesis, future research) | "
            "Bibliography"
        )
        word_targets = (
            "Abstract: 250, Introduction: 600, Literature Review: 1000, "
            "Methodology: 600, Findings: 800, Analysis & Discussion: 800, Conclusion: 500"
        )
    else:
        sections_guide = (
            "Abstract | Introduction (background, research question, objectives) | "
            "Literature Review (related work, theoretical basis) | "
            "Methodology (approach, data, analysis method) | "
            "Results & Discussion (findings, interpretation, limitations) | "
            "Conclusion (summary, implications, future work) | "
            "References"
        )
        word_targets = (
            "Abstract: 200, Introduction: 400, Literature Review: 600, "
            "Methodology: 400, Results & Discussion: 600, Conclusion: 300"
        )
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Topic: {state.problem}\n'
        f'Document Type: {doc_type.title()}\n\n'
        f'Verified Claims:\n{claims_json}\n\n'
        f'Generate an academic skeleton following this structure:\n{sections_guide}\n\n'
        f'Target word counts: {word_targets}\n\n'
        f'For each section assign the relevant claim_ids and specify its academic purpose.\n\n'
        f'Output JSON: {{"sections": [{{'
        f'"id": "S1", "heading": "...", "claim_ids": ["C1"], '
        f'"purpose": "...", "dependencies": [], "word_count": 400'
        f'}}]}}'
    )


def article_sot_solve_prompt(state, section: dict, claims_json: str) -> str:
    section_heading = section.get("heading", "")
    style_brief = state.writing_state.get("style_brief", "")
    style_section = f"\nStyle Brief:\n{style_brief}\n" if style_brief else ""
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Topic: {state.problem}\n\n'
        f'Section: {section_heading}\n\n'
        f'Relevant Claims (use these as your evidence):\n{claims_json}\n\n'
        f'Write this section. Rules:\n'
        f'- SCOPE CONSTRAINT: Write ONLY about "{section_heading}". Do NOT include content that belongs in other sections.\n'
        f'- If claims are sparse for this section, synthesize what you can from available claims and note any limitations briefly at the end of the section.\n'
        f'- NEVER output meta-commentary about pipeline limitations, claim gaps, or why a section cannot be written.\n'
        f'- NEVER write sentences like "The claims do not directly address..." or "Constructing this section is not possible...".\n'
        f'- Use the provided claims as evidence and draw connections to the section topic where possible.\n'
        f'- Inline [Source: URL] citations\n'
        f'- Do not invent new facts\n'
        f'- Target word count: {section.get("word_count", 200)}\n'
        f'{style_section}\n'
        f'Output JSON: {{"content": "...", "word_count": 200}}'
    )


def academic_sot_solve_prompt(state, section: dict, claims_json: str) -> str:
    section_heading = section.get("heading", "")
    doc_type = state.writing_state.get("document_type", "paper")
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Document Type: {doc_type.title()}\n'
        f'Topic: {state.problem}\n\n'
        f'Section: {section_heading}\n'
        f'Section purpose: {section.get("purpose", "")}\n\n'
        f'Verified Claims for this section:\n{claims_json}\n\n'
        f'Write this section in formal academic style. Rules:\n'
        f'- Use ONLY the provided claims as evidence\n'
        f'- Third-person voice, formal register\n'
        f'- Inline citations as [Source: URL]\n'
        f'- Hedge where evidence is limited: "suggests", "indicates", "appears to"\n'
        f'- State gaps or limitations explicitly if evidence is thin\n'
        f'- Do not use first-person ("I", "we") unless writing an acknowledgements section\n'
        f'- Target word count: {section.get("word_count", 400)}\n\n'
        f'Output JSON: {{"content": "...", "word_count": 400}}'
    )


WRITING_OUTLINE_SYSTEM = (
    "You are an expert research editor. Create a detailed article outline based on the provided "
    "sources. Each section must map to specific sources. Do NOT write the article yet — only the outline. "
    "Prioritize high-signal sections supported by multiple sources. "
    + JSON_ONLY_FOOTER
)


def writing_outline_prompt(state: PipelineState) -> str:
    sources = state.web_discovery_results[:ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION]
    sources_text = json.dumps(sources, indent=2, ensure_ascii=False) if sources else "No sources available."
    # ── Inject pre-research insights ──
    pre_research = state.writing_state.get("pre_research_summary", "")
    pre_research_block = ""
    if pre_research:
        pre_research_block = (
            f"\nPre-Research Insights (from automated debate/critique/multi-perspective analysis):\n"
            f"{_wrap_external_content(pre_research)}\n"
        )
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Available Sources:\n{_wrap_external_content(sources_text)}'
        f'{pre_research_block}\n'
        f'Create a detailed article outline. For each section, specify:\n'
        f'1. Section title\n'
        f'2. Key points to cover\n'
        f'3. Required sources (by URL) that support this section\n'
        f'4. Estimated word count\n\n'
        f'Incorporate the pre-research insights where relevant to strengthen the outline. '
        f'Use the source set aggressively. Aim to cover at least {ARTICLE_MIN_SOURCE_COUNT} distinct sources across the full outline when available.\n\n'
        f'Output JSON: {{"outline": [{{'
        f'"title": "<section title>", '
        f'"key_points": ["<point>"], '
        f'"source_urls": ["<url>"], '
        f'"word_count": 200'
        f'}}], '
        f'"total_word_count": 1200, '
        f'"suggested_title": "<article title>"}}'
    )


WRITING_DRAFT_SYSTEM = (
    "You are a skilled research writer. Write article sections using ONLY the facts from the provided sources. "
    "Every factual claim MUST have an inline markdown citation [Source Title](URL). "
    "Do NOT invent statistics, quotes, or facts. If a section lacks source support, mark it as [NEEDS SOURCE]. "
    "Separate clearly: FACT (from sources) vs INTERPRETATION (your analysis). "
    "The article must read like a publishable high-end magazine or journal explainer, not a generic blog post. "
    + JSON_ONLY_FOOTER
    + HUMANIZATION_RULES
)


def writing_draft_prompt(state: PipelineState) -> str:
    outline = state.writing_state.get("outline", [])
    sources = state.web_discovery_results[:ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION]
    outline_json = json.dumps(outline, indent=2, ensure_ascii=False) if outline else "[]"
    sources_text = json.dumps(sources, indent=2, ensure_ascii=False) if sources else "No sources available."
    # ── Inject pre-research insights ──
    pre_research = state.writing_state.get("pre_research_summary", "")
    pre_research_block = ""
    if pre_research:
        pre_research_block = (
            f"\nPre-Research Insights (analytical findings from debate/critique/multi-perspective):\n"
            f"{_wrap_external_content(pre_research)}\n"
        )
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Problem: {_wrap_user_input(state.problem)}\n\n'
        f'Article Outline:\n{_wrap_external_content(outline_json)}\n\n'
        f'Sources:\n{_wrap_external_content(sources_text)}'
        f'{pre_research_block}\n'
        f'Write the FULL article following the outline. Rules:\n'
        f'1. Use ONLY facts from the provided sources\n'
        f'2. Every factual claim MUST have inline citation in format [Source Title](URL)\n'
        f'3. Do NOT invent statistics, dates, or quotes\n'
        f'4. Mark unsupported sections with [NEEDS SOURCE]\n'
        f'5. Separate FACT paragraphs from INTERPRETATION paragraphs\n'
        f'6. Include a brief abstract at the start\n'
        f'7. Use as many relevant sources as possible, aiming for at least {ARTICLE_MIN_SOURCE_COUNT} distinct URLs when available\n'
        f'8. End the article with a "Sources" section listing every URL actually cited in the body\n'
        f'9. Incorporate the pre-research insights where relevant — use debate findings to '
        f'strengthen arguments, critique findings to address weaknesses\n\n'
        f'Output JSON: {{"article": "<full article text>", '
        f'"abstract": "<abstract>", '
        f'"word_count": 1200, '
        f'"sections_written": ["<section title>"]}}'
    )


WRITING_FACTCHECK_SYSTEM = (
    "You are a rigorous fact-checker. Review the article against the provided sources. "
    "Flag every claim that cannot be verified by the sources. "
    "Calculate a confidence score for the article. "
    + JSON_ONLY_FOOTER
)


def writing_factcheck_prompt(state: PipelineState) -> str:
    article = state.writing_state.get("article", "")
    sources = state.web_discovery_results[:ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION]
    sources_text = json.dumps(sources, indent=2, ensure_ascii=False) if sources else "[]"
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Article to Review:\n{_wrap_external_content(article)}\n\n'
        f'Sources:\n{_wrap_external_content(sources_text)}\n\n'
        f'Review the article and for EACH paragraph:\n'
        f'1. Verify all factual claims against the sources\n'
        f'2. Flag any claim WITHOUT source support as UNVERIFIED\n'
        f'3. Flag any statistic or quote that cannot be traced to a source\n'
        f'4. Check for contradictions between the article and sources\n'
        f'5. Assign a confidence score (0.0-1.0) per paragraph\n\n'
        f'Output JSON: {{"paragraph_reviews": [{{'
        f'"paragraph_num": 1, '
        f'"claims": ["<claim>"], '
        f'"verified": true, '
        f'"unverified_claims": ["<claim>"], '
        f'"confidence": 0.85, '
        f'"notes": "<reviewer notes>"'
        f'}}], '
        f'"overall_confidence": 0.8, '
        f'"hallucination_risk": "low|medium|high", '
        f'"recommendations": ["<suggested fix>"], '
        f'"needs_rewrite": false}}'
    )


WRITING_ASSEMBLE_SYSTEM = (
    "You are a senior editor. Produce the final polished article incorporating fact-check feedback. "
    "Remove or flag unverified claims. Add a 'Sources' section at the end. "
    "The final output must preserve only actual source links used in the article body. "
    + JSON_ONLY_FOOTER
    + HUMANIZATION_RULES
)

WRITING_HUMANIZE_SYSTEM = (
    "You are an expert writing editor who removes AI-writing patterns to make text sound natural and human. "
    "You follow the WikiProject AI Cleanup methodology: scan for AI tells, then rewrite to eliminate them. "
    "Your two-step process: (1) identify specific AI-pattern instances in the text, "
    "(2) rewrite the full article with those patterns removed.\n\n"
    "AI tells to hunt: significance inflation, promotional language, superficial -ing endings, "
    "vague attributions, em dash overuse, rule of three, AI vocabulary (delve, tapestry, vibrant, "
    "pivotal, testament, underscores, showcases, fosters, interplay, nuanced, groundbreaking, "
    "nestled, breathtaking, endeavor, crucial, vital, leverage as 'use'), copula avoidance "
    "(serves as / stands as / marks / boasts → use is/are/has), negative parallelisms "
    "(not just X; it's Y), generic positive conclusions, excessive hedging, filler phrases, "
    "signposting (let's dive in, here's what you need to know), persuasive authority tropes "
    "(the real question is, at its core, what really matters), fragmented headers, "
    "sycophantic tone, chatbot artifacts (I hope this helps, let me know).\n\n"
    "Preserve all inline citations [Title](URL), factual claims, and document structure. "
    "Keep the same language as the input. "
    "Do NOT add new facts, change citations, or alter meaning. "
    + JSON_ONLY_FOOTER
)


def writing_humanize_prompt(state: PipelineState, article: str) -> str:
    style_brief = state.writing_state.get("style_brief", {})
    style_hint = ""
    if style_brief.get("author") or style_brief.get("publication"):
        author = style_brief.get("author", "")
        publication = style_brief.get("publication", "")
        parts = []
        if author:
            parts.append(f"in the style of {author}")
        if publication:
            parts.append(f"for {publication}")
        if parts:
            style_hint = (
                f"CRITICAL STYLE CONSTRAINT: The article was requested to be written {' '.join(parts)}. "
                f"When rewriting, preserve the distinctive voice, rhythm, and register of that author/publication. "
                f"Do NOT flatten it into generic 'human' prose. "
                f"Remove AI tells while keeping the stylistic fingerprints intact: "
                f"sentence rhythm, vocabulary level, narrative devices, and tonal quirks.\n\n"
            )
    return (
        f'{get_language_instruction(state)}\n\n'
        f'{style_hint}'
        f'Article to humanize:\n{_wrap_external_content(article)}\n\n'
        f'Step 1 — Audit: List every specific AI-writing tell you find. '
        f'Be concrete: quote the phrase or pattern, not just the category.\n\n'
        f'Step 2 — Rewrite: Produce the full humanized article. Rules:\n'
        f'- Eliminate every tell you identified\n'
        f'- Keep all inline citations [Title](URL) exactly as-is\n'
        f'- Keep all headings, section structure, and factual content\n'
        f'- Keep the same language as the input\n'
        f'- Vary sentence length: mix short punchy sentences with longer ones\n'
        f'- Use direct simple language; prefer is/are/has over elaborate substitutes\n'
        f'- Have a point of view where the evidence supports one\n'
        f"- If a specific author/publication style was requested above, preserve that style's voice\n\n"
        f'Output JSON: {{"ai_tells": ["<specific quoted pattern>", ...], '
        f'"humanized_article": "<full rewritten article>"}}'
    )


def writing_assemble_prompt(state: PipelineState) -> str:
    article = state.writing_state.get("article", "")
    reviews = state.writing_state.get("factcheck_reviews", [])
    reviews_json = json.dumps(reviews, indent=2, ensure_ascii=False) if reviews else "[]"
    sources = state.web_discovery_results[:ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION]
    sources_text = json.dumps(sources, indent=2, ensure_ascii=False) if sources else "[]"
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Original Article:\n{_wrap_external_content(article)}\n\n'
        f'Fact-Check Reviews:\n{_wrap_external_content(reviews_json)}\n\n'
        f'Sources:\n{_wrap_external_content(sources_text)}\n\n'
        f'Produce the FINAL article. Instructions:\n'
        f'1. Remove all claims flagged as UNVERIFIED\n'
        f'2. Add caveats for claims with insufficient evidence\n'
        f'3. Keep all inline citations in format [Source Title](URL)\n'
        f'4. Add a "Sources" section at the end listing all cited URLs and only cited URLs\n'
        f'5. Add a "Confidence Notice" paragraph noting overall reliability\n'
        f'6. Include the abstract at the top\n'
        f'7. If fewer than {ARTICLE_MIN_SOURCE_COUNT} sources are available, be explicit about the evidence limit\n\n'
        f'Output JSON: {{"final_article": "<full final article>", '
        f'"abstract": "<abstract>", '
        f'"changes_made": ["<change description>"], '
        f'"sources_cited": ["<url>"], '
        f'"confidence_notice": "<notice text>", '
        f'"word_count": 1200}}'
    )
