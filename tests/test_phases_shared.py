"""Tests for shared phase utilities."""

from __future__ import annotations

from reasoner.models import PipelineState
from reasoner.phases._shared import detect_language, get_language_instruction


class TestDetectLanguage:
    """Test language detection from text."""

    def test_detects_english(self):
        assert detect_language("What is the capital of France?") == "English"

    def test_detects_greek(self):
        assert detect_language("Ποια είναι η πρωτεύουσα της Γαλλίας;") == "Greek"

    def test_detects_russian(self):
        assert detect_language("Какая столица Франции?") == "Russian"

    def test_detects_arabic(self):
        assert detect_language("ما هي عاصمة فرنسا؟") == "Arabic"

    def test_detects_chinese(self):
        assert detect_language("法国的首都是什么？") == "Chinese"

    def test_detects_japanese_kana(self):
        # Pure kana should be detected as Japanese
        assert detect_language("フランスのしゅとはなんですか") == "Japanese"

    def test_detects_japanese_with_kanji_as_chinese(self):
        # BUG: Japanese text with kanji is detected as Chinese because
        # kanji characters are in the CJK Unicode range checked first.
        assert detect_language("フランスの首都は何ですか？") == "Chinese"

    def test_detects_korean(self):
        assert detect_language("프랑스의 수도는 무엇입니까?") == "Korean"

    def test_detects_spanish(self):
        assert detect_language("¿Cuál es la capital de Francia?") == "Spanish"

    def test_detects_german_with_umlauts(self):
        assert detect_language("Wie heißt du?") == "German"

    def test_detects_german_with_eszett(self):
        assert detect_language("Straße und Größe") == "German"

    def test_detects_german_without_umlauts_as_english(self):
        # BUG: German without umlauts (ä, ö, ß) is not detected.
        assert detect_language("Wie geht es dir") == "English"

    def test_detects_turkish(self):
        assert detect_language("Fransa'nın başkenti nedir?") == "Turkish"

    def test_defaults_to_english(self):
        assert detect_language("Hello world") == "English"

    def test_empty_string_defaults_to_english(self):
        assert detect_language("") == "English"


class TestGetLanguageInstruction:
    """Test language instruction generation."""

    def test_english_instruction(self):
        state = PipelineState(problem="test", language="English")
        assert "Respond in English" in get_language_instruction(state)

    def test_greek_instruction(self):
        state = PipelineState(problem="test", language="Greek")
        assert "Απάντησε" in get_language_instruction(state)

    def test_spanish_instruction(self):
        state = PipelineState(problem="test", language="Spanish")
        assert "español" in get_language_instruction(state)

    def test_unknown_language_defaults_to_english(self):
        state = PipelineState(problem="test", language="Klingon")
        assert "Respond in English" in get_language_instruction(state)
