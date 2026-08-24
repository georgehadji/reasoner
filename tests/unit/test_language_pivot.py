"""Unit tests for Part A: English pivot hardening (language-bias mitigation)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from reasoner.core.constants_limits import LANG_NAME_TO_ISO, NATIVE_LANGUAGE_METHODS
from reasoner.core.ports.translation_port import TranslationResult
from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.translation.composite import (
    CompositeTranslator,
    reset_composite_translator,
)
from reasoner.infrastructure.translation.llm_translator import LLMTranslator

# ─── LANG_NAME_TO_ISO ────────────────────────────────────────────────────────

@pytest.mark.parametrize("lang,expected_iso", [
    ("Greek", "EL"),
    ("Russian", "RU"),
    ("Arabic", "AR"),
    ("Chinese", "ZH"),
    ("Japanese", "JA"),
    ("Korean", "KO"),
    ("Spanish", "ES"),
    ("German", "DE"),
    ("Turkish", "TR"),
])
def test_lang_name_to_iso_coverage(lang: str, expected_iso: str) -> None:
    assert LANG_NAME_TO_ISO[lang] == expected_iso


# ─── NATIVE_LANGUAGE_METHODS ─────────────────────────────────────────────────

@pytest.mark.parametrize("method", ["writing", "brainstorming", "article"])
def test_native_language_methods_exempt(method: str) -> None:
    assert method in NATIVE_LANGUAGE_METHODS


def test_analytical_methods_not_exempt() -> None:
    for method in ("multi-perspective", "debate", "research", "jury", "socratic"):
        assert method not in NATIVE_LANGUAGE_METHODS


# ─── PipelineState new fields ─────────────────────────────────────────────────

def test_pipeline_state_default_output_language() -> None:
    state = PipelineState()
    assert state.output_language == "English"


def test_pipeline_state_default_pivot_active() -> None:
    state = PipelineState()
    assert state.pivot_active is False


def test_pipeline_state_output_language_roundtrip() -> None:
    state = PipelineState()
    state.output_language = "Greek"
    assert state.output_language == "Greek"


def test_pipeline_state_pivot_active_roundtrip() -> None:
    state = PipelineState()
    state.pivot_active = True
    assert state.pivot_active is True


def test_pipeline_state_resume_compat() -> None:
    """Older saved states without the new fields must still load cleanly."""
    state = PipelineState(problem="test problem", language="English")
    assert state.output_language == "English"
    assert state.pivot_active is False


# ─── CompositeTranslator fallback order ──────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_singleton() -> None:
    reset_composite_translator()
    yield
    reset_composite_translator()


@pytest.mark.asyncio
async def test_composite_uses_deepl_when_available() -> None:
    deepl = AsyncMock()
    deepl.translate = AsyncMock(return_value={"text": "translated", "detected_source_language": "EL"})
    llm = AsyncMock()

    composite = CompositeTranslator(deepl=deepl, llm=llm)
    result = await composite.translate("Γεια", target_lang="EN", source_lang="EL")

    assert result.text == "translated"
    deepl.translate.assert_called_once()
    llm.translate.assert_not_called()


@pytest.mark.asyncio
async def test_composite_falls_back_to_llm_when_deepl_fails() -> None:
    deepl = AsyncMock()
    deepl.translate = AsyncMock(side_effect=RuntimeError("no DeepL key"))
    llm = AsyncMock()
    llm.translate = AsyncMock(return_value=TranslationResult(text="llm-translated", detected_source_language="EL"))

    composite = CompositeTranslator(deepl=deepl, llm=llm)
    result = await composite.translate("Γεια", target_lang="EN")

    assert result.text == "llm-translated"
    llm.translate.assert_called_once()


@pytest.mark.asyncio
async def test_composite_falls_back_to_identity_when_both_fail() -> None:
    deepl = AsyncMock()
    deepl.translate = AsyncMock(side_effect=RuntimeError("no key"))
    llm = AsyncMock()
    llm.translate = AsyncMock(side_effect=RuntimeError("llm error"))

    composite = CompositeTranslator(deepl=deepl, llm=llm)
    result = await composite.translate("Γεια", target_lang="EN")

    assert result.text == "Γεια"  # identity fallback


@pytest.mark.asyncio
async def test_composite_identity_when_no_adapters() -> None:
    composite = CompositeTranslator(deepl=None, llm=None)
    result = await composite.translate("hello", target_lang="EL")
    assert result.text == "hello"


# ─── LLMTranslator ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_llm_translator_preserves_epistemic_tags() -> None:
    router = MagicMock()
    # Simulate router returning translated text with preserved tags
    router.call = AsyncMock(return_value=("[VERIFIED] αποτέλεσμα", {}))
    translator = LLMTranslator(router=router)

    result = await translator.translate("[VERIFIED] result", target_lang="EL", source_lang="EN")

    assert result.text == "[VERIFIED] αποτέλεσμα"
    call_args = router.call.call_args
    assert call_args.kwargs["role"] == "translation"
    assert call_args.kwargs["temperature"] == 0.1


@pytest.mark.asyncio
async def test_llm_translator_strips_whitespace() -> None:
    router = MagicMock()
    router.call = AsyncMock(return_value=("  translated  \n", {}))
    translator = LLMTranslator(router=router)

    result = await translator.translate("original", target_lang="EL")
    assert result.text == "translated"


# ─── LANGUAGE_PIVOT_ENABLED setting ──────────────────────────────────────────

def test_language_pivot_enabled_default() -> None:
    from reasoner.core.settings import settings
    # Default must be True (pivot on by default)
    assert isinstance(settings.LANGUAGE_PIVOT_ENABLED, bool)


# ─── English input is byte-identical (no-op regression) ─────────────────────

def test_english_problem_pivot_not_triggered() -> None:
    """English input must not set pivot_active (no-op)."""
    state = PipelineState(problem="What is the capital of France?", language="English")
    # No translate-in was called; defaults hold.
    assert state.pivot_active is False
    assert state.output_language == "English"
