"""A method the user names in the prompt is the method that runs.

"use the iterative-critique method to propose what subject to write an article
in linkedin ..." ran the article pipeline (2026-11-09): HyperGate never looked
for a named method, and the orchestrator's article regex overrode the gate.
"""

from __future__ import annotations

import pytest

from reasoner.hypergate.hyperagent import fast_path, named_method

PROMPT = (
    "use the iterative-critique method to propose what subject to write an "
    "article in linkedin for establishing authority in the field of ai"
)


@pytest.mark.parametrize(
    ("problem", "method"),
    [
        (PROMPT, "iterative_critique"),
        ("Using the Bayesian approach, estimate whether our churn will rise", "bayesian"),
        ("Apply the pre-mortem method to our product launch plan", "pre_mortem"),
        ("Run the tree of thoughts method on this puzzle", "tot"),
        ("With the chain-of-verification technique, check these claims", "cove"),
        ("Use the debate method: should we raise VC money?", "debate"),
        ("use the self discover method for this question", "self_discover"),
    ],
)
def test_named_method_is_recognised(problem, method):
    assert named_method(problem) == method


@pytest.mark.parametrize(
    "problem",
    [
        "write an article about research methods in psychology",
        "use research to back every claim in this essay",
        "Should we debate this at the board meeting?",
        "What is the scientific method?",
    ],
)
def test_ordinary_wording_names_no_method(problem):
    assert named_method(problem) is None


def test_named_method_wins_over_writing_intent():
    decision = fast_path(PROMPT)
    assert decision is not None
    assert decision.action == "pipeline"
    assert decision.method == "iterative_critique"
