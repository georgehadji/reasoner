"""The critic's `scores` key collides with the multi-perspective critique's.

`perspective_phases.run_critique_phase` reads `scores` as a *list* of
per-perspective objects. `iterative_critique_phases.run_critic_phase` reads the
same key as an *object* of dimensions. A model returning the first shape to the
second reader raised `AttributeError: 'list' object has no attribute 'get'`, and
the read sits outside the try/except that exists to turn a malformed critic
response into a REVISE round — so the phase died rather than degrading.

Found on 2026-09-09 by giving tests/test_e2e_budget_presets_mock.py's shared
payload a non-empty `scores` list, which its own docstring already claimed it
had ("a superset of what any phase parser looks for").
"""

from __future__ import annotations

import logging

import pytest

from reasoner.application.flows.iterative_critique_phases import _parse_critic_dimensions


def test_object_of_dimensions_is_read_normally():
    out = _parse_critic_dimensions(
        {"factuality": 8, "reasoning": 7.5, "completeness": 6, "clarity": 9}
    )
    assert (out.factuality, out.reasoning, out.completeness, out.helpfulness) == (
        8.0, 7.5, 6.0, 9.0,
    )


@pytest.mark.parametrize(
    "wrong_shape",
    [
        pytest.param(
            [{"perspective": "constructive", "logical_consistency": 8.0}],
            id="multi-perspective list",
        ),
        pytest.param("8/10", id="string"),
        pytest.param(None, id="null"),
    ],
)
def test_a_wrong_shape_scores_zero_instead_of_raising(wrong_shape, caplog):
    with caplog.at_level(logging.WARNING):
        out = _parse_critic_dimensions(wrong_shape)

    assert out.factuality == 0.0
    assert out.reasoning == 0.0
    assert "expected an object of dimensions" in caplog.text, (
        "a wrong shape must leave a trace; scoring 0 in silence is the failure "
        "mode this repo tracks as a silent failure"
    )


# ── IC-4: degraded critic rounds must not fake convergence ──────────────────


def _round(
    n, *, score=5.0, flaw="Critic produced malformed JSON", degraded=False, verdict="REVISE"
):
    from reasoner.application.flows.iterative_critique_phases import AdversarialRound
    from reasoner.domain.core_types import CriticDimensionScore

    return AdversarialRound(
        round_number=n,
        critic_score=CriticDimensionScore(
            factuality=score, reasoning=score, completeness=score, helpfulness=score
        ),
        flaws_identified=[{"flaw": flaw}],
        verdict=verdict,
        degraded=degraded,
    )


def test_two_degraded_rounds_stop_as_critic_unavailable():
    from reasoner.application.flows.iterative_critique_phases import check_convergence

    assert check_convergence([_round(1, degraded=True)]) == (False, "")
    assert check_convergence([_round(1, degraded=True), _round(2, degraded=True)]) == (
        True,
        "critic_unavailable",
    )


def test_identical_placeholder_rounds_are_not_a_plateau():
    """Three identical synthetic rounds used to read as score_converged."""
    from reasoner.application.flows.iterative_critique_phases import check_convergence

    # One real round, then placeholders: never score_converged/stalemate.
    rounds = [_round(1, score=3.0, flaw="real"), _round(2, degraded=True)]
    assert check_convergence(rounds) == (False, "")
    rounds.append(_round(3, degraded=True))
    assert check_convergence(rounds) == (True, "critic_unavailable")


def test_plateau_windows_only_see_real_rounds():
    from reasoner.application.flows.iterative_critique_phases import check_convergence

    # Real scores 3, 6, 9 are not a plateau; a degraded round (5.0) between them
    # must not be pulled into the window.
    rounds = [_round(1, score=3.0, flaw="a"), _round(2, score=6.0, flaw="b"),
              _round(3, degraded=True), _round(4, score=9.0, flaw="c")]
    assert check_convergence(rounds) == (False, "")
    # Three real, flat scores with a degraded round between them still converge.
    rounds = [_round(1, score=6.0, flaw="a"), _round(2, score=6.1, flaw="b"),
              _round(3, degraded=True), _round(4, score=6.2, flaw="c")]
    assert check_convergence(rounds) == (True, "score_converged")


def test_a_degraded_round_cannot_accept():
    from reasoner.application.flows.iterative_critique_phases import check_convergence

    assert check_convergence([_round(1, degraded=True, verdict="ACCEPT")]) == (False, "")
