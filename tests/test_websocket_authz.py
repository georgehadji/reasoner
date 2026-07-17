"""Tests for WebSocket pipeline ownership enforcement.

Uses a real PipelineOwnershipRepository against an isolated temp SQLite file,
patched in as the singleton _authorized_for_pipeline resolves against —
deliberately not a mock of the (now removed) JSON-file lookup function. A
mistargeted mock of that function is exactly what let the fail-open
authorization bug through this suite undetected for a while (see this file's
git history / the Phase 0 fix): the patch targeted a module the code under
test never imported from, so the mock never applied and the real (fail-open)
lookup ran silently. Testing against the real repo removes that entire class
of mistake — there is no second module path to get wrong.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from reasoner.infrastructure.persistence.pipeline_ownership_repo import (
    PipelineOwnershipRepository,
)
from reasoner.infrastructure.websocket.manager import (
    WebSocketManager,
    handle_websocket_message,
)


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        from starlette.websockets import WebSocketState
        self.client_state = WebSocketState.CONNECTED

    async def accept(self):
        pass

    async def send_text(self, text: str) -> None:
        self.sent.append(text)


@pytest.fixture
def ownership_repo(tmp_path: Path):
    """A real, isolated PipelineOwnershipRepository patched in as the
    singleton the ownership check resolves."""
    repo = PipelineOwnershipRepository(db_path=tmp_path / "ownership_test.db")
    with patch(
        "reasoner.infrastructure.persistence.pipeline_ownership_repo.get_pipeline_ownership_repo",
        return_value=repo,
    ):
        yield repo


@pytest.mark.asyncio
async def test_dynamic_subscribe_ownership_enforced(ownership_repo):
    """User B may not subscribe to User A's pipeline."""
    await ownership_repo.set_owner("pipeline-123", "user-a", "pipeline-123")

    manager = WebSocketManager()
    ws = FakeWebSocket()
    await manager.connect(ws, "conn-1", metadata={"user_id": "user-b"})

    await handle_websocket_message(
        manager,
        "conn-1",
        {"type": "subscribe", "pipeline_id": "pipeline-123"},
    )

    # Should have received an error, not a subscribed confirmation
    assert len(ws.sent) == 2  # welcome + error
    assert '"type": "error"' in ws.sent[1]
    assert "Not authorized" in ws.sent[1]
    assert "pipeline-123" not in manager.subscriptions


@pytest.mark.asyncio
async def test_dynamic_subscribe_same_user_allowed(ownership_repo):
    """A user subscribing to their own pipeline should succeed."""
    await ownership_repo.set_owner("pipeline-456", "user-a", "pipeline-456")

    manager = WebSocketManager()
    ws = FakeWebSocket()
    await manager.connect(ws, "conn-2", metadata={"user_id": "user-a"})

    await handle_websocket_message(
        manager,
        "conn-2",
        {"type": "subscribe", "pipeline_id": "pipeline-456"},
    )

    assert "pipeline-456" in manager.subscriptions
    assert '"type": "subscribed"' in ws.sent[1]


@pytest.mark.asyncio
async def test_dynamic_subscribe_unknown_pipeline_denied(ownership_repo):
    """No ownership record at all must deny (fail closed).

    This is the case the old JSON-file store got backwards: a missing file
    or a pipeline_id never written also returned None, and every caller
    (including this one) treated that as "no owner recorded, so anyone may
    access it". An unrecorded pipeline is now denied, not allowed.
    """
    manager = WebSocketManager()
    ws = FakeWebSocket()
    await manager.connect(ws, "conn-3", metadata={"user_id": "user-a"})

    await handle_websocket_message(
        manager,
        "conn-3",
        {"type": "subscribe", "pipeline_id": "never-recorded"},
    )

    assert '"type": "error"' in ws.sent[1]
    assert "never-recorded" not in manager.subscriptions


@pytest.mark.asyncio
async def test_dynamic_subscribe_anonymous_owner_allowed(ownership_repo):
    """A pipeline explicitly recorded with no owner (anonymous run) is
    accessible to anyone -- distinct from no record existing at all."""
    await ownership_repo.set_owner("anon-pipeline", None, "anon-pipeline")

    manager = WebSocketManager()
    ws = FakeWebSocket()
    await manager.connect(ws, "conn-4", metadata={"user_id": "user-anyone"})

    await handle_websocket_message(
        manager,
        "conn-4",
        {"type": "subscribe", "pipeline_id": "anon-pipeline"},
    )

    assert "anon-pipeline" in manager.subscriptions
    assert '"type": "subscribed"' in ws.sent[1]


@pytest.mark.asyncio
async def test_dynamic_subscribe_lookup_error_denied():
    """A storage error during the ownership lookup must deny -- never let an
    exception be treated as "no owner recorded, so allow". This is the exact
    failure mode the JSON-file store had (any read error collapsed to the
    same None as "no owner")."""
    manager = WebSocketManager()
    ws = FakeWebSocket()
    await manager.connect(ws, "conn-5", metadata={"user_id": "user-a"})

    with patch(
        "reasoner.infrastructure.persistence.pipeline_ownership_repo.get_pipeline_ownership_repo",
        side_effect=RuntimeError("db is on fire"),
    ):
        await handle_websocket_message(
            manager,
            "conn-5",
            {"type": "subscribe", "pipeline_id": "pipeline-999"},
        )

    assert '"type": "error"' in ws.sent[1]
    assert "pipeline-999" not in manager.subscriptions
