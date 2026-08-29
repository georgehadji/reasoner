'use client';

import { esc, formatMarketCap } from '@/lib/utils';
import { TrendingUp } from 'lucide-react';

interface StockData {
  symbol: string;
  price: number;
  currency: string;
  change: number;
  change_percent: number;
  market_cap?: number;
  volume?: number;
  source: string;
}

export function StockWidget({ data }: { data: StockData }) {
  const changeClass = data.change >= 0 ? 'stock-up' : 'stock-down';
  const changeSign = data.change >= 0 ? '+' : '';

  return (
    <div className="widget stock-widget">
      <div className="widget-header">
        <span className="widget-icon" aria-hidden="true">
          <TrendingUp className="h-4 w-4" strokeWidth={1.75} />
        </span>
        <span className="widget-title">{esc(data.symbol)} Stock Price</span>
      </div>
      <div className="widget-content">
        <div className="stock-main">
          <span className="stock-price">{data.price.toFixed(2)} {data.currency}</span>
          <span className={`stock-change ${changeClass}`}>
            {changeSign}{data.change.toFixed(2)} ({changeSign}{data.change_percent.toFixed(2)}%)
          </span>
        </div>
        <div className="stock-details">
          {data.market_cap ? <span>Market Cap: {formatMarketCap(data.market_cap)}</span> : null}
          <span>Volume: {data.volume ? data.volume.toLocaleString() : 'N/A'}</span>
        </div>
      </div>
      <div className="widget-source">Source: {esc(data.source)}</div>
    </div>
  );
}
