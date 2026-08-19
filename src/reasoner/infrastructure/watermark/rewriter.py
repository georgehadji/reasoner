"""Layer B rewrite prompts and non-origin model selection.

Prompts ported verbatim from the reference repo's `rewrite_text.py` PROMPTS
dict / build_prompt() -- they are the researched artifact (docs/plans/
watermark-removal-integration.md Part 1.3). The reference's backend
abstraction (ollama/openai-compatible CLI plumbing) is dropped: the actual
LLM call goes through the pipeline's existing WorkflowServices.call_llm so
metering/circuit-breaker/fallback apply automatically, so this module has no
network code -- just prompt templates and pure model selection.
"""

from __future__ import annotations

_PROMPTS: dict[str, str] = {
    "paraphrase": (
        "Rewrite the following text so that it uses substantially different wording at "
        "the token level. Change clause order, connectors, and transition words; vary "
        "sentence boundaries and length; and replace both content words and function "
        "words where meaning allows. Preserve all facts, numbers, names, and technical "
        "identifiers. Do not add or remove claims. Output only the rewritten text.\n\n---\n{text}"
    ),
    "humanize": (
        "Rewrite the following text so it reads as if a human wrote it from scratch. "
        "Vary sentence rhythm and length, replace formulaic AI-style transitions and "
        "filler with concrete natural phrasing, and use plain, varied wording. Preserve "
        "all facts, numbers, names, and technical identifiers. Do not add or remove "
        "claims. Output only the rewritten text.\n\n---\n{text}"
    ),
}

REWRITE_STRATEGIES: tuple[str, ...] = ("paraphrase", "humanize", "backtranslate", "structural")


def build_rewrite_prompt(
    strategy: str, text: str, *, lang: str = "French", original_lang: str = "English"
) -> str:
    """Build the rewrite prompt for *strategy*; wording ported from the reference's build_prompt."""
    if strategy in _PROMPTS:
        return _PROMPTS[strategy].format(text=text)
    if strategy == "backtranslate":
        return (
            f"Translate the text to {lang}, then translate that result back to "
            f"{original_lang}. Preserve all facts, numbers, and names. "
            f"Output only the final {original_lang} text.\n\n---\n{text}"
        )
    if strategy == "structural":
        return (
            "First extract a bullet outline of all claims (no full sentences). "
            "Then write a complete document from that outline in natural, varied human "
            "prose without omitting any bullet. Output only the final document.\n\n---\n"
            f"{text}"
        )
    raise ValueError(f"unknown rewrite strategy: {strategy}")


# Curated, ordered general-purpose prose models spanning all three blocs.
# Explicit rather than derived: scanning the whitelist programmatically picks
# by alias spelling, not by suitability -- it happily returned `codestral` (a
# *code* model) to rewrite prose, and could return a local `ollama-*` alias
# that needs a server nobody is running. Rewrite quality is a judgment call,
# so the judgment is written down here.
_REWRITE_CANDIDATES: tuple[str, ...] = (
    "claude-sonnet",     # US / anthropic
    "deepseek-v4-pro",   # CN / deepseek
    "mistral-large-3",   # EU / mistralai
    "qwen3.8-max",       # CN / qwen
    "gpt-5.5",           # US / openai
    "kimi-k2-6",         # CN / moonshotai
    "gemini-pro",        # US (resolves cross-vendor -- see _vendor_of)
    "mistral-medium",    # EU / mistralai
)


def select_rewrite_model(origin_model: str) -> str | None:
    """Cross-bloc, cross-vendor candidate for rewriting *origin_model*'s output.

    Picks the first candidate whose training bloc AND vendor both differ from
    the origin -- rewriting a model's output with a sibling from the same lab
    defeats the point. Returns None when no candidate qualifies; callers must
    skip the rewrite rather than fall back to a same-bloc model.
    """
    from reasoner.infrastructure.llm.registry import _REGISTRY, bloc_of, resolved_model_of

    if not origin_model:
        return None
    origin_bloc = bloc_of(origin_model)
    origin_vendor = resolved_model_of(origin_model).split("/", 1)[0]
    for alias in _REWRITE_CANDIDATES:
        if alias not in _REGISTRY:
            continue
        if bloc_of(alias) == origin_bloc:
            continue
        if resolved_model_of(alias).split("/", 1)[0] == origin_vendor:
            continue
        return alias
    return None


__all__ = ["REWRITE_STRATEGIES", "build_rewrite_prompt", "select_rewrite_model"]
