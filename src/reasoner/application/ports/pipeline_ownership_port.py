"""
Pipeline Ownership Port — who is allowed to read/stop/resume a pipeline run.

Replaces the JSON-file store (domain/pipeline_owner.py), whose lookup
swallowed every read error (missing file, corrupt JSON) into `None`, and
whose every caller treated `None` as authorization to proceed. That made
"no ownership record" and "explicitly unowned" and "the store is broken"
indistinguishable — a fail-open authorization bug.

This port distinguishes all three: `get_owner` returns `None` only when no
record exists for the pipeline at all (callers should fail closed on that),
an `OwnershipRecord` with `user_id=None` for an explicitly anonymous/unowned
run (callers should allow), or a record with a `user_id` to check for a
match. A genuine storage error must propagate as an exception rather than
collapse to `None` — callers fail closed on errors too.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OwnershipRecord:
    """An ownership record for one pipeline run.

    `user_id=None` means the run was explicitly created without an owner
    (e.g. an anonymous/unauthenticated request) — distinct from no record
    existing at all, which `PipelineOwnershipPort.get_owner` signals by
    returning `None` rather than a record.
    """

    user_id: str | None
    run_id: str


class PipelineOwnershipPort(Protocol):
    """Port for persisting and querying pipeline ownership."""

    async def get_owner(self, pipeline_id: str) -> OwnershipRecord | None:
        """Return the ownership record for *pipeline_id*.

        Returns None if no record exists for this pipeline at all (unknown
        pipeline — callers should fail closed, not treat this as allowed).
        Raises on a genuine storage/lookup failure; callers must not
        interpret an exception as "unowned".
        """
        ...

    async def set_owner(self, pipeline_id: str, user_id: str | None, run_id: str) -> None:
        """Persist (or update) the owner of *pipeline_id*. Idempotent upsert."""
        ...

    async def list_pipeline_ids_for_user(self, user_id: str) -> list[str]:
        """Return every pipeline_id owned by *user_id* (for GDPR erasure)."""
        ...
