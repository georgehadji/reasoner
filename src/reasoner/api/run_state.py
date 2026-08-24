"""Backward-compatibility shim for RunStateStore."""

from __future__ import annotations

import warnings

warnings.warn(
    "reasoner.api.run_state is a backward-compat shim; import from reasoner.infrastructure.redis.in_memory instead.",
    DeprecationWarning,
    stacklevel=2,
)

