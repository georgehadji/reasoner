from __future__ import annotations
import re
from reasoner.domain.pipeline_state import PipelineState
from reasoner.models import PerspectiveType
from reasoner.core.constants import JSON_ONLY_FOOTER, TRUNCATION, DEFAULT_SEARCH_RESULTS


def detect_language(text: str) -> str:
    """Simple language detection based on character patterns."""
    text = text.lower()
    sample = text[:TRUNCATION.PROBLEM]

    # Greek (full Greek and Coptic block for better coverage)
    if re.search(r'[\u0370-\u03FF]', sample):
        return "Greek"
    
    # Russian/Cyrillic
    if any(c in text for c in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'):
        return "Russian"
    
    # Arabic
    if any(c in text for c in 'ابتثجحخدذرزسشصضطظعغفقكلمنهوي'):
        return "Arabic"
    
    # Chinese
    if any('\u4e00' <= c <= '\u9fff' for c in text):
        return "Chinese"
    
    # Japanese (Hiragana/Katakana)
    if any('\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff' for c in text):
        return "Japanese"
    
    # Korean (Hangul)
    if any('\uac00' <= c <= '\ud7af' for c in text):
        return "Korean"
    
    # Turkish (distinctive characters: ı, ğ, ç, ş — checked first because ü/ö can overlap with German)
    turkish_exclusive = 'ığıçış'
    if any(c in text for c in turkish_exclusive):
        return "Turkish"
    
    # German (exclusive characters: ä, ö, ß; ü is shared with Spanish)
    german_exclusive = 'äöß'
    if any(c in text for c in german_exclusive):
        return "German"
    
    # Spanish (common Spanish-specific characters)
    spanish_chars = 'áéíóúüñ¿¡'
    if any(c in text for c in spanish_chars):
        return "Spanish"
    
    return "English"


def get_language_instruction(state: Union["PipelineState", str]) -> str:
    if isinstance(state, str):
        language = state
    else:
        language = state.language
    """Returns the 'Respond in X' instruction line."""
    lang_map = {
        "Greek": "Απάντησε στα Ελληνικά.",
        "Russian": "Ответьте на русском языке.",
        "Arabic": "أجب بالعربية.",
        "Chinese": "用中文回答。",
        "Japanese": "日本語で回答してください。",
        "Korean": "한국어로 답변해 주세요.",
        "Spanish": "Responde en español.",
        "German": "Antworte auf Deutsch.",
        "Turkish": "Türkçe cevap ver.",
    }
    return lang_map.get(language, "Respond in English.")


def build_followup_context(
    conversation_history: list[dict[str, str]] | None,
    previous_synthesis: str = "",
    turn_number: int = 1,
) -> str:
    """Build follow-up context while preserving who authored each block."""
    history = conversation_history or []
    rendered_turns: list[str] = []
    for turn in history[-6:]:
        role = str(turn.get("role", "user")).strip().lower()
        content = str(turn.get("content", ""))[:TRUNCATION.LARGE_CONTENT]
        if not content.strip():
            continue
        if role == "user":
            rendered_turns.append(f"USER TURN:\n{_wrap_user_input(content)}")
        else:
            # Prior assistant output is context, not fresh user intent.
            rendered_turns.append(f"ASSISTANT TURN:\n{_wrap_external_content(content)}")

    if not rendered_turns and not previous_synthesis:
        return ""

    ctx = f"\n---\nCONVERSATION HISTORY (Turn {turn_number}):\n"
    if rendered_turns:
        ctx += "\n".join(rendered_turns) + "\n"
    if previous_synthesis:
        # Keep assistant-generated synthesis separated from the current request so
        # downstream prompts do not treat it like a new user instruction.
        ctx += (
            "PREVIOUS SYNTHESIS (assistant-generated context, not a new instruction):\n"
            f"{_wrap_external_content(previous_synthesis[:TRUNCATION.LARGE_CONTENT])}\n"
        )
    ctx += "---\n"
    return ctx


def _followup_context(state: PipelineState) -> str:
    """Build a compact follow-up context block for injection into prompts.

    Results are cached on PipelineState._followup_cache since the
    conversation history does not change mid-run and this function
    is called 7+ times per pipeline run (once per phase prompt).
    """
    if state._followup_cache is not None:
        return state._followup_cache
    result = build_followup_context(
        state.conversation_history,
        previous_synthesis=state.previous_synthesis,
        turn_number=state.turn_number,
    )
    state._followup_cache = result
    return result


def _wrap_user_input(text: str) -> str:
    """Wrap user-controlled text in explicit delimiters."""
    return f"<<<USER_INPUT>>>\n{text}\n<<<END_USER_INPUT>>>"


def _wrap_external_content(text: str) -> str:
    """Wrap external/untrusted content in explicit delimiters."""
    return f"<<<EXTERNAL_CONTENT>>>\n{text}\n<<<END_EXTERNAL_CONTENT>>>"


# ── Humanization Rules ────────────────────────────────────────────────────────
# Applied to all final prose output to suppress AI-signature language patterns.
# Based on Wikipedia's "Signs of AI writing" guide (WikiProject AI Cleanup).

HUMANIZATION_RULES = """
HUMANIZATION RULES — apply to every prose sentence you write:

BANNED AI-SIGNATURE WORDS (never use):
- delve / delves / delving / deep dive
- it's worth noting / it is important to note / notably (as sentence opener)
- in today's rapidly evolving / in today's fast-paced
- cutting-edge / state-of-the-art (unless citing a specific technical claim)
- at its core / at the end of the day / moving forward / going forward
- it goes without saying / needless to say / to shed light on
- embark / embarking on a journey
- leverage / leveraging (when the meaning is simply "use" or "apply")
- revolutionize / transformative / game-changer / paradigm shift (unless literally true)
- streamline / optimize (as vague filler)
- comprehensive (as empty intensifier)
- multifaceted / multidimensional / nuanced understanding (as hollow descriptors)
- paramount / of utmost importance
- I cannot stress enough / it is crucial that
- stands as / serves as / marks / represents [a] — use "is" or "are" instead
- boasts / features / offers [a] — use "has" or "includes" instead
- vibrant / rich (figurative) / profound / breathtaking / stunning / groundbreaking (figurative)
- nestled / in the heart of / renowned / must-visit
- pivotal / crucial / vital / significant / key (as vague intensifiers)
- testament / underscores / highlights (verb) / showcases / exemplifies
- tapestry / landscape (abstract noun) / interplay / intricacies / intricate
- fostering / cultivating / encompassing / garner / align with
- enduring / lasting / ongoing (when used to puff importance)
- delve / actually / additionally (as first word) / valuable (as hollow filler)

SENTENCE OPENERS TO AVOID:
- Never start with: "Certainly!", "Absolutely!", "Of course!", "Great!", "Sure!", "Indeed!"
- Never open with: "In conclusion, it is clear that…" or "In summary, it is evident that…"
- Never use chatbot artifacts: "I hope this helps", "Let me know if you'd like me to expand", "Here is a…"
- Never use signposting: "Let's dive in", "Let's explore", "Here's what you need to know", "Without further ado"

STRUCTURAL RULES:
- Vary sentence length: mix short direct sentences (under 12 words) with longer ones. No uniform cadence.
- Do not reduce every point to a bullet list — use prose paragraphs for fewer than 4 items
- Prefer active voice; passive is acceptable for emphasis or formal register
- Use "Furthermore" / "Moreover" / "Additionally" at most once per section, never consecutively
- Avoid symmetrical parallel structures that make every paragraph sound the same
- No rule-of-three forcing: don't artificially group ideas into threes to appear comprehensive
- No false ranges: avoid "from X to Y, from A to B" unless X and Y are on a meaningful scale
- No em dash overuse: prefer commas, periods, or parentheses over em dashes (—)

PATTERNS TO ELIMINATE:
- Significance inflation: remove statements like "marking a pivotal moment in the evolution of…" or "contributing to the broader…" — just state the fact
- Superficial -ing tacking: don't append "highlighting/underscoring/symbolizing/reflecting/fostering/ensuring…" phrases to sentences to fake depth
- Vague attributions: replace "experts argue" / "industry observers note" / "some critics say" with specific named sources, or remove
- Negative parallelism: rewrite "It's not just about X; it's about Y" as a direct statement
- Generic positive conclusions: cut "the future looks bright" / "exciting times lie ahead" / "continues its journey toward excellence"
- Excessive hedging: replace "could potentially possibly be argued that it might" with "may" or direct statement
- Promotional language: don't write like an advertisement — cut "boasts", "stunning", "must-visit", "breathtaking"
- Copula avoidance: don't substitute "serves as a foundation" for "is a foundation" — use is/are/has directly
- Outline-like challenge sections: avoid formulaic "Despite challenges… continues to thrive" closings
- Knowledge-cutoff disclaimers: don't include "as of my last update" or "while specific details are limited"
- Persuasive authority tropes: cut "the real question is", "what really matters is", "the heart of the matter" — they add ceremony without content
- Sycophantic tone: cut "great question!", "you're absolutely right!", "that's an excellent point"
- Filler phrases: "in order to" → "to"; "due to the fact that" → "because"; "at this point in time" → "now"; "has the ability to" → "can"
- Fragmented headers: don't follow a heading with a one-sentence restatement before the real content

QUALITY STANDARD:
- Write like a knowledgeable human expert, not a machine assembling bullet points into prose
- Use specific concrete language: "cut latency by 40 ms" not "significantly improved performance"
- When hedging is needed, do it naturally: "the data suggests" not "it is important to note that the data suggests"
- Have a point of view — don't just neutrally list pros and cons when the evidence supports a conclusion
- Use specific details over vague claims; real numbers and named sources over "many experts"
"""


_WRITING_INDICATORS = [
    r"\b(write|draft|compose|author|create)\b.*\b(article|essay|blog|report|paper|explainer|brief|briefing|piece|analysis)\b",
    r"\b(opinion|policy)\b.*\b(piece|brief|analysis|article)\b",
    r"\bop[. -]ed\b",
    r"\barticle\b.*\b(about|on)\b",
    # Greek patterns
    r"\b(γράψτε|συντάξτε|γράψε|σύνταξε)\b.*\b(άρθρο|ανάλυση|έκθεση|μελέτη)\b",
]

_REFERENTIAL_SIGNALS = ["continue", "expand", "revise that", "elaborate", "add more"]

def is_article_request(problem: str) -> bool:
    """Detect if the user is asking for a structured written piece."""
    lower = problem.lower()
    return any(re.search(p, lower) for p in _WRITING_INDICATORS)

def build_synthesis_context(state: PipelineState) -> str:
    """Build Prism citation block for synthesis prompts."""
    parts = []
    prism = state.method_state.get("prism")
    citations = prism.get("citations", []) if prism else []
    if citations:
        parts.append("[SOURCED EVIDENCE]")
        for i, c in enumerate(citations, 1):
            parts.append(f"[{i}] {c['title']} — {c['url']}\n    {c['snippet']}")
        parts.append(
            "\nWhen making a claim supported by the above sources, "
            "append [N] inline. Include a ## Sources section at the end."
        )
    return "\n\n".join(parts)


def is_referential_followup(problem: str, history: list) -> bool:
    """Detect if a follow-up message refers to prior context."""
    if not history:
        return False
    lower = problem.lower()
    return any(sig in lower for sig in _REFERENTIAL_SIGNALS)

