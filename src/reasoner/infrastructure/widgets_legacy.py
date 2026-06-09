"""
Widgets Backend Engine
Provides data for smart widgets: Weather, Stocks, Calculations, Discover, Images, Videos.
"""

from __future__ import annotations

import ast
import logging
import asyncio
import math
import operator
from typing import Any, Optional
from dataclasses import dataclass, asdict
import httpx

from reasoner.core.constants import (
    OPENMETEO_GEOCODING_URL,
    OPENMETEO_FORECAST_URL,
    TIMEOUTS,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────
# CALCULATION WIDGET - SECURE IMPLEMENTATION
# ─────────────────────────────────────────────────────────────────────

try:
    import mathjs
    MATHJS_AVAILABLE = True
except ImportError:
    MATHJS_AVAILABLE = False
    logger.warning("mathjs not installed - calculation widget using safe fallback")

# Safe math operators
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Safe math functions
SAFE_FUNCTIONS = {
    'abs': abs,
    'round': round,
    'min': min,
    'max': max,
    'sum': sum,
    'pow': pow,
}

# Safe constants
SAFE_CONSTANTS = {
    'pi': 3.141592653589793,
    'e': 2.718281828459045,
}


class SafeExpressionError(Exception):
    """Raised when expression contains unsafe operations."""
    pass


def _safe_eval_expr(node: ast.AST, depth: int = 0) -> Any:
    """
    Recursively evaluate AST node with safety checks.
    Raises SafeExpressionError for unsafe operations.
    """
    if depth > 20:
        raise SafeExpressionError("Expression too deeply nested")
    if isinstance(node, ast.Constant):  # Python 3.8+
        if isinstance(node.value, bool):
            raise SafeExpressionError("Boolean constants not allowed")
        if isinstance(node.value, (int, float, complex)):
            if isinstance(node.value, float) and not math.isfinite(node.value):
                raise SafeExpressionError("Inf/NaN not allowed")
            return node.value
        raise SafeExpressionError("Only numeric constants allowed")
    elif isinstance(node, ast.BinOp):
        left = _safe_eval_expr(node.left, depth + 1)
        right = _safe_eval_expr(node.right, depth + 1)
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise SafeExpressionError(f"Unsafe operator: {op_type.__name__}")
        # Prevent division by zero
        if op_type == ast.Div and right == 0:
            raise SafeExpressionError("Division by zero")
        # Prevent excessive exponentiation
        if op_type == ast.Pow:
            if abs(right) > 1000:
                raise SafeExpressionError("Exponent too large")
            if abs(left) > 10000 and abs(right) > 10:
                raise SafeExpressionError("Result would be too large")
        return SAFE_OPERATORS[op_type](left, right)
    elif isinstance(node, ast.UnaryOp):
        operand = _safe_eval_expr(node.operand, depth + 1)
        op_type = type(node.op)
        if op_type not in SAFE_OPERATORS:
            raise SafeExpressionError(f"Unsafe operator: {op_type.__name__}")
        return SAFE_OPERATORS[op_type](operand)
    elif isinstance(node, ast.Call):
        if node.keywords:
            raise SafeExpressionError("Keyword arguments not allowed")
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name not in SAFE_FUNCTIONS:
                raise SafeExpressionError(f"Unsafe function: {func_name}")
            args = [_safe_eval_expr(arg, depth + 1) for arg in node.args]
            return SAFE_FUNCTIONS[func_name](*args)
        raise SafeExpressionError("Function calls must be simple names")
    elif isinstance(node, ast.Name):
        if node.id in SAFE_CONSTANTS:
            return SAFE_CONSTANTS[node.id]
        raise SafeExpressionError(f"Unknown variable: {node.id}")
    elif isinstance(node, ast.Expression):
        return _safe_eval_expr(node.body, depth + 1)
    else:
        raise SafeExpressionError(f"Unsupported expression type: {type(node).__name__}")


def calculate_expression(expression: str) -> dict[str, Any]:
    """
    Evaluate a mathematical expression SAFELY.
    
    Supports:
    - Basic arithmetic: +, -, *, /
    - Exponents: **
    - Functions: abs, round, min, max, sum, pow
    - Constants: pi, e
    
    Security: Uses AST parsing instead of eval() to prevent code injection.
    
    Returns:
        dict with 'result', 'valid', 'expression' keys
    """
    expr = expression.strip()
    if not expr:
        return {"error": "Empty expression", "valid": False}
    if len(expr) > 10000:
        return {"error": "Expression too long", "valid": False}

    try:
        tree = ast.parse(expr, mode='eval')
        
        # Safely evaluate the AST
        result = _safe_eval_expr(tree)
        
        # Validate result is numeric
        if not isinstance(result, (int, float, complex)):
            return {"error": "Result must be numeric", "valid": False}
            
        return {"result": result, "valid": True, "expression": expression}
        
    except SafeExpressionError as e:
        return {"error": str(e), "valid": False}
    except SyntaxError:
        return {"error": "Invalid expression syntax", "valid": False}
    except ZeroDivisionError:
        return {"error": "Division by zero", "valid": False}
    except OverflowError:
        return {"error": "Result too large", "valid": False}
    except Exception as e:
        logger.error(f"Unexpected calculation error: {e}")
        return {"error": "Calculation failed", "valid": False}


# ─────────────────────────────────────────────────────────────────────
# WEATHER WIDGET
# ─────────────────────────────────────────────────────────────────────

# Weather condition mappings (from Open-Meteo WMO codes)
WEATHER_CONDITIONS = {
    0: {"condition": "Clear sky", "icon": "sun"},
    1: {"condition": "Mainly clear", "icon": "sun"},
    2: {"condition": "Partly cloudy", "icon": "cloud-sun"},
    3: {"condition": "Overcast", "icon": "cloud"},
    45: {"condition": "Foggy", "icon": "fog"},
    48: {"condition": "Depositing rime fog", "icon": "fog"},
    51: {"condition": "Light drizzle", "icon": "drizzle"},
    53: {"condition": "Moderate drizzle", "icon": "drizzle"},
    55: {"condition": "Dense drizzle", "icon": "drizzle"},
    61: {"condition": "Slight rain", "icon": "rain"},
    63: {"condition": "Moderate rain", "icon": "rain"},
    65: {"condition": "Heavy rain", "icon": "rain"},
    71: {"condition": "Slight snow", "icon": "snow"},
    73: {"condition": "Moderate snow", "icon": "snow"},
    75: {"condition": "Heavy snow", "icon": "snow"},
    80: {"condition": "Slight rain showers", "icon": "rain"},
    81: {"condition": "Moderate rain showers", "icon": "rain"},
    82: {"condition": "Violent rain showers", "icon": "thunderstorm"},
    95: {"condition": "Thunderstorm", "icon": "thunderstorm"},
    96: {"condition": "Thunderstorm with hail", "icon": "thunderstorm"},
    99: {"condition": "Thunderstorm with heavy hail", "icon": "thunderstorm"},
}


async def geocode_location(location: str) -> Optional[dict[str, float]]:
    """Geocode a location name to coordinates."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUTS.WIDGET) as client:
            response = await client.get(
                OPENMETEO_GEOCODING_URL,
                params={"name": location, "count": 1, "language": "en", "format": "json"},
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("results"):
                result = data["results"][0]
                return {
                    "latitude": result["latitude"],
                    "longitude": result["longitude"],
                    "name": f"{result['name']}, {result.get('country', '')}",
                }
    except Exception as e:
        logger.error(f"Geocoding error: {e}")
    
    return None


async def get_weather_data(location: str) -> dict[str, Any]:
    """
    Get weather data for a location using Open-Meteo API.
    
    Returns current weather + 3-day forecast.
    """
    # Geocode location
    coords = await geocode_location(location)
    if not coords:
        return {"error": f"Location '{location}' not found"}
    
    try:
        async with httpx.AsyncClient(timeout=TIMEOUTS.WIDGET) as client:
            response = await client.get(
                OPENMETEO_FORECAST_URL,
                params={
                    "latitude": coords["latitude"],
                    "longitude": coords["longitude"],
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m,pressure_msl",
                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "auto",
                    "forecast_days": 3,
                },
            )
            response.raise_for_status()
            data = response.json()
            
            current = data.get("current", {})
            daily = data.get("daily", {})
            
            # Parse current weather
            weather_code = current.get("weather_code", 0)
            condition_info = WEATHER_CONDITIONS.get(weather_code, {"condition": "Unknown", "icon": "question"})
            
            current_weather = {
                "location": coords["name"],
                "temperature": current.get("temperature_2m"),
                "temperature_unit": "°C",
                "feels_like": current.get("apparent_temperature"),
                "condition": condition_info["condition"],
                "icon": condition_info["icon"],
                "humidity": current.get("relative_humidity_2m"),
                "wind_speed": current.get("wind_speed_10m"),
                "wind_direction": current.get("wind_direction_10m"),
                "pressure": current.get("pressure_msl"),
            }
            
            # Parse forecast
            forecast = []
            if daily.get("time"):
                for i, date in enumerate(daily["time"]):
                    day_code = daily.get("weather_code", [])[i] if i < len(daily.get("weather_code", [])) else 0
                    day_condition = WEATHER_CONDITIONS.get(day_code, {"condition": "Unknown", "icon": "question"})
                    
                    forecast.append({
                        "date": date,
                        "condition": day_condition["condition"],
                        "icon": day_condition["icon"],
                        "temp_max": daily.get("temperature_2m_max", [])[i] if i < len(daily.get("temperature_2m_max", [])) else None,
                        "temp_min": daily.get("temperature_2m_min", [])[i] if i < len(daily.get("temperature_2m_min", [])) else None,
                        "precipitation_probability": daily.get("precipitation_probability_max", [])[i] if i < len(daily.get("precipitation_probability_max", [])) else None,
                    })
            
            return {
                "current": current_weather,
                "forecast": forecast,
                "source": "Open-Meteo",
            }
            
    except httpx.HTTPError as e:
        logger.error(f"Weather API error: {e}")
        return {"error": f"Weather service unavailable: {str(e)}"}
    except Exception as e:
        logger.error(f"Weather error: {e}")
        return {"error": str(e)}


# NOTE: the sync wrapper and get_weather_data_async that used to live here were
# removed.  They shadowed the async get_weather_data() defined above, causing
# RuntimeError ("event loop already running") when called from FastAPI's async
# context and infinite recursion when called from the sync wrapper.  All callers
# should await get_weather_data() directly.


# ─────────────────────────────────────────────────────────────────────
# STOCK WIDGET
# ─────────────────────────────────────────────────────────────────────

def _has_yahooquery() -> bool:
    try:
        import yahooquery
        return True
    except Exception:
        return False


def _has_yfinance() -> bool:
    try:
        import yfinance
        return True
    except Exception:
        return False


def get_stock_data(symbol: str) -> dict[str, Any]:
    """
    Get stock data for a symbol using Yahoo Finance.

    Returns current price, change, market cap, etc.
    """
    yahoo_available = _has_yahooquery() or _has_yfinance()
    if not yahoo_available:
        # Mock data for demonstration
        return {
            "symbol": symbol,
            "price": 0,
            "change": 0,
            "change_percent": 0,
            "market_cap": None,
            "volume": None,
            "source": "Demo Mode",
            "note": "Install yahooquery or yfinance for real data",
        }

    try:
        # Try yahooquery first
        try:
            from yahooquery import Ticker
            ticker = Ticker(symbol)

            price = ticker.price(symbol)
            if not price or symbol not in price:
                return {"error": f"Symbol '{symbol}' not found"}

            quote = price[symbol]

            return {
                "symbol": symbol,
                "price": quote.get("regularMarketPrice", 0),
                "change": quote.get("regularMarketChange", 0),
                "change_percent": quote.get("regularMarketChangePercent", 0),
                "currency": quote.get("currency", "USD"),
                "market_cap": quote.get("marketCap"),
                "volume": quote.get("regularMarketVolume"),
                "previous_close": quote.get("regularMarketPreviousClose"),
                "open": quote.get("regularMarketOpen"),
                "day_high": quote.get("regularMarketDayHigh"),
                "day_low": quote.get("regularMarketDayLow"),
                "source": "Yahoo Finance",
            }
        except ImportError:
            # Fallback to yfinance
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            info = ticker.info

            if not info or "currentPrice" not in info:
                return {"error": f"Symbol '{symbol}' not found"}

            # Yahoo Finance returns null for some fields when data is unavailable.
            # dict.get(key, default) only substitutes when the KEY is missing; if the
            # key IS present with value None, it returns None.  Guard with `or 0` to
            # prevent TypeError in arithmetic.
            _price = info.get("currentPrice") or 0
            _prev = info.get("previousClose") or 0
            _change = _price - _prev
            return {
                "symbol": symbol,
                "price": _price,
                "change": _change,
                "change_percent": (_change / _prev * 100) if _prev else 0.0,
                "currency": info.get("currency", "USD"),
                "market_cap": info.get("marketCap"),
                "volume": info.get("volume"),
                "previous_close": info.get("previousClose"),
                "open": info.get("open"),
                "day_high": info.get("dayHigh"),
                "day_low": info.get("dayLow"),
                "source": "Yahoo Finance",
            }

    except Exception as e:
        logger.error(f"Stock data error: {e}")
        return {"error": str(e), "symbol": symbol}


# ─────────────────────────────────────────────────────────────────────
# DISCOVER MODE
# ─────────────────────────────────────────────────────────────────────

DISCOVER_TOPICS = {
    "tech": {
        "queries": ["technology news", "latest tech", "AI", "science and innovation"],
        "sites": ["techcrunch.com", "wired.com", "theverge.com", "arstechnica.com"],
    },
    "finance": {
        "queries": ["finance news", "economy", "stock market", "investing"],
        "sites": ["bloomberg.com", "cnbc.com", "marketwatch.com", "reuters.com"],
    },
    "science": {
        "queries": ["science news", "research", "discovery", "space"],
        "sites": ["nature.com", "science.org", "scientificamerican.com", "space.com"],
    },
    "sports": {
        "queries": ["sports news", "latest sports"],
        "sites": ["espn.com", "bbc.com/sport", "skysports.com"],
    },
    "entertainment": {
        "queries": ["entertainment news", "movies", "TV shows"],
        "sites": ["hollywoodreporter.com", "variety.com", "deadline.com"],
    },
}


async def search_searxng(query: str, engines: list[str] = None) -> list[dict[str, Any]]:
    """Search using SearXNG."""
    from reasoner.core.search import get_searxng_urls
    searxng_urls = get_searxng_urls()
    
    for url in searxng_urls:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUTS.WIDGET_SHORT) as client:
                response = await client.get(
                    url,
                    params={"q": query, "format": "json", "engines": ",".join(engines) if engines else ""},
                )
                if response.status_code == 200:
                    data = response.json()
                    return data.get("results", [])
        except Exception:
            continue
    
    return []


async def get_discover_content(topic: str = "tech", mode: str = "normal") -> dict[str, Any]:
    """
    Get trending content for a topic.

    Aggregates from multiple sources based on topic.
    """
    topic = topic.lower()
    if topic not in DISCOVER_TOPICS:
        topic = "tech"

    topic_config = DISCOVER_TOPICS[topic]
    results = []
    seen_urls = set()

    # Search for each query
    for query in topic_config["queries"]:
        # Try SearXNG
        searxng_results = await search_searxng(query, ["bing news"])
        
        for result in searxng_results[:5]:
            if result.get("url") not in seen_urls:
                seen_urls.add(result.get("url"))
                results.append({
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "content": result.get("content", ""),
                    "source": result.get("source", ""),
                    "published": result.get("publishedDate", ""),
                })
        
        if len(results) >= 10:
            break
    
    # If no results from SearXNG, return curated list
    if not results:
        results = [
            {
                "title": f"Latest {topic} news - Demo Mode",
                "url": f"https://{topic_config['sites'][0]}",
                "content": f"Install SearXNG for live {topic} content",
                "source": topic_config["sites"][0],
                "published": "",
            },
        ]
    
    return {
        "topic": topic,
        "mode": mode,
        "results": results[:10],
        "total": len(results),
    }


# ─────────────────────────────────────────────────────────────────────
# IMAGE SEARCH
# ─────────────────────────────────────────────────────────────────────

def search_images(query: str, limit: int = 20) -> dict[str, Any]:
    """Search for images using SearXNG."""
    results = []
    
    # Try SearXNG
    from reasoner.core.search import get_searxng_urls
    searxng_urls = get_searxng_urls()
    
    for url in searxng_urls:
        try:
            response = httpx.get(
                url,
                params={"q": query, "format": "json", "categories": "images"},
                timeout=TIMEOUTS.WIDGET_SHORT,
            )
            if response.status_code == 200:
                data = response.json()
                for result in data.get("results", [])[:limit]:
                    results.append({
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "img_src": result.get("img_src", ""),
                        "thumbnail": result.get("thumbnail", ""),
                        "source": result.get("source", ""),
                    })
                break
        except Exception:
            continue
    
    return {
        "query": query,
        "results": results,
        "total": len(results),
    }


# ─────────────────────────────────────────────────────────────────────
# VIDEO SEARCH
# ─────────────────────────────────────────────────────────────────────

def search_videos(query: str, limit: int = 20) -> dict[str, Any]:
    """Search for videos using SearXNG."""
    results = []
    
    # Try SearXNG
    from reasoner.core.search import get_searxng_urls
    searxng_urls = get_searxng_urls()
    
    for url in searxng_urls:
        try:
            response = httpx.get(
                url,
                params={"q": query, "format": "json", "categories": "videos"},
                timeout=TIMEOUTS.WIDGET_SHORT,
            )
            if response.status_code == 200:
                data = response.json()
                for result in data.get("results", [])[:limit]:
                    results.append({
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "thumbnail": result.get("thumbnail", ""),
                        "source": result.get("source", ""),
                        "duration": result.get("duration", ""),
                    })
                break
        except Exception:
            continue
    
    return {
        "query": query,
        "results": results,
        "total": len(results),
    }
