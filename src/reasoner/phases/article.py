from __future__ import annotations

import json

from reasoner.domain.pipeline_state import PipelineState
from reasoner.core.constants import ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION, JSON_ONLY_FOOTER, TRUNCATION
from reasoner.phases._shared import get_language_instruction, _wrap_user_input, _wrap_external_content

# ── Retrieval Planning ────────────────────────────────────────────────────────

ARTICLE_RETRIEVAL_PLAN_SYSTEM = (
    "You are an expert research librarian. Your job is to produce targeted search queries "
    "that will surface the most authoritative, recent, and specific sources for a given topic. "
    "Avoid generic queries. Prefer precise, entity-specific phrasing. "
    + JSON_ONLY_FOOTER
)

ARTICLE_RETRIEVAL_SONAR_SYSTEM = (
    "You are an expert research librarian with live web search capability. "
    "Research the topic thoroughly using your web search. For every claim or source "
    "you reference, provide an inline citation as [Source Title](URL). "
    "Cover multiple angles: technical details, expert opinion, historical context, "
    "and recent developments. Return the researched information as natural prose "
    "with citations inline — do NOT output JSON."
)


def article_retrieval_plan_prompt(state: PipelineState) -> str:
    base = (
        f"{get_language_instruction(state)}\n\n"
        f"Research Topic: {_wrap_user_input(state.problem)}\n\n"
        f"Generate 3-5 distinct search queries to find the most useful sources. "
        f"Each query should target a different facet of the topic (e.g. technical details, "
        f"expert reactions, historical context, recent developments, critical perspectives)."
    )
    # ── Inject pre-research insights from augmentation methods ──
    pre_research = state.writing_state.get("pre_research_summary", "")
    if pre_research:
        base += (
            f"\n\n=== PRE-RESEARCH INSIGHTS (from automated debate/critique/multi-perspective analysis) ===\n"
            f"{pre_research}\n"
            f"=== END PRE-RESEARCH ===\n\n"
            f"Use these insights to refine your search queries — target specific claims, "
            f"counterarguments, and perspectives identified above."
        )
    base += f'\n\nOutput JSON: {{"queries": ["<query 1>", "<query 2>", "<query 3>"]}}'
    return base


# ── Drafting ─────────────────────────────────────────────────────────────────

ARTICLE_DRAFT_SYSTEM = (
    "You are a senior journalist and long-form writer. Your articles are published in top-tier "
    "magazines and journals. You write with narrative depth, intellectual rigour, and a clear "
    "point of view. Every factual claim is grounded in the provided sources. "
    "When a specific author or publication style is requested, honour it precisely: "
    "replicate their sentence rhythm, vocabulary register, narrative devices, and argumentative structure. "
    "Write for a sophisticated general audience — no jargon without explanation, "
    "no unverified statistics, no invented quotes. "
    "Output the full article as a single prose document. Do NOT use JSON for the article body."
)


