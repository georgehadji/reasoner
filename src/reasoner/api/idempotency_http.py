"""HTTP translation for the application-layer idempotency guard.

Every route that accepts ``client_run_id`` calls :func:`register_run_or_error`
so a duplicate id always produces the same 409, and a Redis outage always
produces the same 503 -- one implementation, shared the way ``auth_deps.py``
already is, instead of copied per route.
"""

from __future__ import annotations

from fastapi import HTTPException

from reasoner.application.services.idempotency import (
    RunAlreadyInProgressError,
    RunStateUnavailableError,
    register_run,
)


async def register_run_or_error(client_run_id: str | None) -> None:
    """Claim *client_run_id*, or raise the matching HTTPException.

    A store outage and a genuine duplicate are distinguished so a caller does
    not mistake "try again shortly" for "this exact run already happened".
    """
    try:
        await register_run(client_run_id)
    except RunStateUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail="Run state store unavailable. Retry after Redis recovers.",
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except RunAlreadyInProgressError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Run {exc.client_run_id} is already in progress",
        ) from exc


__all__ = ["register_run_or_error"]
