"""Unit tests for multilingual article request detection."""

from __future__ import annotations

import pytest

article_pipeline = pytest.importorskip(
    "reasoner.application.mixins.article_pipeline",
    reason="reasoner.application.mixins not present in this build",
)
detect_document_type = article_pipeline.detect_document_type
is_article_request = article_pipeline.is_article_request


class TestIsArticleRequestMultilingual:
    """Verify article detection works across languages."""

    # ── Greek ──────────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "problem, expected",
        [
            ("γράψε ένα άρθρο για τις νεώτερες εξελίξεις", True),
            ("γράψτε μια έκθεση για το διάστημα", True),
            ("συντάξε μια αναφορά", True),
            ("δημιούργησε ένα κείμενο", True),
            ("άρθρο για την τεχνητή νοημοσύνη", True),
            ("τι καιρό κάνει σήμερα", False),
            ("εξήγησε την κβαντική μηχανική", False),
        ],
    )
    def test_greek(self, problem: str, expected: bool) -> None:
        assert is_article_request(problem) is expected

    # ── English ────────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "problem, expected",
        [
            ("write an article about space", True),
            ("draft a blog post on AI", True),
            ("compose a report about climate change", True),
            ("what is the weather today", False),
            ("solve this math problem", False),
            ("explain quantum mechanics", False),
        ],
    )
    def test_english(self, problem: str, expected: bool) -> None:
        assert is_article_request(problem) is expected

    # ── Spanish ────────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "problem, expected",
        [
            ("escribe un artículo sobre el espacio", True),
            ("redacta un ensayo sobre la política", True),
            ("crea un blog sobre tecnología", True),
            ("qué tiempo hace hoy", False),
        ],
    )
    def test_spanish(self, problem: str, expected: bool) -> None:
        assert is_article_request(problem) is expected

    # ── French ─────────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "problem, expected",
        [
            ("écris un article sur l'espace", True),
            ("rédige un essai sur la politique", True),
            ("crée un blog sur la technologie", True),
            ("quel temps fait-il aujourd'hui", False),
        ],
    )
    def test_french(self, problem: str, expected: bool) -> None:
        assert is_article_request(problem) is expected


class TestDetectDocumentType:
    """Verify document type classification."""

    def test_thesis_greek(self) -> None:
        assert detect_document_type("διπλωματική εργασία") == "thesis"

    def test_paper_greek(self) -> None:
        assert detect_document_type("ακαδημαϊκή εργασία") == "paper"

    def test_article_default(self) -> None:
        assert detect_document_type("write an article") == "article"
