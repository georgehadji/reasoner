"""Low-level LLM utilities: platform patches, JSON heuristics, response formatting."""

from __future__ import annotations

from typing import Any


def _patch_openai_platform_detection() -> None:
    """
    Windows WMI can hang indefinitely when the openai library calls
    platform.system() / platform.platform() / platform.machine() to build
    its X-Stainless-* headers. We pre-patch these to safe defaults on Windows
    before openai is imported so that API calls never deadlock.
    """
    import sys
    if sys.platform != "win32":
        return
    import platform
    platform.system = lambda: "Windows"  # type: ignore[method-assign]
    platform.platform = lambda: "Windows"  # type: ignore[method-assign]
    platform.machine = lambda: "AMD64"  # type: ignore[method-assign]


_patch_openai_platform_detection()


def _requests_strict_json(system_prompt: str, user_prompt: str) -> bool:
    """Heuristic: only enable structured outputs for prompts that already demand pure JSON."""
    combined = f"{system_prompt}\n{user_prompt}"
    if "[SOLUTION]" in combined:
        return False
    return (
        "Output ONLY valid JSON" in combined
        or "Output JSON:" in combined
    )


# Models observed to misbehave under the permissive JSON schema below even
# though nothing else marks them unsupported. Keyed on the fully-qualified
# served model string (what providers actually carry as `self.model` for
# every OpenRouter-routed call — see registry.build_provider's
# `case "openrouter"` branch), the same shape _supports_json_mode() resolves
# everything else to.
_JSON_MODE_DENYLIST: frozenset[str] = frozenset({
    # May emit <think> sections even when response_format is requested.
    "perplexity/sonar-reasoning-pro",
    # Long-form research calls can collapse to an empty `{}` under a
    # permissive generic schema.
    "perplexity/sonar-deep-research",
})

# The OpenRouter catalogue snapshot omits response_format/structured_outputs
# from Perplexity Sonar's supported_parameters, even though the Sonar API
# accepts a json_schema response_format and this project relied on that
# working for these three models. Treated as a documented override rather
# than trusting the (catalogue-wrong) capability field — the same reasoning
# providers/openai_compat.py's _FIXED_TEMPERATURE_MARKERS already applies to
# a different supported_parameters gap.
_JSON_MODE_CATALOGUE_OVERRIDE: frozenset[str] = frozenset({
    "perplexity/sonar",
    "perplexity/sonar-pro",
    "perplexity/sonar-pro-search",
})


def _supports_json_mode(model: str) -> bool:
    """True when *model* can be sent a json_object response_format.

    Resolves through the capability registry so any model that advertises
    ``response_format``/``structured_outputs`` in the OpenRouter catalogue
    becomes eligible automatically — not just the Perplexity models this
    check used to be hardcoded to. A profile with ``data_source == "unknown"``
    (no catalogue entry, no manual hint) is treated as unsupported: guessing a
    capability is how a phase that used to work starts getting 400s.
    """
    try:
        from reasoner.infrastructure.llm.capability_registry import get_constraints
    except Exception:
        return False
    constraints = get_constraints(model)
    served = constraints.served_model or model
    if served in _JSON_MODE_DENYLIST:
        return False
    if served in _JSON_MODE_CATALOGUE_OVERRIDE:
        return True
    return constraints.data_source != "unknown" and constraints.supports_json_mode


def _json_response_format(
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> dict[str, Any] | None:
    """
    Return a JSON-object response format for a model that can use one.

    All three must hold:
      1. The prompt already demands strict JSON (_requests_strict_json) — this
         never introduces JSON-mode behaviour the prompt didn't already ask for.
      2. LLM_JSON_MODE_ENABLED is on (default true; a kill switch for the
         first release of this without a redeploy).
      3. The model's capability profile says it supports it (_supports_json_mode).

    Generalised from a Perplexity-only check: every JSON-contract phase across
    all 29 phase modules previously relied on the prose instruction alone
    ("Output ONLY valid JSON."), which a chatty reasoning model can and did
    ignore — see docs/plans/article-flow-truncation-remediation.md W3.

    Deliberately ``json_object``, not ``json_schema``: this project has no
    real per-role schema to enforce (every phase re-validates its own shape
    via extract_json() afterward), and the earlier property-less schema
    (``{"type": "object", "additionalProperties": true}``) asked providers to
    grammar-compile a degenerate case. On qwen/qwen3.5-flash-02-23 that
    produced a bare scalar (e.g. "1.0647932541382034e-05") as the entire
    response instead of an object — the same failure class the
    _JSON_MODE_DENYLIST comment above already documents for two Perplexity
    models ("collapse to an empty {}"). json_object asks for valid JSON
    syntax without forcing constrained decoding against an empty schema.
    """
    if not _requests_strict_json(system_prompt, user_prompt):
        return None
    try:
        from reasoner.core.settings import settings
        if not settings.LLM_JSON_MODE_ENABLED:
            return None
    except Exception:
        pass
    if not _supports_json_mode(model):
        return None
    return {"type": "json_object"}
