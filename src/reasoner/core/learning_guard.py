"""Invariant: the online learner's reward signal must never depend on user approval.

Mirrors application/services/harness_guard.check_mutation_invariants — same
(ok, reason) shape, same "fail the check, don't fail silently" contract. Lives
in core/, not application/services/, because its only caller
(infrastructure/learning/online_learner.OnlineLearner.__init__) is
infrastructure — the Dependency Rule forbids infrastructure importing
application, and core has no outer dependencies, so this is the correct home
for a pure check both layers can reach.

WHY THIS EXISTS
===============
Sycophancy in deployed models is widely understood to emerge from optimising on
human approval. compute_reward() (infrastructure/learning/quality_signals.py)
deliberately reads only completion, JSON validity, critique score, and
stress-test survival — never a user rating. FeedbackStore
(infrastructure/persistence/feedback_store.py) is one import away from
ThompsonSampler.update(), and wiring them together is exactly the kind of
change that reads as an obvious improvement in review. This guard makes the
absence a checked invariant instead of an accident.

See docs/SYCOPHANCY_MITIGATION.md §3.1 and docs/plans/sycophancy-mitigation.md
workstream W5.
"""

from __future__ import annotations

# Field names that would mean a user-supplied approval signal is feeding the
# learner. Checked against the telemetry dataclass's own field names, not
# against a runtime value — this catches the wiring before it ever runs.
_APPROVAL_FIELD_NAMES = frozenset({
    "rating", "upvote", "downvote", "thumbs", "user_score",
    "feedback", "satisfaction", "nps", "stars", "approval",
})


def check_reward_signal_purity(telemetry_field_names: frozenset[str]) -> tuple[bool, str]:
    """Reject a telemetry schema that carries a user-approval-shaped field.

    Args:
        telemetry_field_names: field names of the dataclass compute_reward()
            is called with (e.g. ``frozenset(LLMCallTelemetry.__dataclass_fields__)``).

    Returns:
        (ok, reason) — False + reason if an approval-shaped field is present.
    """
    hit = telemetry_field_names & _APPROVAL_FIELD_NAMES
    if hit:
        return False, (
            f"Telemetry schema carries approval-shaped field(s) {sorted(hit)}. "
            "The online learner must optimise on process quality (completion, "
            "JSON validity, critique score, stress-test survival), never on user "
            "approval — that is the mechanism sycophancy is trained by. Route "
            "user feedback to analytics, not to the reward signal."
        )
    return True, ""


__all__ = ["check_reward_signal_purity"]
