'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertCircle, Check, Info } from 'lucide-react';
import { Button } from '@/components/ui';
import { signUpWithEmail, signInWithOAuth, getEnabledOAuthProviders } from '@/lib/auth';
import type { AuthError } from '@/lib/auth';

/* ────────────────────────────────────────────────────────────────────────────
   Field chrome — identical to /login on purpose. Two auth screens that look
   like siblings is the point; a signup form with 2px more padding than the
   login form is the kind of drift nobody files a bug for and everybody feels.

   Focus is louder than hover: hover only firms the border, focus firms it AND
   adds the accent ring `.input-smooth` supplies.

   `--text-base` (16px) is a floor, not a preference — iOS Safari zooms the
   viewport on focus for anything smaller.
   -------------------------------------------------------------------------- */
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

/* Field-level error. The icon is not decoration: red text alone fails for
   ~8% of men, and prints as grey. */
const FIELD_ERROR =
  'mt-[var(--space-2)] flex items-start gap-[var(--space-2)] ' +
  'text-[length:var(--text-xs)] leading-[var(--lh-ui)] text-[var(--red)]';

const OAUTH_BTN =
  'w-full rounded-[var(--radius)] gap-[var(--space-3)] text-[length:var(--text-sm)]';

function GitHubIcon() {
  return (
    <svg className="size-[var(--space-5)]" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
    </svg>
  );
}

function AppleIcon() {
  return (
    <svg className="size-[var(--space-5)]" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.21-1.98 1.08-3.11-1.05.05-2.31.7-3.06 1.56-.67.77-1.26 2.01-1.1 3.1 1.18.09 2.38-.72 3.08-1.55z"/>
    </svg>
  );
}

function GoogleIcon() {
  return (
    <svg className="size-[var(--space-5)]" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#A0A0A0"/>
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#808080"/>
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#C0C0C0"/>
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#606060"/>
    </svg>
  );
}

/* Status banner. Icon + text carry the meaning; the tint is decoration, so
   the message survives monochrome and every form of colour blindness. */
function Notice({ children }: { children: React.ReactNode }) {
  return (
    <p
      role="status"
      className="flex items-start gap-[var(--space-2)] rounded-[var(--radius)] border border-[var(--border)] bg-[var(--surface-2)] px-[var(--space-3)] py-[var(--space-3)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-2)]"
    >
      <Check aria-hidden="true" className="mt-px size-[var(--space-4)] shrink-0 text-[var(--text)]" />
      <span>{children}</span>
    </p>
  );
}

function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

const MIN_PASSWORD = 6;

type Provider = 'google' | 'github' | 'apple';
type Status = 'idle' | 'submitting' | 'success';
type FieldErrors = { email?: string; password?: string };

