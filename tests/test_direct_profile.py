"""W1 — DIRECT-path epistemic system prompt.

See docs/plans/sycophancy-mitigation.md W1. The DIRECT path has no critique
or stress-test stage, so its system prompt is the only guard a user's stated
conclusion ever meets.
"""

from __future__ import annotations

from pathlib import Path

from reasoner.phases._shared import HUMANIZATION_RULES
from reasoner.phases.direct import (
    DIRECT_ANALYTICAL_SYSTEM,
    DIRECT_CREATIVE_SYSTEM,
    DIRECT_WEB_SEARCH_SYSTEM,
)


def test_direct_analytical_carries_epistemic_rules() -> None:
    assert "treat it as a claim to evaluate, not a premise to build" in DIRECT_ANALYTICAL_SYSTEM
    assert "Do not open by affirming the user" in DIRECT_ANALYTICAL_SYSTEM


def test_direct_web_search_profile_uses_shared_constant() -> None:
    src = Path("src/reasoner/api/execution/direct.py").read_text(encoding="utf-8")
    assert "DIRECT_WEB_SEARCH_SYSTEM" in src
    assert '"You are an analytical assistant' not in src
    assert "treat it as a claim to evaluate, not a premise to build" in DIRECT_WEB_SEARCH_SYSTEM


def test_direct_creative_scopes_compliance_to_form() -> None:
    assert "Do not extend that compliance to endorsing the user's account" in DIRECT_CREATIVE_SYSTEM


def test_all_direct_profiles_include_humanization_rules() -> None:
    for prompt in (DIRECT_ANALYTICAL_SYSTEM, DIRECT_WEB_SEARCH_SYSTEM, DIRECT_CREATIVE_SYSTEM):
        assert HUMANIZATION_RULES in prompt