def article_draft_prompt(state: PipelineState) -> str:
    sources = state.writing_state.get("retrieved_sources", [])
    sources_truncated = sources[:ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION]
    sources_text = (
        json.dumps(sources_truncated, indent=2, ensure_ascii=False)
        if sources_truncated
        else "No sources retrieved — write from general knowledge and clearly mark any factual claims as [UNVERIFIED]."
    )
    style_brief = state.writing_state.get("style_brief", {})
    style_block = ""
    if isinstance(style_brief, dict) and (style_brief.get("author") or style_brief.get("publication")):
        author = style_brief.get("author", "")
        pub = style_brief.get("publication", "")
        parts = []
        if author:
            parts.append(f"in the style of {author}")
        if pub:
            parts.append(f"as published in {pub}")
        style_block = (
            f"STYLE REQUIREMENT: Write {', '.join(parts)}. "
            f"Closely emulate the voice, narrative structure, anecdote-driven openings, "
            f"counterintuitive insights, and rhetorical rhythm of that author/publication.\n\n"
        )
    def _safe_join_list(value) -> str:
        """Safely join a list value — handles None, int, bool, string gracefully."""
        if not isinstance(value, (list, tuple)):
            return str(value) if value else ""
        return ', '.join(str(v) for v in value)

    argument_map = state.writing_state.get("argument_map", {})
    argument_block = ""
    if isinstance(argument_map, dict) and argument_map.get("central_question"):
        argument_block = (
            f"Argument Blueprint (write within this structure):\n"
            f"  Central question: {argument_map.get('central_question', '')}\n"
            f"  Problem: {argument_map.get('problem', '')}\n"
            f"  Current explanations: {_safe_join_list(argument_map.get('current_explanations', []))}\n"
            f"  Limitations: {_safe_join_list(argument_map.get('limitations', []))}\n"
            f"  New insight: {argument_map.get('new_insight', '')}\n"
            f"  Counterarguments to address: {_safe_join_list(argument_map.get('counterarguments', []))}\n"
            f"  Implications: {_safe_join_list(argument_map.get('implications', []))}\n\n"
        )

    # ── Inject pre-research insights ──
    pre_research = state.writing_state.get("pre_research_summary", "")
    pre_research_block = ""
    if pre_research:
        pre_research_block = (
            f"\nPre-Research Insights (analytical findings from debate/critique/multi-perspective):\n"
            f"{_wrap_external_content(pre_research)}\n"
        )

    return (
        f"{get_language_instruction(state)}\n\n"
        f"{style_block}"
        f"{argument_block}"
        f"Assignment: {_wrap_user_input(state.problem[:TRUNCATION.PROMPT])}\n\n"
        f"Sources (use these as your evidence base):\n"
        f"{_wrap_external_content(sources_text)}"
        f"{pre_research_block}\n"
        f"Write a complete, publication-ready article. Requirements:\n"
        f"- Open with a specific anecdote, scene, or surprising fact — not a generic statement\n"
        f"- Incorporate the pre-research insights where relevant — use debate findings to "
        f"strengthen your argument, critique findings to address weaknesses proactively, "
        f"and multi-perspective findings to show intellectual range\n"
        f"- Cite sources inline as [Source Title](URL) whenever you draw on them\n"
        f"- Mark any claim without a source as [UNVERIFIED]\n"
        f"- Close with a forward-looking or thought-provoking conclusion\n"
        f"- Target 800-1200 words\n"
        f"- End with a ## Sources section listing every URL actually cited in the body"
    )


# ── Adversarial Verification ──────────────────────────────────────────────────

ARTICLE_VERIFY_SYSTEM = (
    "You are a rigorous fact-checker at a top publication. Your job is to identify every "
    "factual claim in the article draft that cannot be directly supported by the provided sources. "
    "Be adversarial: assume the author may have hallucinated statistics, misattributed quotes, "
    "or overgeneralised from limited evidence. "
    "Calculate a claim-support ratio (supported / total verifiable claims). "
    + JSON_ONLY_FOOTER
)

ARTICLE_VERIFY_SYSTEM_SONAR = (
    "You are a rigorous fact-checker at a top publication with live web search capability. "
    "Your job is to independently verify every factual claim in the article draft. "
    "Use your web search to check each claim against current, authoritative sources. "
    "Be adversarial: assume the author may have hallucinated statistics, misattributed quotes, "
    "or overgeneralised from limited evidence. "
    "Mark claims as 'supported' only when you can confirm them via live search, not just when "
    "they appear plausible or align with the provided sources alone. "
    "Calculate a claim-support ratio (supported / total verifiable claims). "
    + JSON_ONLY_FOOTER
)


