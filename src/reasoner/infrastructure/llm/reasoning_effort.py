"""Clamp a phase's requested reasoning effort to what a model actually accepts.

``core.temperatures.PHASE_REASONING_EFFORT`` picks an effort per phase on
reasoning quality/cost grounds alone — it does not know which model the router
will land on, and it cannot: the router may fall back to a different model after
the effort is chosen. OpenRouter normalizes effort across providers, but only
within the set a given model advertises in ``supported_efforts``.

54 of the models reachable from ``_MODEL_WHITELIST`` advertise a restricted set.
The two cheapest, highest-frequency phases are the worst affected because
``"minimal"`` is rare upstream:

    google/gemini-3.8-flash  supports high|medium|low   <- classification asks "minimal"
    deepseek/deepseek-v4-pro supports xhigh|high        <- 9 of 15 phases unsupported
    openai/gpt-5-pro         supports high              <- 9 of 15 phases unsupported

This module resolves that at the only point where the served model is known for
certain: payload construction inside the provider.

Placement: this is a leaf module on purpose. The natural home would be
``capability_registry``, but that imports ``llm.registry``, which imports
``providers.openai_compat`` — and openai_compat is the consumer here, so that
would close an import cycle. Reading ``domain.pricing.MODEL_CATALOGUE`` directly
keeps the dependency one-way.
"""

from __future__ import annotations

from reasoner.domain.pricing import MODEL_CATALOGUE

# Ordered most to least thinking. Index distance on this ladder is what
# "nearest supported effort" means below.
EFFORT_LADDER: tuple[str, ...] = (
    "max", "xhigh", "high", "medium", "low", "minimal", "none",
)

_LADDER_INDEX: dict[str, int] = {level: i for i, level in enumerate(EFFORT_LADDER)}


def supported_efforts(served_model: str) -> tuple[str, ...] | None:
    """Effort levels ``served_model`` accepts, or None when unconstrained.

    None means "do not clamp" and covers three distinct upstream cases that all
    warrant the same handling: the model is absent from the catalogue snapshot,
    it is a non-reasoning model (no ``reasoning`` key), or it advertises
    ``supported_efforts: null`` — which OpenRouter documents as "accepts every
    gateway effort value".
    """
    entry = MODEL_CATALOGUE.get(served_model)
    if not entry:
        return None
    reasoning = entry.get("reasoning")
    if not isinstance(reasoning, dict):
        return None
    efforts = reasoning.get("supported_efforts")
    if not efforts:
        return None
    # Ignore any level upstream reports that this gateway does not model.
    known = tuple(e for e in efforts if e in _LADDER_INDEX)
    return known or None


def clamp_effort(desired: str, supported: tuple[str, ...]) -> str:
    """Pick the supported level nearest ``desired`` on :data:`EFFORT_LADDER`.

    Ties break toward *less* thinking, so a phase that asked for a cheap level
    and cannot have it does not silently jump to the expensive side of the
    ladder. ``"none"`` is never substituted in for a phase that asked to think:
    disabling reasoning is a behaviour change, not a clamp, and many of these
    models mark reasoning ``mandatory`` anyway.
    """
    if desired in supported:
        return desired

    target = _LADDER_INDEX.get(desired)
    if target is None:
        return desired

    candidates = [e for e in supported if not (e == "none" and desired != "none")]
    if not candidates:
        return desired

    # Sort by ladder distance, then prefer the higher index (= less thinking).
    return min(candidates, key=lambda e: (abs(_LADDER_INDEX[e] - target), -_LADDER_INDEX[e]))


def clamp_effort_for_model(served_model: str, desired: str) -> str:
    """Clamp ``desired`` to ``served_model``'s advertised efforts.

    Returns ``desired`` unchanged when the model is unconstrained or unknown.
    """
    if not desired:
        return desired
    supported = supported_efforts(served_model)
    if supported is None:
        return desired
    return clamp_effort(desired, supported)


