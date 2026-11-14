"""Jurisdiction resolver chain, as-of date, and the scope prompt block (plan §3).

Behaviour under test: application/services/stakes_service. No existing test
file covers it; test_high_stakes_policy.py covers the evidence policy only.
"""

from datetime import date

from reasoner.application.services.stakes_service import (
    resolve_jurisdiction,
    scope_for,
    scope_prompt_block,
)
from reasoner.domain.core_types import FinalSolution
from reasoner.domain.stakes import StakesDomain


def test_explicit_beats_text():
    assert resolve_jurisdiction("Is this legal in Greece?", explicit="us") == "US"


def test_text_used_when_no_explicit():
    assert resolve_jurisdiction("Ποιος είναι ο φόρος στην Ελλάδα;") == "GR"
    assert resolve_jurisdiction("Is it legal in Germany?") == "DE"


def test_ambiguous_text_is_unresolved():
    assert resolve_jurisdiction("Compare Greek and German tax") is None


def test_invalid_explicit_falls_through():
    assert resolve_jurisdiction("Is it legal in Greece?", explicit="ZZ") == "GR"
    assert resolve_jurisdiction("Is it legal?", explicit="ZZ") is None


def test_scope_uses_run_date_utc():
    s = scope_for("Is it legal in Greece?", today=date(2026, 11, 14))
    assert s == {"jurisdiction": "GR", "as_of": "2026-11-14"}


def test_prompt_block_names_date_and_unresolved_country():
    block = scope_prompt_block(StakesDomain.LEGAL, {"jurisdiction": None, "as_of": "2026-11-14"})
    assert "2026-11-14" in block and "not stated" in block and "do not assume" in block


def test_old_final_solution_without_scope_still_builds():
    fs = FinalSolution(
        core_solution="x", critical_insights=[], action_blueprint=[],
        open_questions=[], claim_labels={}, meta_audit=None,
    )
    assert fs.scope == {}
