"""Stakes policy: a pure function over the routing decision.

Never mutates its input and never touches price: the user's tier is not part of
a GateDecision, so a Budget run stays Budget.
"""

from __future__ import annotations

from reasoner.domain.stakes import StakesProfile
from reasoner.hypergate.gate_agent import GateDecision

# Methods that retrieve and check; anything else is routed to GROUNDED_DEFAULT.
GROUNDED_METHODS = frozenset({"research", "cove"})
GROUNDED_DEFAULT = "research"


def apply_stakes_policy(decision: GateDecision, profile: StakesProfile) -> GateDecision:
    """Return ``decision`` rerouted to a grounded pipeline when ``profile`` is high-stakes."""
    if not profile.is_high:
        return decision
    update: dict[str, object] = {"stakes": profile.to_dict()}
    if decision.action in ("direct", "web_search"):
        update.update(action="pipeline", method=GROUNDED_DEFAULT, complexity="complex")
    elif decision.method not in GROUNDED_METHODS:
        update["method"] = GROUNDED_DEFAULT
    else:
        return decision.model_copy(update=update)
    update["reasoning"] = f"{decision.reasoning or ''} [stakes:{profile.domain.value}]".strip()
    return decision.model_copy(update=update)
