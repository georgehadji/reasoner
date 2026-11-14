"""Answerability assessment and its pipeline hook (plan §5).

Behaviour under test: application/services/answerability (pure) and
ReasonerPipeline._assess_answerability. No existing test file covers them.
"""

from types import SimpleNamespace

import pytest

from reasoner.application.pipeline import ReasonerPipeline
from reasoner.application.services.answerability import (
    ANSWER,
    ANSWER_WITH_CAVEATS,
    REFER,
    assess_answerability,
    audit_failures,
    critic_disagreement,
)
from reasoner.domain.models import ClaimLabel

V, H, U = ClaimLabel.VERIFIED, ClaimLabel.HYPOTHESIS, ClaimLabel.UNKNOWN
BAD_AUDIT = {"evaluation": [{"claim": "a", "verdict": "unsupported"}]}


@pytest.mark.parametrize("labels,audit,picks,level", [
    ({"a": V, "b": V}, None, (), ANSWER),
    ({"a": V, "b": H}, None, (), ANSWER_WITH_CAVEATS),  # 50% unverified
    ({"a": V, "b": V}, BAD_AUDIT, (), ANSWER_WITH_CAVEATS),  # audit flag alone
    ({"a": H, "b": U, "c": H, "d": V}, None, (), ANSWER_WITH_CAVEATS),  # 75%, one signal
    ({"a": H, "b": U, "c": H, "d": V}, BAD_AUDIT, (), REFER),
    ({"a": H, "b": U}, None, ("g1", "g2"), REFER),  # critic split
    ({}, None, (), ANSWER_WITH_CAVEATS),  # nothing labelled
])
def test_level_table(labels, audit, picks, level):
    assert assess_answerability(labels, audit, picks).level == level


def test_no_critic_scores_is_fine():
    assert critic_disagreement([]) is None
    assert critic_disagreement(["g1"]) is None
    assert assess_answerability({"a": V}, None, []).level == ANSWER


def test_disagreement_value():
    assert critic_disagreement(["g1", "g1", "g2"]) == pytest.approx(1 / 3)


def test_audit_failures_tolerates_shapes():
    assert audit_failures(None) == 0
    assert audit_failures({"evaluation": ["claim is overstated", "fine", {"x": "ok"}]}) == 1


def test_reasons_are_reported():
    r = assess_answerability({"a": H}, BAD_AUDIT, ())
    assert any("not verified" in x for x in r.reasons)
    assert any("flagged" in x for x in r.reasons)


def _pipeline_with(fs, critics=()):
    state = SimpleNamespace(final_solution=fs, critic_scores=list(critics), degradations=[])
    return ReasonerPipeline.__new__(ReasonerPipeline), state


def test_hook_sets_reliability_only_on_scoped_runs():
    pipe, state = _pipeline_with(
        SimpleNamespace(scope={}, claim_labels={"a": H}, verification_audit={}, reliability={})
    )
    pipe._assess_answerability(state)
    assert state.final_solution.reliability == {}

    pipe, state = _pipeline_with(
        SimpleNamespace(
            scope={"as_of": "2026-11-14"}, claim_labels={"a": H},
            verification_audit={}, reliability={},
        )
    )
    pipe._assess_answerability(state)
    assert state.final_solution.reliability["level"] == ANSWER_WITH_CAVEATS


def test_hook_with_no_solution_is_a_noop():
    pipe, state = _pipeline_with(None)
    pipe._assess_answerability(state)
