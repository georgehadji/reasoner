'use client';

import { Mail } from 'lucide-react';
import { useAsyncAction } from '@/hooks/useAsyncAction';
import { resendConfirmation } from '@/lib/auth';
import { useAppStore } from '@/stores/app-store';

/**
 * Shown to a signed-in user whose email is not confirmed. Free credits and API
 * key creation wait for the confirmation (docs/plans/email-verification-2026-11-12.md).
 * Supabase rate-limits resends; useAsyncAction keeps one send in flight.
 */
export function EmailVerifyBanner() {
  const user = useAppStore((s) => s.user);
  const send = useAsyncAction();
  if (!user?.email || user.email_confirmed_at) return null;
  const email = user.email;

  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-[var(--space-2)] border-b border-[var(--border)] bg-[var(--surface-2)] px-[var(--space-3)] py-[var(--space-2)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-2)]"
    >
      <Mail aria-hidden="true" className="size-[var(--space-4)] shrink-0 text-[var(--text)]" />
      <span className="flex-1">
        {send.status === 'ok'
          ? `Link sent to ${email}. Check your inbox.`
          : `Confirm ${email} to unlock your free credits and API keys.`}
      </span>
      {send.status !== 'ok' && (
        <button
          type="button"
          onClick={() => send.run('resend', () => resendConfirmation(email), 'Could not resend the link')}
          disabled={send.pending}
          aria-busy={send.pending}
          className="rounded-[var(--radius)] border border-[var(--border)] px-[var(--space-2)] py-[var(--space-1)] text-[var(--text)] hover:bg-[var(--surface-3)] disabled:opacity-60"
        >
          {send.pending ? 'Sending…' : 'Resend link'}
        </button>
      )}
      {send.status === 'error' && (
        <span role="alert" className="w-full text-[var(--red)]">
          {send.error}
        </span>
      )}
    </div>
  );
}
