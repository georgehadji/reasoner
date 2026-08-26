"""Sycophancy-mitigation constants — zero magic numbers outside this file.

See docs/SYCOPHANCY_MITIGATION.md and docs/plans/sycophancy-mitigation.md.
"""
from __future__ import annotations

# W6 — framing-divergence measurement
FRAMING_DIVERGENCE_FLOOR = 0.15   # above this, DIRECT is tracking the user's framing
SELF_FOCUS_SAMPLE_RATE = 0.05     # telemetry sampling rate for the self-focus scorer
