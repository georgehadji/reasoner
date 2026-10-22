'use client';

import { CSRF_COOKIE, CSRF_HEADER } from './security-constants';
import { getAuthToken } from './auth';
import { reportError } from './error-reporting';
import { useAppStore } from '@/stores/app-store';

export function getCsrfToken(): string | null {
  const match = document.cookie.match(new RegExp('(^| )' + CSRF_COOKIE + '=([^;]+)'));
  return match ? decodeURIComponent(match[2]) : null;
}

export async function fetchWithCsrf(url: string, options: RequestInit = {}): Promise<Response> {
  async function getToken(forceRefresh = false): Promise<string | null> {
    if (!forceRefresh) {
      const cached = getCsrfToken();
      if (cached) return cached;
    }
    // POST: Caddy sends /api/* to FastAPI, which has no GET /api/csrf.
    const resp = await fetch('/api/csrf', { method: 'POST' });
    if (resp.ok) {
      const data = await resp.json();
      return data.token as string | null;
    }
    return null;
  }

  const token = await getToken();
  const headers = new Headers(options.headers);
  if (token) {
    headers.set(CSRF_HEADER, token);
  }

  // Inject Supabase auth token if available
  const authToken = await getAuthToken();
  if (authToken) {
    headers.set('Authorization', `Bearer ${authToken}`);
  }

  const resp = await fetch(url, { ...options, headers });

  // A 401 is returned like any other status; the transport never navigates.
  // Public pages must survive it, and a protected page's route guard
  // (useRequireAuth) redirects once the session is marked expired.
  if (resp.status === 401) useAppStore.getState().markSessionExpired();

  // If CSRF validation failed (stale/invalid token), fetch a fresh one and retry once
  if (resp.status === 403) {
    const data = await resp.json().catch(() => null);
    const raw = (data && typeof data === 'object')
      ? (typeof data.error === 'string' ? data.error : typeof data.detail === 'string' ? data.detail : '')
      : '';
    const errorMsg = raw.toLowerCase();
    if (errorMsg.includes('csrf')) {
      const freshToken = await getToken(true);
      if (freshToken) {
        headers.set(CSRF_HEADER, freshToken);
        return fetch(url, { ...options, headers });
      }
    }
  }

  // Capture API errors for observability (excluding expected auth/rate-limit cases)
  if (!resp.ok && resp.status >= 500) {
    const bodyText = await resp.clone().text().catch(() => '');
    reportError(
      `API ${resp.status} ${resp.statusText}: ${options.method || 'GET'} ${url}`,
      {
        source: 'api',
        silent: true,
      },
    ).catch(() => {});
  }

  return resp;
}
