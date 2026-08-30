'use client';

import { useState } from 'react';
import { useAppStore } from '@/stores/app-store';
import { useSubscription } from '@/hooks/useSubscription';
import { useRouter } from 'next/navigation';
import { supabase } from '@/lib/supabase';
import { deleteAccount } from '@/lib/api-client';
import Link from 'next/link';
import { User, ShieldAlert, ShieldCheck, Database, Key } from 'lucide-react';
import { SiteHeader } from '@/components/layout/SiteHeader';
import { SiteFooter } from '@/components/layout/SiteFooter';

export default function SettingsPage() {
  const user = useAppStore((s) => s.user);
  const logout = useAppStore((s) => s.logout);
  const router = useRouter();
  const { subscription } = useSubscription();
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });

  if (!user) {
    if (typeof window !== 'undefined') router.push('/login');
    return null;
  }

  const handleResetPassword = async () => {
    setLoading(true);
    setMessage({ type: '', text: '' });
    if (!supabase) return;
    
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(user.email!, {
        redirectTo: `${window.location.origin}/reset-password`,
      });
      if (error) throw error;
      setMessage({ type: 'success', text: 'Password reset email sent!' });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to send reset email';
      setMessage({ type: 'error', text: msg });
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAccount = async () => {
    const confirmed = window.confirm("Are you sure? This action cannot be undone and will delete all your data.");
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
    <div className="flex min-h-screen flex-col bg-[var(--bg)] text-[var(--text)]">
      <SiteHeader />
      <main className="flex-1 w-full">
        {/* ── Masthead ───────────────────────────────────────────
            Same marginal-marker idiom as the other generic routes —
            no lede here, this is an account-management page, not a
            pitch, so there is nothing genuine to put in one. */}
        <header className="mx-auto w-full max-w-3xl px-[var(--gutter)] pb-[var(--space-8)] pt-[var(--space-48)]">
          <div className="grid gap-[var(--space-6)] lg:grid-cols-[9rem_minmax(0,1fr)] lg:gap-[var(--space-12)]">
            <div>
              <p className="mt-[var(--space-1)] font-sans text-[length:var(--text-xs)] font-medium uppercase leading-[var(--lh-ui)] tracking-[var(--tracking-label)] text-[var(--text-muted)]">
                Settings
              </p>
            </div>
            <h1 className="min-w-0 font-serif text-[length:var(--text-3xl)] font-semibold leading-[var(--lh-heading)] tracking-[var(--tracking-tight)] text-[var(--text)]">
              Account settings.
            </h1>
          </div>
        </header>

      <div className="mx-auto max-w-3xl px-[var(--gutter)] pb-[var(--space-12)] w-full">
      {message.text && (
        <div className={`mb-6 rounded-lg p-4 text-sm ${message.type === 'error' ? 'bg-[var(--red-bg)] text-[var(--red)]' : 'bg-[var(--surface-2)] font-medium text-[var(--text)]'}`}>
          {message.text}
        </div>
      )}

      <div className="space-y-8">
        {/* Profile Section */}
        <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
          <h2 className="mb-4 flex items-center gap-2 text-xl font-semibold">
            <User className="h-5 w-5 text-[var(--accent)]" /> Profile
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium text-[var(--text-muted)]">Email Address</label>
              <div className="rounded-lg bg-[var(--surface-2)] p-3 text-[var(--text)]">{user.email}</div>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-[var(--text-muted)]">Current Plan</label>
              <div className="flex items-center justify-between rounded-lg bg-[var(--surface-2)] p-3 text-[var(--text)] capitalize">
                {subscription?.tier || 'Free'}
                <button onClick={() => router.push('/dashboard')} className="text-sm text-[var(--accent)] hover:underline">Manage</button>
              </div>
            </div>
          </div>
        </section>

        {/* Privacy & Data Section */}
        <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
          <h2 className="mb-4 flex items-center gap-2 text-xl font-semibold text-[var(--text)]">
            <Database className="h-5 w-5 text-[var(--accent)]" /> Privacy & Data
          </h2>
          
          <div className="space-y-6">
            <div className="flex items-center justify-between gap-4 border-b border-[var(--border)] pb-6 opacity-60">
              <div>
                <p className="font-medium text-[var(--text)]">Zero-Retention Mode</p>
                <p className="text-sm text-[var(--text-muted)]">Coming soon — not yet available. To request deletion of stored data today, use <a href="/contact" className="underline hover:text-[var(--accent)]">Contact</a>.</p>
              </div>
              <button
                type="button"
                disabled
                aria-disabled="true"
                title="Coming soon"
                className="relative inline-flex h-6 w-11 shrink-0 cursor-not-allowed rounded-full border-2 border-transparent bg-[var(--surface-3)]"
              >
                <span className="inline-block h-5 w-5 translate-x-0 transform rounded-full bg-[var(--surface)] shadow ring-0" />
              </button>
            </div>

            <div className="flex items-start gap-3 rounded-lg bg-[var(--surface-2)] p-4 border border-[var(--border)]">
              <ShieldCheck className="h-5 w-5 text-[var(--text)] shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-[var(--text)]">Encryption Active</p>
                <p className="text-xs text-[var(--text-muted)] leading-relaxed mt-1">
                  All your data is currently protected with AES-256-GCM encryption at rest and TLS 1.3 in transit.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Developer Access */}
        <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
          <h2 className="mb-4 flex items-center gap-2 text-xl font-semibold">
            <Key className="h-5 w-5 text-[var(--accent)]" /> Developer access
          </h2>
          <div className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
            <div>
              <p className="font-medium text-[var(--text)]">API keys</p>
              <p className="text-sm text-[var(--text-muted)]">
                Call Reasoner from your own code with scoped, revocable keys.
              </p>
            </div>
            <Link
              href="/settings/api-keys"
              className="whitespace-nowrap rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-4 py-2 text-sm font-medium transition-colors hover:bg-[var(--surface-3)]"
            >
              Manage keys
            </Link>
          </div>
        </section>

        {/* Security Section */}
        <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
          <h2 className="mb-4 text-xl font-semibold">Security</h2>
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div>
              <p className="font-medium text-[var(--text)]">Password</p>
              <p className="text-sm text-[var(--text-muted)]">Receive an email to reset your password.</p>
            </div>
            <button
              onClick={handleResetPassword}
              disabled={loading}
              className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-4 py-2 text-sm font-medium hover:bg-[var(--surface-3)] transition-colors disabled:opacity-50"
            >
              Reset Password
            </button>
          </div>
        </section>

        {/* Danger Zone */}
        <section className="rounded-xl border border-[var(--red-border)] bg-[var(--red-bg)] p-6">
          <h2 className="mb-4 flex items-center gap-2 text-xl font-semibold text-[var(--red)]">
            <ShieldAlert className="h-5 w-5" /> Danger Zone
          </h2>
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div>
              <p className="font-medium text-[var(--text)]">Delete Account</p>
              <p className="text-sm text-[var(--text-muted)]">Permanently delete your account and all associated data.</p>
            </div>
            <button
              onClick={handleDeleteAccount}
              disabled={loading}
              className="rounded-lg bg-[var(--red)] px-4 py-2 text-sm font-medium text-[var(--bg)] hover:bg-[color-mix(in_oklab,var(--red)_86%,var(--text))] transition-colors disabled:opacity-50 whitespace-nowrap"
            >
              Delete Account
            </button>
          </div>
        </section>
      </div>
      </div>
      </main>
      <SiteFooter />
    </div>
  );
}
