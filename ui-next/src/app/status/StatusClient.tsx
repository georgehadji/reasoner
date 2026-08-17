'use client';

import { useEffect, useState } from 'react';
import { CheckCircle2, AlertTriangle, XCircle, Loader2 } from 'lucide-react';
import { API } from '@/lib/config';

type CheckStatus = 'ok' | 'warning' | 'degraded' | 'error' | 'unknown';

interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  timestamp?: string;
  checks?: Record<string, { status: CheckStatus; reason?: string }>;
  error?: string;
}

type PollState =
  | { phase: 'loading' }
  | { phase: 'error' }
  | { phase: 'ok'; data: HealthResponse };

const CHECK_LABELS: Record<string, string> = {
  memory: 'Application memory',
  circuit_breakers: 'Provider circuit breakers',
  cache: 'Response cache',
  postgres: 'Database',
  valkey: 'Cache / rate limiter store',
  stripe: 'Billing',
};

function overallTone(status: HealthResponse['status'] | 'unreachable') {
  if (status === 'healthy') return { label: 'All systems operational', tone: 'text-[var(--ok)]', Icon: CheckCircle2 };
  if (status === 'degraded') return { label: 'Degraded performance', tone: 'text-amber-500', Icon: AlertTriangle };
  return { label: 'Service disruption', tone: 'text-red-500', Icon: XCircle };
}

function checkTone(status: CheckStatus) {
  if (status === 'ok') return { tone: 'text-[var(--ok)]', Icon: CheckCircle2 };
  if (status === 'warning' || status === 'degraded') return { tone: 'text-amber-500', Icon: AlertTriangle };
  if (status === 'error') return { tone: 'text-red-500', Icon: XCircle };
  return { tone: 'text-[var(--text-subtle)]', Icon: AlertTriangle };
}

const POLL_INTERVAL_MS = 30_000;

export function StatusClient() {
  const [state, setState] = useState<PollState>({ phase: 'loading' });

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const res = await fetch(API.HEALTH, { cache: 'no-store' });
        const data = (await res.json()) as HealthResponse;
        if (!cancelled) setState({ phase: 'ok', data });
      } catch {
        if (!cancelled) setState({ phase: 'error' });
      }
    }

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  if (state.phase === 'loading') {
    return (
      <div className="flex items-center gap-[var(--space-3)] text-[var(--text-muted)]">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span className="text-[length:var(--text-md)]">Checking live status…</span>
      </div>
    );
  }

  if (state.phase === 'error') {
    const { tone, Icon } = overallTone('unreachable');
    return (
      <div className={`flex items-center gap-[var(--space-3)] ${tone}`}>
        <Icon className="h-6 w-6" />
        <span className="text-[length:var(--text-lg)] font-semibold">Unable to reach the API right now</span>
      </div>
    );
  }

  const { data } = state;
  const { label, tone, Icon } = overallTone(data.status);
  const checks = data.checks ?? {};

  return (
    <div>
      <div className={`flex items-center gap-[var(--space-3)] ${tone}`}>
        <Icon className="h-6 w-6" />
        <span className="text-[length:var(--text-lg)] font-semibold">{label}</span>
      </div>
      <p className="mt-[var(--space-2)] text-[length:var(--text-sm)] text-[var(--text-subtle)]">
        {data.error ?? 'Checked live just now · next check in 30s'}
      </p>

      {Object.keys(checks).length > 0 && (
      <ul className="mt-[var(--space-8)] divide-y divide-[var(--border)] border-y border-[var(--border)]">
        {Object.entries(checks).map(([key, check]) => {
          const { tone: rowTone, Icon: RowIcon } = checkTone(check.status);
          return (
            <li key={key} className="flex items-center justify-between gap-[var(--space-4)] py-[var(--space-4)]">
              <span className="text-[length:var(--text-md)] text-[var(--text)]">
                {CHECK_LABELS[key] ?? key}
              </span>
              <span className={`flex items-center gap-[var(--space-2)] ${rowTone}`}>
                <RowIcon className="h-4 w-4" />
                <span className="text-[length:var(--text-sm)] uppercase tracking-[var(--tracking-label)]">
                  {check.status}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
      )}
    </div>
  );
}