# Share of the output budget each effort level spends on reasoning, per
# https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
# ("max/xhigh ~95%, high ~80%, medium ~50%, low ~20%, minimal ~10%").
_REASONING_SHARE: dict[str, float] = {
    "max": 0.95, "xhigh": 0.95, "high": 0.80,
    "medium": 0.50, "low": 0.20, "minimal": 0.10, "none": 0.0,
}

# Content tokens a reply must still be able to reach after reasoning takes its
# cut. Sized for the smallest thing any phase asks for — a classification
# verdict is a short JSON object — not for a synthesis.
MIN_CONTENT_TOKENS = 256


def reasoning_is_mandatory(served_model: str) -> bool:
    """True when ``served_model`` always spends output tokens on reasoning.

    Keyed on ``mandatory`` alone, deliberately. ``default_enabled`` looks like
    the same signal and is not: ``anthropic/claude-sonnet-5`` carries
    ``default_enabled: true`` yet a live classification call against it reports
    ``reasoning_tokens: 0``. Since Sonnet is the primary of 19 presets, keying
    on ``default_enabled`` would inflate the budget of most traffic in the
    system to buy headroom nothing consumes. 103 of the 472 catalogued models
    are ``mandatory``; those are the ones that take a cut unbidden.
    """
    entry = MODEL_CATALOGUE.get(served_model)
    if not entry:
        return False
    reasoning = entry.get("reasoning")
    if not isinstance(reasoning, dict):
        return False
    return bool(reasoning.get("mandatory"))


def floor_max_tokens(served_model: str, max_tokens: int, effort: str | None) -> int:
    """Raise ``max_tokens`` until content still fits after the reasoning cut.

    OpenRouter counts reasoning tokens as output tokens, and documents that
    "max_tokens must be strictly higher than the reasoning budget to ensure
    there are tokens available for the final response after thinking". When it
    is not, the call does not fail — it returns 200 with empty content, having
    billed for the reasoning.

    How much reasoning a model does varies with the prompt, so this is a
    probabilistic failure rather than a fixed cliff, and that is what makes it
    nasty: the same model and budget can succeed all day and then return empty
    on a harder input. ``openai/gpt-5`` is the primary of five premium presets
    and so serves their classification role at a 256-token budget. Measured
    against the live endpoint:

        classification prompt, max_tokens=256   content len 0     (10 test failures)
        classification prompt, max_tokens=4000  content len 92    valid JSON
        a simpler prompt,      max_tokens=256   content len 40, 128 reasoning tokens

    Raising a ceiling is not the same as spending to it — a model stops when it
    is done, so this costs nothing on replies that already fitted. The call it
    changes is the one now billing full reasoning for zero usable output.

    Returns ``max_tokens`` unchanged for models that do not always reason, and
    never lowers a budget the caller chose.
    """
    if max_tokens <= 0 or not reasoning_is_mandatory(served_model):
        return max_tokens

    if not effort:
        reasoning = (MODEL_CATALOGUE.get(served_model) or {}).get("reasoning")
        effort = reasoning.get("default_effort") if isinstance(reasoning, dict) else None

    # Unknown effort: assume the middle of the ladder rather than the cheapest,
    # so an unrecognised level fails toward a usable reply.
    share = _REASONING_SHARE.get(effort or "", 0.50)
    if share >= 1.0:
        return max_tokens
    return max(max_tokens, int(MIN_CONTENT_TOKENS / (1.0 - share)))


def clamp_extra_body(served_model: str, extra_body: dict | None) -> dict | None:
    """Return ``extra_body`` with ``reasoning.effort`` clamped for the model.

    A new dict is returned whenever a clamp applies, so a shared provider-level
    ``extra_body`` is never mutated in place. Returns the original object
    untouched when there is nothing to change.
    """
    if not extra_body:
        return extra_body
    reasoning = extra_body.get("reasoning")
    if not isinstance(reasoning, dict):
        return extra_body
    desired = reasoning.get("effort")
    if not isinstance(desired, str) or not desired:
        return extra_body

    clamped = clamp_effort_for_model(served_model, desired)
    if clamped == desired:
        return extra_body
    return {**extra_body, "reasoning": {**reasoning, "effort": clamped}}
