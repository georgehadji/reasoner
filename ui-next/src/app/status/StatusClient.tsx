'use client';

import { useEffect, useState } from 'react';
import { API } from '@/lib/config';
import { CAP, ROW } from '@/components/site/ArgumentSection';
import {
  CHECK_WORD,
  HEALTH_CHECKS,
  NOT_CONFIGURED,
  OVERALL,
  type CheckStatus,
  type HealthResponse,
} from '@/lib/status-checks';

type PollState =
  | { phase: 'loading' }
  | { phase: 'error' }
  | { phase: 'ok'; data: HealthResponse; at: Date };

const POLL_INTERVAL_MS = 30_000;
const NAMES = Object.fromEntries(HEALTH_CHECKS.map(({ key, name }) => [key, name]));

const FOOT = 'border-t border-[var(--site-line)] px-[var(--space-4)] py-[var(--space-3)] text-[var(--site-muted)]';

/**
 * The live panel: asks `GET /api/health` on load and every 30 seconds while
 * the page is open. Failure reasons are not shown: the backend's are raw
 * exception text, written for operators.
 */
export function StatusClient() {
  const [state, setState] = useState<PollState>({ phase: 'loading' });

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const res = await fetch(API.HEALTH, { cache: 'no-store' });
        const data = (await res.json()) as HealthResponse;
        if (!cancelled) setState({ phase: 'ok', data, at: new Date() });
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

  // The proxy answers `{status: 'unhealthy', error}` with no checks when the backend is down.
  const unreachable = state.phase === 'error' || (state.phase === 'ok' && !state.data.checks);
  const headline =
    state.phase === 'loading' ? 'Checking…' : unreachable ? OVERALL.unreachable : (OVERALL[state.data.status] ?? state.data.status);
  // With no answer yet, list the same six lines so the panel keeps its height and says what is pending.
  const placeholder = state.phase === 'loading' ? 'Checking' : 'Not checked';
  const checks: Array<[string, { status: CheckStatus; reason?: string } | null]> =
    state.phase === 'ok' && state.data.checks
      ? Object.entries(state.data.checks)
      : HEALTH_CHECKS.map(({ key }) => [key, null]);

  return (
    <figure
      data-ui
      aria-busy={state.phase === 'loading'}
      className="w-full rounded-[var(--radius-lg)] border border-[var(--site-line)] bg-[var(--site-bg)] lg:max-w-[var(--site-fragment)]"
    >
      <figcaption className={CAP}>
        <code className="font-mono">GET /api/health</code>
      </figcaption>
      <p role="status" className="px-[var(--space-4)] py-[var(--space-4)] text-[length:var(--site-lead)] font-semibold">
        {headline}
      </p>
      <ul className="list-none border-t border-[var(--site-line)]">
        {checks.map(([key, check]) => {
          const notSetUp = check?.status === 'ok' && check.reason === NOT_CONFIGURED;
          const word = !check ? placeholder : notSetUp ? 'Not configured' : (CHECK_WORD[check.status] ?? check.status);
          return (
            <li key={key} className={`grid grid-cols-[minmax(0,1fr)_auto] gap-[var(--space-3)] ${ROW}`}>
              <span>{NAMES[key] ?? key}</span>
              <span
                className={
                  !check ? 'text-[var(--site-muted)]' : check.status === 'ok' && !notSetUp ? '' : 'font-semibold'
                }
              >
                {word}
              </span>
            </li>
          );
        })}
      </ul>
      <p className={FOOT}>
        {state.phase === 'ok'
          ? `Checked at ${state.at.toLocaleTimeString()}. Checks again every 30 seconds while this page is open.`
          : state.phase === 'error'
            ? 'The request failed. Trying again every 30 seconds.'
            : 'Asking the API now.'}
      </p>
    </figure>
  );
}