def article_verify_prompt(state: PipelineState, use_sonar: bool = False) -> str:
    article = state.writing_state.get("final_article", "")
    sources = state.writing_state.get("retrieved_sources", [])
    sources_truncated = sources[:ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION]

    if use_sonar:
        # Sonar searches live — skip pre-retrieved sources to save tokens
        sources_block = ""
    else:
        sources_text = (
            json.dumps(sources_truncated, indent=2, ensure_ascii=False)
            if sources_truncated
            else "[]"
        )
        sources_block = f"Available Sources:\n{_wrap_external_content(sources_text)}\n\n"

    return (
        f"{get_language_instruction(state)}\n\n"
        f"Article Draft:\n{_wrap_external_content(article)}\n\n"
        f"{sources_block}"
        f"Review EVERY factual claim in the article. For each one, determine whether "
        f"it is directly supported by the sources provided.\n\n"
        f'Output JSON: {{"verified_claims": [{{'
        f'"claim": "<exact quote from article>", '
        f'"verdict": "supported|unsupported|partially_supported", '
        f'"source_url": "<url or null>", '
        f'"note": "<brief reason>"'
        f'}}], '
        f'"metrics": {{"total_claims": 0, "supported": 0, "unsupported": 0, "claim_support_ratio": 0.0}}, '
        f'"gaps": ["<topic needing more evidence>"], '
        f'"high_risk_sentences": ["<sentence with unverifiable claim>"], '
        f'"claim_ledger": [{{'
        f'"claim": "<exact claim from article>", '
        f'"source": "<supporting source URL or null>", '
        f'"status": "verified|supported|speculative|unsupported"'
        f'}}]}}'
    )


# ── Argument Map / Outline ────────────────────────────────────────────────────

ARTICLE_OUTLINE_SYSTEM = (
    "You are an argument architect and editorial strategist. Your job is to construct the "
    "logical blueprint for a publication-quality article — NOT to write prose.\n\n"
    "Build a structured argument map that answers these questions:\n"
    "1. What is the central question this article addresses?\n"
    "2. What is the problem or tension that makes the question worth answering?\n"
    "3. What are the current explanations or prevailing views on this topic?\n"
    "4. What are their limitations — what do they miss or get wrong?\n"
    "5. What new insight does this article contribute?\n"
    "6. What evidence supports this insight, and from which sources?\n"
    "7. What are the strongest counterarguments, and how does the article address them?\n"
    "8. What are the implications of this insight — what follows?\n"
    "9. What conclusion ties everything together?\n\n"
    "Each section should specify which sources from the evidence base support it. "
    "The output is a JSON blueprint — no prose, no section content, just structure. "
    + JSON_ONLY_FOOTER
)


def article_outline_prompt(state: PipelineState) -> str:
    sources = state.writing_state.get("retrieved_sources", [])
    sources_truncated = sources[:ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION]
    sources_text = (
        json.dumps(sources_truncated, indent=2, ensure_ascii=False)
        if sources_truncated
        else "[]"
    )
    style_brief = state.writing_state.get("style_brief", {})
    style_block = ""
    if isinstance(style_brief, dict) and (style_brief.get("publication")):
        pub = style_brief.get("publication", "")
        style_block = f"\nTarget publication: {pub}\n"

    # ── Inject pre-research insights ──
    pre_research = state.writing_state.get("pre_research_summary", "")
    pre_research_block = ""
    if pre_research:
        pre_research_block = (
            f"\nPre-Research Insights (from automated debate/critique/multi-perspective analysis):\n"
            f"{_wrap_external_content(pre_research)}\n"
        )

    return (
        f"{get_language_instruction(state)}\n\n"
        f"Topic: {_wrap_user_input(state.problem[:TRUNCATION.PROMPT])}{style_block}\n\n"
        f"Available Sources:\n{_wrap_external_content(sources_text)}"
        f"{pre_research_block}\n"
        f"Construct an argument blueprint. Incorporate the pre-research insights where "
        f"relevant to strengthen the argument map (e.g., use debate findings for "
        f"counterarguments, critique findings for limitations, perspective findings for "
        f"current_explanations). Output JSON with this exact structure:\n"
        f"{{\n"
        f'  "suggested_title": "<article title>",\n'
        f'  "argument_map": {{\n'
        f'    "central_question": "<the core question>",\n'
        f'    "problem": "<why this matters now>",\n'
        f'    "current_explanations": ["<prevailing view 1>", "<prevailing view 2>"],\n'
        f'    "limitations": ["<what current views miss>"],\n'
        f'    "new_insight": "<what this article adds that is genuinely new>",\n'
        f'    "evidence_sources": ["<source_url>", "<source_url>"],\n'
        f'    "counterarguments": ["<strongest objection 1>", "<strongest objection 2>"],\n'
        f'    "implications": ["<what follows from this insight>"],\n'
        f'    "conclusion_type": "call_to_action|forward_looking|synthesis"\n'
        f"  }},\n"
        f'  "outline": [{{\n'
        f'    "section_title": "<heading>",\n'
        f'    "key_points": ["<point 1>", "<point 2>"],\n'
        f'    "sources_used": ["<url>"],\n'
        f'    "estimated_words": 250\n'
        f"  }}],\n"
        f'  "total_word_count": 1200\n'
        f"}}"
    )


