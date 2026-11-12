import { supabase } from './supabase';

export interface AuthError {
  message: string;
  status?: number;
  code?: string;
}

function toAuthError(err: unknown): AuthError {
  if (err && typeof err === 'object') {
    const e = err as Record<string, unknown>;

    // Supabase errors use either `message` or `msg`; `code` or `error_code`
    const rawMessage =
      typeof e.message === 'string' ? e.message
      : typeof e.msg === 'string' ? e.msg
      : 'An unexpected error occurred';

    const code =
      typeof e.code === 'string' ? e.code
      : typeof e.error_code === 'string' ? e.error_code
      : undefined;

    const status =
      typeof e.status === 'number' ? e.status
      : typeof e.code === 'number' ? e.code
      : undefined;

    // Provide friendlier messages for common OAuth configuration errors
    let message = rawMessage;
    if (
      (code === 'validation_failed' || status === 400) &&
      rawMessage.toLowerCase().includes('provider is not enabled')
    ) {
      message = 'Apple Sign In is not enabled. Ask the admin to turn it on in Supabase Dashboard → Authentication → Providers → Apple, or use email/password instead.';
    } else if (
      code === 'unexpected_failure' &&
      rawMessage.toLowerCase().includes('oauth')
    ) {
      message = 'Sign-in provider is not configured. Please contact the administrator or use email/password.';
    }

    return { message, status, code };
  }
  return { message: 'An unexpected error occurred' };
}

function guardSupabase() {
  if (!supabase) {
    throw new Error('Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.');
  }
  return supabase;
}

export async function getSession() {
  const client = guardSupabase();
  const { data, error } = await client.auth.getSession();
  if (error) throw toAuthError(error);
  return data.session;
}

export async function getCurrentUser() {
  const client = guardSupabase();
  const { data, error } = await client.auth.getUser();
  if (error) throw toAuthError(error);
  return data.user;
}

export async function signInWithEmail(email: string, password: string) {
  const client = guardSupabase();
  const { data, error } = await client.auth.signInWithPassword({ email, password });
  if (error) throw toAuthError(error);
  return data;
}

/**
 * List of OAuth providers enabled for this deployment.
 * Controlled via NEXT_PUBLIC_ENABLED_OAUTH_PROVIDERS env var.
 * Defaults to all providers if not set.
 */
export function getEnabledOAuthProviders(): Array<'google' | 'github' | 'apple'> {
  const env = process.env.NEXT_PUBLIC_ENABLED_OAUTH_PROVIDERS;
  if (!env) return ['google', 'github', 'apple'];
  const enabled = env.split(',').map((p) => p.trim().toLowerCase());
  const allProviders: Array<'google' | 'github' | 'apple'> = ['google', 'github', 'apple'];
  return allProviders.filter((p) => enabled.includes(p));
}

export async function signInWithOAuth(provider: 'google' | 'github' | 'apple') {
  const client = guardSupabase();
  try {
    const { data, error } = await client.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: `${window.location.origin}/chat`,
      },
    });
    if (error) throw toAuthError(error);
    return data;
  } catch (err) {
    // Supabase may throw raw objects instead of returning { error }
    // Ensure we always throw a proper AuthError with a string message
    const authErr = toAuthError(err);
    // eslint-disable-next-line no-console
    console.error('[OAuth Error]', provider, err);
    throw authErr;
  }
}

export async function signUpWithEmail(email: string, password: string) {
  const client = guardSupabase();
  const { data, error } = await client.auth.signUp({
    email,
    password,
    // The confirmation link returns to the app, not the Supabase Site URL;
    // detectSessionInUrl finishes the sign-in there.
    options: { emailRedirectTo: `${window.location.origin}/chat` },
  });
  if (error) throw toAuthError(error);
  return data;
}

export async function resendConfirmation(email: string) {
  const client = guardSupabase();
  const { error } = await client.auth.resend({
    type: 'signup',
    email,
    options: { emailRedirectTo: `${window.location.origin}/chat` },
  });
  if (error) throw toAuthError(error);
}

export async function signOut() {
  const client = guardSupabase();
  const { error } = await client.auth.signOut();
  if (error) throw toAuthError(error);
}

export async function getAuthToken(): Promise<string | null> {
  if (!supabase) return null;
  const session = await getSession();
  return session?.access_token ?? null;
}
