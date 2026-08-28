"""Smoke coverage for the Skeleton-of-Thought section prompt builders.

article_sot_solve_prompt referenced a local, style_section, that the
style_brief removal deleted along with its two defining lines. Nothing under
tests/ called the function, so the NameError was invisible to the suite and
surfaced only as one mypy [name-defined] error against the ratchet.

These builders take state plus a section dict and return a string. Calling
them is the whole test: an undefined name in an f-string cannot survive it.
"""

from __future__ import annotations

import pytest

from reasoner.domain.pipeline_state import PipelineState


def _state() -> PipelineState:
    return PipelineState(
        problem="Test article about grid storage",
        language="English",
        preset_name="article-budget",
        method="article",
    )


@pytest.mark.parametrize("builder_name", ["article_sot_solve_prompt", "academic_sot_solve_prompt"])
def test_sot_solve_prompt_builds(builder_name: str) -> None:
    # Arrange
    import reasoner.phases as phases

    builder = getattr(phases, builder_name)
    section = {"heading": "Storage economics", "word_count": 200}

    # Act
    prompt = builder(_state(), section, "[]")

    # Assert
    assert isinstance(prompt, str)
    assert "Storage economics" in prompt


def test_article_sot_solve_prompt_survives_a_bare_section() -> None:
    """section is a plain dict off parsed LLM output, so its keys are optional."""
    # Arrange
    import reasoner.phases as phases

    # Act
    prompt = phases.article_sot_solve_prompt(_state(), {}, "[]")

    # Assert
    assert isinstance(prompt, str) and prompt
