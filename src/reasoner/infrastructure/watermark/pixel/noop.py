"""Null Object PixelScrubberPort — the bound default (ADR-8).

Pixel-domain watermark removal (CtrlRegen/DiffusionPurification-class
backends) needs roughly 10 GB of model weights and a GPU, which does not
belong in Reasoner's runtime or container image. This adapter always reports
itself unavailable so callers fail closed rather than silently pretend to
remove something. Mirrors infrastructure/execution/noop_executor.py's
precedent: `NoopExecutor` is used instead of `None` so callers don't need a
separate "nothing bound" branch, and it never simulates the real operation.
"""

from __future__ import annotations

from reasoner.core.ports.watermark_port import ScrubOutcome


class NoopPixelScrubber:
    """Always unavailable. Never simulates pixel-domain removal."""

    async def available(self) -> bool:
        return False

    async def scrub(self, data: bytes, *, strength: float = 0.25) -> ScrubOutcome:
        return ScrubOutcome(
            data=data,
            degraded=True,
            degraded_reason=(
                "pixel-domain removal is not configured on this deployment; "
                "input returned unchanged"
            ),
        )


__all__ = ["NoopPixelScrubber"]
