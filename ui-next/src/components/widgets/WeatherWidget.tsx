'use client';

import { esc } from '@/lib/utils';
import { CloudSun } from 'lucide-react';

interface WeatherData {
  current: {
    location: string;
    temperature: number;
    condition: string;
    feels_like: number;
    humidity: number;
    wind_speed: number;
  };
  source: string;
}

export function WeatherWidget({ data }: { data: WeatherData }) {
  const current = data.current;
  return (
    <div className="widget weather-widget">
      <div className="widget-header">
        <span className="widget-icon" aria-hidden="true">
          <CloudSun className="h-4 w-4" strokeWidth={1.75} />
        </span>
        <span className="widget-title">Weather in {esc(current.location)}</span>
      </div>
      <div className="widget-content">
        <div className="weather-main">
          <span className="weather-temp">{Math.round(current.temperature)}°C</span>
          <span className="weather-condition">{esc(current.condition)}</span>
        </div>
        <div className="weather-details">
          <span>Feels like {Math.round(current.feels_like)}°C</span>
          <span>Humidity: {current.humidity}%</span>
          <span>Wind: {current.wind_speed} km/h</span>
        </div>
      </div>
      <div className="widget-source">Source: {esc(data.source)}</div>
    </div>
  );
}
