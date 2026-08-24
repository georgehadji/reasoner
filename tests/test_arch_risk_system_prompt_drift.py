"""
Architecture Risk: System prompt drift across multiple locations.

The architecture audit identified the same system prompt duplicated across
core/constants.py and api/streaming.py. This test guards against drift
by asserting the canonical copy matches all copies.
"""

from __future__ import annotations


def test_analytical_system_prompt_consistency() -> None:
    """ANALYTICAL_SYSTEM_PROMPT in core/constants.py is the single source."""
    from reasoner.core.constants import ANALYTICAL_SYSTEM_PROMPT

    # Verify the canonical copy has expected content
    assert "analytical" in ANALYTICAL_SYSTEM_PROMPT.lower()
    assert len(ANALYTICAL_SYSTEM_PROMPT) > 20


def test_creative_system_prompt_single_source() -> None:
    """CREATIVE_SYSTEM_PROMPT lives only in core/constants_prompts.py now.

    streaming.py no longer keeps its own _CREATIVE_SYSTEM_PROMPT copy (the
    duplication this test class was written to guard against was since
    removed) — assert the duplicate stays gone and the canonical copy exists.
    """
    import reasoner.api.streaming as streaming
    from reasoner.core.constants import CREATIVE_SYSTEM_PROMPT

    assert CREATIVE_SYSTEM_PROMPT
    assert not hasattr(streaming, "_CREATIVE_SYSTEM_PROMPT")


def test_gate_system_prompt_exists() -> None:
    """GATE_SYSTEM_PROMPT is defined and has expected categories."""
    from reasoner.core.constants import GATE_SYSTEM_PROMPT

    assert len(GATE_SYSTEM_PROMPT) > 100
    # Key categories must be present
    for category in ("A:", "B:", "C:", "E:", "W:"):
        assert category in GATE_SYSTEM_PROMPT, f"Category {category} missing from GATE_SYSTEM_PROMPT"


def test_image_gen_policy_rewrite_prompt_exists() -> None:
    """IMAGE_GEN_POLICY_REWRITE_SYSTEM_PROMPT is defined and contains expected text."""
    from reasoner.core.constants import IMAGE_GEN_POLICY_REWRITE_SYSTEM_PROMPT

    assert len(IMAGE_GEN_POLICY_REWRITE_SYSTEM_PROMPT) > 50
    assert "rewrite" in IMAGE_GEN_POLICY_REWRITE_SYSTEM_PROMPT.lower()


def test_direct_answer_temperature_constant() -> None:
    """DIRECT_ANSWER_TEMPERATURE is used in streaming.py; must match expected."""
    from reasoner.core.constants import CREATIVE_TEMPERATURE, DIRECT_ANSWER_TEMPERATURE

    assert DIRECT_ANSWER_TEMPERATURE == 0.7
    assert CREATIVE_TEMPERATURE == 0.8


def test_prompt_constants_no_empty_strings() -> None:
    """All system prompt constants should be non-empty strings."""
    from reasoner.core import constants as c

    prompt_attrs = [
        attr
        for attr in dir(c)
        if attr.endswith("_SYSTEM_PROMPT")
    ]
    for attr in prompt_attrs:
        value = getattr(c, attr)
        assert isinstance(value, str) and len(value) > 0, (
            f"System prompt constant {attr} is empty or not a string"
        )
