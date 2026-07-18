'use client';

import { useEffect } from 'react';
import { useAppStore } from '@/stores/app-store';
import { shallow } from 'zustand/shallow';

export interface SubscriptionStatus {
  tier: string;
  status: string;
  current_period_end?: string;
  cancel_at_period_end?: boolean;
}

/**
 * Shared subscription hook — reads from the Zustand app store.
 * A single fetch is shared across all components (Dashboard, Settings,
 * Composer, UserMenu) to eliminate duplicate API calls.
 */
export function useSubscription() {
  const subscription = useAppStore((s) => s.subscription);
  const loading = useAppStore((s) => s.subscriptionLoading);
  const error = useAppStore((s) => s.subscriptionError);
  const fetchSubscription = useAppStore((s) => s.fetchSubscription);

  useEffect(() => {
    // Fetch on first mount if never fetched; subsequent mounts are no-ops
    // because fetchSubscription deduplicates concurrent calls.
    fetchSubscription();
  }, [fetchSubscription]);

  const refresh = () => fetchSubscription();

  return { subscription, loading, error, refresh };
}
