import pytest

from reasoner.domain.stakes import StakesDomain as D
from reasoner.hypergate.stakes_patterns import match_stakes


@pytest.mark.parametrize("text,domain", [
    ("What is the maximum dosage of ibuprofen per day?", D.HEALTH),
    ("Ποια είναι η δοσολογία της παρακεταμόλης για παιδιά;", D.HEALTH),
    ("Είναι ασφαλές αυτό το φάρμακο στην εγκυμοσύνη;", D.HEALTH),
    ("Is it legal to record a phone call in my country?", D.LEGAL),
    ("Μπορώ να κάνω αγωγή στον ιδιοκτήτη μου για την μίσθωση;", D.LEGAL),
    ("Should I invest in index funds or pay off my mortgage?", D.FINANCIAL),
    ("Πώς υπολογίζεται ο φόρος εισοδήματος για ελεύθερους επαγγελματίες;", D.FINANCIAL),
])
def test_positives(text, domain):
    assert match_stakes(text) is domain


@pytest.mark.parametrize("text", [
    "How do I draw a health bar in a game?",
    "Explain the law of large numbers",
    "What is Moore's law?",
    "Write a poem about the sea",
    "Εξήγησε μου το νόμο του Ohm",
])
def test_near_misses_and_unrelated(text):
    assert match_stakes(text) is D.NONE
