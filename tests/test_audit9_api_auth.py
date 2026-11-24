"""Audit 9: body caps, read scopes, discover cache, feedback, metrics IPs, deleted accounts."""

from __future__ import annotations

import importlib
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request

from reasoner.api.middleware import BodySizeLimitMiddleware
from reasoner.domain.saas import User

pytestmark = pytest.mark.unit


async def _post(app, path, content, headers=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.post(path, content=content, headers=headers)


# 1. body caps ----------------------------------------------------------------


def _limits_app():
    app = FastAPI()

    @app.post("/api/generate-image")
    @app.post("/api/provenance/inspect")
    async def echo(request: Request):
        return {"n": len(await request.body())}

    app.add_middleware(BodySizeLimitMiddleware, **BodySizeLimitMiddleware.app_limits())
    return app


def test_provenance_cap_is_base64_of_one_upload():
    from reasoner.core.constants import UPLOAD_MAX_FILE_BYTES

    cap = BodySizeLimitMiddleware.app_limits()["per_path"]["/api/provenance/"]
    assert cap < UPLOAD_MAX_FILE_BYTES * 1.5


@pytest.mark.asyncio
async def test_anonymous_generate_image_big_body_refused_but_authed_passes():
    body = b"x" * (2 * 2**20)
    anon = await _post(_limits_app(), "/api/generate-image", body)
    authed = await _post(
        _limits_app(), "/api/generate-image", body, headers={"Authorization": "Bearer a.b.c"}
    )
    assert anon.status_code == 413
    assert authed.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("junk", ["x", "Bearer t", "Basic a.b.c", "Bearer"])
async def test_junk_authorization_header_does_not_lift_the_anon_cap(junk):
    resp = await _post(
        _limits_app(), "/api/generate-image", b"x" * (2 * 2**20), headers={"Authorization": junk}
    )
    assert resp.status_code == 413


# 2. read scopes --------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "module,func,scope",
    [
        ("routes.history", "get_history", "history:read"),
        ("routes.history", "get_history_entry", "history:read"),
        ("routes.history", "get_tagged_history", "history:read"),
        ("routes.pipelines", "list_pipelines", "history:read"),
        ("routes.pipelines", "get_pipeline_status", "history:read"),
        ("routes.credits", "get_ledger", "read"),
        ("routes.uploads", "get_uploads", "read"),
        ("routes.uploads", "get_uploaded_file", "read"),
        ("routes.account_keys", "list_api_keys", "read"),
        ("billing_router", "get_subscription", "read"),
    ],
)
async def test_read_routes_enforce_scope(module, func, scope):
    from reasoner.api.dependencies import get_current_user

    fn = getattr(importlib.import_module(f"reasoner.api.{module}"), func)
    guard = inspect.signature(fn).parameters["user"].default.dependency
    assert guard is not get_current_user
    req = SimpleNamespace(state=SimpleNamespace(auth_method="api_key"))
    narrow = User(id=uuid4(), email="a@b.c", scopes={"run"})
    with pytest.raises(HTTPException) as e:
        await guard(req, narrow)
    assert e.value.status_code == 403 and scope in e.value.detail
    ok = User(id=uuid4(), email="a@b.c", scopes={scope})
    assert await guard(req, ok) is ok
    # JWT/session callers keep full access
    jwt_req = SimpleNamespace(state=SimpleNamespace(auth_method="bearer"))
    assert await guard(jwt_req, narrow) is narrow


# 3. discover cache -----------------------------------------------------------


@pytest.mark.asyncio
async def test_discover_is_cached_and_topic_normalized():
    from reasoner.api.routes import legacy_widgets as lw

    lw._discover_cache.clear()
    fake = AsyncMock(return_value={"results": [1]})
    req = SimpleNamespace()
    # The charge on a miss is covered by test_audit7_phase4; here only the cache is under test.
    with patch.object(lw, "_run", fake), patch.object(lw, "admit_flat_charge", AsyncMock()), \
            patch.object(lw, "close_flat_charge", AsyncMock()):
        await lw.discover(req, topic="tech", mode="normal")
        await lw.discover(req, topic="TECH", mode="normal")
        await lw.discover(req, topic="not-a-topic", mode="normal")
    assert fake.await_count == 1
    assert len(lw._discover_cache) == 1
    lw._discover_cache.clear()


