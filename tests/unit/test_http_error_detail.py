"""A structured HTTPException detail reaches the client as JSON, not a repr.

`http_exception_handler` built its body with ``str(exc.detail)``, so a dict
detail such as the anonymous trial cap's ``{"error", "message",
"retry_after"}`` arrived as the Python repr ``"{'error': ...}"``. The UI
showed that raw text, and its ``detail.upgrade_url`` check could never match.
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from reasoner.api.error_handler import http_exception_handler


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/run", "headers": []})


@pytest.mark.asyncio
async def test_dict_detail_is_sent_as_json():
    exc = HTTPException(
        status_code=429,
        detail={
            "error": "Anonymous trial limit reached",
            "message": "Free trial usage for this address is exhausted for today.",
            "retry_after": 86400,
        },
        headers={"Retry-After": "86400"},
    )
    resp = await http_exception_handler(_request(), exc)
    body = json.loads(resp.body)

    assert body["error"] == "Free trial usage for this address is exhausted for today."
    assert body["detail"]["retry_after"] == 86400
    assert resp.headers.get("retry-after") == "86400"


@pytest.mark.asyncio
async def test_string_detail_is_unchanged():
    resp = await http_exception_handler(
        _request(), HTTPException(status_code=404, detail="Not found")
    )
    body = json.loads(resp.body)

    assert body["error"] == "Not found"
    assert "detail" not in body


# ── What reaches the error store and Sentry (audit 8 WS4-3) ──────────────────


@pytest.fixture
def sinks(monkeypatch):
    """Capture error-store inserts and Sentry messages."""
    import asyncio  # noqa: F401  (tasks run on the test's loop)
    import contextlib
    import sys
    from types import ModuleType, SimpleNamespace

    from reasoner.api import error_handler

    stored: list = []
    sent: list = []

    class _Store:
        async def insert(self, entry):
            stored.append(entry)

    @contextlib.contextmanager
    def push_scope():
        yield SimpleNamespace(
            set_tag=lambda *a: None, set_user=lambda *a: None, set_extra=lambda *a: None
        )

    # A stand-in module: the real SDK is optional and absent from some environments.
    fake = ModuleType("sentry_sdk")
    fake.Hub = SimpleNamespace(current=SimpleNamespace(client=object()))
    fake.push_scope = push_scope
    fake.capture_message = lambda msg, level=None: sent.append(msg)
    fake.capture_exception = lambda exc: sent.append(str(exc))
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake)

    monkeypatch.setattr(error_handler, "_get_error_store", lambda: _Store())
    return SimpleNamespace(stored=stored, sent=sent)


async def _drain():
    import asyncio

    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_300_anonymous_404s_write_no_rows_and_send_nothing_to_sentry(sinks):
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from reasoner.api import error_handler

    def not_found(path):
        return Request({"type": "http", "method": "GET", "path": path, "headers": []})

    for i in range(300):
        await error_handler.http_exception_handler(
            not_found(f"/wp-login-{i}.php"),
            StarletteHTTPException(status_code=404, detail="Not Found")
        )
    await _drain()

    assert sinks.stored == []
    assert sinks.sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [404, 405, 422, 400, 409])
async def test_client_errors_are_counted_by_status(sinks, status_code):
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from reasoner.api import error_handler
    from reasoner.metrics import REASONER_API_CLIENT_ERRORS_TOTAL

    counter = REASONER_API_CLIENT_ERRORS_TOTAL.labels(status=str(status_code))
    before = counter._value.get()
    await error_handler.http_exception_handler(
        _request(), StarletteHTTPException(status_code=status_code, detail="x")
    )
    assert counter._value.get() == before + 1


@pytest.mark.asyncio
async def test_a_validation_failure_is_logged_not_stored(sinks):
    from fastapi.exceptions import RequestValidationError

    from reasoner.api import error_handler

    resp = await error_handler.validation_exception_handler(
        _request(), RequestValidationError([{"loc": ("body",), "msg": "bad", "type": "x"}])
    )
    await _drain()
    assert resp.status_code == 422
    assert sinks.stored == [] and sinks.sent == []


@pytest.mark.asyncio
async def test_a_server_error_is_still_stored_and_sent_with_a_short_path(sinks):
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from reasoner.api import error_handler

    long_path = "/" + "a" * 5000
    request = Request({"type": "http", "method": "GET", "path": long_path, "headers": []})
    await error_handler.http_exception_handler(
        request, StarletteHTTPException(status_code=503, detail="down")
    )
    await _drain()

    assert len(sinks.stored) == 1 and sinks.sent == ["down"]
    assert len(sinks.stored[0].path) == error_handler._MAX_LOGGED_PATH_CHARS


@pytest.mark.asyncio
async def test_store_inserts_in_flight_are_capped_but_sentry_still_hears(sinks, monkeypatch):
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from reasoner.api import error_handler
    from reasoner.metrics import REASONER_ERROR_STORE_DROPPED_TOTAL

    full = set(range(error_handler._MAX_INFLIGHT_STORE_TASKS))
    monkeypatch.setattr(error_handler, "_BACKGROUND_TASKS", full)
    before = REASONER_ERROR_STORE_DROPPED_TOTAL._value.get()

    await error_handler.http_exception_handler(
        _request(), StarletteHTTPException(status_code=500, detail="boom")
    )
    await _drain()

    assert sinks.stored == []
    assert sinks.sent == ["boom"]
    assert REASONER_ERROR_STORE_DROPPED_TOTAL._value.get() == before + 1
