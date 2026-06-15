"""Constants for the Evolution Agent (#4) — governed harness mutation.

Paper grounding: §3.5.2 (Evolution Agent), §3.5.3 (governed mutation).
"""

from __future__ import annotations

# ── Mutation limits ──
# Maximum number of mutations per evolution run.
EVOLUTION_MAX_MUTATIONS_PER_RUN: int = 5
# Maximum number of held-out evaluation problems.
EVOLUTION_HELD_OUT_SET_SIZE: int = 20

# ── Regression gate ──
# Minimum absolute improvement on the targeted metric to qualify for promotion.
EVOLUTION_MIN_IMPROVEMENT_DELTA: float = 0.05  # 5%
# Maximum acceptable regression on any non-targeted metric.
EVOLUTION_MAX_REGRESSION: float = 0.02  # 2%

# ── Cross-lab diversity ──
# Minimum number of distinct training ecosystems Phase-2 must span.
EVOLUTION_MIN_CROSS_LAB_DIVERSITY: int = 2
# If the mutation removes a fallback chain, the terminal must be a different lab.
EVOLUTION_REQUIRE_CROSS_LAB_FALLBACK_TERMINAL: bool = True
