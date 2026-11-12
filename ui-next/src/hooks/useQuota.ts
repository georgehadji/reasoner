import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '@/lib/api-client';
import type { LoadStatus } from './useAsyncAction';

export interface QuotaStatus {
  used: number;
  /** null on an unlimited plan (the backend never reports a numeric cap there). */
  max: number | null;
  /** true on an unlimited plan; `remaining` is then a -1 sentinel, not a count. */
  unlimited?: boolean;
  remaining: number;
  reset_date: string;
}

/** Pure network call, no React state — shared by `refresh` and the mount effect below. */
async function fetchQuota(): Promise<QuotaStatus | null> {
  const res = await apiFetch('/api/quota');
  return res.ok ? await res.json() : null;
}

export function useQuota() {
  const [quota, setQuota] = useState<QuotaStatus | null>(null);
  // Starts `loading`: `false` made the first render look loaded with no quota (U9).
  const [status, setStatus] = useState<LoadStatus>('loading');

  // Exposed for manual re-fetching (e.g. after an action that changes quota).
  const refresh = useCallback(async () => {
    setStatus('loading');
    try {
      const data = await fetchQuota();
      if (data) setQuota(data);
      setStatus(data ? 'ok' : 'error');
    } catch {
      setStatus('error');
    }
  }, []);

  // Mount fetch is intentionally self-contained rather than calling `refresh`:
  // an Effect must not synchronously trigger a setState chain, which is what
  // calling the (also setState-ing) `refresh` from here would do. See
  // https://react.dev/learn/you-might-not-need-an-effect#fetching-data.
  useEffect(() => {
    let ignore = false;
    async function loadOnMount() {
      try {
        const data = await fetchQuota();
        if (ignore) return;
        if (data) setQuota(data);
        setStatus(data ? 'ok' : 'error');
      } catch {
        // No console error on mount (unhandled-rejection guard); the status carries it.
        if (!ignore) setStatus('error');
      }
    }
    loadOnMount();
    return () => {
      ignore = true;
    };
  }, []);

  return { quota, status, loading: status === 'loading', error: status === 'error', refresh };
}
