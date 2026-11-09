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
    resp = await http_exception_handler(_request(), HTTPException(status_code=404, detail="Not found"))
    body = json.loads(resp.body)

    assert body["error"] == "Not found"
    assert "detail" not in body
