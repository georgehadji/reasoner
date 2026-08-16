"""Prompt-building for the direct-answer path (HyperGate DIRECT / WEB_SEARCH).

Pure functions only — no IO, no provider calls. The imperative shell that
drives the LLM call lives in ``api/execution/direct.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from reasoner.domain.preset_core import get_preset_price_tier
from reasoner.phases._shared import _wrap_user_input, build_followup_context


@dataclass(frozen=True)
class DirectProfile:
    """Model/prompt configuration for one direct-answer call."""
    system_prompt: str
    max_tokens: int
    temperature: float
    models: tuple[str, ...]  # preference order; empty = use the router's own routing


DIRECT_ANALYTICAL_SYSTEM = "You are an analytical assistant. Provide a clear, concise answer."

# Enhanced system prompt for creative writing with hallucination guards.
DIRECT_CREATIVE_SYSTEM = (
    "You are an expert writer and creative assistant.\n"
    "\n"
    "WRITING PRINCIPLES:\n"
    "1. Produce well-structured, engaging, and original content.\n"
    "2. Follow the user's instructions precisely regarding tone, length, format, and style.\n"
    "3. Maintain a consistent voice and perspective throughout the piece.\n"
    "\n"
    "HALLUCINATION PREVENTION:\n"
    "1. If you include historical events, real people, statistics, or scientific claims, "
    "ensure they are accurate and widely accepted. Do NOT invent studies, citations, dates, or data.\n"
    "2. Clearly distinguish between factual claims and creative interpretation, opinion, or speculation.\n"
    "3. If you are uncertain about a fact, rephrase it as a general observation or omit it.\n"
    "4. Do NOT fabricate quotes, sources, or references.\n"
    "\n"
    "SELF-CORRECTION:\n"
    "Before finalizing, mentally review your draft for any unsupported factual claims. "
    "Replace dubious claims with safer, more general statements.\n"
)

_CREATIVE_MODELS_PREMIUM: tuple[str, ...] = ("claude-sonnet", "gpt-5", "gemini-pro")
_CREATIVE_MODELS_BUDGET: tuple[str, ...] = ()  # budget tier uses the router's own primary


def build_direct_prompt(
    problem: str,
    conversation_history: list[dict[str, str]] | None,
    previous_synthesis: str,
    turn_number: int,
) -> str:
    """Build the user-prompt for a direct answer.

    History goes first (it's the stable, cacheable prefix — see
    infrastructure/llm/caching.py); the current request goes last since it
    changes on every call.
    """
    context_block = build_followup_context(
        conversation_history,
        previous_synthesis=previous_synthesis[:2000],
        turn_number=turn_number,
    )
    if context_block:
        return f"{context_block}\nCURRENT USER REQUEST:\n{_wrap_user_input(problem)}"
    return _wrap_user_input(problem)


def select_direct_profile(problem: str, preset_name: str) -> DirectProfile:
    """Pick system prompt, sampling params, and model preference for ``problem``."""
    from reasoner.hypergate.hyperagent import _is_creative_writing

    if not _is_creative_writing(problem):
        return DirectProfile(
            system_prompt=DIRECT_ANALYTICAL_SYSTEM,
            max_tokens=2048,
            temperature=0.7,
            models=(),
        )

    tier = get_preset_price_tier(preset_name)
    models = _CREATIVE_MODELS_PREMIUM if tier == "premium" else _CREATIVE_MODELS_BUDGET
    return DirectProfile(
        system_prompt=DIRECT_CREATIVE_SYSTEM,
        max_tokens=4096,
        temperature=0.8,
        models=models,
    )
