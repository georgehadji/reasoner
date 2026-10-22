'use client';

import { useEffect } from 'react';
import { selectAuthStatus, useAppStore } from '@/stores/app-store';

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
  const cached = useAppStore((s) => s.subscription);
  const owner = useAppStore((s) => s.subscriptionOwner);
  const loading = useAppStore((s) => s.subscriptionLoading);
  const error = useAppStore((s) => s.subscriptionError);
  const fetchSubscription = useAppStore((s) => s.fetchSubscription);
  const status = useAppStore(selectAuthStatus);
  const userId = useAppStore((s) => s.user?.id ?? null);

  useEffect(() => {
    // Signed-in users only: for anonymous visitors the endpoint answers 401,
    // and there is no plan to show. A new user id refetches, so one account's
    // plan is never shown to the next. fetchSubscription deduplicates
    // concurrent calls.
    if (status === 'authenticated') fetchSubscription();
  }, [status, userId, fetchSubscription]);

  const refresh = () => fetchSubscription();

  const subscription = owner === userId ? cached : null;
  return { subscription, loading, error, refresh };
}
