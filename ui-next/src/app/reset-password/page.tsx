'use client';

import { useState, Suspense } from 'react';
import { useRouter } from 'next/navigation';
import { AlertCircle, Check, Info } from 'lucide-react';
import { Button } from '@/components/ui';
import { supabase } from '@/lib/supabase';
import type { AuthError } from '@/lib/auth';

/* Field chrome — identical to /login, /signup and /forgot-password. Focus is
   louder than hover: hover firms the border, focus firms it AND adds the accent
   ring `.input-smooth` supplies. 16px is the iOS zoom floor, not a preference. */
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

const HINT =
  'mt-[var(--space-2)] flex items-start gap-[var(--space-2)] ' +
  'text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--text-muted)]';

/* The icon is not decoration: red text alone fails for ~8% of men, and prints
   as grey. */
const FIELD_ERROR =
  'mt-[var(--space-2)] flex items-start gap-[var(--space-2)] ' +
  'text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--red)]';

const MIN_PASSWORD = 6;

type Status = 'idle' | 'submitting' | 'success';

function ResetPasswordForm() {
  const [password, setPassword] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState('');
  const [fieldError, setFieldError] = useState('');
  const router = useRouter();

  const busy = status !== 'idle';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    /* Validate late (on submit), re-validate early (on change) — telling
       someone their password is too short while they are still typing it is
       noise, not help. */
    if (password.length < MIN_PASSWORD) {
      setFieldError(`Use at least ${MIN_PASSWORD} characters — ${password.length} so far.`);
      return;
    }
    setFieldError('');

    if (!supabase) {
      setError('Authentication is not configured');
      return;
    }

    setStatus('submitting');
    try {
      const { error: supaError } = await supabase.auth.updateUser({
        password: password,
      });
      if (supaError) throw supaError;

      // Password updated successfully, redirect to login. Stay in `success`
      // through the redirect — dropping back to idle would flash an enabled
      // form and read as "nothing happened".
      setStatus('success');
      router.push('/login?message=password-updated');
    } catch (err) {
      const authErr = err as AuthError;
      setError(authErr.message || 'Failed to update password');
      setStatus('idle');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-[var(--space-4)]" noValidate>
      {error && (
        <p
          id="reset-error"
          role="alert"
          className="flex items-start gap-[var(--space-2)] rounded-[var(--radius)] border border-[var(--red-border)] bg-[var(--red-bg)] px-[var(--space-3)] py-[var(--space-3)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--red)]"
        >
          <AlertCircle aria-hidden="true" className="mt-px size-[var(--space-4)] shrink-0" />
          <span>{error}</span>
        </p>
      )}

      {status === 'success' && (
        <p
          role="status"
          className="flex items-start gap-[var(--space-2)] rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] px-[var(--space-3)] py-[var(--space-3)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-2)]"
        >
          <Check aria-hidden="true" className="mt-px size-[var(--space-4)] shrink-0 text-[var(--ok)]" />
          <span>Password updated. Taking you to sign in…</span>
        </p>
      )}

      <div>
        <label htmlFor="password" className={LABEL}>
          New Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="new-password"
          minLength={MIN_PASSWORD}
          placeholder="••••••••"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            if (fieldError) setFieldError('');
          }}
          className={FIELD}
          required
          disabled={busy}
          aria-invalid={!!fieldError}
          /* Points at the error when there is one, at the rule when there is
             not — never at both, so the field is never read twice. */
          aria-describedby={fieldError ? 'password-error' : 'password-hint'}
        />
        {fieldError ? (
          <p id="password-error" role="alert" className={FIELD_ERROR}>
            <AlertCircle aria-hidden="true" className="mt-px size-[var(--space-4)] shrink-0" />
            <span>{fieldError}</span>
          </p>
        ) : (
          <p id="password-hint" className={HINT}>
            <Info aria-hidden="true" className="mt-px size-[var(--space-4)] shrink-0" />
            <span>Must be at least {MIN_PASSWORD} characters</span>
          </p>
        )}
      </div>

      <Button
        type="submit"
        size="lg"
        className="w-full rounded-[var(--radius)] gap-[var(--space-2)]"
        disabled={busy || !password}
        loading={status === 'submitting'}
        aria-busy={status === 'submitting'}
      >
        {status === 'success' ? 'Password updated' : status === 'submitting' ? 'Updating…' : 'Update Password'}
      </Button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="flex min-h-dvh items-center justify-center px-[var(--gutter)] py-[var(--space-12)]">
      <div className="flex w-full max-w-[var(--width-form)] flex-col gap-[var(--space-5)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-8)] shadow-[var(--shadow)]">
        <h1 className="text-[length:var(--text-2xl)] font-bold text-[var(--text)]">Update Password</h1>
        <Suspense
          fallback={
            <div
              role="status"
              aria-label="Loading the password form"
              className="h-[var(--space-32)] animate-pulse rounded-[var(--radius)] bg-[var(--surface-2)]"
            />
          }
        >
          <ResetPasswordForm />
        </Suspense>
      </div>
    </div>
  );
}
