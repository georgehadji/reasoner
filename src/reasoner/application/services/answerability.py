"""Answerability: should a high-stakes answer be shown plainly, with caveats, or with a referral?

Pure and deterministic: no LLM call, no state write. The caller (the pipeline)
applies the result at the edge. Thresholds are provisional until the §6
evaluation data tunes them (docs/plans/high-stakes-reliability.md).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from reasoner.core.constants_limits import (
    ANSWERABILITY_CAVEAT_UNVERIFIED_SHARE,
    ANSWERABILITY_DISAGREEMENT,
    ANSWERABILITY_REFER_UNVERIFIED_SHARE,
)

ANSWER = "answer"
ANSWER_WITH_CAVEATS = "answer_with_caveats"
REFER = "refer"

_AUDIT_FAIL_WORDS = ("unsupported", "contradict", "overstated", "incorrect", "false", "fail")


@dataclass(frozen=True, slots=True)
class Answerability:
    level: str
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level, "reasons": list(self.reasons)}


def unverified_share(claim_labels: Mapping[str, Any]) -> float:
    """Share of claims that are not VERIFIED. 0.0 when there are no claims."""
    if not claim_labels:
        return 0.0
    ok = sum(1 for v in claim_labels.values() if str(getattr(v, "value", v)).upper() == "VERIFIED")
    return 1.0 - ok / len(claim_labels)


def audit_failures(verification_audit: Mapping[str, Any] | None) -> int:
    """Evaluation items the independent checker flagged. Tolerates any item shape."""
    count = 0
    for item in (verification_audit or {}).get("evaluation", []) or []:
        text = " ".join(str(v) for v in item.values()) if isinstance(item, dict) else str(item)
        if any(word in text.lower() for word in _AUDIT_FAIL_WORDS):
            count += 1
    return count


def critic_disagreement(top_picks: Iterable[str]) -> float | None:
    """1 - (share of critics agreeing on the top candidate). None when fewer than 2 critics."""
    picks = [p for p in top_picks if p]
    if len(picks) < 2:
        return None
    return 1.0 - Counter(picks).most_common(1)[0][1] / len(picks)


def assess_answerability(
    claim_labels: Mapping[str, Any],
    verification_audit: Mapping[str, Any] | None = None,
    critic_top_picks: Iterable[str] = (),
) -> Answerability:
    share = unverified_share(claim_labels)
    failures = audit_failures(verification_audit)
    spread = critic_disagreement(critic_top_picks)  # absent for some methods: never required

    reasons: list[str] = []
    if not claim_labels:
        reasons.append("no claim was labelled")
    elif share >= ANSWERABILITY_CAVEAT_UNVERIFIED_SHARE:
        reasons.append(f"{share:.0%} of claims are not verified")
    if failures:
        reasons.append(f"the independent check flagged {failures} claim(s)")
    disagree = spread is not None and spread >= ANSWERABILITY_DISAGREEMENT
    if disagree:
        reasons.append("the critics disagreed on the best answer")

    if (
        share >= ANSWERABILITY_REFER_UNVERIFIED_SHARE
        and claim_labels
        and (failures or disagree)
    ):
        return Answerability(REFER, tuple(reasons))
    if reasons:
        return Answerability(ANSWER_WITH_CAVEATS, tuple(reasons))
    return Answerability(ANSWER)
