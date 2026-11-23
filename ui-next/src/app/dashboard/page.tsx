'use client';

import { useState } from 'react';
import { apiFetch } from '@/lib/api-client';
import { useCredits } from '@/hooks/useCredits';
import { useQuota } from '@/hooks/useQuota';
import { useSubscription } from '@/hooks/useSubscription';
import { useRequireAuth } from '@/hooks/useRequireAuth';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';
import { DashboardView } from '@/components/dashboard/DashboardView';

function isValidPortalUrl(url: string): boolean {
  try {
    const u = new URL(url);
    return u.protocol === 'https:' && u.hostname.endsWith('.stripe.com');
  } catch {
    return false;
  }
}

function DashboardContent() {
  const { quota, status: quotaStatus } = useQuota();
  const { subscription, loading: planLoading } = useSubscription();
  const { credits, ledger, status: creditsStatus, refresh } = useCredits({ withLedger: true });
  const [portalError, setPortalError] = useState('');

  const openPortal = async () => {
    setPortalError('');
    try {
      const res = await apiFetch('/api/billing/portal', { method: 'POST' });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Portal failed (HTTP ${res.status})`);
      }
      const data = await res.json();
      const url = data.portal_url;
      if (!url || typeof url !== 'string' || !isValidPortalUrl(url)) {
        throw new Error('Invalid portal URL');
      }
      window.location.href = url;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to open billing portal';
      setPortalError(msg);
    }
  };

  return (
    <DashboardView
      credits={credits}
      ledger={ledger ?? []}
      creditsStatus={creditsStatus}
      onRetryCredits={refresh}
      quota={quota}
      quotaStatus={quotaStatus}
      tier={subscription?.tier ?? null}
      planLoading={planLoading}
      onManageBilling={openPortal}
      portalError={portalError}
    />
  );
}

export default function DashboardPage() {
  // Signed-in only: an anonymous visitor used to see an empty balance and a
  // made-up "0 / 20" quota.
  const status = useRequireAuth();

  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main id="main-content" className="flex-1">
        {status === 'authenticated' && <DashboardContent />}
      </main>
      <SiteFooter />
    </div>
  );
}
