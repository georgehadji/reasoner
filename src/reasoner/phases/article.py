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


def article_retrieval_plan_prompt(state: PipelineState) -> str:
    return (
        f"{get_language_instruction(state)}\n\n"
        f"Research Topic: {_wrap_user_input(state.problem)}\n\n"
        f"Generate 3-5 distinct search queries to find the most useful sources. "
        f"Each query should target a different facet of the topic (e.g. technical details, "
        f"expert reactions, historical context, recent developments, critical perspectives).\n\n"
        f'Output JSON: {{"queries": ["<query 1>", "<query 2>", "<query 3>"]}}'
    )


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
    return (
        f"{get_language_instruction(state)}\n\n"
        f"{style_block}"
        f"Assignment: {_wrap_user_input(state.problem[:TRUNCATION.PROMPT])}\n\n"
        f"Sources (use these as your evidence base):\n"
        f"{_wrap_external_content(sources_text)}\n\n"
        f"Write a complete, publication-ready article. Requirements:\n"
        f"- Open with a specific anecdote, scene, or surprising fact — not a generic statement\n"
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


def article_verify_prompt(state: PipelineState) -> str:
    article = state.writing_state.get("final_article", "")
    sources = state.writing_state.get("retrieved_sources", [])
    sources_truncated = sources[:ARTICLE_MAX_SOURCES_FOR_CLAIM_EXTRACTION]
    sources_text = (
        json.dumps(sources_truncated, indent=2, ensure_ascii=False)
        if sources_truncated
        else "[]"
    )
    return (
        f"{get_language_instruction(state)}\n\n"
        f"Article Draft:\n{_wrap_external_content(article)}\n\n"
        f"Available Sources:\n{_wrap_external_content(sources_text)}\n\n"
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
        f'"high_risk_sentences": ["<sentence with unverifiable claim>"]}}'
    )


# ── Refinement ────────────────────────────────────────────────────────────────

ARTICLE_REFINE_SYSTEM = (
    "You are a senior editor refining a draft article based on fact-check feedback. "
    "Your goal is to produce the cleanest, most accurate, most publishable version. "
    "Remove or caveat every unsupported claim. Strengthen the narrative where evidence allows. "
    "Preserve the author's voice and style intent. "
    "Do NOT invent new facts. Do NOT change inline citations. "
    "Output the full refined article as a single prose document — do not use JSON."
)


def article_refine_prompt(state: PipelineState) -> str:
    draft = state.writing_state.get("final_article", "")
    verification = state.writing_state.get("verification", {})
    gaps = verification.get("gaps", [])
    high_risk = verification.get("high_risk_sentences", [])
    metrics = state.writing_state.get("metrics", {})
    support_ratio = metrics.get("claim_support_ratio", 1.0)

    issues_block = ""
    if high_risk:
        issues_block += "Sentences to fix or remove:\n" + "\n".join(f"  - {s}" for s in high_risk[:10]) + "\n\n"
    if gaps:
        issues_block += "Evidence gaps (add caveats or remove):\n" + "\n".join(f"  - {g}" for g in gaps[:5]) + "\n\n"

    quality_note = (
        f"Claim support ratio from fact-check: {support_ratio:.0%}. "
        + ("The draft needs significant tightening." if support_ratio < 0.6 else "Minor fixes needed.")
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
            parts.append(f"for {pub}")
        style_block = (
            f"PRESERVE STYLE: This article was written {', '.join(parts)}. "
            f"When removing unsupported claims, rewrite the surrounding prose to "
            f"maintain that distinctive voice — do not flatten it into generic language.\n\n"
        )

    return (
        f"{get_language_instruction(state)}\n\n"
        f"{style_block}"
        f"{quality_note}\n\n"
        f"{issues_block}"
        f"Draft Article:\n{_wrap_external_content(draft)}\n\n"
        f"Produce the final, publication-ready version. Rules:\n"
        f"- Remove or caveat all high-risk / unsupported sentences listed above\n"
        f"- Keep all properly sourced claims and inline citations\n"
        f"- Maintain narrative flow — patch any gaps left by removed claims\n"
        f"- End with a ## Sources section listing every URL cited in the body\n"
        f"- Do NOT add new factual claims not present in the draft"
    )
