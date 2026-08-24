import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api-client';
import { API } from '@/lib/config';

export interface CreditBalance {
  balance: number;
  balance_usd: number;
  lifetime_granted: number;
  lifetime_spent: number;
  tier: string;
  monthly_allowance: number;
  credits_per_usd: number;
  updated_at: string;
}

export interface CreditLedgerEntry {
  id: string;
  delta: number;
  balance_after: number;
  reason: string;
  description: string | null;
  created_at: string;
}

interface CreditsFetchResult {
  credits: CreditBalance;
  /** `null` when `withLedger` is false, i.e. "don't touch ledger state". */
  ledger: CreditLedgerEntry[] | null;
}

/** Pure network calls, no React state — shared by `refresh` and the mount/deps effect below. */
async function fetchCredits(withLedger: boolean, ledgerLimit: number): Promise<CreditsFetchResult> {
  const res = await apiFetch(API.CREDITS);
  if (!res.ok) throw new Error(`Could not load credits (HTTP ${res.status})`);
  const credits = await res.json();

  let ledger: CreditLedgerEntry[] | null = null;
  if (withLedger) {
    const ledgerRes = await apiFetch(`${API.CREDITS_LEDGER}?limit=${ledgerLimit}`);
    if (ledgerRes.ok) {
      const data = await ledgerRes.json();
      ledger = Array.isArray(data?.entries) ? data.entries : [];
    }
  }
  return { credits, ledger };
}

/** Reads the caller's credit balance, and optionally their recent ledger. */
export function useCredits({ withLedger = false, ledgerLimit = 10 } = {}) {
  const [credits, setCredits] = useState<CreditBalance | null>(null);
  const [ledger, setLedger] = useState<CreditLedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Exposed for manual re-fetching (e.g. after a purchase changes balance).
  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCredits(withLedger, ledgerLimit);
      setCredits(data.credits);
      if (data.ledger !== null) setLedger(data.ledger);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load credits');
    } finally {
      setLoading(false);
    }
  }, [withLedger, ledgerLimit]);

  // Self-contained rather than calling `refresh`: an Effect must not
  // synchronously trigger a setState chain, which is what calling the (also
  // setState-ing) `refresh` from here would do. See
  // https://react.dev/learn/you-might-not-need-an-effect#fetching-data.
  useEffect(() => {
    let ignore = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchCredits(withLedger, ledgerLimit);
        if (ignore) return;
        setCredits(data.credits);
        if (data.ledger !== null) setLedger(data.ledger);
      } catch (err) {
        if (!ignore) setError(err instanceof Error ? err.message : 'Could not load credits');
      } finally {
        if (!ignore) setLoading(false);
      }
    }
    load();
    return () => {
      ignore = true;
    };
  }, [withLedger, ledgerLimit]);

  return { credits, ledger, loading, error, refresh };
}
