'use client';

import { useState, type ReactNode } from 'react';
import { useAppStore } from '@/stores/app-store';
import { useSubscription } from '@/hooks/useSubscription';
import { useRouter } from 'next/navigation';
import { useRequireAuth } from '@/hooks/useRequireAuth';
import { supabase } from '@/lib/supabase';
import { deleteAccount } from '@/lib/api-client';
import { deleteHistory } from '@/lib/db';
import Link from 'next/link';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';

/*
 * Account settings in the app style the dashboard set ("true-black-flat" in
 * the site palette): groups as cards one lightness step above the ground, no
 * borders, rows of label on the left and value or control on the right.
 * Usage lives on the dashboard; this screen links there instead of repeating it.
 */
const CARD = 'rounded-[var(--radius-lg)] bg-[var(--site-surface)] px-[var(--space-6)] py-[var(--space-2)]';
const MUTED = 'text-[var(--site-muted)]';
const LINK = 'site-link font-semibold text-current';
// Filled one lightness step up rather than outlined (the style's depth is lightness alone);
// hover inverts, the same move as the dashboard's primary pill.
const PILL =
  'inline-flex min-h-[var(--space-10)] shrink-0 items-center justify-center rounded-full px-[var(--space-4)] font-semibold transition-colors duration-[var(--dur-micro)] disabled:cursor-not-allowed disabled:opacity-60';
const BUTTON = `${PILL} bg-[var(--site-surface-2)] hover:bg-[var(--site-ink)] hover:text-[var(--site-bg)]`;
const DANGER = `${PILL} bg-[var(--red-bg)] text-[var(--red)] hover:bg-[var(--red)] hover:text-[var(--site-bg)]`;

function Group({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="grid gap-[var(--space-3)] lg:grid-cols-3 lg:gap-[var(--space-4)]">
      <h2 id={id} className="pt-[var(--space-4)] font-semibold">
        {title}
      </h2>
      <div className={`${CARD} lg:col-span-2`}>{children}</div>
    </section>
  );
}

/** One setting: what it is on the left, its value or control on the right. */
function Row({ label, detail, children }: { label: string; detail?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-[var(--space-6)] gap-y-[var(--space-3)] border-t border-[var(--site-line)] py-[var(--space-4)] first:border-t-0">
      <div className="min-w-0 flex-1 basis-[30ch]">
        <p className="font-semibold">{label}</p>
        {detail && <p className={`mt-[var(--space-1)] ${MUTED}`}>{detail}</p>}
      </div>
      {children}
    </div>
  );
}

export default function SettingsPage() {
  const user = useAppStore((s) => s.user);
  const logout = useAppStore((s) => s.logout);
  const router = useRouter();
  const status = useRequireAuth();
  const { subscription } = useSubscription();
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });

  // Waits for the session to load before judging; redirects from an effect.
  if (status !== 'authenticated' || !user) return null;

  const handleResetPassword = async () => {
    setMessage({ type: '', text: '' });
    // Without a configured auth client there is nothing to send; say so rather than spin.
    if (!supabase) {
      setMessage({ type: 'error', text: 'Password reset is not available right now.' });
      return;
    }
    setLoading(true);
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(user.email!, {
        redirectTo: `${window.location.origin}/reset-password`,
      });
      if (error) throw error;
      setMessage({ type: 'success', text: `We sent a reset link to ${user.email}.` });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to send reset email';
      setMessage({ type: 'error', text: msg });
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    const confirmed = window.confirm('Are you sure? This action cannot be undone and will delete all your data.');
    if (!confirmed) return;

    setLoading(true);
    setMessage({ type: '', text: '' });

    try {
      // Phase 0.2b: Call backend first (atomic DB deletion + external cleanup)
      await deleteAccount();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete account. Please contact support.';
      setMessage({ type: 'error', text: msg });
      setLoading(false);
      return;
    }

    // The account is gone: so is its local history on this browser (UI-5).
    await deleteHistory(user.id).catch(() => {});

    try {
      if (supabase) {
        await supabase.auth.signOut();
      }
      logout();
      router.push('/?deleted=true');
    } catch {
      // Sign-out failure is non-fatal after backend deletion succeeded
      logout();
      router.push('/?deleted=true');
    }
  };

  return (
    <div className="site flex min-h-dvh flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main id="main-content" className="flex-1">
        <div className="mx-auto w-full max-w-[var(--site-max)] px-[var(--site-margin)] pb-[var(--space-16)] pt-[var(--space-24)] text-[length:var(--site-small)] leading-[var(--lh-ui)]">
          <h1 className="font-display text-[length:var(--text-2xl)] leading-[var(--site-lh-head)]">Settings</h1>
          <p className="mt-[var(--space-3)] break-words text-[length:var(--site-body)]">Signed in as {user.email}.</p>

          {message.text && (
            <p
              role={message.type === 'error' ? 'alert' : 'status'}
              className={`mt-[var(--space-6)] rounded-[var(--radius)] p-[var(--space-3)] ${
                message.type === 'error' ? 'bg-[var(--red-bg)] text-[var(--red)]' : 'bg-[var(--site-surface-2)]'
              }`}
            >
              {message.text}
            </p>
          )}

          <div className="mt-[var(--space-10)] space-y-[var(--space-10)]">
            <Group id="account-h" title="Account">
              {/* No Email row: the line under the title already says who is signed in. */}
              <Row label="Plan" detail="Your balance, queries and credit activity are on the dashboard.">
                <span className="flex items-baseline gap-[var(--space-4)]">
                  <span className="capitalize">{subscription?.tier || 'Free'}</span>
                  <Link href="/dashboard" className={LINK}>
                    Open the dashboard
                  </Link>
                </span>
              </Row>
              <Row label="Password" detail="We email you a link to choose a new one.">
                <button type="button" onClick={handleResetPassword} disabled={loading} className={BUTTON}>
                  Send reset link
                </button>
              </Row>
            </Group>

            <Group id="developer-h" title="Developer access">
              <Row label="API keys" detail="Call Reasoner from your own code with scoped, revocable keys.">
                <Link href="/settings/api-keys" className={BUTTON}>
                  Manage keys
                </Link>
              </Row>
            </Group>

            <Group id="privacy-h" title="Privacy and data">
              <Row
                label="Encryption"
                detail="Stored runs, uploads and their search index are encrypted per field at rest, and connections use HTTPS with HSTS. This is not end-to-end: the model provider decrypts a request to answer it."
              />
              <Row
                label="Zero-retention mode"
                detail={
                  <>
                    Not available yet. To request deletion of stored data today, use{' '}
                    <Link href="/contact" className={LINK}>
                      Contact
                    </Link>
                    .
                  </>
                }
              />
            </Group>

            <Group id="delete-h" title="Delete account">
              <Row label="Delete your account" detail="Permanently deletes your account and all its data. This cannot be undone.">
                <button
                  type="button"
                  onClick={handleDeleteAccount}
                  disabled={loading}
                  className={DANGER}
                >
                  Delete account
                </button>
              </Row>
            </Group>
          </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
