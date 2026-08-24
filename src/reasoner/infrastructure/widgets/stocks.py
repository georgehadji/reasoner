"""
Stock Widget

Provides real-time stock prices using Yahoo Finance.
"""

from __future__ import annotations

import re
from typing import Any

from reasoner.infrastructure.widgets.protocol import BaseWidget, WidgetType


class StockWidget(BaseWidget):
    """
    Stock price widget using Yahoo Finance.
    
    Features:
    - Real-time stock prices
    - Price change and percentage
    - Market cap, volume
    - Day range
    """

    name = "stocks"
    widget_type = WidgetType.STOCKS
    description = "Real-time stock prices from Yahoo Finance"

    trigger_patterns = [
        re.compile(r'(?:stock|stock price|share price)\s+(?:for\s+)?([a-z]+)', re.I),
        re.compile(r'([a-z]+)\s+(?:stock|stock price|share price)', re.I),
        re.compile(r'(?:price|quote)\s+(?:for\s+)?([a-z]{1,5})\b', re.I),
        re.compile(r'\$([a-z]{1,5})\b', re.I),  # e.g., $AAPL
        re.compile(r'(?:ticker|symbol)\s*:?\s*([a-z]{1,5})\b', re.I),
    ]

    def _extract_from_match(
        self,
        match: re.Match,
        query: str,
    ) -> dict[str, Any]:
        """Extract stock symbol from match."""
        symbol = None

        # Check for $ prefix (e.g., $AAPL)
        dollar_match = re.search(r'\$([a-z]{1,5})\b', query, re.I)
        if dollar_match:
            symbol = dollar_match.group(1)
        else:
            # Get from capture group
            if match.lastindex and match.lastindex >= 1:
                symbol = match.group(1)

        if symbol:
            return {'symbol': symbol.upper().strip()}

        return {'symbol': ''}

    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch stock data from Yahoo Finance."""
        symbol = params.get('symbol', '')

        if not symbol:
            return {'error': 'Stock symbol not specified'}

        # Try yahooquery first, then yfinance
        data = await self._fetch_stock_data(symbol)

        if 'error' in data:
            return data

        return {
            'symbol': symbol.upper(),
            **data,
        }

    async def _fetch_stock_data(self, symbol: str) -> dict[str, Any]:
        """Fetch stock data from Yahoo Finance."""
        # Try yahooquery
        try:
            from yahooquery import Ticker

            ticker = Ticker(symbol)
            price = ticker.price(symbol)

            if price and symbol in price:
                quote = price[symbol]
                return self._parse_yahoo_data(quote)

        except ImportError:
            pass
        except Exception:
            pass

        # Try yfinance
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            info = ticker.info

            if info and 'currentPrice' in info:
                return self._parse_yfinance_info(info)

        except ImportError:
            pass
        except Exception:
            pass

        return {'error': 'Stock data unavailable (install yahooquery or yfinance)'}

    def _parse_yahoo_data(self, quote: dict[str, Any]) -> dict[str, Any]:
        """Parse yahooquery data."""
        return {
            'price': quote.get('regularMarketPrice', 0),
            'change': quote.get('regularMarketChange', 0),
            'change_percent': quote.get('regularMarketChangePercent', 0),
            'currency': quote.get('currency', 'USD'),
            'market_cap': quote.get('marketCap'),
            'volume': quote.get('regularMarketVolume'),
            'previous_close': quote.get('regularMarketPreviousClose'),
            'open': quote.get('regularMarketOpen'),
            'day_high': quote.get('regularMarketDayHigh'),
            'day_low': quote.get('regularMarketDayLow'),
            'fifty_two_week_high': quote.get('fiftyTwoWeekHigh'),
            'fifty_two_week_low': quote.get('fiftyTwoWeekLow'),
            'source': 'Yahoo Finance',
        }

    def _parse_yfinance_info(self, info: dict[str, Any]) -> dict[str, Any]:
        """Parse yfinance info."""
        current_price = info.get('currentPrice', 0)
        previous_close = info.get('previousClose', current_price)

        change = current_price - previous_close
        change_percent = (change / previous_close * 100) if previous_close else 0

        return {
            'price': current_price,
            'change': change,
            'change_percent': change_percent,
            'currency': info.get('currency', 'USD'),
            'market_cap': info.get('marketCap'),
            'volume': info.get('volume'),
            'previous_close': previous_close,
            'open': info.get('open'),
            'day_high': info.get('dayHigh'),
            'day_low': info.get('dayLow'),
            'fifty_two_week_high': info.get('fiftyTwoWeekHigh'),
            'fifty_two_week_low': info.get('fiftyTwoWeekLow'),
            'source': 'Yahoo Finance',
        }
