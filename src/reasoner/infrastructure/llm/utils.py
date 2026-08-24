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


def _perplexity_response_format(
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> dict[str, Any] | None:
    """
    Return a permissive JSON-schema response format for compatible Perplexity models.

    sonar-reasoning-pro is excluded because it may emit <think> sections even when
    response_format is requested.
    sonar-deep-research is excluded because long-form research calls can collapse to
    an empty `{}` under a permissive generic schema.
    """
    if not model.startswith("sonar"):
        return None
    if model in {"sonar-reasoning-pro", "sonar-deep-research"}:
        return None
    if not _requests_strict_json(system_prompt, user_prompt):
        return None
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "ara_pipeline_response",
            "schema": {
                "type": "object",
                "additionalProperties": True,
            },
        },
    }
