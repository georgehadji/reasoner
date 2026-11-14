"""Constants for the Evolution Agent (#4) — governed harness mutation.

Paper grounding: §3.5.2 (Evolution Agent), §3.5.3 (governed mutation).
"""

from __future__ import annotations


# ── Cross-lab diversity ──
# Minimum number of distinct training ecosystems Phase-2 must span.
EVOLUTION_MIN_CROSS_LAB_DIVERSITY: int = 2
# If the mutation removes a fallback chain, the terminal must be a different lab.
EVOLUTION_REQUIRE_CROSS_LAB_FALLBACK_TERMINAL: bool = True
