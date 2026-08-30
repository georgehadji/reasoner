'use client';

import { useEffect, useRef, useState } from 'react';
import { AlertCircle, Check } from 'lucide-react';
import { Button } from '@/components/ui';
import { supabase } from '@/lib/supabase';
import type { AuthError } from '@/lib/auth';

/* Field chrome — identical to /login and /signup. Focus is louder than hover:
   hover firms the border, focus firms it AND adds the accent ring that
   `.input-smooth` supplies. 16px is the iOS zoom floor, not a preference. */
const FIELD =
  'w-full rounded-[var(--radius)] border border-[var(--border)] bg-[var(--bg)] input-smooth ' +
  'px-[var(--space-4)] py-[var(--space-3)] ' +
  'text-[length:var(--text-base)] leading-[var(--lh-ui)] text-[var(--text)] ' +
  'placeholder:text-[var(--text-subtle)] ' +
  'hover:border-[var(--border-strong)] focus:border-[var(--accent)] ' +
  'aria-[invalid=true]:border-[var(--red)] ' +
  'disabled:cursor-not-allowed disabled:opacity-60';

const LABEL =
  'mb-[var(--space-2)] block text-[length:var(--text-sm)] font-medium ' +
  'leading-[var(--lh-ui)] text-[var(--text-2)]';

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Success replaces the whole form, so the submit button that had focus is
  // unmounted and the browser drops focus to <body> — a keyboard user is
  // returned to the top of the document with no idea the send worked. Move
  // focus onto the confirmation instead.
  const successRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (sent) successRef.current?.focus();
  }, [sent]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!isValidEmail(email)) {
      setError('Enter an address in the form name@example.com.');
      return;
    }

    if (!supabase) {
      setError('Authentication is not configured');
      return;
    }

    setLoading(true);
    try {
      const { error: supaError } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/reset-password`,
      });
      if (supaError) throw supaError;
      setSent(true);
    } catch (err) {
      const authErr = err as AuthError;
      setError(authErr.message || 'Failed to send reset email');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-dvh items-center justify-center px-[var(--gutter)] py-[var(--space-12)]">
      <div className="flex w-full max-w-[var(--width-form)] flex-col gap-[var(--space-5)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-8)] shadow-[var(--shadow)]">
        <h1 className="text-[length:var(--text-2xl)] font-bold text-[var(--text)]">Reset Password</h1>

        {sent ? (
          <>
            {/* Success. Tick + sentence carry it; the surface tint is decoration,
                so it survives monochrome and every form of colour blindness. */}
            <p
              ref={successRef}
              tabIndex={-1}
              role="status"
              className="flex items-start gap-[var(--space-2)] rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] px-[var(--space-4)] py-[var(--space-4)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-2)]"
            >
              <Check aria-hidden="true" className="mt-px size-[var(--space-4)] shrink-0 text-[var(--text)]" />
              <span>Check your email for a reset link.</span>
            </p>
            <p className="text-center text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
              Remember your password?{' '}
              <a href="/login" className="link-smooth inline-flex min-h-[var(--space-10)] items-center text-[var(--accent)] hover:underline">
                Sign in
              </a>
            </p>
          </>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-[var(--space-4)]" noValidate>
            {error && (
              <p
                id="email-error"
                role="alert"
                className="flex items-start gap-[var(--space-2)] rounded-[var(--radius)] border border-[var(--red-border)] bg-[var(--red-bg)] px-[var(--space-3)] py-[var(--space-3)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--red)]"
              >
                {/* mt-px, matching /contact, /signup and /reset-password: this is
                    optical alignment of a glyph against the first text line, not
                    a spacing-scale gap. --space-1 pushed it a line too low. */}
                <AlertCircle aria-hidden="true" className="mt-px size-[var(--space-4)] shrink-0" />
                <span>{error}</span>
              </p>
            )}

            <div>
              <label htmlFor="email" className={LABEL}>
                Email
              </label>
              <input
                id="email"
                type="email"
                inputMode="email"
                autoComplete="email"
                autoCapitalize="none"
                spellCheck={false}
                placeholder="you@example.com"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (error) setError('');
                }}
                className={FIELD}
                required
                aria-invalid={!!error}
                /* The id below now exists — it previously pointed at nothing,
                   so the message was never announced with the field. */
                aria-describedby={error ? 'email-error' : undefined}
                disabled={loading}
              />
            </div>

            <Button
              type="submit"
              size="lg"
              className="w-full rounded-[var(--radius)] gap-[var(--space-2)]"
              disabled={loading || !email}
              loading={loading}
              aria-busy={loading}
            >
              {loading ? 'Sending…' : 'Send Reset Link'}
            </Button>

            <p className="text-center text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
              Remember your password?{' '}
              <a href="/login" className="link-smooth inline-flex min-h-[var(--space-10)] items-center text-[var(--accent)] hover:underline">
                Sign in
              </a>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
