"""Sandbox worker HTTP API — the only surface `backend` talks to for code
execution.

Runs inside its own container on the internal Compose network (never a
published host port); `backend` reaches it as
``http://sandbox-worker:8901`` with a bearer token. The request schema
forbids extra fields so no image/command/mount/environment can ever come
from the caller — those are fixed by the registered ``LanguageRunner``.
"""

from __future__ import annotations

import hmac
import logging
import os

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from reasoner.core.ports.code_executor import ExecutionLimits
from reasoner.infrastructure.execution.sandbox_worker.docker_runner import (
    check_docker_health,
    run_in_container,
)

logger = logging.getLogger(__name__)

_TOKEN = os.getenv("SANDBOX_WORKER_TOKEN", "")

app = FastAPI(
    title="Reasoner Sandbox Worker",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class ExecuteRequest(BaseModel):
    """extra="forbid" is the load-bearing control here: it's what stops a
    caller from ever injecting an image, command, mount, or env var."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., max_length=200_000)
    language: str = "python"
    stdin: str = Field("", max_length=1_000_000)
    timeout_ms: int = Field(30_000, ge=1_000, le=120_000)
    memory_limit_mb: int = Field(256, ge=16, le=1024)
    max_output_bytes: int = Field(65_536, ge=1_024, le=1_048_576)


class ExecuteResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    duration_ms: int
    truncated: bool
    blocked: bool
    blocked_reason: str
    policy_version: str


def _require_token(authorization: str | None) -> None:
    if not _TOKEN:
        # Fail closed: an unconfigured worker must refuse everything, not
        # accept requests because there's nothing to compare against.
        raise HTTPException(status_code=503, detail="Sandbox worker has no token configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    provided = authorization[len("Bearer "):]
    if not hmac.compare_digest(provided, _TOKEN):
        raise HTTPException(status_code=401, detail="Invalid bearer token")


@app.get("/health")
async def health() -> dict:
    if not await check_docker_health():
        raise HTTPException(status_code=503, detail="Docker engine or sandbox image unavailable")
    return {"status": "ok"}


@app.post("/execute", response_model=ExecuteResponse)
async def execute(
    request: ExecuteRequest,
    authorization: str | None = Header(default=None),
) -> ExecuteResponse:
    _require_token(authorization)

    limits = ExecutionLimits(
        timeout_ms=request.timeout_ms,
        memory_limit_mb=request.memory_limit_mb,
        max_output_bytes=request.max_output_bytes,
    )
    result = await run_in_container(
        request.code,
        language=request.language,
        stdin=request.stdin,
        limits=limits,
    )
    return ExecuteResponse(
        success=result.success,
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        timed_out=result.timed_out,
        duration_ms=result.duration_ms,
        truncated=result.truncated,
        blocked=result.blocked,
        blocked_reason=result.blocked_reason,
        policy_version=result.policy_version,
    )
