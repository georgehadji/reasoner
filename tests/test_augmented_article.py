"""
Unit tests for augmented article pipeline:
- Depth detection regex heuristics
- Augmentation prompt selection
- HyperGate fast-path deep concept exclusion
"""

from __future__ import annotations

import pytest

from reasoner.application.flows.augmentation import (
    AUGMENTATION_PROMPTS,
    AUGMENTATION_ROLES,
    DEFAULT_AUGMENTATION_METHODS,
    is_deep_question,
)

# Re-import the HyperGate patterns for direct testing
from reasoner.hypergate.hyperagent import (
    _DEEP_CONCEPT_PATTERNS,
    _FACTUAL_PATTERNS,
)

# ── Depth Detection: should-detect cases ─────────────────────────────

_DEEP_QUESTIONS = [
    # Greek — τι είναι + abstract
    "Τι είναι τέχνη;",
    "Τι είναι δικαιοσύνη;",
    "Τι είναι αλήθεια;",
    "Τι είναι η συνείδηση;",
    "Τι είναι η ομορφιά;",
    # Greek — philosophical keywords
    "Ποια είναι η έννοια της ύπαρξης;",
    "Ορίστε την αισθητική.",
    "Ανάλυσε την έννοια της ελευθερίας.",
    "Ποια είναι η φύση της ηθικής;",
    "Εξήγησε την οντολογία του Αριστοτέλη.",
    # English — what is + abstract concept
    "What is art?",
    "What is consciousness?",
    "What is the meaning of life?",
    "What is the nature of reality?",
    "What is the definition of beauty?",
    "What is the purpose of existence?",
    "What exactly is love?",
    # English — philosophical keywords
    "Is there such a thing as free will?",
    "Can we ever truly know anything?",
    "Explain the concept of justice.",
    "What does epistemology study?",
    # Cross-language abstract markers
    "Ο ορισμός της τέχνης στην αρχαιότητα.",
    "Η υπόσταση του ανθρώπου κατά τον Χέγκελ.",
]


@pytest.mark.parametrize("question", _DEEP_QUESTIONS)
def test_deep_questions_detected(question: str):
    """All philosophically deep questions should be detected."""
    assert is_deep_question(question), f"Should detect as deep: {question!r}"


# ── Depth Detection: should-NOT-detect cases ─────────────────────────

_SHALLOW_QUESTIONS = [
    # Greek — practical/factual
    "Πώς να φτιάξω καφέ;",
    "Ποια είναι η πρωτεύουσα της Γαλλίας;",
    "Πόσα χιλιόμετρα είναι από Αθήνα μέχρι Θεσσαλονίκη;",
    "Πότε έγινε η Ελληνική Επανάσταση;",
    "Ποιος είναι ο πρόεδρος των ΗΠΑ;",
    "Γράψε μια συνταγή για μουσακά.",
    # English — practical/factual
    "How to make coffee",
    "What is the capital of France?",
    "How many planets are in the solar system?",
    "Write an article about Python 3.12 features",
    "Explain how photosynthesis works",
    "Latest news about AI",
    "What time is it in Tokyo?",
    # Edge: descriptive, not definitional
    "Περιέγραψε την ιστορία της τέχνης στην Ελλάδα.",
]


@pytest.mark.parametrize("question", _SHALLOW_QUESTIONS)
def test_shallow_questions_not_detected(question: str):
    """Practical/factual questions should NOT be detected as deep."""
    assert not is_deep_question(question), f"Should NOT detect as deep: {question!r}"


# ── HyperGate fast-path exclusion ────────────────────────────────────

@pytest.mark.parametrize("question", [
    "What is art?",
    "What is consciousness?",
    "What is truth?",
    "Τι είναι τέχνη;",
    "Τι είναι δικαιοσύνη;",
])
def test_deep_concepts_bypass_factual_fastpath(question: str):
    """Deep concept questions should trigger the HyperGate exclusion and NOT
    be captured by the factual lookup fast-path."""
    matches_factual = any(p.search(question) for p in _FACTUAL_PATTERNS)
    matches_deep = any(p.search(question) for p in _DEEP_CONCEPT_PATTERNS)

    # These questions WOULD match factual patterns without the deep concept guard
    assert matches_factual, f"{question!r} should match factual patterns (baseline)"
    # But the deep concept guard should intercept them
    assert matches_deep, f"{question!r} should match deep concept patterns (exclusion)"


@pytest.mark.parametrize("question", [
    "What is the capital of France?",
    "Who is the president of USA?",
    "How many planets are there?",
    "Ποια είναι η πρωτεύουσα της Γαλλίας;",
    "Πού είναι το Παρίσι;",
])
def test_factual_questions_not_excluded(question: str):
    """Genuine factual questions should still match factual patterns AND NOT
    be excluded by deep concept patterns."""
    matches_factual = any(p.search(question) for p in _FACTUAL_PATTERNS)
    matches_deep = any(p.search(question) for p in _DEEP_CONCEPT_PATTERNS)

    assert matches_factual, f"{question!r} should match factual patterns"
    assert not matches_deep, f"{question!r} should NOT match deep concept patterns"


# ── Augmentation configuration ───────────────────────────────────────

def test_default_augmentation_methods():
    """Default augmentation should be debate + iterative critique."""
    assert "debate" in DEFAULT_AUGMENTATION_METHODS
    assert "iterative_critique" in DEFAULT_AUGMENTATION_METHODS
    assert len(DEFAULT_AUGMENTATION_METHODS) == 2


def test_augmentation_prompts_exist_for_all_methods():
    """Every method in AUGMENTATION_ROLES must have a prompt."""
    for method in AUGMENTATION_ROLES:
        assert method in AUGMENTATION_PROMPTS, f"Missing prompt for {method}"


def test_augmentation_roles_valid():
    """All augmentation roles must be valid pipeline roles."""
    for method, role in AUGMENTATION_ROLES.items():
        assert isinstance(role, str), f"Role for {method} must be a string"
        assert len(role) > 0, f"Role for {method} must not be empty"


# ── Edge cases ───────────────────────────────────────────────────────

def test_empty_string_not_deep():
    """Empty strings should never be detected as deep."""
    assert not is_deep_question("")


def test_very_long_question():
    """Long questions with deep keywords should still be detected."""
    long_q = (
        "Μπορείς να μου εξηγήσεις αναλυτικά, σε βάθος, τι ακριβώς είναι η τέχνη "
        "και πώς έχει εξελιχθεί η έννοιά της από την αρχαιότητα μέχρι σήμερα, "
        "λαμβάνοντας υπόψη φιλοσοφικές, κοινωνιολογικές και ψυχολογικές διαστάσεις;"
    )
    assert is_deep_question(long_q)


def test_english_deep_question_not_detected_by_greek_only():
    """English deep questions must be detected even without any Greek text."""
    assert is_deep_question("What is art?")