# ── Structural Adversarial Review ─────────────────────────────────────────────

ARTICLE_CRITIC_SYSTEM = (
    "You are a merciless editorial devil's advocate. Your job is NOT to correct grammar "
    "or check facts — that work has already been done. Your job is to find the structural "
    "weaknesses that make a piece merely polished rather than genuinely rigorous.\n\n"
    "Ask every question a skeptical domain expert would ask:\n"
    "- Which claims lack evidence, not just in citation count but in quality of support?\n"
    "- What assumptions does the article make without stating them?\n"
    "- How would a domain expert challenge the central thesis?\n"
    "- Which obvious counterarguments have been ignored or given short shrift?\n"
    "- Where does the argument rely on speculative leaps or unstated premises?\n"
    "- What could a reasonable reader misunderstand?\n"
    "- Are any terms used in non-standard ways without definition?\n\n"
    "Be specific. Point to exact sections and sentences. "
    "Do NOT soften your critique — the author needs real feedback, not encouragement. "
    + JSON_ONLY_FOOTER
)


def article_critic_prompt(state: PipelineState) -> str:
    draft = state.writing_state.get("final_article", "")
    argument_map = state.writing_state.get("argument_map", {})
    verification = state.writing_state.get("verification", {})

    map_block = (
        f"Original Argument Blueprint (verify the draft follows this structure):\n"
        f"{json.dumps(argument_map, indent=2, ensure_ascii=False)}\n\n"
        if argument_map else ""
    )
    fact_block = (
        f"Fact-check findings (note which claims are already flagged):\n"
        f"{json.dumps(verification, indent=2, ensure_ascii=False)[:2000]}\n\n"
        if verification else ""
    )

    return (
        f"{get_language_instruction(state)}\n\n"
        f"Article Draft:\n{_wrap_external_content(draft)}\n\n"
        f"{map_block}"
        f"{fact_block}"
        f"Perform a structural adversarial review. Focus on logic, assumptions, "
        f"counterarguments, and completeness — NOT facts or grammar.\n\n"
        f'Output JSON: {{"implicit_assumptions": [{{'
        f'"assumption": "<stated>", "section": "<section name>", "risk": "high|medium|low"'
        f'}}], '
        f'"ignored_counterarguments": [{{'
        f'"argument": "<the counterargument>", "relevance": "high|medium|low"'
        f'}}], '
        f'"logical_gaps": [{{'
        f'"gap": "<description>", "section": "<section name>", "severity": "high|medium|low"'
        f'}}], '
        f'"speculative_leaps": ["<sentence that goes beyond evidence>"], '
        f'"misunderstanding_risks": ["<sentence a reader could misinterpret>"], '
        f'"overall_rigor_score": 0.0}}'
    )


# ── Developmental Editing ─────────────────────────────────────────────────────

