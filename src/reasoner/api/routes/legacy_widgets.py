"""Legacy widget endpoints (weather, stocks, calculator, discover)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from reasoner.api.auth_deps import require_csrf
from reasoner.api.schemas import CalculationRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/weather")
async def get_weather(location: str = ""):
    """Get weather data for a location (legacy endpoint)."""
    if not location:
        raise HTTPException(status_code=400, detail="Location parameter required")
    try:
        from reasoner.widgets import get_weather_data

        weather_data = await get_weather_data(location)
        return weather_data
    except Exception as e:
        logger.error(f"Weather error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/api/stocks")
async def get_stock(symbol: str = ""):
    """Get stock data for a symbol (legacy endpoint)."""
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol parameter required")
    try:
        from reasoner.widgets import get_stock_data

        stock_data = get_stock_data(symbol.upper())
        return stock_data
    except Exception as e:
        logger.error(f"Stock error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.post("/api/calculate")
async def calculate(
    req: CalculationRequest,
    csrf_checked=Depends(require_csrf),
):
    """Evaluate a mathematical expression (legacy endpoint)."""
    try:
        import asyncio

        from reasoner.widgets import calculate_expression

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


@router.get("/api/discover")
async def discover(topic: str = "tech", mode: str = "normal"):
    """Get trending content for a topic (legacy endpoint)."""
    try:
        from reasoner.widgets import get_discover_content

        content = await get_discover_content(topic, mode)
        return content
    except Exception as e:
        logger.error(f"Discover error: {e}")
        return {"error": "Internal server error", "results": []}
