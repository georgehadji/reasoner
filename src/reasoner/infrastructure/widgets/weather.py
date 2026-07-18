"""
Weather Widget

Provides real-time weather data using Open-Meteo API.
"""

from __future__ import annotations

import re
from typing import Any

from reasoner.infrastructure.widgets.protocol import BaseWidget, WidgetResult, WidgetType
from reasoner.core.constants import OPENMETEO_GEOCODING_URL, OPENMETEO_FORECAST_URL, TIMEOUTS


class WeatherWidget(BaseWidget):
    """
    Weather widget for real-time weather data.
    
    Features:
    - Current weather conditions
    - 3-day forecast
    - Temperature, humidity, wind, pressure
    """
    
    name = "weather"
    widget_type = WidgetType.WEATHER
    description = "Real-time weather with 3-day forecast"

    trigger_patterns = [
        re.compile(r'weather(?:\s+in)?\s+([a-z\s]+)', re.I),
        re.compile(r"(?:what's|tell me) (?:the )?weather(?:\s+in)?\s*([a-z\s]+)?", re.I),
        re.compile(r'(?:forecast|temperature)\s+(?:for\s+)?([a-z\s]+)', re.I),
        re.compile(r"how's (?:the )?weather(?:\s+in)?\s+([a-z\s]+)", re.I),
    ]
    
    def _extract_from_match(
        self,
        match: re.Match,
        query: str,
    ) -> dict[str, Any]:
        """Extract location from match."""
        # Try to get location from named group or first capture group
        location = match.group(1) if match.lastindex and match.lastindex >= 1 else None
        
        if not location:
            # Try to extract location from query
            location = query.split('weather')[-1].strip() if 'weather' in query.lower() else ''
        
        return {'location': location.strip() if location else 'current location'}
    
    async def _execute_impl(self, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch weather data from Open-Meteo API."""
        location = params.get('location', '')
        
        if not location:
            return {'error': 'Location not specified'}
        
        # Geocode location
        coords = await self._geocode_location(location)
        
        if not coords:
            return {'error': f"Location '{location}' not found"}
        
        # Fetch weather data
        weather_data = await self._fetch_weather(coords['latitude'], coords['longitude'])
        
        return {
            'location': coords['name'],
            'coordinates': {
                'latitude': coords['latitude'],
                'longitude': coords['longitude'],
            },
            **weather_data,
        }
    
    async def _geocode_location(self, location: str) -> dict[str, Any] | None:
        """Geocode location name to coordinates."""
        import httpx
        
        from reasoner.core.constants import TIMEOUTS
        try:
            async with httpx.AsyncClient(timeout=TIMEOUTS.WIDGET_SHORT) as client:
                response = await client.get(
                    OPENMETEO_GEOCODING_URL,
                    params={
                        'name': location,
                        'count': 1,
                        'language': 'en',
                        'format': 'json',
                    },
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('results'):
                        result = data['results'][0]
                        return {
                            'latitude': result['latitude'],
                            'longitude': result['longitude'],
                            'name': f"{result['name']}, {result.get('country', '')}",
                        }
        except Exception as e:
            pass
        
        return None
    
    async def _fetch_weather(
        self,
        latitude: float,
        longitude: float,
    ) -> dict[str, Any]:
        """Fetch weather data from Open-Meteo."""
        import httpx
        
        try:
            async with httpx.AsyncClient(timeout=TIMEOUTS.WIDGET) as client:
                response = await client.get(
                    OPENMETEO_FORECAST_URL,
                    params={
                        'latitude': latitude,
                        'longitude': longitude,
                        'current': 'temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m,pressure_msl',
                        'daily': 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max',
                        'timezone': 'auto',
                        'forecast_days': 3,
                    },
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return self._parse_weather_data(data)
                else:
                    return {'error': 'Weather service unavailable'}
                    
        except Exception as e:
            return {'error': f'Weather fetch failed: {str(e)}'}
    
    def _parse_weather_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """Parse Open-Meteo response."""
        current = data.get('current', {})
        daily = data.get('daily', {})
        
        # Weather code mapping
        weather_codes = {
            0: {'condition': 'Clear sky', 'icon': '☀️'},
            1: {'condition': 'Mainly clear', 'icon': '🌤️'},
            2: {'condition': 'Partly cloudy', 'icon': '⛅'},
            3: {'condition': 'Overcast', 'icon': '☁️'},
            45: {'condition': 'Foggy', 'icon': '🌫️'},
            48: {'condition': 'Rime fog', 'icon': '🌫️'},
            51: {'condition': 'Light drizzle', 'icon': '🌦️'},
            53: {'condition': 'Moderate drizzle', 'icon': '🌦️'},
            55: {'condition': 'Dense drizzle', 'icon': '🌧️'},
            61: {'condition': 'Slight rain', 'icon': '🌧️'},
            63: {'condition': 'Moderate rain', 'icon': '🌧️'},
            65: {'condition': 'Heavy rain', 'icon': '⛈️'},
            71: {'condition': 'Slight snow', 'icon': '🌨️'},
            73: {'condition': 'Moderate snow', 'icon': '🌨️'},
            75: {'condition': 'Heavy snow', 'icon': '❄️'},
            80: {'condition': 'Rain showers', 'icon': '🌦️'},
            81: {'condition': 'Moderate showers', 'icon': '🌧️'},
            82: {'condition': 'Violent showers', 'icon': '⛈️'},
            95: {'condition': 'Thunderstorm', 'icon': '⚡'},
            96: {'condition': 'Thunderstorm with hail', 'icon': '⛈️'},
            99: {'condition': 'Heavy thunderstorm', 'icon': '⛈️'},
        }
        
        weather_code = current.get('weather_code', 0)
        condition_info = weather_codes.get(weather_code, {'condition': 'Unknown', 'icon': '❓'})
        
        # Parse forecast
        forecast = []
        if daily.get('time'):
            for i, date in enumerate(daily['time']):
                day_code = daily.get('weather_code', [])[i] if i < len(daily.get('weather_code', [])) else 0
                day_condition = weather_codes.get(day_code, {'condition': 'Unknown', 'icon': '❓'})
                
                forecast.append({
                    'date': date,
                    'condition': day_condition['condition'],
                    'icon': day_condition['icon'],
                    'temp_max': daily.get('temperature_2m_max', [])[i] if i < len(daily.get('temperature_2m_max', [])) else None,
                    'temp_min': daily.get('temperature_2m_min', [])[i] if i < len(daily.get('temperature_2m_min', [])) else None,
                    'precipitation_probability': daily.get('precipitation_probability_max', [])[i] if i < len(daily.get('precipitation_probability_max', [])) else None,
                })
        
        return {
            'current': {
                'temperature': current.get('temperature_2m'),
                'temperature_unit': '°C',
                'feels_like': current.get('apparent_temperature'),
                'condition': condition_info['condition'],
                'icon': condition_info['icon'],
                'humidity': current.get('relative_humidity_2m'),
                'wind_speed': current.get('wind_speed_10m'),
                'wind_direction': current.get('wind_direction_10m'),
                'pressure': current.get('pressure_msl'),
            },
            'forecast': forecast[:3],  # Next 3 days
            'source': 'Open-Meteo',
        }
