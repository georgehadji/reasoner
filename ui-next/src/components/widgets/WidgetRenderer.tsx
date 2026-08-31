'use client';

import { CalculationWidget } from './CalculationWidget';
import { StockWidget } from './StockWidget';
import { WeatherWidget } from './WeatherWidget';

export interface WidgetData {
  widget_type: string;
  name: string;
  result: Record<string, unknown>;
  citations?: string[];
}

type WidgetComponent = React.FC<Record<string, unknown>>;

const WIDGET_MAP: Record<string, WidgetComponent> = {
  calculator: CalculationWidget as WidgetComponent,
  stock: StockWidget as WidgetComponent,
  weather: WeatherWidget as WidgetComponent,
};

export function WidgetRenderer({ widget }: { widget: WidgetData }) {
  const Component = WIDGET_MAP[widget.widget_type];
  if (!Component) {
    return (
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] px-4 py-3 text-[length:var(--text-sm)] text-[var(--text-muted)]">
        Unknown widget: {widget.widget_type}
      </div>
    );
  }

  // Adapt data shape to each widget's expected props
  if (widget.widget_type === 'calculator') {
    return (
      <Component
        expression={(widget.result.expression as string) || ''}
        result={(widget.result.result as number) || 0}
      />
    );
  }

  return <Component data={widget.result} />;
}