# 4. feedback / telemetry -----------------------------------------------------


@pytest.mark.asyncio
async def test_feedback_context_over_4kb_is_422_and_rate_limited():
    from reasoner.api.dependencies import check_rate_limit
    from reasoner.api.routes import feedback as fb

    params = inspect.signature(fb.submit_feedback).parameters
    assert params["rate_limit_checked"].default.dependency is check_rate_limit
    req = fb.FeedbackRequest(
        conversation_id="c", message_id="m", rating="up", context={"k": "x" * 5000}
    )
    with pytest.raises(HTTPException) as e:
        await fb.submit_feedback(req, SimpleNamespace(), True, True)
    assert e.value.status_code == 422


@pytest.mark.asyncio
async def test_scorecard_requires_admin_and_hides_exception_text():
    from reasoner.api.dependencies import require_admin_scope
    from reasoner.api.routes import telemetry as tm

    dep = inspect.signature(tm.get_scorecard).parameters["user"].default.dependency
    assert dep is require_admin_scope
    boom = AsyncMock(side_effect=RuntimeError("secret-dsn"))
    with patch.object(tm, "handle_get_harness_scorecard", boom):
        with pytest.raises(HTTPException) as e:
            await tm.get_scorecard(window_days=7, user=None)
    assert "secret-dsn" not in e.value.detail


# 5. client ip / metrics ------------------------------------------------------


def _req(peer, xff=None):
    headers = {"X-Forwarded-For": xff} if xff else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def test_xff_ignored_unless_peer_is_trusted_proxy():
    from reasoner.api.client_ip import get_client_ip

    assert get_client_ip(_req("198.51.100.9", "1.2.3.4"), ["10.0.0.1"]) == "198.51.100.9"
    assert get_client_ip(_req("10.0.0.1", "1.2.3.4"), ["10.0.0.1"]) == "1.2.3.4"


def test_cidr_proxies_supported():
    from reasoner.api.client_ip import get_client_ip

    assert get_client_ip(_req("10.1.2.3", "1.2.3.4, 10.9.9.9"), ["10.0.0.0/8"]) == "1.2.3.4"


@pytest.mark.asyncio
async def test_metrics_allowlist_accepts_cidr():
    from reasoner.api import _metrics_ip_restricted
    from reasoner.core.settings import settings

    with patch.object(settings, "METRICS_ALLOWED_IPS", "10.0.0.0/8, 192.0.2.5"):
        await _metrics_ip_restricted(_req("10.4.4.4"))
        with pytest.raises(HTTPException):
            await _metrics_ip_restricted(_req("11.0.0.1"))


# 6. deleted accounts ---------------------------------------------------------


class _Pool:
    def __init__(self, deleted=False, fail=False):
        self.deleted, self.fail = deleted, fail

    async def fetchval(self, *_a):
        if self.fail:
            raise OSError("pg down")
        return 1 if self.deleted else None

    async def execute(self, *_a):
        return None


@pytest.mark.asyncio
async def test_deletion_lookup_failure_fails_closed_503():
    from reasoner.api import dependencies as deps

    with patch.object(deps, "_get_provision_pool", AsyncMock(return_value=_Pool(fail=True))):
        with pytest.raises(HTTPException) as e:
            await deps._ensure_user_in_db(User(id=uuid4(), email="x@y.z"))
    assert e.value.status_code == 503


@pytest.mark.asyncio
async def test_mcp_resolve_caller_refuses_deleted_jwt_user():
    from reasoner.api import dependencies as deps
    from reasoner.api.mcp import context as mctx

    user = User(id=uuid4(), email="x@y.z")
    with (
        patch.object(mctx, "_bearer_token_from_context", return_value="aaa.bbb.ccc"),
        patch.object(deps, "_resolve_auth_token", AsyncMock(return_value=user)),
        patch.object(deps, "_get_provision_pool", AsyncMock(return_value=_Pool(deleted=True))),
    ):
        deps.forget_provisioned_user(user.id)
        with pytest.raises(mctx.McpAuthError):
            await mctx.resolve_caller(SimpleNamespace())


