'use client';

import { useState } from 'react';
import { apiFetch } from '@/lib/api-client';
import { X, Lock } from 'lucide-react';
import { cn } from '@/lib/utils';

interface UpgradeModalProps {
  open: boolean;
  onClose: () => void;
}

function isValidCheckoutUrl(url: string): boolean {
  try {
    const u = new URL(url);
    return u.protocol === 'https:' && (
      u.hostname === 'checkout.stripe.com' ||
      u.hostname.endsWith('.stripe.com')
    );
  } catch {
    return false;
  }
}

export function UpgradeModal({ open, onClose }: UpgradeModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleUpgrade = async () => {
    setError('');
    setLoading(true);
    try {
      const res = await apiFetch('/api/billing/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tier: 'pro' }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Checkout failed (HTTP ${res.status})`);
      }
      const data = await res.json();
      const url = data.checkout_url;
      if (!url || typeof url !== 'string') {
        throw new Error('Invalid checkout response');
      }
      if (!isValidCheckoutUrl(url)) {
        throw new Error('Invalid checkout URL');
      }
      window.location.href = url;
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Checkout failed';
      setError(msg);
      setLoading(false);
    }
  };

  return (
    <div
      className={cn(
        'fixed inset-0 z-50 flex items-center justify-center px-4 transition-all duration-300',
        open ? 'bg-[var(--scrim)] opacity-100' : 'bg-transparent opacity-0 pointer-events-none',
      )}
      role="dialog"
      aria-modal="true"
      aria-labelledby="upgrade-title"
      aria-describedby="upgrade-desc"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={cn(
          'w-full max-w-[var(--width-form)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-6 shadow-[var(--shadow-lg)] transition-all duration-300',
          open ? 'translate-y-0 opacity-100 scale-100' : 'translate-y-4 opacity-0 scale-95',
        )}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 id="upgrade-title" className="text-xl font-bold text-[var(--text)]">
            Upgrade to Pro
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-[var(--radius)] p-1 text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
            aria-label="Close upgrade modal"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <p id="upgrade-desc" className="mb-6 text-[var(--text-2)]">
          You&apos;ve reached your free tier limit. Upgrade to Pro for 500 queries/month and unlock all premium presets.
        </p>

        {error && (
          <div className="mb-4 rounded-[var(--radius)] bg-[var(--red-bg)] p-3 text-sm text-[var(--red)]" role="alert">
            {error}
          </div>
        )}

        <div className="mb-6 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-[var(--text)]">
            <Lock className="h-4 w-4 text-[var(--accent)]" />
            Pro Plan — $12/month
          </div>
          <ul className="mt-2 space-y-1 text-sm text-[var(--text-muted)]">
            <li>500 queries per month</li>
            <li>All premium presets</li>
            <li>Priority support</li>
          </ul>
        </div>

        <div className="flex gap-3">
          <button
            type="button"
            onClick={handleUpgrade}
            disabled={loading}
            className="flex-1 rounded-[var(--radius)] bg-[var(--accent)] py-2.5 text-[var(--accent-text)] font-medium transition-opacity hover:opacity-90 disabled:opacity-40"
            aria-busy={loading}
          >
            {loading ? 'Loading…' : 'Upgrade Now'}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="flex-1 rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] py-2.5 text-[var(--text)] font-medium transition-colors hover:bg-[var(--surface-3)]"
          >
            Maybe Later
          </button>
        </div>
      </div>
    </div>
  );
}
