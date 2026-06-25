"""Unit tests for Part B: cross-lingual probe (language-bias mitigation)."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from reasoner.application.services.sensitivity_service import classify_sensitivity
from reasoner.core.settings import settings
from reasoner.domain.pipeline_state import PipelineState


# ─── Sensitivity classifier ───────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_sensitive,expected_axis", [
    ("What is the government policy on Ukraine sanctions?", True, "politics"),
    ("Discuss the election interference allegations.", True, "politics"),
    ("Explain the human rights situation in the region.", True, "governance"),
    ("The genocide of the Armenian people in 1915.", True, "history"),
    ("How do I sort a list in Python?", False, ""),
    ("Explain the Pythagorean theorem.", False, ""),
    ("What is the best recipe for baklava?", False, ""),
    ("Compare quantum computing and classical computing.", False, ""),
])
def test_sensitivity_classifier_precision(
    text: str,
    expected_sensitive: bool,
    expected_axis: str,
) -> None:
    sensitive, axis = classify_sensitivity(text)
    assert sensitive == expected_sensitive
    if expected_sensitive:
        assert axis == expected_axis
    else:
        assert axis == ""


def test_sensitivity_classifier_returns_first_axis() -> None:
    text = "The election was marred by war crimes and human rights abuses."
    sensitive, axis = classify_sensitivity(text)
    assert sensitive is True
    assert axis  # some axis matched


def test_sensitivity_classifier_empty_string() -> None:
    sensitive, axis = classify_sensitivity("")
    assert sensitive is False
    assert axis == ""


# ─── PipelineState B-fields ───────────────────────────────────────────────────

def test_language_sensitive_default() -> None:
    state = PipelineState()
    assert state.language_sensitive is False


def test_language_divergence_default_empty() -> None:
    state = PipelineState()
    assert state.language_divergence == {}


def test_language_divergence_roundtrip() -> None:
    state = PipelineState()
    state.language_divergence = {"diverged": True, "reason": "test", "axis": "politics"}
    assert state.language_divergence["diverged"] is True
    assert state.language_divergence["axis"] == "politics"


def test_language_sensitive_roundtrip() -> None:
    state = PipelineState()
    state.language_sensitive = True
    assert state.language_sensitive is True


# ─── Probe gating ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_probe_does_not_run_when_disabled() -> None:
    from reasoner.application.flows.language_probe_phase import run_language_probe_phase

    state = PipelineState()
    state.language_sensitive = True
    state.output_language = "Greek"
    state.pivot_active = True

    services = MagicMock()
    services.call_llm = AsyncMock()

    with patch("reasoner.core.settings.settings") as mock_settings:
        mock_settings.LANGUAGE_PROBE_ENABLED = False
        await run_language_probe_phase(state, services)

    services.call_llm.assert_not_called()


@pytest.mark.asyncio
async def test_probe_does_not_run_when_not_sensitive() -> None:
    from reasoner.application.flows.language_probe_phase import run_language_probe_phase

    state = PipelineState()
    state.language_sensitive = False
    state.output_language = "Greek"
    state.pivot_active = True

    services = MagicMock()
    services.call_llm = AsyncMock()

    with patch("reasoner.core.settings.settings") as mock_settings:
        mock_settings.LANGUAGE_PROBE_ENABLED = True
        await run_language_probe_phase(state, services)

    services.call_llm.assert_not_called()


@pytest.mark.asyncio
async def test_probe_does_not_run_when_english_output() -> None:
    from reasoner.application.flows.language_probe_phase import run_language_probe_phase

    state = PipelineState()
    state.language_sensitive = True
    state.output_language = "English"
    state.pivot_active = True

    services = MagicMock()
    services.call_llm = AsyncMock()

    with patch("reasoner.core.settings.settings") as mock_settings:
        mock_settings.LANGUAGE_PROBE_ENABLED = True
        await run_language_probe_phase(state, services)

    services.call_llm.assert_not_called()


@pytest.mark.asyncio
async def test_probe_does_not_run_when_no_pivot() -> None:
    from reasoner.application.flows.language_probe_phase import run_language_probe_phase

    state = PipelineState()
    state.language_sensitive = True
    state.output_language = "Greek"
    state.pivot_active = False  # no pivot — native language already

    services = MagicMock()
    services.call_llm = AsyncMock()

    with patch("reasoner.core.settings.settings") as mock_settings:
        mock_settings.LANGUAGE_PROBE_ENABLED = True
        await run_language_probe_phase(state, services)

    services.call_llm.assert_not_called()


# ─── LANGUAGE_PROBE_ENABLED default ──────────────────────────────────────────

def test_language_probe_disabled_by_default() -> None:
    assert settings.LANGUAGE_PROBE_ENABLED is False
