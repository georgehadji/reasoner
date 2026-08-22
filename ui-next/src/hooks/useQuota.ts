import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '@/lib/api-client';

interface QuotaStatus {
  used: number;
  max: number;
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
  const [loading, setLoading] = useState(false);

  // Exposed for manual re-fetching (e.g. after an action that changes quota).
  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchQuota();
      if (data) setQuota(data);
    } finally {
      setLoading(false);
    }
  }, []);

  // Mount fetch is intentionally self-contained rather than calling `refresh`:
  // an Effect must not synchronously trigger a setState chain, which is what
  // calling the (also setState-ing) `refresh` from here would do. See
  // https://react.dev/learn/you-might-not-need-an-effect#fetching-data.
  useEffect(() => {
    let ignore = false;
    async function loadOnMount() {
      setLoading(true);
      try {
        const data = await fetchQuota();
        if (!ignore && data) setQuota(data);
      } catch {
        // Silently ignore quota fetch errors on mount to avoid unhandled rejection
      } finally {
        if (!ignore) setLoading(false);
      }
    }
    loadOnMount();
    return () => {
      ignore = true;
    };
  }, []);

  return { quota, loading, refresh };
}
