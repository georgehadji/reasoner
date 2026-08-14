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

/** Reads the caller's credit balance, and optionally their recent ledger. */
export function useCredits({ withLedger = false, ledgerLimit = 10 } = {}) {
  const [credits, setCredits] = useState<CreditBalance | null>(null);
  const [ledger, setLedger] = useState<CreditLedgerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(API.CREDITS);
      if (!res.ok) throw new Error(`Could not load credits (HTTP ${res.status})`);
      setCredits(await res.json());

      if (withLedger) {
        const ledgerRes = await apiFetch(`${API.CREDITS_LEDGER}?limit=${ledgerLimit}`);
        if (ledgerRes.ok) {
          const data = await ledgerRes.json();
          setLedger(Array.isArray(data?.entries) ? data.entries : []);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load credits');
    } finally {
      setLoading(false);
    }
  }, [withLedger, ledgerLimit]);

  useEffect(() => {
    refresh().catch(() => {
      // refresh already records the failure in state.
    });
  }, [refresh]);

  return { credits, ledger, loading, error, refresh };
}