ARTICLE_DEVELOPMENTAL_EDIT_SYSTEM = (
    "You are a senior developmental editor at a top publication. Your job is to fix the "
    "article's substance — argument, structure, evidence, and narrative flow — while "
    "preserving the author's voice and intent.\n\n"
    "Address, in order:\n"
    "1. ARGUMENT: Fix logical gaps identified by the structural reviewer. Shore up weak "
    "   reasoning. Address ignored counterarguments by adding qualifying text.\n"
    "2. EVIDENCE: Strengthen weak claims using the available sources. Remove any claim "
    "   that cannot be supported by the evidence base.\n"
    "3. NARRATIVE FLOW: Smooth transitions between sections. Remove redundancies. "
    "   Ensure each paragraph advances the thesis.\n"
    "4. ACCURACY: Correct any technical inaccuracies (but do NOT invent new facts).\n\n"
    "You may restructure paragraphs and add qualifying language. "
    "Do NOT change the author's voice, sentence rhythm, or vocabulary register — "
    "the style edit pass handles that. "
    "Output the full revised article as a single prose document. Do NOT use JSON."
)


def article_developmental_edit_prompt(state: PipelineState) -> str:
    draft = state.writing_state.get("final_article", "")
    critique = state.writing_state.get("structural_critique", {})
    argument_map = state.writing_state.get("argument_map", {})

    def _safe_iter(items):
        """Safely iterate critique items — handles non-list values."""
        if not isinstance(items, (list, tuple)):
            return []
        return items[:5]

    critique_block = ""
    if critique.get("logical_gaps") or critique.get("ignored_counterarguments"):
        critique_block = "Structural feedback to address:\n"
        for gap in _safe_iter(critique.get("logical_gaps")):
            if isinstance(gap, dict):
                sev = str(gap.get('severity', 'medium')).upper()
                g = gap.get('gap', str(gap))
                sec = gap.get('section', '?')
                critique_block += f"  - [{sev}] {g} (section: {sec})\n"
        for carg in _safe_iter(critique.get("ignored_counterarguments")):
            if isinstance(carg, dict):
                rel = str(carg.get('relevance', 'medium')).upper()
                arg = carg.get('argument', str(carg))
                critique_block += f"  - [{rel}] {arg}\n"
        for ass in _safe_iter(critique.get("implicit_assumptions")):
            if isinstance(ass, dict):
                risk = str(ass.get('risk', 'medium')).upper()
                a = ass.get('assumption', str(ass))
                sec = ass.get('section', '?')
                critique_block += f"  - [{risk}] {a} (section: {sec})\n"
        if critique_block != "Structural feedback to address:\n":
            critique_block += "\n"

    map_block = (
        f"Original argument blueprint (maintain this structure):\n"
        f"{json.dumps(argument_map, indent=2, ensure_ascii=False)[:1500]}\n\n"
        if argument_map else ""
    )

    return (
        f"{get_language_instruction(state)}\n\n"
        f"{critique_block}"
        f"{map_block}"
        f"Article Draft:\n{_wrap_external_content(draft)}\n\n"
        f"Revise this draft. Fix argument gaps, shore up weak evidence, "
        f"smooth narrative flow. Preserve the author's voice. "
        f"Output the full revised article as a single prose document."
    )


# ── Style Editing ─────────────────────────────────────────────────────────────

ARTICLE_STYLE_EDIT_SYSTEM = (
    "You are a style editor who makes good writing read like it was written by a human, "
    "not generated by an AI. Your focus is readability, rhythm, and voice — NOT facts or structure.\n\n"
    "Refine without rewriting from scratch:\n"
    "- Vary sentence length and structure to create natural rhythm\n"
    "- Replace generic or hedging phrases with direct, confident language\n"
    "- Adjust vocabulary register to match the target publication\n"
    "- Break up long or monotonous paragraphs\n"
    "- Preserve the author's original voice and argumentative intent\n"
    "- Do NOT add new facts, remove citations, or restructure sections\n\n"
    "Output the full stylistically refined article as a single prose document. Do NOT use JSON."
)


def article_style_edit_prompt(state: PipelineState) -> str:
    draft = state.writing_state.get("final_article", "")
    publication_style = ""
    style_brief = state.writing_state.get("style_brief", {})
    if isinstance(style_brief, dict) and style_brief.get("publication"):
        publication_style = (
            f"\nTarget publication: {style_brief['publication']}.\n"
            f"Match their typical sentence length, paragraph structure, technical depth, "
            f"and use of quotations.\n"
        )

    return (
        f"{get_language_instruction(state)}\n\n"
        f"Article Draft:\n{_wrap_external_content(draft)}\n"
        f"{publication_style}\n"
        f"Refine the style of this article. Make it read like a human wrote it. "
        f"Preserve all facts, citations, and structural organization. "
        f"Output the full stylistically refined article as a single prose document."
    )


