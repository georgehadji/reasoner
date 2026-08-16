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


async def register_run(client_run_id: str | None) -> None:
    """Atomically claim *client_run_id*, or raise if that is not possible.

    A None or empty id is a no-op: idempotency is opt-in per request, exactly
    as it is on ``RunRequest.client_run_id`` today.
    """
    if not client_run_id:
        return

    from reasoner.infrastructure.redis.run_state import _run_state_manager

    try:
        authoritative = await _run_state_manager.is_authoritative()
        claimed = authoritative and await _run_state_manager.try_register(client_run_id)
    except Exception as exc:
        logger.warning("Idempotency check failed for %s: %s", client_run_id, exc)
        raise RunStateUnavailableError(retry_after_seconds=5) from exc

    if not authoritative:
        raise RunStateUnavailableError(retry_after_seconds=10)
    if not claimed:
        raise RunAlreadyInProgressError(client_run_id)


__all__ = ["RunAlreadyInProgressError", "RunStateUnavailableError", "register_run"]
