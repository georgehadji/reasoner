"""client_run_id is the only thing standing between a dropped connection and
a double-charged run. These pin the semantics that used to be duplicated,
untested, inline in two route handlers.
"""

from __future__ import annotations

import pytest

from reasoner.application.services.idempotency import (
    RunAlreadyInProgressError,
    RunStateUnavailableError,
    register_run,
)

pytestmark = pytest.mark.unit


class FakeRunStateManager:
    def __init__(
        self, *, authoritative: bool = True, registered: bool = False, explode: bool = False
    ):
        self.authoritative = authoritative
        self.registered = registered
        self.explode = explode
        self.register_calls: list[str] = []

    async def is_authoritative(self) -> bool:
        if self.explode:
            raise ConnectionError("redis unreachable")
        return self.authoritative

    async def try_register(self, client_run_id: str) -> bool:
        self.register_calls.append(client_run_id)
        if self.registered:
            return False
        self.registered = True
        return True


@pytest.fixture
def patched_manager(monkeypatch):
    def _patch(**kwargs) -> FakeRunStateManager:
        fake = FakeRunStateManager(**kwargs)
        monkeypatch.setattr(
            "reasoner.infrastructure.redis.run_state._run_state_manager", fake
        )
        return fake

    return _patch


# ── application layer ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blank_id_is_a_no_op(patched_manager):
    fake = patched_manager()

    await register_run(None)
    await register_run("")

    assert fake.register_calls == []


@pytest.mark.asyncio
async def test_a_fresh_id_registers_cleanly(patched_manager):
    fake = patched_manager()

    await register_run("run-1")

    assert fake.register_calls == ["run-1"]


@pytest.mark.asyncio
async def test_a_duplicate_id_is_rejected(patched_manager):
    patched_manager(registered=True)

    with pytest.raises(RunAlreadyInProgressError) as exc_info:
        await register_run("run-1")

    assert exc_info.value.client_run_id == "run-1"


@pytest.mark.asyncio
async def test_a_non_authoritative_store_fails_closed(patched_manager):
    patched_manager(authoritative=False)

    with pytest.raises(RunStateUnavailableError) as exc_info:
        await register_run("run-1")

    assert exc_info.value.retry_after_seconds == 10


@pytest.mark.asyncio
async def test_an_unexpected_redis_error_becomes_a_retryable_unavailable(patched_manager):
    patched_manager(explode=True)

    with pytest.raises(RunStateUnavailableError) as exc_info:
        await register_run("run-1")

    assert exc_info.value.retry_after_seconds == 5


# ── HTTP translation ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_http_translator_maps_duplicate_to_409(patched_manager):
    from fastapi import HTTPException

    from reasoner.api.idempotency_http import register_run_or_error

    patched_manager(registered=True)

    with pytest.raises(HTTPException) as exc_info:
        await register_run_or_error("run-1")

    assert exc_info.value.status_code == 409
    assert "run-1" in exc_info.value.detail


@pytest.mark.asyncio
async def test_http_translator_maps_store_outage_to_503_with_retry_after(patched_manager):
    from fastapi import HTTPException

    from reasoner.api.idempotency_http import register_run_or_error

    patched_manager(authoritative=False)

    with pytest.raises(HTTPException) as exc_info:
        await register_run_or_error("run-1")

    assert exc_info.value.status_code == 503
    assert exc_info.value.headers["Retry-After"] == "10"


@pytest.mark.asyncio
async def test_http_translator_passes_through_a_clean_registration(patched_manager):
    from reasoner.api.idempotency_http import register_run_or_error

    patched_manager()

    await register_run_or_error("run-1")  # must not raise
