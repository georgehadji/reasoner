import { useCallback, useEffect, useRef, useState } from 'react';
import { defineMachine } from '@/lib/state-machine';

/** U9: lifecycle of a fetched value. Starts `loading` so a first render never looks loaded. */
export type LoadStatus = 'loading' | 'ok' | 'error';

export type AsyncStatus = 'idle' | 'pending' | 'ok' | 'error';

/** U7/U8: one lifecycle for every submit button. `pending -> idle` is the bfcache/timeout escape. */
export const ASYNC_ACTION = defineMachine<AsyncStatus>(
  'ui.asyncAction',
  { idle: ['pending'], pending: ['ok', 'error', 'idle'], ok: ['pending', 'idle'], error: ['pending', 'idle'] },
  'idle',
);

interface State {
  status: AsyncStatus;
  /** Which action is pending (or last ran), so a button can show its own spinner. */
  key: string | null;
  error: string;
}

const INITIAL: State = { status: 'idle', key: null, error: '' };

function messageOf(err: unknown, fallback: string): string {
  if (typeof err === 'string' && err) return err;
  const m = (err as { message?: unknown } | null | undefined)?.message;
  return typeof m === 'string' && m ? m : fallback;
}

/**
 * Runs ONE async action at a time across every control that shares it (email and OAuth
 * buttons, both checkout providers). A second `run` while one is pending is ignored
 * synchronously (a ref, so two clicks in one tick cannot both pass). Restoring the page
 * from bfcache re-shows frozen `pending` state with no code left to clear it, so
 * `pageshow` with `persisted` resets it (and a navigated-away `ok`).
 */
export function useAsyncAction() {
  const [state, setState] = useState<State>(INITIAL);
  const inflight = useRef(false);
  const runId = useRef(0);

  const reset = useCallback((error?: string) => {
    runId.current++; // a late settle of the abandoned run must not overwrite this
    inflight.current = false;
    setState((s) =>
      s.status === 'idle' && !error
        ? s
        : { status: ASYNC_ACTION.move(s.status, error ? 'error' : 'idle'), key: s.key, error: error ?? '' },
    );
  }, []);

  useEffect(() => {
    // `ok` is reset too: a checkout/sign-in that "succeeded" by navigating away would
    // otherwise come back from bfcache with every control still locked.
    const onShow = (e: PageTransitionEvent) => {
      if (!e.persisted) return;
      runId.current++;
      inflight.current = false;
      setState((s) => (s.status === 'pending' || s.status === 'ok' ? { ...s, status: ASYNC_ACTION.move(s.status, 'idle') } : s));
    };
    window.addEventListener('pageshow', onShow);
    return () => window.removeEventListener('pageshow', onShow);
  }, []);

  /** Resolves true on success, false on failure or when ignored. Never rejects. */
  const run = useCallback(
    async (key: string, fn: () => Promise<unknown>, fallback = 'Something went wrong'): Promise<boolean> => {
      if (inflight.current) return false;
      inflight.current = true;
      const id = ++runId.current;
      setState((s) => ({ status: ASYNC_ACTION.move(s.status, 'pending'), key, error: '' }));
      try {
        await fn();
        if (id !== runId.current) return false;
        inflight.current = false;
        setState((s) => ({ ...s, status: ASYNC_ACTION.move(s.status, 'ok') }));
        return true;
      } catch (err) {
        if (id !== runId.current) return false;
        inflight.current = false;
        setState((s) => ({ ...s, status: ASYNC_ACTION.move(s.status, 'error'), error: messageOf(err, fallback) }));
        return false;
      }
    },
    [],
  );

  return { status: state.status, key: state.key, error: state.error, pending: state.status === 'pending', run, reset };
}
