"""The regex must never misfile or over-flag the routing corpus (benchmarks/high_stakes).

Recall is reported in BASELINE.md, not asserted: the model detector covers what
the regex misses, and pinning recall here would reward tuning to the corpus.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "benchmarks" / "high_stakes"))

from route_eval import evaluate, load_cases  # noqa: E402


def test_regex_has_no_false_positives_or_wrong_domains():
    result = evaluate(load_cases())
    assert result["false_positives"] == []
    assert result["wrong_domain"] == []


def test_corpus_has_no_invented_reference_answers():
    assert all(c["reference"] is None for c in load_cases())
