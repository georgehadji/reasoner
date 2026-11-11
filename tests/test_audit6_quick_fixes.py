"""Audit 6 quick fixes (docs/plans/audit-remediation-6-2026-11-10.md, round 2).

Non-ASCII secrets must be refused, not crash; the ACR mode route is gone;
upload failures are a 500, not a 200.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from reasoner.api import admin_auth, csrf
from reasoner.api.routes import admin, uploads
from reasoner.application.services import ws_ticket
from reasoner.core.constant_time import constant_time_equals
from reasoner.core.settings import settings
from reasoner.domain.saas import User
from reasoner.neuro import server as neuro_server

pytestmark = pytest.mark.unit

NON_ASCII = "café"


def test_constant_time_equals_handles_non_ascii():
    assert constant_time_equals(NON_ASCII, NON_ASCII)
    assert not constant_time_equals(NON_ASCII, "cafe")
    assert not constant_time_equals("", NON_ASCII)


def test_csrf_verify_refuses_non_ascii_signature():
    assert csrf.verify_csrf_token(f"1:2:3.{NON_ASCII}") is False
    assert csrf.verify_csrf_token(f"1:2:{NON_ASCII}.{'0' * 64}") is False


def test_admin_key_refuses_non_ascii(monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "right-key")
    assert admin_auth.verify_admin_key("right-key") is True
    assert admin_auth.verify_admin_key(NON_ASCII) is False


@pytest.mark.asyncio
async def test_ws_ticket_refuses_non_ascii_signature():
    ticket = ws_ticket.issue_ticket("u1")
    forged = ticket.rsplit(".", 1)[0] + "." + NON_ASCII
    assert await ws_ticket.redeem_ticket(forged) is None


def test_neuro_key_non_ascii_is_403(monkeypatch):
    monkeypatch.setattr(type(settings), "neuro_internal_key", property(lambda _self: "internal"))
    request = SimpleNamespace(headers={"X-Neuro-Key": NON_ASCII})
    with pytest.raises(HTTPException) as exc:
        neuro_server.require_neuro_key(request)
    assert exc.value.status_code == 403


def test_acr_mode_route_is_gone():
    paths = {getattr(r, "path", "") for r in admin.router.routes}
    assert "/api/admin/acr/mode" not in paths


class _Item:
    filename = "a.txt"

    async def read(self, _size):
        return b""


@pytest.mark.asyncio
async def test_upload_failure_is_a_500(monkeypatch):
    form = SimpleNamespace(getlist=lambda _k: [_Item()])
    request = SimpleNamespace(headers={}, form=AsyncMock(return_value=form))
    usage = SimpleNamespace(reserve=AsyncMock(return_value=True), adjust=AsyncMock())
    monkeypatch.setattr(uploads, "get_upload_usage_repo", lambda: usage)
    monkeypatch.setattr(uploads, "save_uploaded_file", AsyncMock(side_effect=RuntimeError("disk")))
    user = User(id=uuid4(), email="u@example.com")
    with pytest.raises(HTTPException) as exc:
        await uploads.upload_file(request, False, user, None, None)
    assert exc.value.status_code == 500
    assert "disk" not in str(exc.value.detail)
    usage.adjust.assert_awaited()