# 3. default body cap and rate-limited cheap routes (audit 8 WS4-2) ------------


def _routes_app():
    app = FastAPI()

    @app.post("/api/estimate")
    @app.post("/api/suggestions")
    @app.post("/api/stop")
    @app.post("/api/run")
    @app.post("/api/run-followup")
    @app.post("/api/run-with-context")
    @app.post("/api/agent/run")
    async def echo(request: Request):
        return {"n": len(await request.body())}

    app.add_middleware(BodySizeLimitMiddleware, **BodySizeLimitMiddleware.app_limits())
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/estimate", "/api/suggestions", "/api/stop"])
async def test_a_one_megabyte_body_is_refused_on_routes_that_take_small_json(path):
    resp = await _post(_routes_app(), path, b"x" * 2**20)
    assert resp.status_code == 413


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["/api/run", "/api/run-followup", "/api/run-with-context", "/api/agent/run"]
)
async def test_a_run_with_a_full_attachment_still_passes(path):
    from reasoner.api.schemas import MAX_ATTACHMENT_TEXT_CHARS

    body = b"x" * (MAX_ATTACHMENT_TEXT_CHARS + 2**16)  # one attachment of the largest text
    resp = await _post(_routes_app(), path, body)
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "module,path",
    [
        ("reasoner.api.routes.estimate", "/api/estimate"),
        ("reasoner.api.routes.widgets", "/api/suggestions"),
        ("reasoner.api", "/api/stop"),
    ],
)
def test_cheap_routes_carry_the_rate_limit(module, path):
    from reasoner.api.dependencies import check_rate_limit

    mod = importlib.import_module(module)
    holder = getattr(mod, "router", None) or mod.app
    route = next(r for r in holder.routes if getattr(r, "path", None) == path)
    assert check_rate_limit in [d.call for d in route.dependant.dependencies]


# audit 8 WS4-4/6/7 ---------------------------------------------------------------


@pytest.mark.parametrize("bad", ["../x", "a/b", "a\b", "A1", "", "g" * 3, "a" * 37])
def test_attachment_ref_refuses_a_malformed_file_id(bad):
    from pydantic import ValidationError

    from reasoner.api.schemas import AttachmentRef

    with pytest.raises(ValidationError):
        AttachmentRef(file_id=bad, filename="a", mime_type="text/plain", extracted_text="")


@pytest.mark.parametrize("bad", ["../x", "a/b", "a\b", "", "..", "a.meta"])
def test_upload_meta_refuses_a_path_shaped_id(bad, tmp_path, monkeypatch):
    from reasoner.infrastructure import uploader

    up = tmp_path / "up"
    up.mkdir()
    (tmp_path / "x.meta.json").write_text('{"user_id": "u"}')
    monkeypatch.setattr(uploader, "UPLOAD_DIR", up)
    assert uploader._get_upload_meta(bad) is None
    (up / "ok-1.meta.json").write_text('{"user_id": "u"}')
    assert uploader._get_upload_meta("ok-1") == {"user_id": "u"}


@pytest.mark.asyncio
async def test_search_failure_does_not_leak_the_provider_error(monkeypatch):
    import reasoner.api as api

    class Boom:
        async def search(self, *a, **k):
            raise RuntimeError("https://secret.internal:9200 key=sk-abc quota")

    async def no_charge(*a, **k):
        return None

    async def close(*a, **k):
        return None

    monkeypatch.setattr(api, "admit_flat_charge", no_charge)
    monkeypatch.setattr(api, "close_flat_charge", close)
    req = api.SearchRequest(query="hello world", smart=False)
    with pytest.raises(HTTPException) as e:
        await api.search_web(req, SimpleNamespace(), None, None, Boom())
    assert e.value.status_code == 503
    assert "secret" not in e.value.detail and "sk-abc" not in e.value.detail


@pytest.mark.parametrize("func", ["create_checkout", "create_portal"])
def test_billing_money_routes_are_rate_limited(func):
    from reasoner.api import billing_router
    from reasoner.api.dependencies import check_rate_limit

    params = inspect.signature(getattr(billing_router, func)).parameters
    assert any(
        getattr(p.default, "dependency", None) is check_rate_limit for p in params.values()
    )
