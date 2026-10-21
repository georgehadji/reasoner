"""How a streaming run ended, as a closed set.

`PipelineExecutionPort.execute_run` used to encode this as "a state, or None,
plus whatever side effects it happened to have", so the handler could not tell
a finished run from a stopped one and dereferenced `None` after a refused one.
The handler matches on `status` instead, and each arm sees only what it can
use: `state` is None only for a run that never started.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from reasoner.domain.pipeline_state import PipelineState

RunStatus = Literal["completed", "cancelled", "failed", "rejected"]


@dataclass(frozen=True)
class RunOutcome:
    """completed: every phase ran. cancelled: the caller stopped it.
    failed: it broke part-way. rejected: it never started (plan cap, or an
    answer given without a pipeline)."""

    status: RunStatus
    state: PipelineState | None = None
    reason: str | None = None
