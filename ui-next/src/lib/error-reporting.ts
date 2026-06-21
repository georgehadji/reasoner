'use client';

import { API } from './config';

/**
 * Report an error to both Sentry (if configured) and the backend error store.
 * This ensures no user-facing error goes unlogged in production.
 */
export async function reportError(
  error: Error | string,
  options: {
    source?: 'client' | 'widget' | 'chat' | 'api';
    url?: string;
    silent?: boolean;
  } = {},
): Promise<void> {
  const { source = 'client', url = typeof window !== 'undefined' ? window.location.href : undefined, silent = false } = options;

  const message = typeof error === 'string' ? error : error.message;
  const stack = typeof error === 'string' ? undefined : error.stack;

  // Report to Sentry if available
  try {
    const Sentry = await import('@sentry/nextjs');
    if (typeof error === 'string') {
      Sentry.captureMessage(message, { level: 'error', tags: { source } });
    } else {
      Sentry.captureException(error, { tags: { source } });
    }
  } catch {
    // Sentry not available — continue to backend report
  }

  // Report to backend error store
  try {
    await fetch(API.ERROR_REPORT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        source,
        stack: stack || undefined,
        url,
        user_agent: typeof navigator !== 'undefined' ? navigator.userAgent : undefined,
      }),
    });
  } catch (fetchErr) {
    // If backend reporting fails, at least log to console
    if (!silent) {
      // eslint-disable-next-line no-console
      console.error('Failed to report error to backend:', fetchErr);
    }
  }
}

/**
 * Wrap an async function with automatic error reporting.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function withErrorReporting<T extends (...args: any[]) => Promise<any>>(
  fn: T,
  options: Parameters<typeof reportError>[1] = {},
): T {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (async (...args: any[]) => {
    try {
      return await fn(...args);
    } catch (error) {
      await reportError(error as Error, options);
      throw error;
    }
  }) as T;
}
