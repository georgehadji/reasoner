'use client';

import { useEffect, useRef } from 'react';
import { useAsyncAction } from '@/hooks/useAsyncAction';
import { apiFetch } from '@/lib/api-client';
import { X, Lock } from 'lucide-react';
import { Button } from '@/components/ui/Button';

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
  const checkout = useAsyncAction();
  const { error } = checkout;
  // `ok` = redirect started; stay locked until the page unloads.
  const loading = checkout.status === 'pending' || checkout.status === 'ok';

  const handleUpgrade = () =>
    checkout.run('pro', async () => {
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
    }, 'Checkout failed');

  /* A modal <dialog> traps Tab, closes on Escape and returns focus to whatever
     opened it. Same pattern as SiteHeader's drawer and ChatFeed's lightbox. */
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    // No `display` utility on the <dialog>: it would override the UA's display:none while closed.
    <dialog
      ref={dialogRef}
      aria-labelledby="upgrade-title"
      aria-describedby="upgrade-desc"
      onClose={onClose}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      className="m-0 h-full max-h-none w-full max-w-none border-0 bg-[var(--scrim)] p-0 text-[var(--text)]"
    >
      <div
        className="flex h-full items-center justify-center px-[var(--space-4)]"
        onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      >
        <div className="animate-phase-reveal w-full max-w-[var(--width-form)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-6)] shadow-[var(--shadow-lg)]">
          <div className="mb-[var(--space-4)] flex items-center justify-between">
            <h2 id="upgrade-title" className="text-[length:var(--text-xl)] font-bold text-[var(--text)]">
              Upgrade to Pro
            </h2>
            <button
              type="button"
              onClick={onClose}
              className="-mr-[var(--space-3)] flex h-11 w-11 items-center justify-center rounded-[var(--radius)] text-[var(--text-muted)] transition-colors duration-[var(--dur-micro)] ease-[var(--ease-standard)] hover:bg-[var(--surface-2)] hover:text-[var(--text)]"
              aria-label="Close upgrade dialog"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>

          <p id="upgrade-desc" className="mb-[var(--space-6)] text-[var(--text-2)]">
            You&apos;ve reached your free tier limit. Upgrade to Pro to unlock all premium presets.
          </p>

          {error && (
            <div className="mb-[var(--space-4)] rounded-[var(--radius)] bg-[var(--red-bg)] p-[var(--space-3)] text-[length:var(--text-sm)] text-[var(--red)]" role="alert">
              {error}
            </div>
          )}

          <div className="mb-[var(--space-6)] rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] p-[var(--space-4)]">
            <div className="flex items-center gap-[var(--space-2)] text-[length:var(--text-sm)] font-medium text-[var(--text)]">
              <Lock className="h-4 w-4 text-[var(--accent)]" aria-hidden="true" />
              Pro Plan — [INPUT REQUIRED: Pro plan price]
            </div>
            <ul className="mt-[var(--space-2)] space-y-[var(--space-1)] text-[length:var(--text-sm)] text-[var(--text-muted)]">
              <li>[INPUT REQUIRED: Pro plan monthly allowance]</li>
              <li>All premium presets</li>
              <li>[INPUT REQUIRED: Pro plan support level]</li>
            </ul>
          </div>

          <div className="flex gap-[var(--space-3)]">
            <Button type="button" onClick={handleUpgrade} loading={loading} className="flex-1 rounded-[var(--radius)]">
              Upgrade Now
            </Button>
            <Button type="button" variant="secondary" onClick={onClose} className="flex-1 rounded-[var(--radius)]">
              Maybe Later
            </Button>
          </div>
        </div>
      </div>
    </dialog>
  );
}
