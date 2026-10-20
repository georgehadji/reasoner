"""Widget endpoints are rate-limited and keep blocking calls off the loop (OPS-6).

/api/stocks, /api/weather and /api/discover were anonymous with no rate limit,
and /api/widget/execute had CSRF only. Stock quotes (yahooquery/yfinance) and
the asteval calculator ran synchronously on the event loop.
See docs/plans/audit-remediation-2026-10-20.md, OPS-6.
"""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from fastapi import FastAPI

from reasoner.api import dependencies
from reasoner.api.auth_deps import require_csrf
from reasoner.api.routes import legacy_widgets, widgets


class _Limiter:
    def __init__(self, allow: int):
        self.left = allow

    async def is_allowed(self, client_id):
        self.left -= 1
        return self.left >= 0, {"limit_minute": 1, "remaining_minute": 0, "retry_after": 60}


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(legacy_widgets.router)
    app.include_router(widgets.router)
    app.dependency_overrides[dependencies.get_optional_user] = lambda: None
    app.dependency_overrides[require_csrf] = lambda: True
    monkeypatch.setattr("reasoner.widgets.get_stock_data", lambda s: {"symbol": s})
    monkeypatch.setattr("reasoner.widgets.get_weather_data", _weather)
    monkeypatch.setattr("reasoner.widgets.get_discover_content", _discover)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://t")


async def _weather(location):
    return {"location": location}


async def _discover(topic, mode):
    return {"results": []}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/api/stocks?symbol=ACME", None),
        ("GET", "/api/weather?location=Athens", None),
        ("GET", "/api/discover", None),
        ("POST", "/api/widget/execute", {"widget_type": "calculator", "params": {}}),
    ],
)
async def test_a_burst_past_the_limit_gets_429(client, monkeypatch, method, path, body):
    limiter = _Limiter(allow=1)
    monkeypatch.setattr(dependencies, "_get_rate_limiter_instance", lambda: limiter)
    async with client:
        first = await client.request(method, path, json=body)
        second = await client.request(method, path, json=body)
    assert first.status_code != 429
    assert second.status_code == 429


@pytest.mark.asyncio
async def test_a_slow_stock_fetch_does_not_block_the_loop(client, monkeypatch):
    limiter = _Limiter(allow=10)
    monkeypatch.setattr(dependencies, "_get_rate_limiter_instance", lambda: limiter)

    def _slow(symbol):
        time.sleep(0.6)  # yahooquery doing blocking network I/O
        return {"symbol": symbol}

    monkeypatch.setattr("reasoner.widgets.get_stock_data", _slow)
    gaps: list[float] = []

    async def ticker():
        last = time.monotonic()
        for _ in range(12):
            await asyncio.sleep(0.05)
            now = time.monotonic()
            gaps.append(now - last)
            last = now

    async with client:
        response, _ = await asyncio.gather(client.get("/api/stocks?symbol=ACME"), ticker())

    assert response.json() == {"symbol": "ACME"}
    assert max(gaps) < 0.4, f"the loop stalled for {max(gaps):.2f}s"


@pytest.mark.asyncio
async def test_a_looping_expression_is_refused_not_run():
    from reasoner.infrastructure.widgets.calculator import CalculatorWidget

    pytest.importorskip("asteval")
    start = time.monotonic()
    result = await CalculatorWidget()._execute_impl({"expression": "x = 0\nwhile True: x += 1"})
    assert time.monotonic() - start < 3
    assert result["valid"] is False
