'use client';

import { esc } from '@/lib/utils';
import { Sigma } from 'lucide-react';

export function CalculationWidget({ expression, result }: { expression: string; result: number }) {
  return (
    <div className="widget calculation-widget">
      <div className="widget-header">
        <span className="widget-icon" aria-hidden="true">
          <Sigma className="h-4 w-4" strokeWidth={1.75} />
        </span>
        <span className="widget-title">Calculation Result</span>
      </div>
      <div className="widget-content">
        <div className="calc-expression">{esc(expression)}</div>
        <div className="calc-result">= {result}</div>
      </div>
    </div>
  );
}
