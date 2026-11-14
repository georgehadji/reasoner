"""Legacy widget endpoints (weather, stocks, calculator, discover).

Thin routes over the infrastructure/widgets package, the same widgets
/api/widget/execute runs.
"""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException

from reasoner.api.auth_deps import require_csrf
from reasoner.api.dependencies import check_rate_limit
from reasoner.api.schemas import CalculationRequest
from reasoner.infrastructure.widgets.calculator import calculate_expression
from reasoner.infrastructure.widgets.registry import get_widget_registry

logger = logging.getLogger(__name__)
router = APIRouter()


async def _run(name: str, params: dict) -> dict:
    result = await get_widget_registry().get_widget(name).execute(params)
    if not result.success:
        raise RuntimeError(result.error)
    return result.data


@router.get("/api/weather")
async def get_weather(location: str = "", rate_limit_checked=Depends(check_rate_limit)):
    """Get weather data for a location (legacy endpoint)."""
    if not location:
        raise HTTPException(status_code=400, detail="Location parameter required")
    try:
        data = await _run("weather", {"location": location})
        if "error" in data:
            return {"error": data["error"]}
        # Legacy shape: location inside "current", no coordinates.
        return {
            "current": {"location": data["location"], **data["current"]},
            "forecast": data["forecast"],
            "source": data["source"],
        }
    except Exception as e:
        logger.error(f"Weather error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/api/stocks")
async def get_stock(symbol: str = "", rate_limit_checked=Depends(check_rate_limit)):
    """Get stock data for a symbol (legacy endpoint)."""
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol parameter required")
    try:
        return await _run("stocks", {"symbol": symbol.upper()})
    except Exception as e:
        logger.error(f"Stock error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/api/calculate")
async def calculate(
    req: CalculationRequest,
    csrf_checked=Depends(require_csrf),
    rate_limit_checked=Depends(check_rate_limit),
):
    """Evaluate a mathematical expression (legacy endpoint)."""
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(calculate_expression, req.expression),
            timeout=1.0,
        )
        return result
    except TimeoutError:
        return {"error": "Calculation timed out", "valid": False}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Calculation error: %s", e)
        return {"error": "Internal server error", "valid": False}


# shortcut: per-worker TTL cache (each gunicorn worker pays one search per key per
# window); move to Valkey if the paid-search bill shows it.
_DISCOVER_TTL_SECONDS = 300
_DISCOVER_CACHE_MAX = 64
_discover_cache: dict[tuple[str, str], tuple[float, dict]] = {}


@router.get("/api/discover")
async def discover(
    topic: str = "tech", mode: str = "normal", rate_limit_checked=Depends(check_rate_limit)
):
    """Get trending content for a topic (legacy endpoint)."""
    try:
        # Unknown topics already fall back to "tech" downstream; do it here so
        # arbitrary strings cannot mint cache keys.
        topics = get_widget_registry().get_widget("discover").topics
        key = (topic.lower() if topic.lower() in topics else "tech", mode[:32])
        hit = _discover_cache.get(key)
        if hit and time.monotonic() - hit[0] < _DISCOVER_TTL_SECONDS:
            return hit[1]
        data = await _run("discover", {"topic": key[0]})
        # Legacy shape: echoes the mode, no "sources".
        content = {k: v for k, v in data.items() if k != "sources"} | {"mode": key[1]}
        cacheable = isinstance(content, dict) and not content.get("error")
        if cacheable and (len(_discover_cache) < _DISCOVER_CACHE_MAX or key in _discover_cache):
            _discover_cache[key] = (time.monotonic(), content)
        return content
    except Exception as e:
        logger.error(f"Discover error: {e}")
        return {"error": "Internal server error", "results": []}