# ── Copy Editing ──────────────────────────────────────────────────────────────

ARTICLE_COPY_EDIT_SYSTEM = (
    "You are a meticulous copy editor. Your job is mechanical precision — NOT substance or style.\n\n"
    "Check and correct:\n"
    "- Grammar, punctuation, and spelling errors\n"
    "- Inconsistent terminology or formatting\n"
    "- Citation format consistency (all [Title](URL) format)\n"
    "- Missing or malformed ## Sources section\n"
    "- Run-on sentences and comma splices\n"
    "- Subject-verb agreement and tense consistency\n\n"
    "Do NOT change sentence structure, word choice, or factual content. "
    "Do NOT add or remove arguments. "
    "Output the full copy-edited article as a single prose document. Do NOT use JSON."
)


def article_copy_edit_prompt(state: PipelineState) -> str:
    draft = state.writing_state.get("final_article", "")
    return (
        f"{get_language_instruction(state)}\n\n"
        f"Article Draft:\n{_wrap_external_content(draft)}\n\n"
        f"Copy edit this article for grammar, consistency, and formatting. "
        f"Preserve every fact, source citation, and structural choice. "
        f"Output the full corrected article as a single prose document."
    )


# ── Final Editorial Audit ─────────────────────────────────────────────────────

ARTICLE_FINAL_AUDIT_SYSTEM = (
    "You are a senior editorial director performing a pre-publication audit. "
    "Your job is a structured checklist evaluation of the final article.\n\n"
    "Score each dimension 0.0-1.0:\n"
    "- THESIS ADVANCEMENT: Does every paragraph advance the central thesis?\n"
    "- CLAIM SUPPORT: Are all significant claims supported by evidence?\n"
    "- INTERNAL CONSISTENCY: Is the reasoning logically consistent throughout?\n"
    "- TRANSITION QUALITY: Are transitions between sections smooth and logical?\n"
    "- REDUNDANCY: Has all redundant material been removed?\n"
    "- CITATION ACCURACY: Are all citations correctly formatted and present in ## Sources?\n"
    "- POLICY COMPLIANCE: Does the article comply with AI-use disclosure requirements?\n\n"
    "If any score is below 0.6, the article needs another revision pass. "
    "Be honest — this is the last gate before publication. "
    + JSON_ONLY_FOOTER
)


def article_final_audit_prompt(state: PipelineState) -> str:
    draft = state.writing_state.get("final_article", "")
    argument_map = state.writing_state.get("argument_map", {})

    map_block = (
        f"Expected thesis (from argument blueprint):\n"
        f"{json.dumps(argument_map, indent=2, ensure_ascii=False)[:1000]}\n\n"
        if argument_map else ""
    )

    return (
        f"{get_language_instruction(state)}\n\n"
        f"Final Article:\n{_wrap_external_content(draft)}\n\n"
        f"{map_block}"
        f"Audit this article for publication readiness.\n\n"
        f'Output JSON: {{\n'
        f'  "audit": {{'
        f'"thesis_advancement": 0.0, '
        f'"claim_support": 0.0, '
        f'"internal_consistency": 0.0, '
        f'"transition_quality": 0.0, '
        f'"redundancy_removed": 0.0, '
        f'"citation_accuracy": 0.0, '
        f'"policy_compliance": 0.0'
        f'}}, '
        f'"issues": [{{'
        f'"section": "<section name>", '
        f'"severity": "high|medium|low", '
        f'"description": "<what needs fixing>", '
        f'"fix_suggestion": "<specific suggestion>"'
        f'}}], '
        f'"audit_score": 0.0, '
        f'"passes_audit": true'
        f'}}'
    )