export default function SignupPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [status, setStatus] = useState<Status>('idle');
  const [oauth, setOauth] = useState<Provider | null>(null);
  const router = useRouter();

  /* `busy` covers the whole surface; `status`/`oauth` say WHICH control is
     working, so the spinner lands on the button the user actually pressed. */
  const busy = status !== 'idle' || oauth !== null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    /* Validate late (on submit), re-validate early (on change). Validating
       on every keystroke tells someone their email is invalid while they are
       still typing the @. */
    const next: FieldErrors = {};
    if (!isValidEmail(email)) {
      next.email = 'Enter an address in the form name@example.com.';
    }
    if (password.length < MIN_PASSWORD) {
      next.password = `Use at least ${MIN_PASSWORD} characters — ${password.length} so far.`;
    }
    setFieldErrors(next);
    if (next.email || next.password) return;

    setStatus('submitting');
    try {
      await signUpWithEmail(email, password);
      // Stay in `success` through the redirect — dropping back to idle would
      // flash an enabled form and read as "nothing happened".
      setStatus('success');
      router.push('/login?message=check-email');
    } catch (err) {
      const authErr = err as AuthError;
      setError(authErr.message || 'Signup failed');
      setStatus('idle');
    }
  };

  const enabledProviders = getEnabledOAuthProviders();

  const handleOAuth = async (provider: Provider) => {
    setError('');
    setOauth(provider);
    try {
      await signInWithOAuth(provider);
      // Supabase handles redirect
    } catch (err) {
      const authErr = err as AuthError | undefined;
      const msg =
        typeof authErr?.message === 'string' ? authErr.message
        : typeof err === 'string' ? err
        : `${provider} signup failed`;
      setError(msg);
      setOauth(null);
    }
  };

  return (
    <div className="flex min-h-dvh items-center justify-center px-[var(--gutter)] py-[var(--space-12)]">
      <div className="flex w-full max-w-[var(--width-form)] flex-col gap-[var(--space-5)] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface)] p-[var(--space-8)] shadow-[var(--shadow)]">
        <h1 className="text-[length:var(--text-2xl)] font-bold text-[var(--text)]">Create Account</h1>

        {error && (
          <p
            id="signup-error"
            role="alert"
            className="flex items-start gap-[var(--space-2)] rounded-[var(--radius)] border border-[var(--red-border)] bg-[var(--red-bg)] px-[var(--space-3)] py-[var(--space-3)] text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--red)]"
          >
            <AlertCircle aria-hidden="true" className="mt-px size-[var(--space-4)] shrink-0" />
            <span>{error}</span>
          </p>
        )}

        {status === 'success' && (
          <Notice>Account created. Check your email to confirm it.</Notice>
        )}

        {enabledProviders.length > 0 && (
          <>
            <div className="flex flex-col gap-[var(--space-3)]">
              {enabledProviders.includes('google') && (
                <Button
                  type="button"
                  variant="secondary"
                  size="lg"
                  className={OAUTH_BTN}
                  onClick={() => handleOAuth('google')}
                  disabled={busy}
                  loading={oauth === 'google'}
                  aria-busy={oauth === 'google'}
                  leftIcon={<GoogleIcon />}
                >
                  {oauth === 'google' ? 'Opening Google…' : 'Continue with Google'}
                </Button>
              )}
              {enabledProviders.includes('github') && (
                <Button
                  type="button"
                  variant="secondary"
                  size="lg"
                  className={OAUTH_BTN}
                  onClick={() => handleOAuth('github')}
                  disabled={busy}
                  loading={oauth === 'github'}
                  aria-busy={oauth === 'github'}
                  leftIcon={<GitHubIcon />}
                >
                  {oauth === 'github' ? 'Opening GitHub…' : 'Continue with GitHub'}
                </Button>
              )}
              {enabledProviders.includes('apple') && (
                <Button
                  type="button"
                  variant="secondary"
                  size="lg"
                  /* Apple's mark wants the near-black/near-white pair. `--text`
                     and `--bg` already ARE that pair, and they invert with the
                     theme, so this stays on-brand without a literal. */
                  className={`${OAUTH_BTN} border-transparent bg-[var(--text)] text-[var(--bg)] hover:border-transparent hover:bg-[var(--text-2)]`}
                  onClick={() => handleOAuth('apple')}
                  disabled={busy}
                  loading={oauth === 'apple'}
                  aria-busy={oauth === 'apple'}
                  leftIcon={<AppleIcon />}
                >
                  {oauth === 'apple' ? 'Opening Apple…' : 'Continue with Apple'}
                </Button>
              )}
            </div>

            <div className="flex items-center gap-[var(--space-4)]">
              <span aria-hidden="true" className="h-px flex-1 bg-[var(--border)]" />
              <span className="smallcaps text-[length:var(--text-xs)] text-[var(--text-muted)]">Or</span>
              <span aria-hidden="true" className="h-px flex-1 bg-[var(--border)]" />
            </div>
          </>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-[var(--space-4)]" noValidate>
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
                if (fieldErrors.email) setFieldErrors((prev) => ({ ...prev, email: undefined }));
              }}
              className={FIELD}
              required
              disabled={busy}
              aria-invalid={!!fieldErrors.email}
              aria-describedby={fieldErrors.email ? 'email-error' : undefined}
            />
            {fieldErrors.email && (
              <p id="email-error" role="alert" className={FIELD_ERROR}>
                <AlertCircle aria-hidden="true" className="mt-px size-[var(--space-4)] shrink-0" />
                <span>{fieldErrors.email}</span>
              </p>
            )}
          </div>

          <div>
            <label htmlFor="password" className={LABEL}>
              Password
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
                if (fieldErrors.password) setFieldErrors((prev) => ({ ...prev, password: undefined }));
              }}
              className={FIELD}
              required
              disabled={busy}
              aria-invalid={!!fieldErrors.password}
              /* Points at the error when there is one, at the rule when there
                 is not — never at both, so the field is never read twice. */
              aria-describedby={fieldErrors.password ? 'password-error' : 'password-hint'}
            />
            {fieldErrors.password ? (
              <p id="password-error" role="alert" className={FIELD_ERROR}>
                <AlertCircle aria-hidden="true" className="mt-px size-[var(--space-4)] shrink-0" />
                <span>{fieldErrors.password}</span>
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
            disabled={busy || !email || !password}
            loading={status === 'submitting'}
            aria-busy={status === 'submitting'}
          >
            {status === 'success'
              ? 'Account created'
              : status === 'submitting'
                ? 'Creating account…'
                : 'Sign Up'}
          </Button>
        </form>

        <p className="text-center text-[length:var(--text-sm)] leading-[var(--lh-ui)] text-[var(--text-muted)]">
          Already have an account?{' '}
          <a href="/login" className="link-smooth inline-flex min-h-[var(--space-10)] items-center text-[var(--accent)] hover:underline">
            Sign in
          </a>
        </p>
      </div>
    </div>
  );
}
