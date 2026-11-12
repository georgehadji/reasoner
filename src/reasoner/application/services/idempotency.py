"""Idempotent run registration, shared by every inbound adapter.

``client_run_id`` is both the duplicate-run guard and the credit idempotency
key: registering it twice must return the same "already running" answer
whether the caller is the web UI, an agent's HTTP call, or an MCP tool. This
was previously duplicated between ``run_pipeline`` and ``run_followup_pipeline``
in ``api/__init__.py`` -- copy/paste is how the next adapter forgets it.

Raises plain exceptions rather than ``HTTPException``: this module has no
FastAPI dependency, so an adapter translates these at its own boundary
(``application`` may not import ``reasoner.api``).
"""

from __future__ import annotations

import logging
import uuid

from reasoner.core.degrade import degraded

logger = logging.getLogger(__name__)


class RunStateUnavailableError(Exception):
    """The idempotency store (Redis) is not authoritative right now.

    Retryable -- the caller should back off and try again once the store
    recovers, rather than risk a duplicate charge by proceeding without it.
    """

    def __init__(self, retry_after_seconds: int = 10):
        self.retry_after_seconds = retry_after_seconds
        super().__init__("Run state store unavailable")


class RunAlreadyInProgressError(Exception):
    """``client_run_id`` is already registered to a run in flight."""

    def __init__(self, client_run_id: str):
        self.client_run_id = client_run_id
        super().__init__(f"Run {client_run_id} is already in progress")


class RunAlreadyFinishedError(RunAlreadyInProgressError):
    """``client_run_id`` belongs to a run that already ended and kept its claim.

    Still a 409, and still a RunAlreadyInProgressError for callers that do not
    care which: only the message differs, so a retry is not told the run is live.
    """

    def __init__(self, client_run_id: str):
        super().__init__(client_run_id)
        self.args = (f"Run {client_run_id} already finished",)


def claim_key(owner_key: str, client_run_id: str) -> str:
    """The claim for one caller's *client_run_id*.

    Scoped to the owner: an idempotency key is a promise to one caller, not a
    global name. A global key let one tenant's id lock out another's
    (docs/plans/audit-remediation-2-2026-10-20.md SEC-7).
    """
    return f"{owner_key}:{client_run_id}"


async def register_run(client_run_id: str | None, *, owner_key: str) -> str | None:
    """Atomically claim *client_run_id* for *owner_key*, or raise if that is not possible.

    Returns the claim, for :func:`release_run` and :func:`complete_run`. It is the
    key plus this holder's token, so a late release by an earlier holder cannot
    free a later holder's claim. A None or empty id is a no-op
    returning None: idempotency is opt-in per request, exactly as it is on
    ``RunRequest.client_run_id`` today.

    *owner_key* is the user id, or ``anon:<client ip>`` for an anonymous caller.
    """
    if not client_run_id:
        return None

    from reasoner.infrastructure.redis.run_state import _run_state_manager

    key = claim_key(owner_key, client_run_id)
    token = uuid.uuid4().hex
    finished = False
    try:
        authoritative = await _run_state_manager.is_authoritative()
        claimed = authoritative and await _run_state_manager.try_register(key, token=token)
        finished = authoritative and not claimed and await _run_state_manager.claim_finished(key)
    except Exception as exc:
        logger.warning("Idempotency check failed for %s: %s", client_run_id, exc)
        raise RunStateUnavailableError(retry_after_seconds=5) from exc

    if not authoritative:
        raise RunStateUnavailableError(retry_after_seconds=10)
    if finished:
        raise RunAlreadyFinishedError(client_run_id)
    if not claimed:
        raise RunAlreadyInProgressError(client_run_id)
    return f"{key}:{token}"


def _split(claim: str) -> tuple[str, str]:
    key, _, token = claim.rpartition(":")
    return key, token


async def release_run(claim: str | None) -> None:
    """Give back a claim whose run did not complete, so the caller can retry.

    A run refused with 402, or one that failed or was dropped mid-stream, kept
    its claim for the full TTL, so the documented retry got 409 for an hour
    (SEC-7). A completed run keeps its claim: a duplicate of it must still 409.
    Only the holder's own token releases: a second release, or one from a run
    that has since been retried, is a no-op.
    Never raises; an unreleased claim expires at its TTL.
    """
    if not claim:
        return

    from reasoner.infrastructure.redis.run_state import _run_state_manager

    try:
        await _run_state_manager.release(*_split(claim))
    except Exception as exc:
        degraded(
            "idempotency.release_run", None, exc=exc,
            detail=f"claim {claim} held until its TTL",
        )


async def complete_run(claim: str | None) -> None:
    """Mark a claim finished: it keeps its TTL, and a duplicate is told so.

    Never raises: the claim still blocks the duplicate as "in progress" if this
    write is lost.
    """
    if not claim:
        return

    from reasoner.infrastructure.redis.run_state import _run_state_manager

    try:
        await _run_state_manager.complete(*_split(claim))
    except Exception as exc:
        degraded("idempotency.complete_run", None, exc=exc, detail=f"claim {claim} left unmarked")


__all__ = [
    "RunAlreadyFinishedError",
    "RunAlreadyInProgressError",
    "RunStateUnavailableError",
    "claim_key",
    "complete_run",
    "register_run",
    "release_run",
]
